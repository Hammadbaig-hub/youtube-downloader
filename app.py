"""
app.py — Flask web frontend for the YouTube Downloader.

Routes:
  GET  /                  → single-page UI
  POST /start             → start a background download, returns {job_id}
  GET  /progress/<job_id> → poll job state as JSON
  GET  /download/<job_id> → stream the finished file to the browser
"""

import threading
import uuid
from pathlib import Path

from flask import Flask, jsonify, render_template, request, send_file

from downloader import DOWNLOAD_DIR, QUALITY_OPTIONS, VideoDownloader

app = Flask(__name__)

# ── Job store ─────────────────────────────────────────────────────────────────
# Each download gets a UUID key. Protected by a lock for thread safety.
_jobs: dict = {}
_lock = threading.Lock()


def _update(job_id: str, **kwargs) -> None:
    with _lock:
        if job_id in _jobs:
            _jobs[job_id].update(kwargs)


# ── Routes ────────────────────────────────────────────────────────────────────

@app.route("/")
def index():
    return render_template("index.html", qualities=QUALITY_OPTIONS)


@app.route("/start", methods=["POST"])
def start():
    data        = request.get_json(force=True) or {}
    url         = (data.get("url") or "").strip()
    quality_key = str(data.get("quality") or "1")

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


# ── Background worker ─────────────────────────────────────────────────────────

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
            # yt-dlp may now run FFmpeg to merge or convert
            _update(job_id, status="processing")

    try:
        dl    = VideoDownloader()
        saved = dl.download(url, quality_key, progress_callback=hook)
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
        # yt-dlp sometimes wraps the real error inside [Errno 22]; unwrap it.
        if "Sign in to confirm" in msg or "bot" in msg.lower():
            msg = (
                "YouTube blocked this download (bot detection). "
                "Make sure Microsoft Edge is open and signed in to YouTube, then try again."
            )
        elif "429" in msg or "Too Many Requests" in msg:
            msg = "YouTube rate limit (HTTP 429). Wait a few minutes and try again."
        elif "Video unavailable" in msg:
            msg = "This video is unavailable or private."
        elif "This live event will begin" in msg:
            msg = "This video is a future live stream that hasn't started yet."
        _update(job_id, status="error", error=msg)


# ── Entry point ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    DOWNLOAD_DIR.mkdir(exist_ok=True)
    # use_reloader=False prevents the reloader from spawning a second process
    # which would break background threads.
    app.run(debug=True, port=5000, use_reloader=False)
