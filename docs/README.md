# VidFlow

A Flask-based video downloader web application supporting YouTube, Instagram, TikTok, Facebook, Twitter, and Vimeo.

## Features

- Download videos in multiple quality levels (audio-only through 4K)
- Playlist support with per-video progress tracking
- Google OAuth login with per-user download history
- Guest mode — full download functionality without an account
- Admin panel with dashboard, user management, download logs, and statistics
- Dark/light theme with persistent preference
- Maintenance mode toggle from the admin panel

## Project Structure

```
youtube-downloader/
├── backend/
│   ├── app.py              # Flask application factory
│   ├── config.py           # Configuration classes + user prefs
│   ├── models.py           # SQLAlchemy models (User, Download, Admin)
│   ├── downloader.py       # yt-dlp wrapper (VideoDownloader)
│   ├── create_admin.py     # CLI script to create the first admin
│   ├── requirements.txt
│   ├── routes/
│   │   ├── main.py         # /, /info, /config
│   │   ├── api.py          # /start, /progress, /download, /api/history
│   │   ├── auth.py         # /login, /auth/google, /logout
│   │   └── admin.py        # /admin/* routes
│   └── utils/
│       ├── platform_detector.py
│       ├── progress_tracker.py
│       └── error_handler.py
├── frontend/
│   ├── templates/
│   │   ├── index.html
│   │   ├── login.html
│   │   ├── maintenance.html
│   │   └── admin/
│   └── static/
│       ├── css/
│       │   ├── main.css
│       │   ├── auth.css
│       │   └── admin.css
│       ├── js/
│       │   ├── utils.js
│       │   ├── downloader.js
│       │   ├── main.js
│       │   └── admin.js
│       └── assets/
│           └── favicon.svg
├── database/               # SQLite database (gitignored)
├── docs/
├── run.py                  # Entry point
└── .gitignore
```

## Quick Start

```bash
# 1. Create and activate a virtual environment
python -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate

# 2. Install dependencies
pip install -r backend/requirements.txt

# 3. Set environment variables (copy from .env.example)
cp .env.example .env
# Edit .env with your GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET

# 4. Create the first admin account
python backend/create_admin.py

# 5. Run the development server
python run.py
```

The app will be available at `http://localhost:5000`.

## Environment Variables

| Variable | Description |
|---|---|
| `SECRET_KEY` | Flask secret key (required in production) |
| `GOOGLE_CLIENT_ID` | Google OAuth client ID |
| `GOOGLE_CLIENT_SECRET` | Google OAuth client secret |
| `FLASK_ENV` | `development` or `production` (default: `development`) |
| `PORT` | Server port (default: `5000`) |

## Admin Panel

Access at `/admin/login`. Create the initial admin with:

```bash
python backend/create_admin.py
```

See [GOOGLE_SETUP.md](GOOGLE_SETUP.md) for OAuth configuration.
See [DEPLOYMENT.md](DEPLOYMENT.md) for production deployment.
