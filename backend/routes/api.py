import threading
import time
from datetime import datetime, timedelta
from pathlib import Path

from flask import Blueprint, current_app, jsonify, request, send_file
from flask_login import current_user, login_required

import config as _config
from downloader import (
    DEFAULT_LIVE_DURATION,
    LIVE_DURATIONS,
    QUALITY_OPTIONS,
    VideoDownloader,
    stop_live_job,
)
from models import Download, db
from utils.platform_detector import detect_platform, extract_url
from utils.progress_tracker import create_job, generate_job_id, get_job, update_job
from utils.error_handler import classify_error

api_bp = Blueprint("api", __name__)

_MEDIA_EXTS = {".mp4", ".mkv", ".webm", ".m4a", ".mp3", ".aac", ".opus"}


def _rate_limit_check(user_id: int):
    """Returns (ok, error_response) tuple. error_response is None if within limit."""
    since = datetime.utcnow() - timedelta(hours=24)
    recent = Download.query.filter(
        Download.user_id == user_id,
        Download.date >= since,
    ).all()
    if len(recent) >= 3:
        oldest = min(d.date for d in recent)
        reset_at = oldest + timedelta(hours=24)
        seconds_left = int((reset_at - datetime.utcnow()).total_seconds())
        hours_left = seconds_left // 3600
        mins_left  = (seconds_left % 3600) // 60
        return False, jsonify(error="limit_reached", hours=hours_left, minutes=mins_left), 429
    return True, None, None


@api_bp.route("/start", methods=["POST"])
def start():
    if not current_user.is_authenticated:
        return jsonify(error="Please sign in to download videos."), 401

    data = request.get_json(force=True) or {}
    url = extract_url(data.get("url") or "")
    quality_key = str(data.get("quality") or _config.load().get("default_quality", "1"))
    is_playlist = bool(data.get("is_playlist", False))
    playlist_count = int(data.get("playlist_count") or 0)
    live_key = str(data.get("live_duration") or DEFAULT_LIVE_DURATION)
    user_id = current_user.id

    if not url:
        return jsonify(error="No URL provided."), 400
    if quality_key not in QUALITY_OPTIONS:
        return jsonify(error="Invalid quality option."), 400
    if live_key not in LIVE_DURATIONS:
        return jsonify(error="Invalid recording length."), 400

    ok, err_resp, err_code = _rate_limit_check(user_id)
    if not ok:
        return err_resp, err_code

    job_id = generate_job_id()

    create_job(
        job_id,
        status="starting",
        user_id=user_id,
        is_playlist=is_playlist,
        playlist_title="",
        playlist_count=playlist_count,
        playlist_index=0,
        skipped=0,
        percent=0,
        overall_percent=0,
        title="",
        speed="",
        eta="",
        size="",
        filepath=None,
        filename=None,
        files=[],
        error=None,
        is_live=False,
        live_seconds=0,
        live_elapsed=0,
    )

    app_ref = current_app._get_current_object()
    threading.Thread(
        target=_worker,
        args=(app_ref, job_id, url, quality_key, is_playlist, live_key),
        daemon=True,
    ).start()

    return jsonify(job_id=job_id)


@api_bp.route("/stop/<job_id>", methods=["POST"])
def stop(job_id):
    """End a live recording early. The partial file stays playable."""
    job = get_job(job_id)
    if not job:
        return jsonify(error="Job not found."), 404
    if not current_user.is_authenticated or job.get("user_id") != current_user.id:
        return jsonify(error="Not allowed."), 403
    if not job.get("is_live"):
        return jsonify(error="Only live recordings can be stopped."), 400

    update_job(job_id, stop_requested=True)
    if not stop_live_job(job_id):
        return jsonify(error="Recording is not running yet."), 409
    return jsonify(ok=True)


@api_bp.route("/progress/<job_id>")
def progress(job_id):
    job = get_job(job_id)
    if not job:
        return jsonify(error="Job not found."), 404
    job.pop("user_id", None)
    return jsonify(job)


@api_bp.route("/download/<job_id>")
def download_file(job_id):
    job = get_job(job_id)
    if not job or job.get("status") != "done":
        return jsonify(error="File not ready yet."), 404
    filepath = job.get("filepath")
    if not filepath or not Path(filepath).exists():
        return jsonify(error="File not found on disk."), 404
    return send_file(filepath, as_attachment=True, download_name=Path(filepath).name)


@api_bp.route("/api/history")
@login_required
def api_history():
    records = (
        Download.query.filter_by(user_id=current_user.id)
        .order_by(Download.date.desc())
        .limit(50)
        .all()
    )
    return jsonify([
        {
            "id": r.id,
            "title": r.title or "Unknown",
            "platform": r.platform or "YouTube",
            "quality": r.quality or "—",
            "file_size": r.file_size or "—",
            "date": r.date.isoformat() if r.date else "",
        }
        for r in records
    ])


@api_bp.route("/api/history/<int:record_id>", methods=["DELETE"])
@login_required
def delete_history_record(record_id):
    record = Download.query.filter_by(id=record_id, user_id=current_user.id).first()
    if not record:
        return jsonify(error="Not found"), 404
    db.session.delete(record)
    db.session.commit()
    return jsonify(ok=True)


# ── Background worker (local dev only) ───────────────────────────────────────

def _live_ticker(job_id: str, total_seconds: int, done: threading.Event) -> None:
    """
    Drive progress for a live recording.

    yt-dlp hands live streams to ffmpeg, which reports nothing through
    progress_hooks — without this the UI would sit on "starting" for the whole
    recording. Recording runs at real time, so elapsed seconds *is* the progress.
    """
    started = time.monotonic()
    while not done.wait(1.0):
        elapsed = int(time.monotonic() - started)
        pct = min(elapsed / total_seconds * 100, 100) if total_seconds else 0
        left = max(total_seconds - elapsed, 0)
        update_job(
            job_id,
            status="downloading",
            percent=round(pct, 1),
            overall_percent=round(pct, 1),
            live_elapsed=elapsed,
            speed="recording",
            eta=f"{left // 60}:{left % 60:02d}",
            size=f"{elapsed // 60}:{elapsed % 60:02d} / {total_seconds // 60}:{total_seconds % 60:02d}",
        )


def _worker(
    app,
    job_id: str,
    url: str,
    quality_key: str,
    is_playlist: bool,
    live_key: str = DEFAULT_LIVE_DURATION,
) -> None:
    last_pl_index = [0]

    def hook(d: dict) -> None:
        status = d.get("status")
        info = d.get("info_dict", {})

        pl_index = info.get("playlist_index") or last_pl_index[0] or 1
        pl_count = info.get("n_entries") or 0

        if pl_index != last_pl_index[0]:
            last_pl_index[0] = pl_index

        if status == "downloading":
            downloaded = d.get("downloaded_bytes") or 0
            total = d.get("total_bytes") or d.get("total_bytes_estimate") or 0
            speed = d.get("speed") or 0
            eta = int(d.get("eta") or 0)
            title = info.get("title", "")
            pct_video = min(downloaded / total * 100, 100) if total else 0

            job = get_job(job_id)
            saved_count = job.get("playlist_count") or pl_count
            overall = (
                ((pl_index - 1) + pct_video / 100) / saved_count * 100
                if saved_count
                else pct_video
            )

            update_job(
                job_id,
                status="downloading",
                percent=round(pct_video, 1),
                overall_percent=round(overall, 1),
                title=title,
                playlist_index=pl_index,
                playlist_count=pl_count or None,
                speed=f"{speed / 1_048_576:.1f} MB/s" if speed else "",
                eta=f"{eta // 60}:{eta % 60:02d}" if eta else "",
                size=(
                    f"{downloaded / 1_048_576:.1f} / {total / 1_048_576:.1f} MB"
                    if total
                    else f"{downloaded / 1_048_576:.1f} MB"
                ),
            )

        elif status == "finished":
            update_job(job_id, status="processing")

    try:
        cfg = _config.load()
        out_dir = Path(cfg.get("download_dir", _config.DEFAULTS["download_dir"]))
        out_dir.mkdir(parents=True, exist_ok=True)

        archive_file = out_dir / ".yt-dlp-archive.txt" if is_playlist else None

        dl = VideoDownloader()

        # Decide up front whether this is a live broadcast: it changes the whole
        # strategy from "download a file" to "record for a while".
        live_seconds = 0
        if not is_playlist:
            state = dl.live_state(dl.get_info(url))
            if state == "upcoming":
                raise ValueError(
                    "This stream hasn't started yet. Try again once it is live."
                )
            if state == "live":
                live_seconds = LIVE_DURATIONS[live_key]["seconds"]
                update_job(
                    job_id,
                    is_live=True,
                    live_seconds=live_seconds,
                    status="downloading",
                )

        ticker_done = threading.Event()
        if live_seconds:
            threading.Thread(
                target=_live_ticker,
                args=(job_id, live_seconds, ticker_done),
                daemon=True,
            ).start()

        started_at = time.time()
        try:
            saved = dl.download(
                url,
                quality_key,
                is_playlist=is_playlist,
                progress_callback=hook,
                output_dir=out_dir,
                archive_file=archive_file,
                live_seconds=live_seconds or None,
                job_id=job_id,
            )
        except Exception:
            # Stopping a recording quits ffmpeg mid-stream, which yt-dlp reports
            # as a failure even though the partial file is complete and
            # playable. Recover the file this job just wrote — matched on mtime
            # so a concurrent job's output is never picked up by mistake.
            if not (live_seconds and get_job(job_id).get("stop_requested")):
                raise
            saved = [
                str(p) for p in out_dir.glob("*")
                if p.is_file()
                and p.suffix.lower() in _MEDIA_EXTS
                and p.stat().st_mtime >= started_at
            ]
        finally:
            ticker_done.set()

        fp = saved[0] if saved else None

        job = get_job(job_id)
        uid = job.get("user_id")
        title = job.get("title", "")
        size = job.get("size", "")

        update_job(
            job_id,
            status="done",
            percent=100,
            overall_percent=100,
            files=saved,
            filepath=str(fp) if fp else None,
            filename=Path(fp).name if fp else None,
        )

        if uid:
            with app.app_context():
                rec = Download(
                    user_id=uid,
                    title=title or (Path(fp).stem if fp else "Unknown"),
                    platform=detect_platform(url),
                    quality=QUALITY_OPTIONS.get(quality_key, {}).get("name", ""),
                    file_size=size,
                )
                db.session.add(rec)
                db.session.commit()

    except Exception as exc:
        update_job(job_id, status="error", error=classify_error(exc))
