# Stem Splitter

A free stem splitter for Windows. Give it a song and it separates the vocals, drums, bass,
guitar, piano and everything else into their own tracks. It runs on your own computer, so
nothing gets uploaded and there are no limits.

**[Download the latest version](../../releases/latest)**

![The results screen, with each stem's waveform and mute, solo and download buttons](docs/screenshot-results.png)

## Features

- Splits a song into 6 stems: vocals, drums, bass, guitar, piano and other. There's also
  a 4-stem mode if you only need vocals, drums, bass and the rest.
- Can split a stem again into separate parts. If a song has one guitar on the left and
  another on the right, you get each guitar as its own track.
- Lets you listen before downloading. All the stems play together, and you can mute or
  solo any of them to check how clean the separation is.
- Works with mp3, wav, flac, m4a, ogg and most video files.
- Saves stems as 24-bit WAV.

With an NVIDIA graphics card, a song takes about 20 to 40 seconds. Without one, it runs
on the CPU and takes a few minutes.

## Installing

You need Windows 10 or 11 and about 6 GB of free space.

1. Download the zip from the [releases page](../../releases/latest).
2. Unzip it somewhere, for example your Desktop.
3. Double-click `Stem Splitter.bat`.

You don't need to install Python. The first launch downloads everything it needs by
itself: about 3 GB if you have an NVIDIA card, or 1 GB otherwise. That takes a few
minutes. After that it starts in a few seconds and works offline.

Windows may show a "Windows protected your PC" warning, since the app isn't signed.
Click "More info" and then "Run anyway".

## Using it

![The start screen, with a song picked and the model options](docs/screenshot-setup.png)

1. Drag a song onto the page, or click to choose one.
2. Pick a model:
   - **6 stems** (default) gives vocals, drums, bass, guitar, piano and other.
   - **4 stems, best** gives vocals, drums, bass and other, with the cleanest results.
     It's about 4 times slower.
   - **4 stems, fast** gives the same four stems, quickly.
3. Under "Split into separate parts", tick any instrument you want split further. Guitar
   is ticked by default.
4. Click "Split stems".
5. Press Space to play, and click a waveform to jump to that point. M mutes a track and
   S solos it. Ctrl-click S to solo more than one.
6. Download the stems you want with the arrow next to each one, or get them all with
   "Download all".

## FAQ

**Does it work on Mac or Linux?**
Not yet, it's Windows only for now.

**Do I need a graphics card?**
No. An NVIDIA card makes it much faster, but it works without one. AMD and Intel
graphics cards aren't supported, so on those it uses the CPU.

**Why didn't my two guitars get separated?**
Parts are separated by where they sit in the stereo mix. If both guitars are panned to
the same place, for example both in the middle, they can't be pulled apart this way. The
app tells you when that happens.

**Where's the violin, synth or sax?**
The models only know vocals, drums, bass, guitar and piano. Anything else ends up in
"other".

**How do I uninstall it?**
Delete the app folder, and also the `.stemsplitter` folder in your user folder
(`%USERPROFILE%\.stemsplitter`). That's where Python, PyTorch and the models are stored.

**It didn't work.**
Close the black window and run `Stem Splitter.bat` again. If setup got interrupted, it
starts over by itself. If it still fails, [open an issue](../../issues) and paste in what
the black window says.

## How it works

The separation is done by [Demucs](https://github.com/facebookresearch/demucs), Meta's
open source source-separation model.

Splitting a stem into parts is done afterwards, based on stereo position. The app finds
where most of the sound sits between left and right, and unmixes each frequency between
those positions. Guitars that were recorded separately and panned hard left and right are
a common case. There, the two channels have almost nothing in common, so the app takes
them as two separate parts. The parts always add back up to the original stem.

## Development

The app is a small local web server with a single HTML page as the interface.

- `engine.py` does the separation. You can also run it from the command line:
  `python engine.py song.mp3 --split guitar`
- `app.py` is the server (FastAPI). It runs the splits and serves the page.
- `static/index.html` is the whole interface: layout, mixer and waveforms. There's no
  build step.
- `setup.bat` is the installer. It uses [uv](https://github.com/astral-sh/uv) to get
  Python 3.12, then installs PyTorch (the CUDA build if there's an NVIDIA card) and
  `requirements.txt` into `%USERPROFILE%\.stemsplitter`.
- `config.json` holds the version number and the links shown in the app.
- `make_release.ps1` builds the release zip into `dist\`.

## License

MIT, see [LICENSE](LICENSE). Separation models by
[Demucs](https://github.com/facebookresearch/demucs) (also MIT).
