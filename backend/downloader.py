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

DOWNLOAD_DIR = Path(__file__).parent / "downloads"


def _find_ffmpeg() -> str | None:
    if shutil.which("ffmpeg"):
        return None

    winget_base = Path.home() / "AppData" / "Local" / "Microsoft" / "WinGet" / "Packages"
    for candidate in sorted(winget_base.glob("Gyan.FFmpeg*"), reverse=True):
        for bin_dir in candidate.rglob("bin"):
            if (bin_dir / "ffmpeg.exe").exists():
                return str(bin_dir)

    return None


_FFMPEG_LOCATION: str | None = _find_ffmpeg()


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
    def __init__(self) -> None:
        DOWNLOAD_DIR.mkdir(parents=True, exist_ok=True)
        self._progress: Progress | None = None
        self._task_id: TaskID | None = None
        self._current_filename: str = ""

    def get_info(self, url: str) -> dict:
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
        quality = QUALITY_OPTIONS[quality_key]
        is_audio = quality_key == "6"
        self._current_filename = ""

        base_dir = output_dir or DOWNLOAD_DIR
        base_dir.mkdir(parents=True, exist_ok=True)

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
            ydl_opts["postprocessor_args"] = {
                "merger": ["-c:v", "copy", "-c:a", "aac", "-b:a", "192k"],
            }

        info: dict | None = None

        if progress_callback:
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
        if self._progress is None or self._task_id is None:
            return

        status = d.get("status")

        if status == "downloading":
            fname = d.get("filename", "")

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
            total = d.get("total_bytes") or d.get("total_bytes_estimate") or None
            self._progress.update(self._task_id, completed=downloaded, total=total)

        elif status == "finished":
            self._progress.update(
                self._task_id,
                description="[yellow]Processing…[/yellow]",
            )

        elif status == "error":
            self._progress.update(
                self._task_id,
                description="[red]Error — see output above[/red]",
            )

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
