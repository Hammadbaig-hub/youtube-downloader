import sys
from pathlib import Path

from flask import Flask
from flask_cors import CORS
from flask_login import LoginManager

sys.path.insert(0, str(Path(__file__).parent))

from config import config as config_map
from models import db, User
from routes.main import main_bp
from routes.api import api_bp
from routes.auth import auth_bp, init_oauth
from routes.admin import admin_bp

login_manager = LoginManager()


def create_app(config_name: str = "default") -> Flask:
    app = Flask(
        __name__,
        template_folder=str(Path(__file__).parent.parent / "frontend" / "templates"),
        static_folder=str(Path(__file__).parent.parent / "frontend" / "static"),
    )
    app.config.from_object(config_map[config_name])

    CORS(app)
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

    return app
