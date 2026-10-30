# -*- coding: utf-8 -*-
"""NovaDL — configuration & environment (secure, no hardcoded secrets)."""
import os
from pathlib import Path

APP_NAME = "NovaDL"
APP_TAGLINE = "All-in-One Video Downloader"
APP_VERSION = "1.0.0"

DATA_DIR = Path(os.environ.get("DATA_DIR", "/tmp/novadl"))
DOWNLOAD_DIR = DATA_DIR / "downloads"
CACHE_DIR = DATA_DIR / "cache"

for _d in (DOWNLOAD_DIR, CACHE_DIR):
    _d.mkdir(parents=True, exist_ok=True)


def get_bot_token() -> str:
    t = os.environ.get("BOT_TOKEN", "")
    if not t:
        raise RuntimeError("BOT_TOKEN is not set")
    return t


def get_owner_id() -> int:
    try:
        return int(os.environ.get("OWNER_ID", "6097891113"))
    except ValueError:
        return 6097891113


def get_max_file_size() -> int:
    try:
        return int(os.environ.get("MAX_FILE_SIZE", str(180 * 1024 * 1024)))
    except ValueError:
        return 180 * 1024 * 1024


def is_owner(uid: int) -> bool:
    return uid == get_owner_id()


def get_allowed_users() -> set:
    raw = os.environ.get("ALLOWED_USERS", "")
    if not raw:
        return set()
    return {int(x) for x in raw.split(",") if x.strip().isdigit()}
