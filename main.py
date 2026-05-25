"""
main.py — YouTube Downloader CLI.

Entry point: run with `python main.py`.
Prompts for a URL, shows video/playlist info, lets the user pick quality,
downloads with a live progress bar, and reports the saved file locations.
"""

import sys
import argparse
from pathlib import Path

import yt_dlp
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from downloader import DOWNLOAD_DIR, QUALITY_OPTIONS, VideoDownloader

console = Console()


# ---------------------------------------------------------------------------
# UI helpers
# ---------------------------------------------------------------------------

def print_banner() -> None:
    console.print(
        Panel.fit(
            "[bold yellow]  YouTube Downloader  [/bold yellow]\n"
            "[dim]       powered by yt-dlp       [/dim]",
            border_style="yellow",
            padding=(1, 6),
        )
    )


def show_video_info(info: dict) -> None:
    duration = int(info.get("duration") or 0)
    mins, secs = divmod(duration, 60)
    view_count = info.get("view_count")

    table = Table(box=None, show_header=False, padding=(0, 2))
    table.add_column("key", style="bold cyan", min_width=12)
    table.add_column("val", style="white")

    table.add_row("Title",    info.get("title", "Unknown"))
    table.add_row("Channel",  info.get("uploader", "Unknown"))
    table.add_row("Duration", f"{mins}:{secs:02d}" if duration else "Unknown")
    table.add_row("Views",    f"{view_count:,}" if view_count else "N/A")

    console.print(Panel(table, title="[bold]Video Info[/bold]", border_style="green"))


def show_playlist_info(info: dict, video_count: int) -> None:
    table = Table(box=None, show_header=False, padding=(0, 2))
    table.add_column("key", style="bold cyan", min_width=12)
    table.add_column("val", style="white")

    table.add_row("Playlist", info.get("title", "Unknown"))
    table.add_row("Channel",  info.get("uploader", "Unknown"))
    table.add_row("Videos",   str(video_count))

    console.print(Panel(table, title="[bold]Playlist Detected[/bold]", border_style="blue"))


def choose_quality() -> str:
    """Render the quality menu and return the user's choice key."""
    table = Table(title="Quality Options", border_style="cyan", min_width=44)
    table.add_column("#", style="bold yellow", width=4)
    table.add_column("Quality", style="white")

    for key, opt in QUALITY_OPTIONS.items():
        table.add_row(key, opt["name"])

    console.print(table)

    valid = list(QUALITY_OPTIONS.keys())
    while True:
        console.print(f"\n[bold]Select quality[/bold] [dim]({valid[0]}–{valid[-1]}, default=1):[/dim] ", end="")
        choice = input().strip() or "1"
        if choice in valid:
            return choice
        console.print(f"[yellow]Please enter a number between {valid[0]} and {valid[-1]}.[/yellow]")


def show_results(saved_files: list[str]) -> None:
    """Print a summary table of downloaded files with sizes."""
    console.print()
    console.print("[bold green]Download complete![/bold green]")
    console.print(f"[dim]Save location:[/dim] {DOWNLOAD_DIR.resolve()}\n")

    if not saved_files:
        console.print(
            "[yellow]No file paths were returned by yt-dlp.\n"
            "Check the downloads/ folder manually.[/yellow]"
        )
        return

    table = Table(title="Downloaded Files", border_style="green", min_width=60)
    table.add_column("Filename",  style="white", no_wrap=False)
    table.add_column("Size",      style="cyan",  justify="right", width=10)

    for fp in saved_files:
        path = Path(fp)
        if path.exists():
            size_mb = path.stat().st_size / (1024 * 1024)
            table.add_row(path.name, f"{size_mb:.1f} MB")
        else:
            # File may not exist yet if yt-dlp is still finalising (rare)
            table.add_row(path.name, "—")

    console.print(table)


# ---------------------------------------------------------------------------
# Error handling
# ---------------------------------------------------------------------------

def handle_error(exc: Exception) -> None:
    """Map yt-dlp/network exceptions to friendly one-liners, then exit."""
    msg = str(exc)

    if "Private video" in msg or "private" in msg.lower():
        console.print("[red]Error: This video is private and cannot be downloaded.[/red]")
    elif "Video unavailable" in msg or "unavailable" in msg.lower():
        console.print("[red]Error: Video unavailable (deleted, region-blocked, or age-restricted).[/red]")
    elif "is not a valid URL" in msg or "Unable to extract" in msg or "Unsupported URL" in msg:
        console.print("[red]Error: Invalid or unsupported URL. Please enter a YouTube video or playlist URL.[/red]")
    elif "Sign in" in msg or "login" in msg.lower():
        console.print("[red]Error: This video requires sign-in. Age-restricted content cannot be downloaded without cookies.[/red]")
    elif "Network" in type(exc).__name__ or "URLError" in type(exc).__name__ or "ConnectionError" in type(exc).__name__:
        console.print("[red]Error: Network error. Check your internet connection and try again.[/red]")
    elif "ffmpeg" in msg.lower() or "ffprobe" in msg.lower():
        console.print(
            "[red]Error: FFmpeg not found.[/red]\n"
            "[dim]Install FFmpeg and add it to PATH:\n"
            "  Windows: winget install ffmpeg\n"
            "  macOS:   brew install ffmpeg\n"
            "  Linux:   sudo apt install ffmpeg[/dim]"
        )
    else:
        console.print(f"[red]Error: {exc}[/red]")

    sys.exit(1)


# ---------------------------------------------------------------------------
# Main flow
# ---------------------------------------------------------------------------

def main() -> None:
    # Accept an optional URL directly on the command line:  python main.py <url>
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("url", nargs="?", default=None)
    args, _ = parser.parse_known_args()

    print_banner()

    # ── 1. Get URL ──────────────────────────────────────────────────────────
    if args.url:
        url = args.url.strip()
        console.print(f"\n[dim]URL:[/dim] {url}")
    else:
        # Rich's Prompt.ask silently fails in some Windows terminals, so we
        # print the styled prompt ourselves and use plain input() to block.
        while True:
            console.print("\n[bold cyan]Enter YouTube URL:[/bold cyan] ", end="")
            url = input().strip()
            if url:
                break
            console.print("[yellow]Please enter a URL.[/yellow]")

    downloader = VideoDownloader()

    # ── 2. Fetch metadata (fast — no actual download) ───────────────────────
    console.print()
    with console.status("[dim]Fetching video information…[/dim]", spinner="dots"):
        try:
            info = downloader.get_info(url)
        except yt_dlp.utils.DownloadError as exc:
            handle_error(exc)
        except Exception as exc:
            handle_error(exc)

    # ── 3. Show info & playlist prompt ──────────────────────────────────────
    is_playlist = info.get("_type") == "playlist"
    download_playlist = False

    if is_playlist:
        # entries is a generator with extract_flat — consume it once
        entries = list(info.get("entries") or [])
        show_playlist_info(info, len(entries))
        console.print("\n[bold]Download entire playlist?[/bold] [dim][Y/n]:[/dim] ", end="")
        answer = input().strip().lower()
        download_playlist = answer not in ("n", "no")
        if not download_playlist:
            console.print("[dim]Will download only the first/featured video.[/dim]")
    else:
        show_video_info(info)

    # ── 4. Quality selection ─────────────────────────────────────────────────
    console.print()
    quality_key = choose_quality()

    # ── 5. Download ──────────────────────────────────────────────────────────
    console.print(f"\n[bold green]Starting download…[/bold green]\n")

    try:
        saved_files = downloader.download(url, quality_key, is_playlist=download_playlist)
    except KeyboardInterrupt:
        console.print("\n[yellow]Download cancelled.[/yellow]")
        sys.exit(0)
    except yt_dlp.utils.DownloadError as exc:
        handle_error(exc)
    except Exception as exc:
        handle_error(exc)

    # ── 6. Report results ────────────────────────────────────────────────────
    show_results(saved_files)


if __name__ == "__main__":
    main()
