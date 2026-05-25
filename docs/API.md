# VidFlow API Reference

All API endpoints accept and return JSON unless noted otherwise.

---

## POST `/info`

Fetch metadata for a URL without starting a download.

**Request**
```json
{ "url": "https://www.youtube.com/watch?v=..." }
```

**Response (video)**
```json
{
  "type": "video",
  "title": "Video Title",
  "uploader": "Channel Name",
  "duration": 243,
  "thumbnail": "https://..."
}
```

**Response (playlist)**
```json
{
  "type": "playlist",
  "title": "Playlist Title",
  "uploader": "Channel Name",
  "count": 12
}
```

**Error**
```json
{ "error": "Could not fetch info" }
```

---

## POST `/start`

Start a background download job.

**Request**
```json
{
  "url": "https://...",
  "quality": "1",
  "is_playlist": false,
  "playlist_count": 0
}
```

Quality keys: `"0"` = audio only, `"1"` = best, `"2"` = 1080p, `"3"` = 720p, `"4"` = 480p, `"5"` = 360p, `"6"` = 4K.

**Response**
```json
{ "job_id": "abc123" }
```

---

## GET `/progress/<job_id>`

Poll the status of a running or completed download.

**Response (downloading)**
```json
{
  "status": "downloading",
  "percent": 42.5,
  "speed": "3.2 MiB/s",
  "eta": "0:00:18",
  "size": "45.2 MiB",
  "title": "Video Title",
  "is_playlist": false
}
```

**Response (done)**
```json
{
  "status": "done",
  "title": "Video Title",
  "is_playlist": false,
  "files": ["/path/to/file.mp4"]
}
```

**Response (error)**
```json
{
  "status": "error",
  "error": "Private video or age-restricted content"
}
```

Status values: `starting`, `downloading`, `processing`, `done`, `error`.

---

## GET `/download/<job_id>`

Stream the completed file to the browser as a download attachment.

Returns `404` if the job doesn't exist or the file was already served/cleaned up.

---

## GET `/config`

Get current user preferences.

**Response**
```json
{
  "theme": "dark",
  "default_quality": "1",
  "download_dir": ""
}
```

---

## POST `/config`

Save user preferences.

**Request** (all fields optional)
```json
{
  "theme": "light",
  "default_quality": "2",
  "download_dir": "/home/user/Videos"
}
```

**Response**
```json
{ "ok": true }
```

---

## GET `/api/history`

Returns the authenticated user's download history (requires login).

**Response**
```json
[
  {
    "id": 1,
    "title": "Video Title",
    "quality": "1080p",
    "platform": "YouTube",
    "date": "2024-01-15T14:23:00"
  }
]
```

---

## DELETE `/api/history/<record_id>`

Delete a single history record for the authenticated user.

**Response**
```json
{ "ok": true }
```

---

## Admin API

### GET `/admin/stats/json`

Returns aggregated stats for charts. Query param: `days` (default: `30`).

**Response**
```json
{
  "daily": [{ "date": "2024-01-15", "count": 5 }],
  "platforms": [{ "platform": "YouTube", "count": 42 }],
  "top_users": [{ "name": "Alice", "count": 18 }]
}
```
