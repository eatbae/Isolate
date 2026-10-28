"""Isolate: local web app for splitting songs into stems. Run it and it opens in your browser."""

import json
import os
import shutil
import socket
import threading
import uuid
import webbrowser
import zipfile
from pathlib import Path

import torch
import uvicorn
from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse

import engine

HERE = Path(__file__).parent
# Stems are kept here for previewing only; nothing is saved until you click Download.
PREVIEW_ROOT = HERE / ".preview"

# Which stems each model produces that are worth splitting into separate parts.
SPLITTABLE = {
    "htdemucs_6s": ["guitar", "piano", "other", "vocals", "bass"],
    "htdemucs_ft": ["other", "vocals", "bass"],
    "htdemucs": ["other", "vocals", "bass"],
}

app = FastAPI()
jobs = {}
gpu_lock = threading.Lock()  # one separation at a time


def _run_job(job, upload, model, passes, split):
    def progress(frac, msg=""):
        job.update(progress=frac, message=msg)

    try:
        with gpu_lock:
            out_dir, files, notes = engine.separate(
                upload, model, passes, split, PREVIEW_ROOT / job["id"], progress=progress)
        job.update(state="done", out_dir=out_dir, notes=notes,
                   files=list(files.values()), names=list(files))
    except Exception as e:  # shown to the user in the page
        job.update(state="error", message=str(e))


@app.get("/")
def index():
    return FileResponse(HERE / "static" / "index.html")


@app.get("/api/info")
def info():
    gpu = torch.cuda.get_device_name(0) if engine.DEVICE == "cuda" else "CPU"
    return {"device": engine.DEVICE, "gpu": gpu, "splittable": SPLITTABLE, **_config()}


def _config():
    # utf-8-sig: Notepad may save the file with a byte-order mark.
    try:
        return json.loads((HERE / "config.json").read_text(encoding="utf-8-sig"))
    except (OSError, ValueError) as e:
        print(f"Ignoring config.json: {e}")
        return {}


@app.post("/api/split")
def split(file: UploadFile = File(...), model: str = Form("htdemucs_6s"),
          passes: int = Form(1), split: str = Form("")):
    if model not in engine.MODELS:
        raise HTTPException(400, "Unknown model")

    # Single-user app: only the newest result is kept.
    for old in list(jobs):
        if jobs[old]["state"] != "running":
            shutil.rmtree(PREVIEW_ROOT / old, ignore_errors=True)
            del jobs[old]

    job_id = uuid.uuid4().hex[:8]
    upload = PREVIEW_ROOT / job_id / "upload" / Path(file.filename or "song").name
    upload.parent.mkdir(parents=True)
    with open(upload, "wb") as f:
        shutil.copyfileobj(file.file, f)

    job = jobs[job_id] = {"id": job_id, "state": "running", "progress": 0.0,
                          "message": "Starting", "song": upload.stem}
    stems = [s for s in split.split(",") if s]
    threading.Thread(target=_run_job, args=(job, upload, model, max(1, min(passes, 5)), stems),
                     daemon=True).start()
    return {"id": job_id}


@app.get("/api/jobs/{job_id}")
def job_status(job_id: str):
    job = _job(job_id)
    out = {k: job.get(k) for k in ("id", "state", "progress", "message", "song", "notes")}
    if job["state"] == "done":
        out["stems"] = [{"name": n, "url": f"/api/jobs/{job_id}/stems/{i}"}
                        for i, n in enumerate(job["names"])]
    return out


@app.get("/api/jobs/{job_id}/stems/{index}")
def stem(job_id: str, index: int, download: bool = False):
    files = _job(job_id).get("files") or []
    if not 0 <= index < len(files):
        raise HTTPException(404)
    path = Path(files[index])
    return FileResponse(path, media_type="audio/wav",
                        filename=path.name if download else None)


@app.get("/api/jobs/{job_id}/zip")
def zip_all(job_id: str):
    job = _job(job_id)
    if job["state"] != "done":
        raise HTTPException(409, "Not finished yet")
    zip_path = Path(job["out_dir"] + ".zip")
    if not zip_path.exists():
        with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_STORED) as z:
            for f in job["files"]:
                z.write(f, Path(f).name)
    return FileResponse(zip_path, filename=f"{job['song']} - stems.zip")


def _job(job_id):
    if job_id not in jobs:
        raise HTTPException(404, "Unknown job")
    return jobs[job_id]


def _free_port(start):
    for port in range(start, start + 100):
        with socket.socket() as s:
            if s.connect_ex(("127.0.0.1", port)) != 0:
                return port
    raise RuntimeError("No free port found")


if __name__ == "__main__":
    shutil.rmtree(PREVIEW_ROOT, ignore_errors=True)
    port = _free_port(int(os.environ.get("ISOLATE_PORT", 7860)))
    url = f"http://127.0.0.1:{port}"
    print(f"Isolate running at {url}")
    if not os.environ.get("ISOLATE_NO_BROWSER"):
        threading.Timer(1.0, webbrowser.open, [url]).start()
    uvicorn.run(app, host="127.0.0.1", port=port, log_level="warning")
