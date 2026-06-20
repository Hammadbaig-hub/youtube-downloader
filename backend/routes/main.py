import json
from datetime import datetime, timedelta

from flask import Blueprint, jsonify, redirect, render_template, request, url_for
from flask_login import current_user, login_required

import config as _config
from downloader import QUALITY_OPTIONS, VideoDownloader
from models import Download, db
from utils.platform_detector import extract_url

main_bp = Blueprint("main", __name__)

_ADMIN_SETTINGS = _config.ADMIN_SETTINGS_PATH


@main_bp.before_app_request
def check_maintenance():
    if request.path.startswith("/admin") or request.path.startswith("/static"):
        return None
    try:
        if _ADMIN_SETTINGS.exists():
            data = json.loads(_ADMIN_SETTINGS.read_text(encoding="utf-8"))
            if data.get("maintenance_mode"):
                return render_template(
                    "maintenance.html",
                    message=data.get("maintenance_message", "Under maintenance."),
                )
    except Exception:
        pass
    return None


@main_bp.route("/")
def index():
    cfg = _config.load()
    user_stats = {"total": 0, "platforms": 0, "this_month": 0}
    if current_user.is_authenticated:
        now = datetime.utcnow()
        total = Download.query.filter_by(user_id=current_user.id).count()
        platforms = (
            db.session.query(Download.platform)
            .filter_by(user_id=current_user.id)
            .distinct()
            .count()
        )
        this_month = Download.query.filter(
            Download.user_id == current_user.id,
            Download.date >= datetime(now.year, now.month, 1),
        ).count()
        user_stats = {"total": total, "platforms": platforms, "this_month": this_month}

    return render_template(
        "index.html",
        qualities=QUALITY_OPTIONS,
        default_quality=cfg.get("default_quality", "1"),
        theme=cfg.get("theme", "dark"),
        download_dir=cfg.get("download_dir", ""),
        user_stats=user_stats,
    )


@main_bp.route("/pricing")
def pricing():
    cfg = _config.load()
    return render_template("pricing.html", theme=cfg.get("theme", "dark"))


@main_bp.route("/tos")
def tos():
    cfg = _config.load()
    return render_template("tos.html", theme=cfg.get("theme", "dark"))


@main_bp.route("/privacy")
def privacy():
    cfg = _config.load()
    return render_template("privacy.html", theme=cfg.get("theme", "dark"))


@main_bp.route("/account")
@login_required
def account():
    cfg = _config.load()
    now = datetime.utcnow()
    since_24h = now - timedelta(hours=24)

    total      = Download.query.filter_by(user_id=current_user.id).count()
    this_month = Download.query.filter(
        Download.user_id == current_user.id,
        Download.date >= datetime(now.year, now.month, 1),
    ).count()
    platforms  = (
        db.session.query(Download.platform)
        .filter_by(user_id=current_user.id)
        .distinct().count()
    )
    today_dl = Download.query.filter(
        Download.user_id == current_user.id,
        Download.date >= since_24h,
    ).all()
    today_count = len(today_dl)

    reset_in = None
    if today_count >= 3:
        oldest     = min(d.date for d in today_dl)
        reset_at   = oldest + timedelta(hours=24)
        secs_left  = int((reset_at - now).total_seconds())
        h, m       = secs_left // 3600, (secs_left % 3600) // 60
        reset_in   = f"{h}h {m}m" if h else f"{m} minutes"

    history = (
        Download.query
        .filter_by(user_id=current_user.id)
        .order_by(Download.date.desc())
        .limit(15).all()
    )

    stats = {
        "total":      total,
        "this_month": this_month,
        "platforms":  platforms,
        "today":      today_count,
        "reset_in":   reset_in,
    }
    return render_template(
        "account.html",
        theme=cfg.get("theme", "dark"),
        stats=stats,
        history=history,
    )


@main_bp.route("/info", methods=["POST"])
def info_route():
    data = request.get_json(force=True) or {}
    url = extract_url(data.get("url") or "")
    if not url:
        return jsonify(error="No URL"), 400
    try:
        dl = VideoDownloader()
        info = dl.get_info(url)
        is_pl = info.get("_type") == "playlist"
        entries = list(info.get("entries") or []) if is_pl else []
        return jsonify(
            type="playlist" if is_pl else "video",
            title=info.get("title") or "",
            count=len(entries) if is_pl else 1,
            thumbnail=info.get("thumbnail") or "",
            uploader=info.get("uploader") or "",
            duration=int(info.get("duration") or 0),
        )
    except Exception as exc:
        return jsonify(error=str(exc)), 400


@main_bp.route("/config", methods=["GET"])
def get_config():
    return jsonify(_config.load())


@main_bp.route("/config", methods=["POST"])
def update_config():
    data = request.get_json(force=True) or {}
    cfg = _config.load()
    if "theme" in data and data["theme"] in ("dark", "light"):
        cfg["theme"] = data["theme"]
    if "default_quality" in data and str(data["default_quality"]) in QUALITY_OPTIONS:
        cfg["default_quality"] = str(data["default_quality"])
    if "download_dir" in data and str(data["download_dir"]).strip():
        cfg["download_dir"] = str(data["download_dir"]).strip()
    _config.save(cfg)
    return jsonify(cfg)
