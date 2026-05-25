"""
admin.py — VidFlow Admin Panel Blueprint.

Routes (all under /admin prefix):
  GET/POST /admin/login
  GET      /admin/logout
  GET      /admin/dashboard
  GET      /admin/users
  GET      /admin/user/<id>
  POST     /admin/user/<id>/delete
  GET      /admin/downloads
  POST     /admin/downloads/delete/<id>
  GET      /admin/stats
  GET      /admin/stats/json
  GET/POST /admin/settings
  POST     /admin/create-admin   (super admin only)
"""

import json
import secrets
import threading
from datetime import datetime, timedelta
from functools import wraps
from pathlib import Path

from flask import (Blueprint, jsonify, redirect, render_template,
                   request, session, url_for)
from sqlalchemy import func, or_
from werkzeug.security import check_password_hash, generate_password_hash

from models import Admin, Download, SiteStats, User, db

admin_bp = Blueprint('admin', __name__, url_prefix='/admin')

# ── Admin settings store ──────────────────────────────────────────────────────
_SETTINGS_PATH = Path(__file__).parent / 'admin_settings.json'
_SETTINGS_DEFAULTS = {
    'site_name':             'VidFlow',
    'maintenance_mode':      False,
    'maintenance_message':   'We are performing scheduled maintenance. Be right back!',
    'max_downloads_per_day': 100,
    'max_file_size_mb':      2000,
    'allowed_platforms': {
        'youtube':   True,
        'instagram': True,
        'tiktok':    True,
        'facebook':  True,
        'twitter':   True,
        'vimeo':     True,
    },
}
_settings_cache = None
_settings_lock  = threading.Lock()


def load_admin_settings() -> dict:
    global _settings_cache
    with _settings_lock:
        if _SETTINGS_PATH.exists():
            try:
                stored = json.loads(_SETTINGS_PATH.read_text(encoding='utf-8'))
                _settings_cache = {**_SETTINGS_DEFAULTS, **stored}
                return dict(_settings_cache)
            except Exception:
                pass
        _settings_cache = dict(_SETTINGS_DEFAULTS)
        return dict(_settings_cache)


def save_admin_settings(data: dict) -> None:
    global _settings_cache
    with _settings_lock:
        _SETTINGS_PATH.write_text(
            json.dumps(data, indent=2, ensure_ascii=False),
            encoding='utf-8',
        )
        _settings_cache = dict(data)


def get_admin_settings() -> dict:
    global _settings_cache
    with _settings_lock:
        if _settings_cache is None:
            return load_admin_settings()
        return dict(_settings_cache)


# Initialise cache at import time
load_admin_settings()


# ── CSRF helpers ──────────────────────────────────────────────────────────────
def _csrf_token() -> str:
    if 'admin_csrf' not in session:
        session['admin_csrf'] = secrets.token_hex(32)
    return session['admin_csrf']


def _csrf_ok() -> bool:
    return request.form.get('csrf_token') == session.get('admin_csrf')


# ── Auth decorators ───────────────────────────────────────────────────────────
def admin_required(f):
    @wraps(f)
    def wrapped(*args, **kwargs):
        if 'admin_id' not in session:
            return redirect(url_for('admin.login'))
        # 2-hour session expiry
        t = session.get('admin_login_time', 0)
        if datetime.utcnow().timestamp() - t > 7200:
            session.pop('admin_id', None)
            return redirect(url_for('admin.login'))
        return f(*args, **kwargs)
    return wrapped


def super_admin_required(f):
    @wraps(f)
    def wrapped(*args, **kwargs):
        if 'admin_id' not in session:
            return redirect(url_for('admin.login'))
        adm = db.session.get(Admin, session['admin_id'])
        if not adm or not adm.is_super_admin:
            return render_template('admin/error.html',
                                   message='Super admin access required.'), 403
        return f(*args, **kwargs)
    return wrapped


# ── Login / Logout ────────────────────────────────────────────────────────────
@admin_bp.route('/login', methods=['GET', 'POST'])
def login():
    if 'admin_id' in session:
        return redirect(url_for('admin.dashboard'))

    error = None
    lockout_remaining = 0

    if request.method == 'POST':
        if not _csrf_ok():
            error = 'Invalid request. Please try again.'
        else:
            fails = session.get('admin_fails', 0)
            lock_ts = session.get('admin_lock_ts')

            if lock_ts:
                remaining = 900 - (datetime.utcnow().timestamp() - lock_ts)
                if remaining > 0:
                    lockout_remaining = int(remaining)
                    error = f'Locked out. Try again in {remaining // 60:.0f}m {remaining % 60:.0f}s.'
                else:
                    session.pop('admin_lock_ts', None)
                    session['admin_fails'] = 0
                    fails = 0

            if not error:
                username = request.form.get('username', '').strip()
                password = request.form.get('password', '')
                adm = Admin.query.filter_by(username=username).first()

                if adm and check_password_hash(adm.password_hash, password):
                    session['admin_id']         = adm.id
                    session['admin_login_time'] = datetime.utcnow().timestamp()
                    session.pop('admin_fails', None)
                    session.pop('admin_lock_ts', None)
                    adm.last_login = datetime.utcnow()
                    db.session.commit()
                    return redirect(url_for('admin.dashboard'))
                else:
                    fails += 1
                    session['admin_fails'] = fails
                    if fails >= 5:
                        session['admin_lock_ts'] = datetime.utcnow().timestamp()
                        error = 'Too many failed attempts. Locked out for 15 minutes.'
                    else:
                        error = f'Invalid credentials. {5 - fails} attempt(s) remaining.'

    return render_template('admin/login.html',
                           error=error,
                           lockout_remaining=lockout_remaining,
                           csrf_token=_csrf_token())


@admin_bp.route('/logout')
def logout():
    session.pop('admin_id', None)
    session.pop('admin_login_time', None)
    return redirect(url_for('admin.login'))


# ── Dashboard ─────────────────────────────────────────────────────────────────
@admin_bp.route('/dashboard')
@admin_required
def dashboard():
    adm   = db.session.get(Admin, session['admin_id'])
    now   = datetime.utcnow()
    today = datetime(now.year, now.month, now.day)
    week  = now - timedelta(days=7)
    month = datetime(now.year, now.month, 1)

    total_users      = User.query.count()
    total_downloads  = Download.query.count()
    downloads_today  = Download.query.filter(Download.date >= today).count()
    downloads_week   = Download.query.filter(Download.date >= week).count()
    downloads_month  = Download.query.filter(Download.date >= month).count()

    top_platform_row = (db.session.query(Download.platform, func.count(Download.id))
                        .group_by(Download.platform)
                        .order_by(func.count(Download.id).desc())
                        .first())
    top_platform = top_platform_row[0] if top_platform_row else 'N/A'

    recent_downloads = (Download.query.order_by(Download.date.desc()).limit(10).all())
    recent_users     = (User.query.order_by(User.created_at.desc()).limit(10).all())

    return render_template('admin/dashboard.html',
        admin            = adm,
        total_users      = total_users,
        total_downloads  = total_downloads,
        downloads_today  = downloads_today,
        downloads_week   = downloads_week,
        downloads_month  = downloads_month,
        top_platform     = top_platform,
        recent_downloads = recent_downloads,
        recent_users     = recent_users,
        page_title       = 'Dashboard',
    )


# ── Users ─────────────────────────────────────────────────────────────────────
@admin_bp.route('/users')
@admin_required
def users():
    adm    = db.session.get(Admin, session['admin_id'])
    page   = request.args.get('page', 1, type=int)
    search = request.args.get('search', '').strip()

    q = User.query
    if search:
        q = q.filter(or_(User.name.ilike(f'%{search}%'),
                         User.email.ilike(f'%{search}%')))
    pagination = q.order_by(User.created_at.desc()).paginate(
        page=page, per_page=20, error_out=False)

    return render_template('admin/users.html',
        admin      = adm,
        users      = pagination.items,
        pagination = pagination,
        search     = search,
        total      = q.count(),
        page_title = 'Users',
    )


@admin_bp.route('/user/<int:user_id>')
@admin_required
def user_detail(user_id):
    adm  = db.session.get(Admin, session['admin_id'])
    user = db.session.get(User, user_id)
    if not user:
        return redirect(url_for('admin.users'))
    downloads = (Download.query.filter_by(user_id=user_id)
                 .order_by(Download.date.desc()).all())
    return render_template('admin/user_detail.html',
        admin      = adm,
        user       = user,
        downloads  = downloads,
        csrf_token = _csrf_token(),
        page_title = f'User: {user.name or user.email}',
    )


@admin_bp.route('/user/<int:user_id>/delete', methods=['POST'])
@admin_required
def delete_user(user_id):
    if not _csrf_ok():
        return redirect(url_for('admin.users'))
    user = db.session.get(User, user_id)
    if user:
        Download.query.filter_by(user_id=user_id).delete()
        db.session.delete(user)
        db.session.commit()
    return redirect(url_for('admin.users'))


# ── Downloads ─────────────────────────────────────────────────────────────────
@admin_bp.route('/downloads')
@admin_required
def downloads():
    adm       = db.session.get(Admin, session['admin_id'])
    page      = request.args.get('page', 1, type=int)
    search    = request.args.get('search', '').strip()
    platform  = request.args.get('platform', '').strip()
    date_from = request.args.get('date_from', '')
    date_to   = request.args.get('date_to', '')

    q = Download.query
    if search:
        q = q.filter(Download.title.ilike(f'%{search}%'))
    if platform:
        q = q.filter(Download.platform.ilike(f'%{platform}%'))
    if date_from:
        try:
            q = q.filter(Download.date >= datetime.strptime(date_from, '%Y-%m-%d'))
        except ValueError:
            pass
    if date_to:
        try:
            q = q.filter(Download.date < datetime.strptime(date_to, '%Y-%m-%d') + timedelta(days=1))
        except ValueError:
            pass

    pagination = q.order_by(Download.date.desc()).paginate(
        page=page, per_page=20, error_out=False)

    return render_template('admin/downloads.html',
        admin      = adm,
        downloads  = pagination.items,
        pagination = pagination,
        search     = search,
        platform   = platform,
        date_from  = date_from,
        date_to    = date_to,
        total      = q.count(),
        csrf_token = _csrf_token(),
        page_title = 'Downloads',
    )


@admin_bp.route('/downloads/delete/<int:dl_id>', methods=['POST'])
@admin_required
def delete_download(dl_id):
    if not _csrf_ok():
        return redirect(url_for('admin.downloads'))
    rec = db.session.get(Download, dl_id)
    if rec:
        db.session.delete(rec)
        db.session.commit()
    return redirect(request.referrer or url_for('admin.downloads'))


# ── Statistics ────────────────────────────────────────────────────────────────
@admin_bp.route('/stats')
@admin_required
def stats():
    adm   = db.session.get(Admin, session['admin_id'])
    total = Download.query.count()

    platform_rows = (db.session.query(Download.platform, func.count(Download.id))
                     .group_by(Download.platform)
                     .order_by(func.count(Download.id).desc()).all())
    platform_data = [{'platform': r[0] or 'Unknown', 'count': r[1],
                      'pct': round(r[1] / total * 100, 1) if total else 0}
                     for r in platform_rows]

    top_users = (db.session.query(User.name, User.email, func.count(Download.id))
                 .join(Download, User.id == Download.user_id)
                 .group_by(User.id)
                 .order_by(func.count(Download.id).desc())
                 .limit(10).all())

    return render_template('admin/stats.html',
        admin          = adm,
        platform_data  = platform_data,
        top_users      = top_users,
        total_downloads = total,
        page_title     = 'Statistics',
    )


@admin_bp.route('/stats/json')
@admin_required
def stats_json():
    days  = request.args.get('days', 30, type=int)
    since = datetime.utcnow() - timedelta(days=days)

    daily = (db.session.query(func.date(Download.date), func.count(Download.id))
             .filter(Download.date >= since)
             .group_by(func.date(Download.date))
             .order_by(func.date(Download.date)).all())

    platforms = (db.session.query(Download.platform, func.count(Download.id))
                 .filter(Download.date >= since)
                 .group_by(Download.platform)
                 .order_by(func.count(Download.id).desc()).all())

    top_users = (db.session.query(User.name, func.count(Download.id))
                 .join(Download, User.id == Download.user_id)
                 .filter(Download.date >= since)
                 .group_by(User.id)
                 .order_by(func.count(Download.id).desc())
                 .limit(10).all())

    return jsonify({
        'daily':     [{'date': str(r[0]), 'count': r[1]} for r in daily],
        'platforms': [{'platform': r[0] or 'Unknown', 'count': r[1]} for r in platforms],
        'top_users': [{'name': r[0] or 'Unknown', 'count': r[1]} for r in top_users],
    })


# ── Settings ──────────────────────────────────────────────────────────────────
@admin_bp.route('/settings', methods=['GET', 'POST'])
@admin_required
def settings():
    adm     = db.session.get(Admin, session['admin_id'])
    cfg     = load_admin_settings()
    success = None
    error   = None

    if request.method == 'POST':
        if not _csrf_ok():
            error = 'Invalid request.'
        else:
            cfg['site_name']           = request.form.get('site_name', 'VidFlow').strip()
            cfg['maintenance_mode']    = 'maintenance_mode' in request.form
            cfg['maintenance_message'] = request.form.get('maintenance_message', '').strip()
            try:
                cfg['max_downloads_per_day'] = int(request.form.get('max_downloads_per_day') or 100)
                cfg['max_file_size_mb']      = int(request.form.get('max_file_size_mb') or 2000)
            except ValueError:
                pass
            cfg['allowed_platforms'] = {
                p: (p in request.form)
                for p in ('youtube', 'instagram', 'tiktok', 'facebook', 'twitter', 'vimeo')
            }
            save_admin_settings(cfg)
            success = 'Settings saved successfully!'

    all_admins = Admin.query.all() if adm.is_super_admin else []

    return render_template('admin/settings.html',
        admin      = adm,
        settings   = cfg,
        success    = success,
        error      = error,
        all_admins = all_admins,
        csrf_token = _csrf_token(),
        page_title = 'Settings',
    )


@admin_bp.route('/create-admin', methods=['POST'])
@super_admin_required
def create_admin_account():
    if not _csrf_ok():
        return redirect(url_for('admin.settings'))

    username = request.form.get('username', '').strip()
    email    = request.form.get('email', '').strip()
    password = request.form.get('password', '')

    if username and email and password:
        if not Admin.query.filter(or_(Admin.username == username,
                                      Admin.email == email)).first():
            db.session.add(Admin(
                username      = username,
                email         = email,
                password_hash = generate_password_hash(password),
                is_super_admin = False,
            ))
            db.session.commit()

    return redirect(url_for('admin.settings'))
