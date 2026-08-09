import logging
from pathlib import Path

_LOG_DIR = Path(__file__).parent.parent / "logs"
_LOG_DIR.mkdir(exist_ok=True)

try:
    logging.basicConfig(
        filename=str(_LOG_DIR / "errors.log"),
        level=logging.ERROR,
        format="%(asctime)s %(levelname)s %(message)s",
    )
except OSError:
    # Log file isn't writable (e.g. restrictive filesystem permissions) —
    # fall back to console logging instead of crashing the app at import time.
    logging.basicConfig(
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
    "js_runtime": (
        "This video needs YouTube's signature check solved, which requires a "
        "JavaScript runtime on the server. Install Node.js (or Deno) and retry."
    ),
    "forbidden": (
        "YouTube rejected the media link (HTTP 403). This usually means the "
        "link expired mid-download — please try again."
    ),
    "geo": "This video is not available in the server's region.",
    "age": "This video is age-restricted and needs a signed-in YouTube account.",
    "no_format": (
        "This video isn't available in the quality you picked. "
        "Try a lower quality, or Audio Only (MP3)."
    ),
}

# Ordered most-specific first: several yt-dlp messages match more than one rule.
_PATTERNS: list[tuple[tuple[str, ...], str]] = [
    (("Sign in to confirm you're not a bot",
      "Sign in to confirm that you're not a bot",
      "confirm you're not a bot"), "bot_detection"),
    (("Sign in to confirm your age", "age-restricted", "inappropriate for some users"), "age"),
    (("Signature solving failed", "n challenge solving failed",
      "No supported JavaScript runtime", "challenge solver"), "js_runtime"),
    (("HTTP Error 429", "Too Many Requests"), "rate_limit"),
    (("HTTP Error 403", "Forbidden"), "forbidden"),
    (("This live event will begin", "live event will begin in"), "future_stream"),
    (("available in your country", "available from your location",
      "geo restricted", "geo-restricted", "blocked it in your country",
      "not available in your region"), "geo"),
    (("Video unavailable", "This video is private",
      "video has been removed"), "unavailable"),
    (("Requested format is not available",), "no_format"),
]


def classify_error(exc: Exception) -> str:
    msg = str(exc)
    lowered = msg.lower()
    for needles, key in _PATTERNS:
        if any(n.lower() in lowered for n in needles):
            return ERROR_MESSAGES[key]
    return msg


def log_error(context: str, exc: Exception) -> None:
    logging.error("%s: %s", context, exc, exc_info=True)
