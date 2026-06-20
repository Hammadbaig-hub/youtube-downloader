import sys
import threading
import time
from pathlib import Path

from flask import Flask
from flask_cors import CORS
from flask_login import LoginManager
from flask_wtf.csrf import CSRFProtect

sys.path.insert(0, str(Path(__file__).parent))

from config import config as config_map, IS_VERCEL
from models import db, User
from routes.main import main_bp
from routes.api import api_bp
from routes.auth import auth_bp, init_oauth
from routes.admin import admin_bp

login_manager = LoginManager()
csrf = CSRFProtect()


def create_app(config_name: str = "default") -> Flask:
    app = Flask(
        __name__,
        template_folder=str(Path(__file__).parent.parent / "frontend" / "templates"),
        static_folder=str(Path(__file__).parent.parent / "frontend" / "static"),
    )
    app.config.from_object(config_map[config_name])

    CORS(app)
    csrf.init_app(app)
    csrf.exempt(auth_bp)   # Google OAuth redirects don't carry CSRF tokens
    db.init_app(app)

    login_manager.init_app(app)
    login_manager.login_view = "auth.login_page"

    init_oauth(app)

    app.register_blueprint(main_bp)
    app.register_blueprint(api_bp)
    app.register_blueprint(auth_bp)
    app.register_blueprint(admin_bp, url_prefix="/admin")

    @login_manager.user_loader
    def load_user(user_id: str):
        return db.session.get(User, int(user_id))

    with app.app_context():
        db.create_all()

    # Background file cleanup only makes sense when files are stored on disk
    if not IS_VERCEL:
        _start_cleanup_thread(app)

    return app


def _start_cleanup_thread(app: Flask) -> None:
    """Delete downloaded files older than 24 hours every hour."""
    def _run():
        while True:
            time.sleep(3600)
            try:
                with app.app_context():
                    from config import load as load_cfg
                    dl_dir = Path(load_cfg().get("download_dir", ""))
                    if not dl_dir.exists():
                        continue
                    cutoff = time.time() - 86400
                    deleted = 0
                    for f in dl_dir.rglob("*"):
                        if f.is_file() and f.stat().st_mtime < cutoff:
                            try:
                                f.unlink()
                                deleted += 1
                            except OSError:
                                pass
                    if deleted:
                        app.logger.info(f"[cleanup] Deleted {deleted} old file(s)")
            except Exception as e:
                app.logger.warning(f"[cleanup] Error: {e}")

    t = threading.Thread(target=_run, daemon=True)
    t.start()
