# 🎬 NovaDL — All-in-One Video Downloader

**Paste a link → pick a quality → download.** A web app + Telegram bot powered by **yt-dlp**, with a self-updating engine so it keeps working as platforms change.

Two **independent** parts in a **single repo**:

| Part | What it does | How it runs |
|------|-------------|-------------|
| **Web app** (`app.py` + `web/`) | Paste a URL, see thumbnail/title/qualities, download with progress | Flask + gunicorn (Render web service) |
| **Telegram bot** (`bot.py`) | Send a link → inline quality keyboard → uploads the file to Telegram | Long polling (Render background worker) |

The web app and bot are **decoupled** — they share only the `engine` (yt-dlp wrapper) and `config` modules, and neither needs the other to run.

---

## ✨ Features

- **yt-dlp engine** — fetch metadata, list formats, download video/audio streams
- **Smart format list** — deduplicated quality ladder (video heights) + audio-only options
- **ffmpeg merging** — combines best-video + best-audio into a single `.mp4`, converts audio to `.mp3`
- **Self-update system** — upgrades `yt-dlp` at startup **and** on a configurable interval via a background thread
- **Beautiful animated web UI** — gradient/particles, glassmorphism, progress bar, no build step
- **Telegram bot** — inline keyboard quality selection, thumbnail preview, direct file upload
- **Docker + ffmpeg** — reproducible deployment with media codecs preinstalled

---

## 🔄 Self-update (critical)

yt-dlp breaks when video platforms change their code, so NovaDL never relies on a fixed version:

1. **Startup upgrade** — a background thread runs `pip install -U yt-dlp` on boot.
2. **Periodic upgrade** — a daemon thread re-checks/upgrades at a set interval (`YTDLP_UPDATE_INTERVAL`, default **86400s = daily**).

Check the current version via `GET /api/status` (web) or `/status` (bot).

---

## 🗂️ Layout

```
NovaDL/
├── app.py               # Flask web app + download API
├── bot.py               # Telegram bot (LONG POLLING)
├── engine.py            # yt-dlp wrapper + self-updater
├── config.py            # env config (no hardcoded secrets)
├── web/                 # animated single-page UI
├── requirements.txt
├── Dockerfile           # python + ffmpeg
├── render.yaml          # Render blueprint (web + worker)
└── .env.example
```

---

## 🚦 Deploy to Render

Use the **Blueprint** (`render.yaml`) to create both services:

1. Push this repo to GitHub.
2. Render → **New → Blueprint** → connect repo.
3. It creates `novadl-web` (web) and `novadl-bot` (worker).
4. Set the **`BOT_TOKEN`** env var (secret) on both services.

The Docker image installs **ffmpeg** automatically (needed for merging/audio conversion).

---

## 🔧 Local development

```bash
pip install -r requirements.txt
# (recommended: also install ffmpeg via your system package manager)

cp .env.example .env          # fill in BOT_TOKEN

# web
gunicorn app:app --bind 0.0.0.0:10000

# bot (separate terminal)
python bot.py                 # long polling
```

---

## 🌐 API (web)

| Method | Path | Description |
|--------|------|-------------|
| GET | `/health` | service health + yt-dlp version |
| GET | `/api/info?url=` | fetch title/thumbnail/duration/formats |
| POST | `/api/download` | `{url, format_id, kind}` → returns `job_id` |
| GET | `/api/file/<job_id>` | stream the downloaded file |
| GET | `/api/status` | updater/version status |

---

## 🛡️ Notes

- The bot **does not use a webhook** — it polls Telegram continuously.
- Large files > 50 MB cannot be uploaded via the Telegram Bot API; the bot tells the user to lower quality or use the web app.
- `ALLOWED_USERS` (comma-separated ids) optionally restricts bot access; empty = open.

Built with ♥ — NovaDL.
