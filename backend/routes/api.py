import threading
from datetime import datetime, timedelta
from pathlib import Path

from flask import Blueprint, current_app, jsonify, redirect, request, send_file
from flask_login import current_user, login_required

import config as _config
from downloader import QUALITY_OPTIONS, VideoDownloader
from models import Download, DownloadJob, db
from utils.platform_detector import detect_platform, extract_url
from utils.progress_tracker import create_job, generate_job_id, get_job, update_job
from utils.error_handler import classify_error

api_bp = Blueprint("api", __name__)


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
    user_id = current_user.id

    if not url:
        return jsonify(error="No URL provided."), 400
    if quality_key not in QUALITY_OPTIONS:
        return jsonify(error="Invalid quality option."), 400

    ok, err_resp, err_code = _rate_limit_check(user_id)
    if not ok:
        return err_resp, err_code

    job_id = generate_job_id()

    if _config.IS_VERCEL:
        # ── Vercel: synchronous URL extraction, state in DB ───────────────────
        try:
            dl = VideoDownloader()
            result = dl.get_direct_url(url, quality_key)

            job = DownloadJob(
                job_id=job_id,
                user_id=user_id,
                status="done",
                title=result["title"],
                direct_url=result["url"],
                filename=result["filename"],
                quality=QUALITY_OPTIONS.get(quality_key, {}).get("name", ""),
                is_playlist=False,
            )
            db.session.add(job)

            rec = Download(
                user_id=user_id,
                title=result["title"],
                platform=detect_platform(url),
                quality=QUALITY_OPTIONS.get(quality_key, {}).get("name", ""),
                file_size="",
            )
            db.session.add(rec)
            db.session.commit()

            return jsonify(job_id=job_id, status="done", title=result["title"])

        except Exception as exc:
            error_msg = classify_error(exc)
            try:
                job = DownloadJob(
                    job_id=job_id,
                    user_id=user_id,
                    status="error",
                    error=error_msg,
                )
                db.session.add(job)
                db.session.commit()
            except Exception:
                pass
            return jsonify(job_id=job_id, status="error", error=error_msg)

    # ── Local dev: background thread, in-memory state ────────────────────────
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
    )

    app_ref = current_app._get_current_object()
    threading.Thread(
        target=_worker,
        args=(app_ref, job_id, url, quality_key, is_playlist),
        daemon=True,
    ).start()

    return jsonify(job_id=job_id)


@api_bp.route("/progress/<job_id>")
def progress(job_id):
    if _config.IS_VERCEL:
        job = DownloadJob.query.filter_by(job_id=job_id).first()
        if not job:
            return jsonify(error="Job not found."), 404
        return jsonify(
            status=job.status,
            title=job.title or "",
            error=job.error,
            is_playlist=False,
            percent=100 if job.status == "done" else 0,
            overall_percent=100 if job.status == "done" else 0,
            filename=job.filename,
            files=[],
        )

    job = get_job(job_id)
    if not job:
        return jsonify(error="Job not found."), 404
    job.pop("user_id", None)
    return jsonify(job)


@api_bp.route("/download/<job_id>")
def download_file(job_id):
    if _config.IS_VERCEL:
        job = DownloadJob.query.filter_by(job_id=job_id).first()
        if not job or job.status != "done":
            return jsonify(error="File not ready."), 404
        if not job.direct_url:
            return jsonify(error="No download URL available."), 404
        return redirect(job.direct_url)

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

def _worker(app, job_id: str, url: str, quality_key: str, is_playlist: bool) -> None:
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
        saved = dl.download(
            url,
            quality_key,
            is_playlist=is_playlist,
            progress_callback=hook,
            output_dir=out_dir,
            archive_file=archive_file,
        )

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
