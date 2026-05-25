# Deployment Guide

## Prerequisites

- Python 3.10+
- `ffmpeg` installed and on `PATH` (required by yt-dlp for audio/video merging)
- A server or cloud instance (VPS, Render, Railway, etc.)

## Environment Variables

Set these in your deployment environment:

```env
SECRET_KEY=<long-random-string>
GOOGLE_CLIENT_ID=<from-google-console>
GOOGLE_CLIENT_SECRET=<from-google-console>
FLASK_ENV=production
PORT=5000
```

Generate a strong secret key:
```bash
python -c "import secrets; print(secrets.token_hex(32))"
```

## Running with Gunicorn (Linux/macOS)

```bash
pip install gunicorn
gunicorn "run:app" --workers 2 --bind 0.0.0.0:5000
```

For production, run behind Nginx as a reverse proxy.

## Nginx Configuration

```nginx
server {
    listen 80;
    server_name yourdomain.com;

    location / {
        proxy_pass http://127.0.0.1:5000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_read_timeout 300s;
    }
}
```

Add SSL via Let's Encrypt:
```bash
sudo certbot --nginx -d yourdomain.com
```

## Docker

```dockerfile
FROM python:3.11-slim

RUN apt-get update && apt-get install -y ffmpeg && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY backend/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt gunicorn

COPY . .
RUN mkdir -p database backend/downloads backend/logs

EXPOSE 5000
CMD ["gunicorn", "run:app", "--workers", "2", "--bind", "0.0.0.0:5000"]
```

```bash
docker build -t vidflow .
docker run -p 5000:5000 \
  -e SECRET_KEY=... \
  -e GOOGLE_CLIENT_ID=... \
  -e GOOGLE_CLIENT_SECRET=... \
  -v $(pwd)/database:/app/database \
  vidflow
```

## Render / Railway

1. Connect your GitHub repository
2. Set the start command: `gunicorn run:app --workers 2 --bind 0.0.0.0:$PORT`
3. Add environment variables in the dashboard
4. Add a build step to install ffmpeg if needed (Render includes it by default)

## First-Time Setup

After deploying, create the admin account:
```bash
python backend/create_admin.py
```

Then access `/admin/login` with the credentials you set.

## File Cleanup

Downloaded files in `backend/downloads/` are served once then left on disk. Set up a cron job to clean old files:

```bash
# Delete files older than 1 hour
0 * * * * find /app/backend/downloads -type f -mmin +60 -delete
```
