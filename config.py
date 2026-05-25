"""
config.py — load/save user preferences from config.json.

Keys:
  download_dir     absolute path to the save folder
  default_quality  key from QUALITY_OPTIONS ("1"–"6")
  theme            "dark" | "light"
"""
import json
from pathlib import Path

CONFIG_PATH = Path(__file__).parent / "config.json"

DEFAULTS: dict = {
    "download_dir": str(Path(__file__).parent / "downloads"),
    "default_quality": "1",
    "theme": "dark",
}


def load() -> dict:
    """Return config dict merged with defaults for any missing key."""
    if CONFIG_PATH.exists():
        try:
            stored = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
            if isinstance(stored, dict):
                return {**DEFAULTS, **stored}
        except (json.JSONDecodeError, OSError):
            pass
    return dict(DEFAULTS)


def save(cfg: dict) -> None:
    """Persist cfg to config.json."""
    CONFIG_PATH.write_text(
        json.dumps(cfg, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )


def is_first_run() -> bool:
    """True when config.json does not exist yet."""
    return not CONFIG_PATH.exists()
