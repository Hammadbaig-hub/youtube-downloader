# YouTube Downloader

A clean command-line YouTube downloader built with [yt-dlp](https://github.com/yt-dlp/yt-dlp) and [Rich](https://github.com/Textualize/rich).

## Features

- Download single videos or entire playlists
- Six quality presets: Best, 1080p, 720p, 480p, 360p, Audio-only MP3
- Real-time progress bar with download speed and ETA
- Files organised under `./downloads/` (playlists get their own subfolder)
- Friendly error messages for private videos, bad URLs, missing FFmpeg, etc.

## Requirements

| Requirement | Version |
|-------------|---------|
| Python | 3.10+ |
| FFmpeg | any recent |

> **FFmpeg is required** for merging separate video+audio streams (qualities 1–3)
> and for MP3 conversion (quality 6). It is not needed for 480p/360p if those
> resolutions are available as a single pre-muxed file on YouTube.

## Installation

### 1. Install FFmpeg

| OS | Command |
|----|---------|
| Windows | `winget install ffmpeg` |
| macOS | `brew install ffmpeg` |
| Debian/Ubuntu | `sudo apt install ffmpeg` |
| Fedora | `sudo dnf install ffmpeg` |

After installation verify with: `ffmpeg -version`

### 2. Install Python dependencies

```bash
pip install -r requirements.txt
```

## Usage

```bash
python main.py
```

Follow the interactive prompts:

```
Enter YouTube URL: https://www.youtube.com/watch?v=dQw4w9WgXcQ

  Video Info
  Title     Never Gonna Give You Up
  Channel   Rick Astley
  Duration  3:32
  Views     1,234,567,890

  Quality Options
  #   Quality
  1   Best Quality (auto)
  2   1080p HD
  3   720p HD
  4   480p
  5   360p
  6   Audio Only (MP3)

Select quality [1]: 2

Starting download…

  Never Gonna Give You Up  ████████████  45.2 MB  12.3 MB/s  0:00:03

Download complete!
Save location: C:\...\downloads

  Downloaded Files
  Filename               Size
  Never Gonna Give...    89.4 MB
```

## Quality Options

| # | Quality | Notes |
|---|---------|-------|
| 1 | Best Quality (auto) | Highest resolution available — requires FFmpeg |
| 2 | 1080p HD | Full HD — requires FFmpeg |
| 3 | 720p HD | HD — requires FFmpeg |
| 4 | 480p | Standard definition |
| 5 | 360p | Low definition |
| 6 | Audio Only (MP3) | 192 kbps MP3 — requires FFmpeg |

## File Organisation

```
downloads/
├── Some Video Title.mp4          ← single video
└── My Playlist Name/
    ├── 01 - First Video.mp4      ← playlist entries
    ├── 02 - Second Video.mp4
    └── 03 - Third Video.mp3      ← audio-only
```

## Project Structure

```
youtube-downloader/
├── main.py          # CLI entry point — UI, prompts, error handling
├── downloader.py    # VideoDownloader class — yt-dlp logic & progress hooks
├── requirements.txt # Python dependencies
└── README.md
```

## Common Errors

| Error | Fix |
|-------|-----|
| `FFmpeg not found` | Install FFmpeg and add it to your PATH |
| `Video unavailable` | The video was deleted or is region-blocked |
| `Private video` | Cannot download private videos |
| `Invalid URL` | Make sure the URL is a YouTube video or playlist link |
| Network error | Check your internet connection |
