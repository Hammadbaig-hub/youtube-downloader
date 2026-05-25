"""
app.py — Flask web frontend for the YouTube Downloader.

Routes:
  GET  /                  → single-page UI
  POST /start             → start a background download, returns {job_id}
  GET  /progress/<job_id> → poll job state as JSON
  GET  /download/<job_id> → stream the finished file to the browser
  GET  /config            → return current config as JSON
  POST /config            → update and save config, returns updated config
"""

import re
import threading
import uuid
from pathlib import Path

from flask import Flask, jsonify, render_template, request, send_file

import config as _config
from downloader import QUALITY_OPTIONS, VideoDownloader

app = Flask(__name__)

# ── Config ─────────────────────────────────────────────────────────────────
# Loaded once at startup; refreshed in-place when POST /config is called.
_cfg      = _config.load()
_cfg_lock = threading.Lock()


def _get_cfg() -> dict:
    with _cfg_lock:
        return dict(_cfg)


_YT_URL_RE = re.compile(
    r'https?://(?:www\.)?'
    r'(?:youtube\.com/(?:watch\?[^\s<>"\']+|shorts/[^\s<>"\']+|playlist\?[^\s<>"\']+)'
    r'|youtu\.be/[^\s<>"\']+)'
)

def _extract_url(text: str) -> str:
    """Pull the first YouTube URL out of pasted text, however messy."""
    m = _YT_URL_RE.search(text)
    return m.group(0) if m else text.strip()


# ── Job store ───────────────────────────────────────────────────────────────
_jobs: dict = {}
_lock = threading.Lock()


def _update(job_id: str, **kwargs) -> None:
    with _lock:
        if job_id in _jobs:
            _jobs[job_id].update(kwargs)


# ── Routes ──────────────────────────────────────────────────────────────────

@app.route("/")
def index():
    cfg = _get_cfg()
    return render_template(
        "index.html",
        qualities       = QUALITY_OPTIONS,
        default_quality = cfg.get("default_quality", "1"),
        theme           = cfg.get("theme", "dark"),
        download_dir    = cfg.get("download_dir", ""),
    )


@app.route("/start", methods=["POST"])
def start():
    data        = request.get_json(force=True) or {}
    url         = _extract_url(data.get("url") or "")
    quality_key = str(data.get("quality") or _get_cfg().get("default_quality", "1"))

    if not url:
        return jsonify(error="No URL provided."), 400
    if quality_key not in QUALITY_OPTIONS:
        return jsonify(error="Invalid quality option."), 400

    job_id = str(uuid.uuid4())
    with _lock:
        _jobs[job_id] = {
            "status":   "starting",
            "percent":  0,
            "title":    "",
            "speed":    "",
            "eta":      "",
            "size":     "",
            "filepath": None,
            "filename": None,
            "error":    None,
        }

    threading.Thread(
        target=_worker, args=(job_id, url, quality_key), daemon=True
    ).start()

    return jsonify(job_id=job_id)


@app.route("/progress/<job_id>")
def progress(job_id):
    with _lock:
        job = _jobs.get(job_id)
    if job is None:
        return jsonify(error="Job not found."), 404
    return jsonify(job)


@app.route("/download/<job_id>")
def download(job_id):
    with _lock:
        job = _jobs.get(job_id)
    if job is None or job.get("status") != "done":
        return jsonify(error="File not ready yet."), 404

    filepath = job.get("filepath")
    if not filepath or not Path(filepath).exists():
        return jsonify(error="File not found on disk."), 404

    return send_file(
        filepath,
        as_attachment=True,
        download_name=Path(filepath).name,
    )


@app.route("/config", methods=["GET"])
def get_config():
    return jsonify(_get_cfg())


@app.route("/config", methods=["POST"])
def update_config():
    global _cfg
    data = request.get_json(force=True) or {}
    cfg  = _config.load()

    if "theme" in data and data["theme"] in ("dark", "light"):
        cfg["theme"] = data["theme"]
    if "default_quality" in data and str(data["default_quality"]) in QUALITY_OPTIONS:
        cfg["default_quality"] = str(data["default_quality"])
    if "download_dir" in data and str(data["download_dir"]).strip():
        cfg["download_dir"] = str(data["download_dir"]).strip()

    _config.save(cfg)
    with _cfg_lock:
        _cfg = cfg

    return jsonify(cfg)


# ── Background worker ────────────────────────────────────────────────────────

def _worker(job_id: str, url: str, quality_key: str) -> None:
    """Runs the yt-dlp download in a daemon thread, pushing updates to _jobs."""

    def hook(d: dict) -> None:
        status = d.get("status")

        if status == "downloading":
            downloaded = d.get("downloaded_bytes") or 0
            total      = d.get("total_bytes") or d.get("total_bytes_estimate") or 0
            speed      = d.get("speed") or 0
            eta        = d.get("eta") or 0
            title      = d.get("info_dict", {}).get("title", "")
            percent    = min(downloaded / total * 100, 100) if total else 0

            _update(
                job_id,
                status  = "downloading",
                percent = round(percent, 1),
                title   = title,
                speed   = f"{speed / 1_048_576:.1f} MB/s" if speed else "",
                eta     = f"{eta // 60}:{eta % 60:02d}" if eta else "",
                size    = (
                    f"{downloaded / 1_048_576:.1f} / {total / 1_048_576:.1f} MB"
                    if total else
                    f"{downloaded / 1_048_576:.1f} MB downloaded"
                ),
            )

        elif status == "finished":
            _update(job_id, status="processing")

    try:
        cfg     = _get_cfg()
        out_dir = Path(cfg.get("download_dir", _config.DEFAULTS["download_dir"]))
        out_dir.mkdir(parents=True, exist_ok=True)

        dl    = VideoDownloader()
        saved = dl.download(url, quality_key, progress_callback=hook, output_dir=out_dir)
        fp    = saved[0] if saved else None

        _update(
            job_id,
            status   = "done",
            percent  = 100,
            filepath = str(fp) if fp else None,
            filename = Path(fp).name if fp else None,
        )

    except Exception as exc:
        msg = str(exc)
        if "Sign in to confirm" in msg or "bot" in msg.lower():
            msg = (
                "YouTube blocked this download (bot detection). "
                "Make sure Edge is signed in to YouTube, then try again."
            )
        elif "429" in msg or "Too Many Requests" in msg:
            msg = "YouTube rate limit (HTTP 429). Wait a few minutes and try again."
        elif "Video unavailable" in msg:
            msg = "This video is unavailable or private."
        elif "This live event will begin" in msg:
            msg = "This video is a future live stream that hasn't started yet."
        _update(job_id, status="error", error=msg)


# ── Entry point ──────────────────────────────────────────────────────────────

if __name__ == "__main__":
    Path(_cfg.get("download_dir", _config.DEFAULTS["download_dir"])).mkdir(exist_ok=True)
    app.run(debug=True, port=5000, use_reloader=False)
