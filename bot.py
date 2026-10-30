# -*- coding: utf-8 -*-
"""NovaDL — Telegram bot (LONG POLLING, decoupled from the web app)."""
import os
import sys
import time
import threading
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import telebot
from telebot import types

import config
import engine

TOKEN = os.environ.get("BOT_TOKEN", "")
if not TOKEN:
    print("WARNING: BOT_TOKEN not set — bot disabled until configured.")
    bot = telebot.TeleBot("0:placeholder")
else:
    bot = telebot.TeleBot(TOKEN)

MAX_UPLOAD = 50 * 1024 * 1024

_info_cache = {}


def _esc(s) -> str:
    return str(s).replace("_", "\\_").replace("*", "\\*").replace("`", "\\`").replace("[", "\\[")


def _name(user) -> str:
    if user.username:
        return f"@{user.username}"
    if user.first_name:
        return user.first_name
    return str(user.id)


def _allowed(uid: int) -> bool:
    allowed = config.get_allowed_users()
    if not allowed:
        return True
    return uid in allowed or config.is_owner(uid)


@bot.message_handler(commands=["start"])
def cmd_start(message):
    uid = message.from_user.id
    if not _allowed(uid):
        bot.reply_to(message, "⛔ Access denied.")
        return
    text = (
        f"👋 Welcome, {_esc(_name(message.from_user))}!\n\n"
        f"🎬 **{config.APP_NAME}** — {config.APP_TAGLINE}\n\n"
        f"Just **send me any video link** and I'll fetch the video, show the available qualities, "
        f"and upload the file straight to Telegram.\n\nTry `/help` for more."
    )
    bot.send_message(message.chat.id, text, parse_mode="Markdown")


@bot.message_handler(commands=["help"])
def cmd_help(message):
    text = (
        "🎬 **NovaDL — Help**\n\n"
        "1️⃣ Send a video link.\n"
        "2️⃣ Pick a quality from the inline keyboard.\n"
        "3️⃣ Wait while I download & upload it to you.\n\n"
        "`/start` — start menu\n`/help` — this help\n`/status` — yt-dlp version / updater info"
    )
    bot.send_message(message.chat.id, text, parse_mode="Markdown")


@bot.message_handler(commands=["status"])
def cmd_status(message):
    s = engine.update_status()
    text = (
        "🛠️ **Status**\n\n"
        f"yt-dlp: `{_esc(s['ytdlp_version'])}`\n"
        f"Updater: {'✅ running' if s['updater_running'] else '⏸ idle'}\n"
        f"Interval: {int(s['update_interval'])}s"
    )
    bot.send_message(message.chat.id, text, parse_mode="Markdown")


@bot.message_handler(func=lambda m: m.chat.type == "private")
def on_private(message):
    uid = message.from_user.id
    if not _allowed(uid):
        bot.reply_to(message, "⛔ Access denied.")
        return
    url = (message.text or "").strip()
    if not engine.is_valid_url(url):
        bot.reply_to(message, "🔗 Please send a valid video link (http/https).")
        return
    process_link(message, url)


def process_link(message, url):
    chat_id = message.chat.id
    busy = bot.send_message(chat_id, "🔍 Processing your link…")
    try:
        info = engine.fetch_info(url)
    except Exception as e:
        bot.edit_message_text(f"❌ Could not fetch video: {_esc(str(e))}", chat_id, busy.message_id)
        return

    _info_cache[chat_id] = {"url": url, "formats": info.get("formats", [])}
    formats = info.get("formats", [])
    if not formats:
        bot.edit_message_text("⚠️ No downloadable formats found for this link.", chat_id, busy.message_id)
        return

    title = info.get("title", "video")
    uploader = info.get("uploader", "")
    duration = info.get("duration", 0)
    thumb = info.get("thumbnail", "")

    dur = f"{int(duration)//60}:{int(duration)%60:02d}" if duration else "?"
    caption = (
        f"🎬 **{_esc(title)}**\n"
        + (f"👤 {_esc(uploader)}\n" if uploader else "")
        + f"⏱ {dur}\n\n_Choose a quality:_"
    )
    kb = quality_kb(formats)

    try:
        if thumb and thumb.startswith("http"):
            bot.send_photo(chat_id, thumb, caption=caption, parse_mode="Markdown", reply_markup=kb)
            bot.delete_message(chat_id, busy.message_id)
        else:
            bot.edit_message_text(caption, chat_id, busy.message_id, parse_mode="Markdown", reply_markup=kb)
    except Exception:
        try:
            bot.edit_message_text(caption, chat_id, busy.message_id, parse_mode="Markdown", reply_markup=kb)
        except Exception:
            bot.send_message(chat_id, caption, parse_mode="Markdown", reply_markup=kb)


def quality_kb(formats):
    kb = types.InlineKeyboardMarkup(row_width=2)
    buttons = []
    for f in formats:
        fid = f.get("format_id", "")
        kind = f.get("kind", "video")
        label = f.get("label", fid)
        cb = f"dl:{kind}:{fid}"
        buttons.append(types.InlineKeyboardButton(f"▶️ {label}" if kind == "video" else f"🎵 {label}", callback_data=cb))
    for i in range(0, len(buttons), 2):
        kb.add(*buttons[i:i + 2])
    kb.add(types.InlineKeyboardButton("🔙 Cancel", callback_data="cancel"))
    return kb


@bot.callback_query_handler(func=lambda c: True)
def on_callback(call):
    data = call.data or ""
    chat_id = call.message.chat.id
    uid = call.from_user.id

    if data == "cancel":
        bot.answer_callback_query(call.id, "Cancelled")
        try:
            bot.edit_message_text("❌ Cancelled.", chat_id, call.message.message_id)
        except Exception:
            pass
        return

    if not data.startswith("dl:"):
        bot.answer_callback_query(call.id, "Unrecognized action")
        return

    _, kind, format_id = data.split(":", 2)
    cached = _info_cache.get(chat_id)
    if not cached:
        bot.answer_callback_query(call.id, "Session expired — send the link again.", show_alert=True)
        return

    url = cached["url"]
    bot.answer_callback_query(call.id)

    busy = bot.send_message(chat_id, "⬇️ Downloading…")
    job_dir = config.DOWNLOAD_DIR / f"bot_{uid}_{int(time.time())}"
    job_dir.mkdir(parents=True, exist_ok=True)

    try:
        result = engine.download(url, format_id, kind, str(job_dir))
        if "error" in result:
            bot.edit_message_text(f"❌ Download failed: {_esc(result['error'])}", chat_id, busy.message_id)
            return
        path = Path(result["path"])
        size = path.stat().st_size
        if size > MAX_UPLOAD:
            bot.edit_message_text(
                f"⚠️ File is {_human(size)} — larger than Telegram's 50 MB limit. Try a lower quality or use the web app.",
                chat_id, busy.message_id,
            )
            return
        with open(path, "rb") as f:
            if kind == "audio":
                bot.send_audio(chat_id, f, caption=f"🎵 {_esc(result.get('title', 'audio'))}", timeout=120)
            else:
                bot.send_video(chat_id, f, caption=f"🎬 {_esc(result.get('title', 'video'))}", timeout=120)
        bot.edit_message_text("✅ Upload complete!", chat_id, busy.message_id)
        bot.delete_message(chat_id, busy.message_id)
    except Exception as e:
        try:
            bot.edit_message_text(f"❌ Error: {_esc(str(e))}", chat_id, busy.message_id)
        except Exception:
            pass
    finally:
        try:
            import shutil
            shutil.rmtree(job_dir, ignore_errors=True)
        except Exception:
            pass


def _human(n):
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024 or unit == "GB":
            return f"{n:.1f} {unit}"
        n /= 1024
    return f"{n:.1f} GB"


def main():
    threading.Thread(target=engine.run_startup_upgrade, daemon=True).start()
    engine.start_updater()
    print("[bot] starting long polling…")
    bot.remove_webhook()
    bot.infinity_polling(timeout=20, long_polling_timeout=60)


if __name__ == "__main__":
    main()
