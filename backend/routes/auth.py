from flask import Blueprint, redirect, render_template, request, url_for
from flask_login import current_user, login_user, logout_user
from authlib.integrations.flask_client import OAuth

import config as _config
from models import User, db

auth_bp = Blueprint("auth", __name__)

oauth = OAuth()
google = None


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
        if not user:
            user = User(
                google_id=user_info["sub"],
                name=user_info.get("name", ""),
                email=user_info.get("email", ""),
                avatar=user_info.get("picture", ""),
            )
            db.session.add(user)
            db.session.commit()
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
