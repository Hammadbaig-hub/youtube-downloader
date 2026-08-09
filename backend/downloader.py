"""
downloader.py — yt-dlp wrapper.

VideoDownloader.download() — saves file to disk, merging with ffmpeg.

Live streams are handled separately: they have no end and no total size, so
they are recorded for a fixed duration (or until stopped) rather than
"downloaded". See LIVE_DURATIONS and stop_live_job().
"""

import os
import shutil
import threading
import yt_dlp
from pathlib import Path

try:
    from rich.console import Console
    from rich.progress import (
        BarColumn,
        DownloadColumn,
        Progress,
        SpinnerColumn,
        TaskID,
        TextColumn,
        TimeRemainingColumn,
        TransferSpeedColumn,
    )
    _RICH = True
    console = Console()
except ImportError:
    _RICH = False
    console = None

DOWNLOAD_DIR = Path(__file__).parent / "downloads"


def _find_ffmpeg() -> str | None:
    if shutil.which("ffmpeg"):
        return None  # already in PATH

    # Windows: check winget install location
    winget_base = Path.home() / "AppData" / "Local" / "Microsoft" / "WinGet" / "Packages"
    if winget_base.exists():
        for candidate in sorted(winget_base.glob("Gyan.FFmpeg*"), reverse=True):
            for bin_dir in candidate.rglob("bin"):
                if (bin_dir / "ffmpeg.exe").exists():
                    return str(bin_dir)

    return None


_FFMPEG_LOCATION: str | None = _find_ffmpeg()


""
# NOTE ON aria2c
# aria2c looks like the obvious fix here (it opens 16 parallel connections and
# YouTube throttles per connection), and a raw range-request probe suggested a
# ~3.5x gain. It does not survive a controlled test: with downloads run
# alternating against the built-in downloader, aria2c came out at 0.62x — i.e.
# consistently SLOWER over 3 rounds — and separately failed with `aria2c exited
# with code 22`. The raw probe was misleading because it split a small sample
# into tiny ranges, measuring YouTube's per-connection opening burst rather
# than sustained throughput. Do not re-add it without an interleaved A/B that
# actually shows a win.


def _find_js_runtime() -> dict[str, dict]:
    """
    YouTube signs its media URLs with a JS challenge. yt-dlp can only solve it
    with a JavaScript runtime, and it enables *deno only* by default — so a box
    with just Node installed silently falls back to the deprecated JS-less path,
    where signature/n-challenge solving fails and formats go missing.
    Enable whichever runtime is actually present.
    """
    for name in ("deno", "node", "bun", "quickjs"):
        if shutil.which(name):
            return {name: {}}
    return {}


_JS_RUNTIMES: dict[str, dict] = _find_js_runtime()

# Solving the challenge also needs yt-dlp's EJS solver script, which is fetched
# on demand rather than shipped in the package. Without it the runtime above is
# useless. Opt out with YTDLP_NO_REMOTE_COMPONENTS=1 if egress is restricted.
_REMOTE_COMPONENTS: list[str] = (
    [] if os.getenv("YTDLP_NO_REMOTE_COMPONENTS") else ["ejs:github"]
)

# Cookies are the documented remedy for "Sign in to confirm you're not a bot".
# YTDLP_COOKIEFILE=/path/to/cookies.txt  (Netscape format), or
# YTDLP_COOKIES_FROM_BROWSER=chrome|firefox|edge|brave (local dev only).
_COOKIEFILE = os.getenv("YTDLP_COOKIEFILE") or None
_COOKIES_FROM_BROWSER = os.getenv("YTDLP_COOKIES_FROM_BROWSER") or None


def _base_opts() -> dict:
    """yt-dlp options every call path needs to get past YouTube's restrictions."""
    opts: dict = {
        "js_runtimes": _JS_RUNTIMES,
        "remote_components": _REMOTE_COMPONENTS,
        # Order matters for speed, not just availability. Measured on one video:
        #   android_vr  27 progressive https formats
        #   web_safari   6 m3u8_native (HLS) + 1 https
        #   tv / web     1 usable https format each
        # HLS is fetched as many small segments, so when web_safari came first
        # the selector picked m3u8 renditions and throughput collapsed.
        # android_vr leads because it exposes plain https formats that download
        # as one ranged request; the rest stay as fallbacks for odd videos.
        "extractor_args": {
            "youtube": {"player_client": ["android_vr", "web_safari", "tv", "web"]},
        },
        # Whenever a format *is* fragmented (HLS, DASH segments, live), fetch
        # segments in parallel — yt-dlp defaults to 1 at a time.
        "concurrent_fragment_downloads": 8,
        # Request the file in 10 MB ranges. A single open-ended request tends to
        # get throttled part-way through; re-ranging keeps throughput up and
        # makes a stall cost one chunk instead of the whole transfer.
        "http_chunk_size": 10 * 1024 * 1024,
        # 429 is usually transient; back off instead of failing the job.
        "retries": 5,
        "extractor_retries": 3,
        "retry_sleep_functions": {"http": lambda n: min(2 ** n, 30)},
    }

    if _COOKIEFILE and Path(_COOKIEFILE).exists():
        opts["cookiefile"] = _COOKIEFILE
    elif _COOKIES_FROM_BROWSER:
        opts["cookiesfrombrowser"] = (_COOKIES_FROM_BROWSER, None, None, None)

    return opts


def _vfmt(h: int) -> str:
    """Format string for local downloads (ffmpeg available)."""
    cap = f"[height<={h}]" if h else ""
    return (
        f"bestvideo{cap}[ext=mp4]+bestaudio[ext=m4a]"
        f"/bestvideo{cap}[ext=mp4]+bestaudio"
        f"/bestvideo{cap}+bestaudio[ext=m4a]"
        f"/bestvideo{cap}+bestaudio"
        f"/best{cap}[ext=mp4]/best{cap}"
        f"/best"  # source may not offer the requested resolution at all
    )


# ── Live streams ─────────────────────────────────────────────────────────────
# A live stream never ends and reports no total size, so it can only be
# *recorded* for a chosen span. Recording runs at real time: 10 minutes of
# stream takes 10 minutes of wall clock, no matter how fast the connection is.
LIVE_DURATIONS: dict[str, dict] = {
    "5":  {"name": "5 minutes",  "seconds": 300},
    "10": {"name": "10 minutes", "seconds": 600},
    "30": {"name": "30 minutes", "seconds": 1800},
    "60": {"name": "1 hour",     "seconds": 3600},
}
DEFAULT_LIVE_DURATION = "10"

# yt-dlp hands live streams to ffmpeg, which it runs via yt_dlp.utils.Popen.
# Tracking those processes is the only way to end a recording early. The list
# lives in thread-local storage so concurrent jobs never see each other's
# processes, and the same list object is published per job_id for the API.
_local = threading.local()
_LIVE_PROCS: dict[str, list] = {}
_LIVE_LOCK = threading.Lock()

_YtPopen = yt_dlp.utils.Popen


class _TrackedPopen(_YtPopen):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        procs = getattr(_local, "procs", None)
        if procs is not None:
            procs.append(self)


yt_dlp.downloader.external.Popen = _TrackedPopen


def stop_live_job(job_id: str) -> bool:
    """End a live recording early, keeping what has been written so far."""
    with _LIVE_LOCK:
        procs = list(_LIVE_PROCS.get(job_id) or [])
    if not procs:
        return False

    for proc in procs:
        if proc.poll() is not None:
            continue
        # 'q' is ffmpeg's graceful quit: it finalises the container so the
        # partial file stays playable. Fall back to killing it if that fails.
        try:
            proc.stdin.write(b"q")
            proc.stdin.flush()
        except Exception:
            pass
        try:
            proc.wait(timeout=10)
        except Exception:
            try:
                proc.kill()
            except Exception:
                pass
    return True


QUALITY_OPTIONS: dict[str, dict] = {
    "1": {"name": "Best Quality (auto)", "format": _vfmt(0)},
    "2": {"name": "1080p HD",            "format": _vfmt(1080)},
    "3": {"name": "720p HD",             "format": _vfmt(720)},
    "4": {"name": "480p",                "format": _vfmt(480)},
    "5": {"name": "360p",                "format": _vfmt(360)},
    "6": {
        "name":   "Audio Only (MP3)",
        "format": "bestaudio[ext=m4a]/bestaudio/best",
    },
}


class VideoDownloader:
    def __init__(self) -> None:
        DOWNLOAD_DIR.mkdir(parents=True, exist_ok=True)
        self._progress = None
        self._task_id = None
        self._current_filename: str = ""

    def get_info(self, url: str) -> dict:
        opts = {
            **_base_opts(),
            "quiet": True,
            "no_warnings": True,
            "extract_flat": "in_playlist",
        }
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(url, download=False)
        if info is None:
            raise ValueError("Could not retrieve information for that URL.")
        return info

    @staticmethod
    def live_state(info: dict) -> str:
        """
        'live'     — broadcasting now; can only be recorded for a fixed span.
        'upcoming' — scheduled but not started; nothing to download yet.
        'ended'    — a finished broadcast, downloadable like any normal video.
        """
        status = info.get("live_status")
        if status == "is_live" or (status is None and info.get("is_live")):
            return "live"
        if status in ("is_upcoming", "post_live"):
            return "upcoming" if status == "is_upcoming" else "ended"
        if status == "was_live" or info.get("was_live"):
            return "ended"
        return "vod"

    def download(
        self,
        url: str,
        quality_key: str,
        is_playlist: bool = False,
        progress_callback=None,
        output_dir: "Path | None" = None,
        archive_file: "Path | None" = None,
        live_seconds: int | None = None,
        job_id: str | None = None,
    ) -> list[str]:
        quality = QUALITY_OPTIONS[quality_key]
        is_audio = quality_key == "6"
        self._current_filename = ""

        base_dir = output_dir or DOWNLOAD_DIR
        base_dir.mkdir(parents=True, exist_ok=True)

        # Titles can run 200+ chars (social-media captions, hashtags, etc.) and
        # some contain periods, which breaks yt-dlp's trim_file_name (it splits
        # on '.' to separate the extension, so a mid-title period causes it to
        # only trim the part before that period). Truncate via the template's
        # printf-style precision instead, so the cap is exact regardless of
        # periods in the title.
        if is_playlist:
            output_tpl = str(
                base_dir
                / "%(playlist_title).60s"
                / "%(playlist_index)02d - %(title).80s.%(ext)s"
            )
        else:
            output_tpl = str(base_dir / "%(title).80s.%(ext)s")

        hook = progress_callback if progress_callback else self._progress_hook
        ydl_opts: dict = {
            **_base_opts(),
            "format": quality["format"],
            "outtmpl": output_tpl,
            "merge_output_format": "mp4",
            "quiet": True,
            "no_warnings": True,
            "progress_hooks": [hook],
            "noplaylist": not is_playlist,
            "windowsfilenames": True,
            "trim_file_name": 200,
            "nopart": True,
        }

        if _FFMPEG_LOCATION:
            ydl_opts["ffmpeg_location"] = _FFMPEG_LOCATION

        if archive_file:
            ydl_opts["download_archive"] = str(archive_file)

        if is_audio:
            ydl_opts["postprocessors"] = [
                {
                    "key": "FFmpegExtractAudio",
                    "preferredcodec": "mp3",
                    "preferredquality": "192",
                }
            ]
            del ydl_opts["merge_output_format"]
        else:
            # Copy both streams instead of re-encoding audio. The format string
            # above asks for m4a first, which is already AAC, so transcoding it
            # to AAC again cost ~9 minutes on a 2-hour video (measured 13x
            # real time vs 8000x for a copy) and looked like a frozen job.
            # yt-dlp picks container-compatible formats for merge_output_format,
            # so a straight copy is safe here.
            ydl_opts["postprocessor_args"] = {
                "merger": ["-c:v", "copy", "-c:a", "copy"],
            }

        if live_seconds:
            # A live stream has no end, so cap the recording with ffmpeg's -t.
            # It exits cleanly at the limit and finalises a playable file.
            # Merge, don't replace: _base_opts() may have put aria2c args here.
            ydl_opts["external_downloader_args"] = {
                **ydl_opts.get("external_downloader_args", {}),
                "ffmpeg_o": ["-t", str(int(live_seconds))],
            }
            # Live HLS is a single muxed stream; there is nothing to merge, and
            # the merger args above would be rejected by the copy-only pipeline.
            ydl_opts.pop("postprocessor_args", None)

        # Publish this thread's ffmpeg processes so stop_live_job() can reach
        # them. Same list object in both places, so appends are visible.
        procs: list = []
        _local.procs = procs
        if job_id:
            with _LIVE_LOCK:
                _LIVE_PROCS[job_id] = procs

        try:
            return self._run(ydl_opts, url, progress_callback)
        finally:
            _local.procs = None
            if job_id:
                with _LIVE_LOCK:
                    _LIVE_PROCS.pop(job_id, None)

    def _run(self, ydl_opts: dict, url: str, progress_callback) -> list[str]:
        info: dict | None = None

        if progress_callback or not _RICH:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url)
        else:
            with Progress(
                SpinnerColumn(),
                TextColumn("[bold blue]{task.description}"),
                BarColumn(bar_width=35),
                DownloadColumn(),
                TransferSpeedColumn(),
                TimeRemainingColumn(),
                console=console,
                transient=False,
            ) as progress:
                self._progress = progress
                self._task_id = progress.add_task("Preparing…", total=None)

                with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                    info = ydl.extract_info(url)

            self._progress = None
            self._task_id = None

        return self._collect_filepaths(info)

    def _progress_hook(self, d: dict) -> None:
        if not _RICH or self._progress is None or self._task_id is None:
            return

        status = d.get("status")

        if status == "downloading":
            fname = d.get("filename", "")
            if fname and fname != self._current_filename:
                self._current_filename = fname
                title = d.get("info_dict", {}).get("title", "Downloading…")
                label = (title[:55] + "…") if len(title) > 55 else title
                self._progress.update(self._task_id, description=label, completed=0, total=None)

            downloaded = d.get("downloaded_bytes") or 0
            total = d.get("total_bytes") or d.get("total_bytes_estimate") or None
            self._progress.update(self._task_id, completed=downloaded, total=total)

        elif status == "finished":
            self._progress.update(self._task_id, description="[yellow]Processing…[/yellow]")

        elif status == "error":
            self._progress.update(self._task_id, description="[red]Error — see output above[/red]")

    @staticmethod
    def _collect_filepaths(info: dict | None) -> list[str]:
        if not info:
            return []

        paths: list[str] = []

        def _from_entry(entry: dict) -> None:
            for dl in entry.get("requested_downloads") or []:
                fp = dl.get("filepath") or dl.get("filename", "")
                if fp:
                    paths.append(fp)

        if info.get("_type") == "playlist":
            for entry in info.get("entries") or []:
                if entry:
                    _from_entry(entry)
        else:
            _from_entry(info)

        return paths
