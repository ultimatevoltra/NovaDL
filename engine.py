# -*- coding: utf-8 -*-
"""NovaDL — core download engine wrapping yt-dlp.

Provides metadata fetching, format listing, and stream download. Includes a
resilient self-update mechanism that (a) upgrades yt-dlp at startup and (b)
runs a background thread that checks & upgrades on a set interval.
"""
import os
import sys
import time
import threading
import traceback
from pathlib import Path
from typing import Any, Dict, List, Optional

_ytdlp = None


def _load_ytdlp():
    global _ytdlp
    if _ytdlp is not None:
        return _ytdlp
    import yt_dlp
    _ytdlp = yt_dlp
    return _ytdlp


_update_lock = threading.Lock()
_last_update_ts = 0.0
_updater_thread = None

DEFAULT_UPDATE_INTERVAL = float(os.environ.get("YTDLP_UPDATE_INTERVAL", "86400"))


def _upgrade_ytdlp() -> Dict[str, Any]:
    import subprocess
    try:
        before = ""
        try:
            import importlib.metadata as md
            before = md.version("yt-dlp")
        except Exception:
            before = "unknown"
        r = subprocess.run(
            [sys.executable, "-m", "pip", "install", "--upgrade", "--quiet", "yt-dlp"],
            capture_output=True, text=True, timeout=300,
        )
        ok = r.returncode == 0
        after = ""
        try:
            import importlib.metadata as md
            after = md.version("yt-dlp")
        except Exception:
            after = "unknown"
        return {"ok": ok, "before": before, "after": after, "output": (r.stderr or r.stdout or "")[-800:]}
    except Exception as e:
        return {"ok": False, "before": "", "after": "", "error": str(e)}


def run_startup_upgrade() -> Dict[str, Any]:
    global _last_update_ts
    with _update_lock:
        res = _upgrade_ytdlp()
        _last_update_ts = time.time()
        return res


def _updater_loop(interval: float):
    global _last_update_ts
    while True:
        time.sleep(max(interval, 3600))
        try:
            _upgrade_ytdlp()
            _last_update_ts = time.time()
        except Exception:
            pass


def start_updater(interval: Optional[float] = None):
    global _updater_thread
    interval = interval if interval is not None else DEFAULT_UPDATE_INTERVAL
    if _updater_thread is not None and _updater_thread.is_alive():
        return
    if interval <= 0:
        return
    _updater_thread = threading.Thread(target=_updater_loop, args=(interval,), daemon=True)
    _updater_thread.start()


def update_status() -> Dict[str, Any]:
    try:
        import importlib.metadata as md
        version = md.version("yt-dlp")
    except Exception:
        version = "unknown"
    return {
        "ytdlp_version": version,
        "last_update_unix": _last_update_ts,
        "updater_running": bool(_updater_thread is not None and _updater_thread.is_alive()),
        "update_interval": DEFAULT_UPDATE_INTERVAL,
    }


VIDEO_EXT = ("mp4", "webm", "mkv", "mov", "avi", "flv", "3gp")
AUDIO_EXT = ("m4a", "mp3", "opus", "ogg", "wav", "aac", "flac")


def _probe_opts() -> Dict[str, Any]:
    return {
        "quiet": True,
        "no_warnings": True,
        "noplaylist": True,
        "skip_download": True,
        "socket_timeout": 20,
    }


def is_valid_url(url: str) -> bool:
    u = (url or "").strip()
    return u.startswith("http://") or u.startswith("https://")


def fetch_info(url: str) -> Dict[str, Any]:
    yt = _load_ytdlp()
    with yt.YoutubeDL(_probe_opts()) as ydl:
        info = ydl.extract_info(url, download=False)

    if info.get("_type") == "playlist" and "entries" in info:
        entries = [e for e in info.get("entries", []) if e]
        if entries:
            info = entries[0]

    title = info.get("title") or "video"
    thumbnail = info.get("thumbnail") or ""
    duration = info.get("duration") or 0
    uploader = info.get("uploader") or info.get("channel") or ""
    formats = _collect_formats(info)

    if not formats:
        ext = (info.get("ext") or "").lower()
        is_audio = ext in AUDIO_EXT or info.get("vcodec") == "none"
        formats = [{
            "format_id": "best",
            "kind": "audio" if is_audio else "video",
            "label": f"best · {ext}" if ext else "best",
            "quality": "",
            "ext": ext,
            "filesize": 0,
        }]

    return {
        "id": info.get("id", ""),
        "title": title,
        "thumbnail": thumbnail,
        "duration": duration,
        "uploader": uploader,
        "webpage_url": info.get("webpage_url") or url,
        "formats": formats,
    }


def _collect_formats(info: Dict[str, Any]) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    seen_ids = set()
    auto_candidates = []
    for f in info.get("formats", []) or []:
        fid = f.get("format_id", "")
        if not fid or fid in seen_ids:
            continue
        seen_ids.add(fid)
        vcodec = f.get("vcodec") or "none"
        acodec = f.get("acodec") or "none"
        ext = (f.get("ext") or "").lower()
        height = f.get("height") or 0
        fps = f.get("fps") or 0
        filesize = f.get("filesize") or f.get("filesize_approx") or 0
        abr = f.get("abr") or 0
        note = f.get("format_note") or ""
        has_video = vcodec != "none"
        has_audio = acodec != "none"
        if has_video:
            label = f"{height}p" if height else (note or ext)
            auto_candidates.append({
                "format_id": fid, "kind": "video", "label": label,
                "quality": f"{height}p" if height else "", "ext": ext,
                "height": height, "fps": fps, "filesize": filesize,
                "has_audio": has_audio, "tbr": f.get("tbr") or 0,
            })
        elif has_audio:
            out.append({
                "format_id": fid, "kind": "audio",
                "label": f"audio · {ext}" + (f" {abr}k" if abr else ""),
                "quality": "", "ext": ext, "abr": abr, "filesize": filesize,
            })

    auto_candidates.sort(key=lambda x: (x.get("height") or 0, -(x.get("tbr") or 0)), reverse=True)
    seen_heights = set()
    video_formats = []
    for c in auto_candidates:
        h = c.get("height") or 0
        key = h if h else c.get("label")
        if key in seen_heights:
            continue
        seen_heights.add(key)
        c["format_id_server"] = c["format_id"]
        video_formats.append(c)

    return video_formats + out


def download(url: str, format_id: str, kind: str, dest_dir: str) -> Dict[str, Any]:
    yt = _load_ytdlp()
    dest_dir = Path(dest_dir)
    dest_dir.mkdir(parents=True, exist_ok=True)

    if kind == "audio":
        outtmpl = str(dest_dir / "%(title).120s.%(ext)s")
        opts = {
            "format": format_id or "bestaudio/best",
            "outtmpl": outtmpl,
            "quiet": True,
            "no_warnings": True,
            "noplaylist": True,
            "postprocessors": [{"key": "FFmpegExtractAudio", "preferredcodec": "mp3", "preferredquality": "192"}],
        }
    else:
        outtmpl = str(dest_dir / "%(title).120s.%(ext)s")
        fmt = format_id or "best"
        if format_id and format_id != "best":
            fmt = f"{format_id}+bestaudio/best"
        opts = {
            "format": fmt,
            "outtmpl": outtmpl,
            "merge_output_format": "mp4",
            "quiet": True,
            "no_warnings": True,
            "noplaylist": True,
            "socket_timeout": 30,
        }

    with yt.YoutubeDL(opts) as ydl:
        result = ydl.extract_info(url, download=True)

    produced = _latest_file(dest_dir)
    if produced is None:
        info_title = result.get("title", "video") if isinstance(result, dict) else "video"
        return {"error": "download produced no file", "title": info_title}

    return {
        "path": str(produced),
        "filename": produced.name,
        "ext": produced.suffix.lstrip(".") or "mp4",
        "size": produced.stat().st_size,
        "title": (result.get("title", produced.stem) if isinstance(result, dict) else produced.stem),
    }


def _latest_file(dest_dir: Path) -> Optional[Path]:
    files = [p for p in dest_dir.iterdir() if p.is_file()]
    if not files:
        return None
    files.sort(key=lambda p: p.stat().st_mtime, reverse=True)
    for f in files:
        if f.suffix in (".part", ".ytdl", ".temp") or f.name.endswith(".part"):
            continue
        return f
    return files[0]
