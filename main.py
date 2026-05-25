"""
main.py — YouTube Downloader CLI.

Entry point: run with `python main.py`.
Prompts for a URL, shows video/playlist info, lets the user pick quality,
downloads with a live progress bar, and reports the saved file locations.

Flags:
  python main.py <url>     pass URL directly
  python main.py --config  open settings wizard
"""

import sys
import argparse
from pathlib import Path

import yt_dlp
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

import config as _config
from downloader import QUALITY_OPTIONS, VideoDownloader

console = Console()


# ---------------------------------------------------------------------------
# Config helpers
# ---------------------------------------------------------------------------

def show_config(cfg: dict) -> None:
    """Print current settings in a Rich panel."""
    table = Table(box=None, show_header=False, padding=(0, 2))
    table.add_column("key", style="bold cyan", min_width=18)
    table.add_column("val", style="white")

    quality_name = QUALITY_OPTIONS.get(cfg["default_quality"], {}).get("name", cfg["default_quality"])
    table.add_row("Download folder", cfg["download_dir"])
    table.add_row("Default quality", quality_name)
    table.add_row("Theme",           cfg["theme"].capitalize())

    console.print(Panel(table, title="[bold]Current Settings[/bold]", border_style="cyan"))


def _ask(prompt: str, current: str = "") -> str:
    """Print a styled prompt and return stripped input (empty = keep current)."""
    hint = f" [dim][{current}][/dim]" if current else ""
    console.print(f"\n[bold cyan]{prompt}[/bold cyan]{hint}: ", end="")
    return input().strip()


def _pick_quality(current: str = "1") -> str:
    """Show the quality table and return a valid key, defaulting to current."""
    table = Table(title="Quality Options", border_style="cyan", min_width=44)
    table.add_column("#", style="bold yellow", width=4)
    table.add_column("Quality", style="white")
    for key, opt in QUALITY_OPTIONS.items():
        marker = " [green]← current[/green]" if key == current else ""
        table.add_row(key, opt["name"] + marker)
    console.print(table)

    valid = list(QUALITY_OPTIONS.keys())
    console.print(f"\n[bold cyan]Default quality[/bold cyan] [dim][{current}]:[/dim] ", end="")
    choice = input().strip() or current
    return choice if choice in valid else current


def first_run_setup() -> dict:
    """Interactive first-run wizard. Returns the saved config dict."""
    console.print(
        Panel.fit(
            "[bold yellow]  Welcome — First Run Setup  [/bold yellow]\n"
            "[dim]  Configure your preferences once and they'll be saved  [/dim]",
            border_style="yellow",
            padding=(1, 4),
        )
    )

    cfg = dict(_config.DEFAULTS)

    # Download folder
    d = _ask("Download folder", cfg["download_dir"])
    if d:
        cfg["download_dir"] = str(Path(d).expanduser().resolve())

    # Default quality
    cfg["default_quality"] = _pick_quality(cfg["default_quality"])

    # Theme (applies to the web UI)
    console.print(f"\n[bold cyan]Web UI theme[/bold cyan] [dim](dark/light) [{cfg['theme']}]:[/dim] ", end="")
    t = input().strip().lower()
    if t in ("dark", "light"):
        cfg["theme"] = t

    _config.save(cfg)
    console.print("\n[bold green]✓ Preferences saved to config.json[/bold green]")
    return cfg


def run_config_wizard() -> None:
    """Show current settings, then let the user update any of them."""
    cfg = _config.load()

    console.print(
        Panel.fit(
            "[bold yellow]  Settings[/bold yellow]",
            border_style="yellow",
            padding=(0, 4),
        )
    )
    show_config(cfg)
    console.print("\n[dim]Press Enter to keep the current value for any setting.[/dim]")

    # Download folder
    d = _ask("Download folder", cfg["download_dir"])
    if d:
        resolved = Path(d).expanduser().resolve()
        cfg["download_dir"] = str(resolved)

    # Default quality
    cfg["default_quality"] = _pick_quality(cfg["default_quality"])

    # Theme
    console.print(f"\n[bold cyan]Web UI theme[/bold cyan] [dim](dark/light) [{cfg['theme']}]:[/dim] ", end="")
    t = input().strip().lower()
    if t in ("dark", "light"):
        cfg["theme"] = t

    _config.save(cfg)
    console.print("\n[bold green]✓ Settings updated.[/bold green]")
    show_config(cfg)


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


def choose_quality(default: str = "1") -> str:
    """Render the quality menu and return the user's choice key."""
    table = Table(title="Quality Options", border_style="cyan", min_width=44)
    table.add_column("#", style="bold yellow", width=4)
    table.add_column("Quality", style="white")

    for key, opt in QUALITY_OPTIONS.items():
        marker = " [green]← default[/green]" if key == default else ""
        table.add_row(key, opt["name"] + marker)

    console.print(table)

    valid = list(QUALITY_OPTIONS.keys())
    while True:
        console.print(f"\n[bold]Select quality[/bold] [dim](default={default}):[/dim] ", end="")
        choice = input().strip() or default
        if choice in valid:
            return choice
        console.print(f"[yellow]Please enter a number between {valid[0]} and {valid[-1]}.[/yellow]")


def show_results(saved_files: list[str], output_dir: Path) -> None:
    console.print()
    console.print("[bold green]Download complete![/bold green]")
    console.print(f"[dim]Save location:[/dim] {output_dir.resolve()}\n")

    if not saved_files:
        console.print(
            "[yellow]No file paths returned by yt-dlp.\n"
            "Check the downloads folder manually.[/yellow]"
        )
        return

    table = Table(title="Downloaded Files", border_style="green", min_width=60)
    table.add_column("Filename", style="white", no_wrap=False)
    table.add_column("Size",     style="cyan",  justify="right", width=10)

    for fp in saved_files:
        path = Path(fp)
        if path.exists():
            size_mb = path.stat().st_size / (1024 * 1024)
            table.add_row(path.name, f"{size_mb:.1f} MB")
        else:
            table.add_row(path.name, "—")

    console.print(table)


# ---------------------------------------------------------------------------
# Error handling
# ---------------------------------------------------------------------------

def handle_error(exc: Exception) -> None:
    msg = str(exc)

    if "Private video" in msg or "private" in msg.lower():
        console.print("[red]Error: This video is private and cannot be downloaded.[/red]")
    elif "Video unavailable" in msg or "unavailable" in msg.lower():
        console.print("[red]Error: Video unavailable (deleted, region-blocked, or age-restricted).[/red]")
    elif "is not a valid URL" in msg or "Unable to extract" in msg or "Unsupported URL" in msg:
        console.print("[red]Error: Invalid or unsupported URL.[/red]")
    elif "Sign in" in msg or "login" in msg.lower():
        console.print("[red]Error: This video requires sign-in.[/red]")
    elif "Network" in type(exc).__name__ or "URLError" in type(exc).__name__:
        console.print("[red]Error: Network error. Check your connection.[/red]")
    elif "ffmpeg" in msg.lower() or "ffprobe" in msg.lower():
        console.print(
            "[red]Error: FFmpeg not found.[/red]\n"
            "[dim]Install: winget install ffmpeg[/dim]"
        )
    else:
        console.print(f"[red]Error: {exc}[/red]")

    sys.exit(1)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("url",      nargs="?", default=None,  help="YouTube URL")
    parser.add_argument("--config", action="store_true",      help="Update saved settings")
    args, _ = parser.parse_known_args()

    print_banner()

    # ── Settings wizard ──────────────────────────────────────────────────────
    if args.config:
        run_config_wizard()
        return

    # ── Load / first-run setup ───────────────────────────────────────────────
    if _config.is_first_run():
        cfg = first_run_setup()
        console.print()
    else:
        cfg = _config.load()
        show_config(cfg)

    output_dir   = Path(cfg["download_dir"])
    default_qual = cfg["default_quality"]

    # ── Get URL ──────────────────────────────────────────────────────────────
    if args.url:
        url = args.url.strip()
        console.print(f"\n[dim]URL:[/dim] {url}")
    else:
        while True:
            console.print("\n[bold cyan]Enter YouTube URL:[/bold cyan] ", end="")
            url = input().strip()
            if url:
                break
            console.print("[yellow]Please enter a URL.[/yellow]")

    downloader = VideoDownloader()

    # ── Fetch metadata ───────────────────────────────────────────────────────
    console.print()
    with console.status("[dim]Fetching video information…[/dim]", spinner="dots"):
        try:
            info = downloader.get_info(url)
        except yt_dlp.utils.DownloadError as exc:
            handle_error(exc)
        except Exception as exc:
            handle_error(exc)

    # ── Show info & playlist prompt ──────────────────────────────────────────
    is_playlist      = info.get("_type") == "playlist"
    download_playlist = False

    if is_playlist:
        entries = list(info.get("entries") or [])
        show_playlist_info(info, len(entries))
        console.print("\n[bold]Download entire playlist?[/bold] [dim][Y/n]:[/dim] ", end="")
        answer = input().strip().lower()
        download_playlist = answer not in ("n", "no")
        if not download_playlist:
            console.print("[dim]Will download only the first/featured video.[/dim]")
    else:
        show_video_info(info)

    # ── Quality selection ────────────────────────────────────────────────────
    console.print()
    quality_key = choose_quality(default=default_qual)

    # ── Download ─────────────────────────────────────────────────────────────
    console.print(f"\n[bold green]Starting download…[/bold green]\n")

    try:
        saved_files = downloader.download(
            url, quality_key,
            is_playlist=download_playlist,
            output_dir=output_dir,
        )
    except KeyboardInterrupt:
        console.print("\n[yellow]Download cancelled.[/yellow]")
        sys.exit(0)
    except yt_dlp.utils.DownloadError as exc:
        handle_error(exc)
    except Exception as exc:
        handle_error(exc)

    # ── Results ──────────────────────────────────────────────────────────────
    show_results(saved_files, output_dir)


if __name__ == "__main__":
    main()
