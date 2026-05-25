import json
import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

_BASE_DIR = Path(__file__).parent.parent  # project root

# ── User preferences (config.json) ───────────────────────────────────────────
CONFIG_PATH = Path(__file__).parent / "config.json"

DEFAULTS: dict = {
    "download_dir": str(Path(__file__).parent / "downloads"),
    "default_quality": "1",
    "theme": "dark",
}

ADMIN_SETTINGS_PATH = Path(__file__).parent / "admin_settings.json"


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
    CONFIG_PATH.write_text(
        json.dumps(cfg, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )


def is_first_run() -> bool:
    return not CONFIG_PATH.exists()


# ── Flask configuration classes ───────────────────────────────────────────────
class Config:
    SECRET_KEY = os.getenv("SECRET_KEY", "dev-change-me-in-production")
    SQLALCHEMY_DATABASE_URI = os.getenv(
        "DATABASE_URL",
        f"sqlite:///{_BASE_DIR / 'database' / 'vidflow.db'}"
    )
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    GOOGLE_CLIENT_ID = os.getenv("GOOGLE_CLIENT_ID")
    GOOGLE_CLIENT_SECRET = os.getenv("GOOGLE_CLIENT_SECRET")
    DOWNLOAD_FOLDER = str(Path(__file__).parent / "downloads")
    MAX_DOWNLOADS_PER_DAY = int(os.getenv("MAX_DOWNLOADS", 10))


class DevelopmentConfig(Config):
    DEBUG = True


class ProductionConfig(Config):
    DEBUG = False


config = {
    "development": DevelopmentConfig,
    "production": ProductionConfig,
    "default": DevelopmentConfig,
}
