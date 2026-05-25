import logging
from pathlib import Path

_LOG_DIR = Path(__file__).parent.parent / "logs"
_LOG_DIR.mkdir(exist_ok=True)

logging.basicConfig(
    filename=str(_LOG_DIR / "errors.log"),
    level=logging.ERROR,
    format="%(asctime)s %(levelname)s %(message)s",
)

ERROR_MESSAGES = {
    "bot_detection": (
        "YouTube blocked this download (bot detection). "
        "Make sure you are signed in to YouTube, then try again."
    ),
    "rate_limit": "YouTube rate limit (HTTP 429). Wait a few minutes and try again.",
    "unavailable": "This video is unavailable or private.",
    "future_stream": "This video is a future live stream that hasn't started yet.",
}


def classify_error(exc: Exception) -> str:
    msg = str(exc)
    if "Sign in to confirm" in msg or "bot" in msg.lower():
        return ERROR_MESSAGES["bot_detection"]
    if "429" in msg or "Too Many Requests" in msg:
        return ERROR_MESSAGES["rate_limit"]
    if "Video unavailable" in msg:
        return ERROR_MESSAGES["unavailable"]
    if "This live event will begin" in msg:
        return ERROR_MESSAGES["future_stream"]
    return msg


def log_error(context: str, exc: Exception) -> None:
    logging.error("%s: %s", context, exc, exc_info=True)
