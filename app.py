"""
app.py — Flask web frontend for VidFlow with Google OAuth2.

Routes (public):
  GET  /                       → main UI
  POST /info                   → fetch video/playlist metadata
  POST /start                  → start a background download
  GET  /progress/<job_id>      → poll job state
  GET  /download/<job_id>      → stream finished file to browser
  GET  /config                 → return current config
  POST /config                 → update and save config
  GET  /login                  → login page
  GET  /auth/google            → start Google OAuth flow
  GET  /auth/google/callback   → Google OAuth callback
  GET  /logout                 → logout and redirect to /login

Routes (login_required):
  GET  /api/history            → current user's download history
  DELETE /api/history/<id>     → delete a history record
"""

import json
import os
import re
import threading
import uuid
from datetime import datetime
from pathlib import Path

from flask import (Flask, jsonify, redirect, render_template,
                   request, send_file, url_for)
from flask_login import (LoginManager, current_user, login_required,
                         login_user, logout_user)
from authlib.integrations.flask_client import OAuth
from dotenv import load_dotenv

import config as _config
from downloader import QUALITY_OPTIONS, VideoDownloader
from models import Download, User, db

load_dotenv()

# ── App & extensions ──────────────────────────────────────────────────────────
app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "dev-change-me-in-production")
app.config["SQLALCHEMY_DATABASE_URI"] = os.environ.get("DATABASE_URL", "sqlite:///vidflow.db")
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

db.init_app(app)

login_manager = LoginManager(app)
login_manager.login_view = "login_page"

oauth = OAuth(app)
google = oauth.register(
    name="google",
    client_id=os.environ.get("GOOGLE_CLIENT_ID"),
    client_secret=os.environ.get("GOOGLE_CLIENT_SECRET"),
    server_metadata_url="https://accounts.google.com/.well-known/openid-configuration",
    client_kwargs={"scope": "openid email profile"},
)

# Register admin blueprint BEFORE create_all so all models are included
from admin import admin_bp          # noqa: E402
app.register_blueprint(admin_bp)

with app.app_context():
    db.create_all()


@login_manager.user_loader
def load_user(user_id: str):
    return db.session.get(User, int(user_id))


# ── Maintenance mode ──────────────────────────────────────────────────────────
_ADMIN_SETTINGS = Path(__file__).parent / 'admin_settings.json'


@app.before_request
def check_maintenance():
    if request.path.startswith('/admin') or request.path.startswith('/static'):
        return None
    try:
        if _ADMIN_SETTINGS.exists():
            data = json.loads(_ADMIN_SETTINGS.read_text(encoding='utf-8'))
            if data.get('maintenance_mode'):
                return render_template(
                    'maintenance.html',
                    message=data.get('maintenance_message', 'Under maintenance.'),
                )
    except Exception:
        pass
    return None


# ── Config ────────────────────────────────────────────────────────────────────
_cfg      = _config.load()
_cfg_lock = threading.Lock()


def _get_cfg() -> dict:
    with _cfg_lock:
        return dict(_cfg)


# ── URL extraction ────────────────────────────────────────────────────────────
_URL_RE = re.compile(r'https?://[^\s<>"\']+')


def _extract_url(text: str) -> str:
    m = _URL_RE.search(text)
    return m.group(0) if m else text.strip()


def _platform_from_url(url: str) -> str:
    """Guess platform name from URL for the Download record."""
    u = url.lower()
    if 'youtube.com' in u or 'youtu.be' in u: return 'YouTube'
    if 'instagram.com' in u:  return 'Instagram'
    if 'tiktok.com' in u:     return 'TikTok'
    if 'twitter.com' in u or 'x.com' in u: return 'Twitter'
    if 'facebook.com' in u or 'fb.watch' in u: return 'Facebook'
    if 'vimeo.com' in u:      return 'Vimeo'
    if 'reddit.com' in u:     return 'Reddit'
    if 'twitch.tv' in u:      return 'Twitch'
    if 'dailymotion.com' in u: return 'Dailymotion'
    return 'Other'


# ── Job store ─────────────────────────────────────────────────────────────────
_jobs: dict = {}
_lock = threading.Lock()


def _update(job_id: str, **kwargs) -> None:
    with _lock:
        if job_id in _jobs:
            _jobs[job_id].update(kwargs)


# ── Auth routes ───────────────────────────────────────────────────────────────

@app.route("/login")
def login_page():
    if current_user.is_authenticated:
        return redirect(url_for("index"))
    cfg = _get_cfg()
    return render_template("login.html", theme=cfg.get("theme", "dark"))


@app.route("/auth/google")
def auth_google():
    redirect_uri = url_for("auth_google_callback", _external=True)
    return google.authorize_redirect(redirect_uri)


@app.route("/auth/google/callback")
def auth_google_callback():
    if request.args.get("error"):
        return redirect(url_for("login_page"))
    try:
        token     = google.authorize_access_token()
        user_info = token.get("userinfo")
        if not user_info:
            return redirect(url_for("login_page"))

        user = User.query.filter_by(google_id=user_info["sub"]).first()
        if not user:
            user = User(
                google_id = user_info["sub"],
                name      = user_info.get("name", ""),
                email     = user_info.get("email", ""),
                avatar    = user_info.get("picture", ""),
            )
            db.session.add(user)
            db.session.commit()
        else:
            user.avatar = user_info.get("picture", user.avatar)
            db.session.commit()

        login_user(user)
        return redirect(url_for("index"))
    except Exception:
        return redirect(url_for("login_page"))


@app.route("/logout")
def logout():
    logout_user()
    return redirect(url_for("login_page"))


# ── Main routes ───────────────────────────────────────────────────────────────

@app.route("/")
def index():
    cfg = _get_cfg()

    user_stats = {"total": 0, "platforms": 0, "this_month": 0}
    if current_user.is_authenticated:
        now        = datetime.utcnow()
        total      = Download.query.filter_by(user_id=current_user.id).count()
        platforms  = (db.session.query(Download.platform)
                      .filter_by(user_id=current_user.id)
                      .distinct().count())
        this_month = Download.query.filter(
            Download.user_id == current_user.id,
            Download.date    >= datetime(now.year, now.month, 1),
        ).count()
        user_stats = {"total": total, "platforms": platforms, "this_month": this_month}

    return render_template(
        "index.html",
        qualities       = QUALITY_OPTIONS,
        default_quality = cfg.get("default_quality", "1"),
        theme           = cfg.get("theme", "dark"),
        download_dir    = cfg.get("download_dir", ""),
        user_stats      = user_stats,
    )


@app.route("/info", methods=["POST"])
def info_route():
    data = request.get_json(force=True) or {}
    url  = _extract_url(data.get("url") or "")
    if not url:
        return jsonify(error="No URL"), 400
    try:
        dl      = VideoDownloader()
        info    = dl.get_info(url)
        is_pl   = info.get("_type") == "playlist"
        entries = list(info.get("entries") or []) if is_pl else []
        return jsonify(
            type      = "playlist" if is_pl else "video",
            title     = info.get("title") or "",
            count     = len(entries) if is_pl else 1,
            thumbnail = info.get("thumbnail") or "",
            uploader  = info.get("uploader") or "",
            duration  = int(info.get("duration") or 0),
        )
    except Exception as exc:
        return jsonify(error=str(exc)), 400


@app.route("/start", methods=["POST"])
def start():
    data           = request.get_json(force=True) or {}
    url            = _extract_url(data.get("url") or "")
    quality_key    = str(data.get("quality") or _get_cfg().get("default_quality", "1"))
    is_playlist    = bool(data.get("is_playlist", False))
    playlist_count = int(data.get("playlist_count") or 0)
    user_id        = current_user.id if current_user.is_authenticated else None

    if not url:
        return jsonify(error="No URL provided."), 400
    if quality_key not in QUALITY_OPTIONS:
        return jsonify(error="Invalid quality option."), 400

    job_id = str(uuid.uuid4())
    with _lock:
        _jobs[job_id] = {
            "status":          "starting",
            "user_id":         user_id,
            "is_playlist":     is_playlist,
            "playlist_title":  "",
            "playlist_count":  playlist_count,
            "playlist_index":  0,
            "skipped":         0,
            "percent":         0,
            "overall_percent": 0,
            "title":           "",
            "speed":           "",
            "eta":             "",
            "size":            "",
            "filepath":        None,
            "filename":        None,
            "files":           [],
            "error":           None,
        }

    threading.Thread(
        target=_worker,
        args=(job_id, url, quality_key, is_playlist),
        daemon=True,
    ).start()

    return jsonify(job_id=job_id)


@app.route("/progress/<job_id>")
def progress(job_id):
    with _lock:
        job = dict(_jobs.get(job_id) or {})
    if not job:
        return jsonify(error="Job not found."), 404
    job.pop("user_id", None)   # never expose internal user_id to client
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


@app.route("/api/history")
@login_required
def api_history():
    records = (Download.query
               .filter_by(user_id=current_user.id)
               .order_by(Download.date.desc())
               .limit(50).all())
    return jsonify([{
        "id":        r.id,
        "title":     r.title     or "Unknown",
        "platform":  r.platform  or "YouTube",
        "quality":   r.quality   or "—",
        "file_size": r.file_size or "—",
        "date":      r.date.isoformat() if r.date else "",
    } for r in records])


@app.route("/api/history/<int:record_id>", methods=["DELETE"])
@login_required
def delete_history_record(record_id):
    record = Download.query.filter_by(
        id=record_id, user_id=current_user.id).first()
    if not record:
        return jsonify(error="Not found"), 404
    db.session.delete(record)
    db.session.commit()
    return jsonify(ok=True)


# ── Background worker ─────────────────────────────────────────────────────────

def _worker(job_id: str, url: str, quality_key: str, is_playlist: bool) -> None:

    last_pl_index = [0]

    def hook(d: dict) -> None:
        status = d.get("status")
        info   = d.get("info_dict", {})

        pl_index = info.get("playlist_index") or last_pl_index[0] or 1
        pl_count = info.get("n_entries") or 0

        if pl_index != last_pl_index[0]:
            last_pl_index[0] = pl_index

        if status == "downloading":
            downloaded = d.get("downloaded_bytes") or 0
            total      = d.get("total_bytes") or d.get("total_bytes_estimate") or 0
            speed      = d.get("speed") or 0
            eta        = d.get("eta") or 0
            title      = info.get("title", "")
            pct_video  = min(downloaded / total * 100, 100) if total else 0

            with _lock:
                saved_count = _jobs[job_id].get("playlist_count") or pl_count
            overall = (
                ((pl_index - 1) + pct_video / 100) / saved_count * 100
                if saved_count else pct_video
            )

            _update(
                job_id,
                status          = "downloading",
                percent         = round(pct_video, 1),
                overall_percent = round(overall, 1),
                title           = title,
                playlist_index  = pl_index,
                playlist_count  = pl_count or None,
                speed           = f"{speed / 1_048_576:.1f} MB/s" if speed else "",
                eta             = f"{eta // 60}:{eta % 60:02d}" if eta else "",
                size            = (
                    f"{downloaded / 1_048_576:.1f} / {total / 1_048_576:.1f} MB"
                    if total else
                    f"{downloaded / 1_048_576:.1f} MB"
                ),
            )

        elif status == "finished":
            _update(job_id, status="processing")

    try:
        cfg     = _get_cfg()
        out_dir = Path(cfg.get("download_dir", _config.DEFAULTS["download_dir"]))
        out_dir.mkdir(parents=True, exist_ok=True)

        archive_file = out_dir / ".yt-dlp-archive.txt" if is_playlist else None

        dl    = VideoDownloader()
        saved = dl.download(
            url, quality_key,
            is_playlist       = is_playlist,
            progress_callback = hook,
            output_dir        = out_dir,
            archive_file      = archive_file,
        )

        fp = saved[0] if saved else None

        # Read user context before the final status update
        with _lock:
            uid   = _jobs[job_id].get("user_id")
            title = _jobs[job_id].get("title", "")
            size  = _jobs[job_id].get("size", "")

        _update(
            job_id,
            status          = "done",
            percent         = 100,
            overall_percent = 100,
            files           = saved,
            filepath        = str(fp) if fp else None,
            filename        = Path(fp).name if fp else None,
        )

        # Persist download record for logged-in users
        if uid:
            with app.app_context():
                rec = Download(
                    user_id   = uid,
                    title     = title or (Path(fp).stem if fp else "Unknown"),
                    platform  = _platform_from_url(url),
                    quality   = QUALITY_OPTIONS.get(quality_key, {}).get("name", ""),
                    file_size = size,
                )
                db.session.add(rec)
                db.session.commit()

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


# ── Entry point ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    Path(_cfg.get("download_dir", _config.DEFAULTS["download_dir"])).mkdir(exist_ok=True)
    app.run(debug=True, port=5000, use_reloader=False)
