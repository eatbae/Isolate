"""Stem separation engine.

Stage 1: Demucs (AI) splits the mix into instrument stems.
Stage 2 (optional): a stem is split again by stereo position (left / center / right),
which pulls apart parts that were panned differently in the mix, e.g. two guitars.
"""

import re
import subprocess
from pathlib import Path

import imageio_ffmpeg
import numpy as np
import soundfile as sf
import torch
from demucs.apply import apply_model
from demucs.pretrained import get_model

SAMPLE_RATE = 44100
DEVICE = "cuda" if torch.cuda.is_available() else "cpu"

MODELS = {
    "htdemucs_6s": "6 stems: vocals, drums, bass, guitar, piano, other",
    "htdemucs_ft": "4 stems, best quality (slower): vocals, drums, bass, other",
    "htdemucs": "4 stems, fast: vocals, drums, bass, other",
}

# Stereo-split settings. Pan runs from -1 (hard left) to +1 (hard right).
MAX_PARTS = 3        # most parts one stem is split into
MIN_PEAK_GAP = 0.2   # pan positions closer than this count as the same part
MIN_PEAK_HEIGHT = 0.25  # a part's pan peak must be at least this fraction of the biggest
MIN_SHARE = 0.04     # drop a part holding less than this share of the stem's energy
WIDE_PAIR_CORR = 0.3  # L/R correlation below this = two separate parts panned hard left/right
SILENCE_RMS = 0.003  # about -50 dBFS; quieter stems are just bleed, not worth splitting

_model_cache = {}


def load_audio(path):
    """Decode any audio/video file to float32 stereo at 44.1 kHz, shape (2, samples)."""
    cmd = [
        imageio_ffmpeg.get_ffmpeg_exe(), "-v", "error", "-i", str(path),
        "-f", "f32le", "-ac", "2", "-ar", str(SAMPLE_RATE), "-",
    ]
    proc = subprocess.run(cmd, capture_output=True)
    if proc.returncode != 0:
        raise RuntimeError(f"Could not decode {path}:\n{proc.stderr.decode(errors='ignore')}")
    audio = np.frombuffer(proc.stdout, dtype=np.float32)
    if audio.size == 0:
        raise RuntimeError(f"No audio found in {path}")
    return audio.reshape(-1, 2).T.copy()


def _load_model(name):
    if name not in _model_cache:
        model = get_model(name)
        model.to(DEVICE).eval()
        _model_cache[name] = model
    return _model_cache[name]


def demucs_separate(audio, model_name, passes=1, progress=None):
    """Run Demucs on a (2, samples) array. Returns {stem_name: (2, samples) array}."""
    model = _load_model(model_name)
    wav = torch.from_numpy(audio)

    # Demucs expects roughly unit-variance input; undo the scaling afterwards.
    ref = wav.mean(0)
    mean, std = ref.mean(), ref.std() + 1e-8
    wav = (wav - mean) / std

    def on_progress(d):
        if progress is None or d.get("state") != "end":
            return
        length = d.get("audio_length") or wav.shape[-1]
        within = (d["shift_idx"] + d["segment_offset"] / length) / passes
        progress((d["model_idx_in_bag"] + within) / d["models"])

    with torch.no_grad():
        sources = apply_model(
            model, wav[None], shifts=passes, split=True, overlap=0.25,
            device=DEVICE, callback=on_progress,
        )[0]
    sources = sources * std + mean
    return {name: src.cpu().numpy() for name, src in zip(model.sources, sources)}


def _pan_peaks(pan, energy):
    """Find the pan positions where a stem's energy is concentrated."""
    hist, edges = np.histogram(pan.flatten().cpu().numpy(), bins=81, range=(-1, 1),
                               weights=energy.flatten().cpu().numpy())
    hist = np.convolve(hist, np.exp(-0.5 * (np.arange(-4, 5) / 1.5) ** 2), mode="same")
    centers = (edges[:-1] + edges[1:]) / 2
    # Small humps are usually bins where two parts overlap, not a part of their own.
    floor = MIN_PEAK_HEIGHT * hist.max()
    is_peak = (hist >= np.roll(hist, 1)) & (hist >= np.roll(hist, -1)) & (hist > floor)
    is_peak[[0, -1]] = hist[[0, -1]] > np.maximum(hist[[1, -2]], floor)
    chosen = []
    for i in np.argsort(hist)[::-1]:
        if not is_peak[i]:
            continue
        # A real part needs a clear dip between it and every louder part; otherwise it is
        # just bleed from frequencies where two parts overlap.
        distinct = all(
            abs(centers[i] - centers[j]) >= MIN_PEAK_GAP
            and hist[min(i, j):max(i, j) + 1].min() < 0.6 * hist[i]
            for j in chosen
        )
        if distinct:
            chosen.append(i)
        if len(chosen) == MAX_PARTS:
            break
    return sorted(float(centers[i]) for i in chosen)


def _pan_label(p):
    if abs(p) < 0.15:
        return "center"
    if abs(p) > 0.95:
        return "left" if p < 0 else "right"
    return f"{'left' if p < 0 else 'right'} {round(abs(p) * 100)}%"


def stereo_split(stem, n_fft=4096, hop=1024):
    """Split a stereo stem into parts by where each sound sits in the stereo field.

    Finds the pan positions holding most of the energy. Each frequency bin is then solved
    as a mix of the two positions either side of it (a 2x2 linear unmix), which stays
    exact even where two parts play the same frequency. The parts always add back up
    to the original stem. Returns ({label: audio}, {label: share of energy}).
    """
    x = torch.from_numpy(stem).to(DEVICE)
    window = torch.hann_window(n_fft, device=DEVICE)
    spec = torch.stft(x, n_fft, hop, window=window, return_complex=True)  # (2, freq, frames)

    mag_l, mag_r = spec[0].abs(), spec[1].abs()
    # Angle of the (L, R) magnitude pair: 0 = hard left, pi/2 = hard right. Mapped to
    # -1..1 it inverts the constant-power pan law, so a part panned 80% right reads ~0.8.
    angle = torch.atan2(mag_r, mag_l)
    pan = angle * (4 / torch.pi) - 1
    energy = mag_l ** 2 + mag_r ** 2
    total = energy.sum() + 1e-8

    peaks = _pan_peaks(pan, energy)
    # Two parts recorded separately and panned hard left/right (e.g. double-tracked rock
    # guitars) overlap in almost every frequency bin, so the pan histogram is one broad blob
    # instead of two peaks. Their channels are nearly unrelated though, so treat that as a
    # hard left/right pair; unmixing at +-1 then returns the two channels exactly.
    if len(peaks) < 2 and float(torch.corrcoef(x)[0, 1]) < WIDE_PAIR_CORR:
        peaks = [-1.0, 1.0]
    while len(peaks) >= 2:
        parts = _unmix(spec, angle, [(c + 1) * torch.pi / 4 for c in peaks])
        shares = [float((p.abs() ** 2).sum() / total) for p in parts]
        if min(shares) >= MIN_SHARE:
            break
        peaks.pop(int(np.argmin(shares)))
    if len(peaks) < 2:
        return {}, {}

    audio, share_by_label = {}, {}
    for c, part, share in zip(peaks, parts, shares):
        label = _pan_label(c)
        audio[label] = torch.istft(part, n_fft, hop, window=window,
                                   length=x.shape[-1]).cpu().numpy()
        share_by_label[label] = share
    return audio, share_by_label


def _unmix(spec, angle, thetas):
    """Split stereo spectrogram `spec` into one stereo part per pan direction in `thetas`."""
    parts = [torch.zeros_like(spec) for _ in thetas]
    # Bins outside the outermost positions go entirely to the nearest one.
    parts[0] += spec * (angle < thetas[0])
    parts[-1] += spec * (angle >= thetas[-1])
    for k in range(len(thetas) - 1):
        t1, t2 = thetas[k], thetas[k + 1]
        inside = (angle >= t1) & (angle < t2)
        # Solve spec = a * [cos t1, sin t1] + b * [cos t2, sin t2] for each bin.
        det = np.sin(t2 - t1)
        a = (spec[0] * np.sin(t2) - spec[1] * np.cos(t2)) / det * inside
        b = (spec[1] * np.cos(t1) - spec[0] * np.sin(t1)) / det * inside
        parts[k] += torch.stack([a * np.cos(t1), a * np.sin(t1)])
        parts[k + 1] += torch.stack([b * np.cos(t2), b * np.sin(t2)])
    return parts


def _safe_name(text):
    return re.sub(r"[^\w\-()%&,. ]+", "_", text).strip(" .") or "track"


def separate(path, model_name="htdemucs_6s", passes=1, split_stems=("guitar",),
             out_root="outputs", progress=None):
    """Full pipeline. Returns (output_dir, {stem_name: wav_path}, notes)."""
    say = progress or (lambda frac, msg="": None)

    say(0.0, "Decoding audio")
    audio = load_audio(path)

    say(0.02, f"Loading {model_name}")
    stems = demucs_separate(
        audio, model_name, passes,
        progress=lambda f: say(0.05 + 0.85 * f, "Separating instruments"),
    )

    notes = []
    for name in split_stems:
        if name not in stems:
            continue
        if np.sqrt((stems[name] ** 2).mean()) < SILENCE_RMS:
            notes.append(f"{name}: stem is nearly silent, so there was nothing to split.")
            continue
        say(0.92, f"Splitting {name} by stereo position")
        parts, shares = stereo_split(stems[name])
        if not parts:
            notes.append(f"{name}: everything sits in one stereo position, "
                         "so it can't be split by panning.")
            continue
        notes.append(f"{name}: split into " + ", ".join(
            f"{label} ({share:.0%} of the sound)" for label, share in shares.items()))
        for label, part in parts.items():
            stems[f"{name} ({label})"] = part

    say(0.96, "Writing files")
    song = _safe_name(Path(path).stem)
    out_dir = Path(out_root) / song
    out_dir.mkdir(parents=True, exist_ok=True)
    files = {}
    for name, data in stems.items():
        file = out_dir / f"{song} - {_safe_name(name)}.wav"
        sf.write(file, data.T, SAMPLE_RATE, subtype="PCM_24")
        files[name] = str(file.resolve())

    say(1.0, "Done")
    return str(out_dir.resolve()), files, notes


if __name__ == "__main__":
    import argparse
    import time

    parser = argparse.ArgumentParser(description="Split a song into stems.")
    parser.add_argument("file")
    parser.add_argument("--model", default="htdemucs_6s", choices=list(MODELS))
    parser.add_argument("--passes", type=int, default=1, help="more = slightly cleaner, slower")
    parser.add_argument("--split", nargs="*", default=["guitar"],
                        help="stems to also split by stereo position")
    parser.add_argument("--out", default="outputs")
    args = parser.parse_args()

    start = time.time()
    out_dir, files, notes = separate(
        args.file, args.model, args.passes, args.split, args.out,
        progress=lambda f, msg="": print(f"\r{f:5.0%}  {msg:<40}", end="", flush=True),
    )
    print(f"\nDevice: {DEVICE}, took {time.time() - start:.1f}s")
    for note in notes:
        print("  " + note)
    for name, file in files.items():
        print(f"  {name:<20} {file}")
