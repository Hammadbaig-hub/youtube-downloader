import re

SUPPORTED_PLATFORMS = [
    "YouTube", "Instagram", "TikTok", "Twitter", "Facebook",
    "Vimeo", "Reddit", "Twitch", "Dailymotion",
]

_URL_RE = re.compile(r"https?://[^\s<>\"']+")


def extract_url(text: str) -> str:
    m = _URL_RE.search(text)
    return m.group(0) if m else text.strip()


def detect_platform(url: str) -> str:
    u = url.lower()
    if "youtube.com" in u or "youtu.be" in u:
        return "YouTube"
    if "instagram.com" in u:
        return "Instagram"
    if "tiktok.com" in u:
        return "TikTok"
    if "twitter.com" in u or "x.com" in u:
        return "Twitter"
    if "facebook.com" in u or "fb.watch" in u:
        return "Facebook"
    if "vimeo.com" in u:
        return "Vimeo"
    if "reddit.com" in u:
        return "Reddit"
    if "twitch.tv" in u:
        return "Twitch"
    if "dailymotion.com" in u:
        return "Dailymotion"
    return "Other"


def is_valid_url(text: str) -> bool:
    return bool(_URL_RE.search(text))
