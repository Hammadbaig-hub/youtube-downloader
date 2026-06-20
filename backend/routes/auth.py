from flask import Blueprint, current_app, redirect, render_template, request, url_for
from flask_login import current_user, login_user, logout_user
from authlib.integrations.flask_client import OAuth

import config as _config
from models import User, db

auth_bp = Blueprint("auth", __name__)

oauth = OAuth()
google = None


def _send_welcome_email(user):
    """Send welcome email — works only when Flask-Mail is configured."""
    try:
        from flask_mail import Mail, Message
        mail = Mail(current_app._get_current_object())
        msg = Message(
            subject="Welcome to VidFlow!",
            recipients=[user.email],
            html=f"""
            <div style="font-family:Poppins,sans-serif;max-width:520px;margin:0 auto;padding:32px 24px;background:#faf7f2;border-radius:16px;">
              <div style="text-align:center;margin-bottom:24px;">
                <div style="display:inline-block;background:#ff0000;border-radius:12px;padding:12px 18px;">
                  <span style="color:#fff;font-size:20px;font-weight:800;">VidFlow</span>
                </div>
              </div>
              <h2 style="color:#1a0a0a;font-size:22px;margin-bottom:10px;">Welcome, {user.name or 'there'}! 🎉</h2>
              <p style="color:#4a3020;font-size:15px;line-height:1.7;">
                Your account is ready. You can now download videos from <strong>1000+ sites</strong> — YouTube, Instagram, TikTok, and more.
              </p>
              <div style="margin:24px 0;padding:16px;background:#fff;border-radius:12px;border:1px solid #f0e6d3;">
                <p style="margin:0;color:#9a8070;font-size:13px;font-weight:600;text-transform:uppercase;letter-spacing:.05em;">Free Plan includes</p>
                <ul style="color:#4a3020;font-size:14px;margin:10px 0 0;padding-left:18px;line-height:2;">
                  <li>3 downloads per day</li>
                  <li>Up to 1080p HD quality</li>
                  <li>1000+ supported platforms</li>
                  <li>MP3 audio extraction</li>
                  <li>Download history</li>
                </ul>
              </div>
              <a href="https://vidflow.app" style="display:inline-block;padding:13px 28px;background:#ff0000;color:#fff;border-radius:10px;text-decoration:none;font-weight:700;font-size:14px;">Start Downloading →</a>
              <p style="color:#9a8070;font-size:12px;margin-top:24px;">
                Need more? <a href="https://vidflow.app/pricing" style="color:#ff0000;">Upgrade your plan</a> for unlimited downloads.
              </p>
            </div>
            """,
        )
        mail.send(msg)
    except Exception:
        pass  # Email is optional — never block signup


def init_oauth(app):
    global google
    oauth.init_app(app)
    google = oauth.register(
        name="google",
        client_id=app.config.get("GOOGLE_CLIENT_ID"),
        client_secret=app.config.get("GOOGLE_CLIENT_SECRET"),
        server_metadata_url="https://accounts.google.com/.well-known/openid-configuration",
        client_kwargs={"scope": "openid email profile"},
    )


@auth_bp.route("/login")
def login_page():
    if current_user.is_authenticated:
        return redirect(url_for("main.index"))
    cfg = _config.load()
    return render_template("login.html", theme=cfg.get("theme", "dark"))


@auth_bp.route("/auth/google")
def auth_google():
    redirect_uri = url_for("auth.auth_google_callback", _external=True)
    return google.authorize_redirect(redirect_uri)


@auth_bp.route("/auth/google/callback")
def auth_google_callback():
    if request.args.get("error"):
        return redirect(url_for("auth.login_page"))
    try:
        token = google.authorize_access_token()
        user_info = token.get("userinfo")
        if not user_info:
            return redirect(url_for("auth.login_page"))

        user = User.query.filter_by(google_id=user_info["sub"]).first()
        is_new = user is None
        if not user:
            user = User(
                google_id=user_info["sub"],
                name=user_info.get("name", ""),
                email=user_info.get("email", ""),
                avatar=user_info.get("picture", ""),
            )
            db.session.add(user)
            db.session.commit()
            if is_new:
                _send_welcome_email(user)
        else:
            user.avatar = user_info.get("picture", user.avatar)
            db.session.commit()

        login_user(user)
        return redirect(url_for("main.index"))
    except Exception:
        return redirect(url_for("auth.login_page"))


@auth_bp.route("/logout")
def logout():
    logout_user()
    return redirect(url_for("auth.login_page"))
