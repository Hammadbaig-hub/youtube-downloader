"""
downloader.py — yt-dlp wrapper with rich progress display.

Handles single videos and playlists. The VideoDownloader class is the only
public surface; QUALITY_OPTIONS and DOWNLOAD_DIR are exported for the CLI.
"""

import shutil
import yt_dlp
from pathlib import Path

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

console = Console()

# Absolute path so it resolves correctly regardless of the working directory
# the caller (Flask, CLI, GUI) was launched from.
DOWNLOAD_DIR = Path(__file__).parent / "downloads"


def _find_ffmpeg() -> str | None:
    """Return the directory that contains ffmpeg(.exe), or None if already on PATH.

    Checks PATH first so a system-wide install is preferred. Falls back to the
    winget per-user install location (Gyan.FFmpeg) which is where winget puts
    it on Windows when it isn't added to PATH automatically.
    """
    if shutil.which("ffmpeg"):
        return None  # already discoverable — let yt-dlp find it normally

    # winget installs under %LOCALAPPDATA%\Microsoft\WinGet\Packages\Gyan.FFmpeg*
    winget_base = Path.home() / "AppData" / "Local" / "Microsoft" / "WinGet" / "Packages"
    for candidate in sorted(winget_base.glob("Gyan.FFmpeg*"), reverse=True):
        for bin_dir in candidate.rglob("bin"):
            if (bin_dir / "ffmpeg.exe").exists():
                return str(bin_dir)

    return None  # not found — yt-dlp will warn if FFmpeg is needed


# Resolved once at import time so every download call uses the same path.
_FFMPEG_LOCATION: str | None = _find_ffmpeg()

# Maps user-facing choice number → yt-dlp format selector string.
#
# Each entry uses the pattern:
#   bestvideo[height<=N][ext=mp4]+bestaudio[ext=m4a]   — best mp4+m4a pair (no re-encode)
#   / bestvideo[height<=N]+bestaudio                   — any codec pair (FFmpeg merges)
#   / best[height<=N]                                  — pre-muxed fallback (has audio)
#
# Format chain for video qualities:
#   1st choice: mp4 video + m4a audio  (H.264 + AAC — plays everywhere)
#   2nd choice: mp4 video + any audio, re-encoded to AAC by postprocessor
#   3rd choice: any video + m4a audio
#   4th choice: any video + any audio  (FFmpeg will merge; postprocessor re-encodes audio)
#   last resort: best pre-muxed stream (always has audio)
def _vfmt(h: int) -> str:
    cap = f"[height<={h}]" if h else ""
    return (
        f"bestvideo{cap}[ext=mp4]+bestaudio[ext=m4a]"
        f"/bestvideo{cap}[ext=mp4]+bestaudio"
        f"/bestvideo{cap}+bestaudio[ext=m4a]"
        f"/bestvideo{cap}+bestaudio"
        f"/best{cap}[ext=mp4]/best{cap}"
    )


QUALITY_OPTIONS: dict[str, dict] = {
    "1": {"name": "Best Quality (auto)", "format": _vfmt(0)},
    "2": {"name": "1080p HD",           "format": _vfmt(1080)},
    "3": {"name": "720p HD",            "format": _vfmt(720)},
    "4": {"name": "480p",               "format": _vfmt(480)},
    "5": {"name": "360p",               "format": _vfmt(360)},
    "6": {
        "name": "Audio Only (MP3)",
        "format": "bestaudio[ext=m4a]/bestaudio/best",
    },
}


class VideoDownloader:
    """Downloads YouTube videos (or full playlists) via yt-dlp.

    Usage:
        dl = VideoDownloader()
        info = dl.get_info(url)          # fast metadata fetch
        files = dl.download(url, "2")    # download 720p, returns file paths
    """

    def __init__(self) -> None:
        DOWNLOAD_DIR.mkdir(parents=True, exist_ok=True)
        # State shared between the download call and the yt-dlp hook callbacks.
        self._progress: Progress | None = None
        self._task_id: TaskID | None = None
        self._current_filename: str = ""  # tracks which file is currently downloading

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def get_info(self, url: str) -> dict:
        """Return video/playlist metadata without downloading any content.

        Uses extract_flat so playlist info is returned quickly (no per-video
        network requests for full metadata).
        """
        opts = {
            "quiet": True,
            "no_warnings": True,
            "extract_flat": "in_playlist",
        }
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(url, download=False)
        if info is None:
            raise ValueError("Could not retrieve information for that URL.")
        return info

    def download(
        self,
        url: str,
        quality_key: str,
        is_playlist: bool = False,
        progress_callback=None,
        output_dir: "Path | None" = None,
        archive_file: "Path | None" = None,
    ) -> list[str]:
        """Download a single video or a full playlist.

        Args:
            url:               YouTube video or playlist URL.
            quality_key:       Key from QUALITY_OPTIONS ("1"–"6").
            is_playlist:       When True the full playlist is fetched and downloaded.
            progress_callback: Optional callable(d: dict) receiving raw yt-dlp
                               progress dicts. When supplied the Rich progress bar
                               is skipped — used by the GUI frontend.
            output_dir:        Override the save directory (defaults to DOWNLOAD_DIR).
            archive_file:      Path to a yt-dlp download archive file. Videos whose
                               IDs appear in this file are skipped (resume support).

        Returns:
            List of absolute file paths for every saved file.
        """
        quality = QUALITY_OPTIONS[quality_key]
        is_audio = quality_key == "6"
        self._current_filename = ""

        base_dir = output_dir or DOWNLOAD_DIR
        base_dir.mkdir(parents=True, exist_ok=True)

        # Playlist videos go into a named subfolder; single videos go flat.
        if is_playlist:
            output_tpl = str(
                base_dir
                / "%(playlist_title)s"
                / "%(playlist_index)02d - %(title)s.%(ext)s"
            )
        else:
            output_tpl = str(base_dir / "%(title)s.%(ext)s")

        hook = progress_callback if progress_callback else self._progress_hook
        ydl_opts: dict = {
            "format": quality["format"],
            "outtmpl": output_tpl,
            "merge_output_format": "mp4",   # combine separate video+audio streams
            "quiet": True,
            "no_warnings": True,
            "progress_hooks": [hook],
            "noplaylist": not is_playlist,  # prevent accidental playlist download
            # Strip characters that Windows rejects in filenames (: * ? " < > |)
            "windowsfilenames": True,
            # Limit path length to avoid MAX_PATH issues on Windows
            "trim_file_name": 200,
            # Never leave .part files around; avoids [Errno 22] on resume attempts
            "nopart": True,
        }

        # Provide explicit FFmpeg path so merging works even when FFmpeg is not
        # on the system PATH (e.g. winget install that skips PATH registration).
        if _FFMPEG_LOCATION:
            ydl_opts["ffmpeg_location"] = _FFMPEG_LOCATION

        # Skip videos that were already downloaded in a previous run.
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
            # During the merge step, copy video and force audio to AAC so the
            # output plays everywhere (Opus/Vorbis in mp4 breaks many players).
            ydl_opts["postprocessor_args"] = {
                "merger": ["-c:v", "copy", "-c:a", "aac", "-b:a", "192k"],
            }

        info: dict | None = None

        if progress_callback:
            # GUI mode: caller owns the UI; just run the download directly.
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url)
        else:
            # CLI mode: wrap in a Rich live progress display.
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
                    # extract_info with download=True both downloads and returns
                    # the full info dict, including requested_downloads with final
                    # file paths after merging/conversion.
                    info = ydl.extract_info(url)

            self._progress = None
            self._task_id = None

        return self._collect_filepaths(info)

    # ------------------------------------------------------------------
    # yt-dlp hook callbacks
    # ------------------------------------------------------------------

    def _progress_hook(self, d: dict) -> None:
        """Called by yt-dlp on every progress update during download."""
        if self._progress is None or self._task_id is None:
            return

        status = d.get("status")

        if status == "downloading":
            fname = d.get("filename", "")

            # A new filename means a new file has started (e.g. separate
            # video+audio streams, or the next playlist entry).
            if fname and fname != self._current_filename:
                self._current_filename = fname
                title = d.get("info_dict", {}).get("title", "Downloading…")
                label = (title[:55] + "…") if len(title) > 55 else title
                self._progress.update(
                    self._task_id,
                    description=label,
                    completed=0,
                    total=None,
                )

            downloaded = d.get("downloaded_bytes") or 0
            # total_bytes is exact; total_bytes_estimate is a fallback
            total = d.get("total_bytes") or d.get("total_bytes_estimate") or None
            self._progress.update(self._task_id, completed=downloaded, total=total)

        elif status == "finished":
            # yt-dlp may run FFmpeg next (merge/convert); show a brief notice
            self._progress.update(
                self._task_id,
                description="[yellow]Processing…[/yellow]",
            )

        elif status == "error":
            self._progress.update(
                self._task_id,
                description="[red]Error — see output above[/red]",
            )

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _collect_filepaths(info: dict | None) -> list[str]:
        """Extract final saved file paths from yt-dlp's extract_info result.

        After download+postprocessing, yt-dlp populates each entry's
        requested_downloads list with the actual on-disk filepath.
        """
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
                if entry:  # None means the video was skipped/failed
                    _from_entry(entry)
        else:
            _from_entry(info)

        return paths
