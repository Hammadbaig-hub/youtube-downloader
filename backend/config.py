import json
import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

_BASE_DIR = Path(__file__).parent.parent  # project root

IS_VERCEL = bool(os.getenv("VERCEL"))

# ── Paths: use /tmp on Vercel (read-only filesystem except /tmp) ──────────────
if IS_VERCEL:
    CONFIG_PATH        = Path("/tmp/config.json")
    ADMIN_SETTINGS_PATH = Path("/tmp/admin_settings.json")
    _DEFAULT_DOWNLOAD_DIR = "/tmp/downloads"
    _DEFAULT_DB_PATH = "sqlite:////tmp/vidflow.db"
else:
    CONFIG_PATH        = Path(__file__).parent / "config.json"
    ADMIN_SETTINGS_PATH = Path(__file__).parent / "admin_settings.json"
    _DEFAULT_DOWNLOAD_DIR = str(Path(__file__).parent / "downloads")
    _DEFAULT_DB_PATH = f"sqlite:///{Path(__file__).parent / 'instance' / 'vidflow.db'}"

DEFAULTS: dict = {
    "download_dir":    _DEFAULT_DOWNLOAD_DIR,
    "default_quality": "1",
    "theme":           "dark",
}


def load() -> dict:
    if CONFIG_PATH.exists():
        try:
            stored = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
            if isinstance(stored, dict):
                return {**DEFAULTS, **stored}
        except (json.JSONDecodeError, OSError):
            pass
    return dict(DEFAULTS)


def save(cfg: dict) -> None:
    try:
        CONFIG_PATH.write_text(
            json.dumps(cfg, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
    except OSError:
        pass  # silently skip on read-only filesystems


def is_first_run() -> bool:
    return not CONFIG_PATH.exists()


# ── Flask configuration classes ───────────────────────────────────────────────
class Config:
    SECRET_KEY = os.getenv("SECRET_KEY", "dev-change-me-in-production")
    SQLALCHEMY_DATABASE_URI = os.getenv("DATABASE_URL", _DEFAULT_DB_PATH)
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    GOOGLE_CLIENT_ID     = os.getenv("GOOGLE_CLIENT_ID")
    GOOGLE_CLIENT_SECRET = os.getenv("GOOGLE_CLIENT_SECRET")
    DOWNLOAD_FOLDER      = _DEFAULT_DOWNLOAD_DIR
    MAX_DOWNLOADS_PER_DAY = int(os.getenv("MAX_DOWNLOADS", 10))
    # Flask-Mail (optional — set in .env to enable welcome emails)
    MAIL_SERVER   = os.getenv("MAIL_SERVER", "smtp.gmail.com")
    MAIL_PORT     = int(os.getenv("MAIL_PORT", 587))
    MAIL_USE_TLS  = True
    MAIL_USERNAME = os.getenv("MAIL_USERNAME", "")
    MAIL_PASSWORD = os.getenv("MAIL_PASSWORD", "")
    MAIL_DEFAULT_SENDER = os.getenv("MAIL_USERNAME", "noreply@vidflow.app")


class DevelopmentConfig(Config):
    DEBUG = True


class ProductionConfig(Config):
    DEBUG = False


config = {
    "development": DevelopmentConfig,
    "production":  ProductionConfig,
    "default":     DevelopmentConfig,
}
