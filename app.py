# -*- coding: utf-8 -*-
"""NovaDL — Flask web app (WEB + API only, decoupled from the Telegram bot).

Serves the animated single-page UI and a JSON API that wraps yt-dlp:
  GET  /api/info?url=...      -> metadata + available formats
  POST /api/download          -> download a selected format (returns file)
  GET  /api/status            -> yt-dlp version / updater status

The Telegram bot (bot.py) runs as a separate long-polling process and shares
only the `engine`/`config` modules.
"""
import os
import sys
import time
import threading
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from flask import Flask, request, jsonify, send_file, send_from_directory, Response

import config
import engine

app = Flask(__name__,
            static_folder=str(Path(__file__).resolve().parent / "web"),
            static_url_path="/static")

WEB_DIR = Path(__file__).resolve().parent / "web"

# in-progress download registry (file_id -> status)
_downloads = {}


@app.route("/health")
def health():
    return jsonify({"ok": True, "service": "novadl", "version": config.APP_VERSION,
                    **engine.update_status()})


@app.route("/api/info")
def api_info():
    url = request.args.get("url", "").strip()
    if not engine.is_valid_url(url):
        return jsonify({"ok": False, "error": "invalid URL"}), 400
    try:
        info = engine.fetch_info(url)
        info["ok"] = True
        return jsonify(info)
    except Exception as e:
        return jsonify({"ok": False, "error": f"Could not fetch video info: {e}"}), 400


@app.route("/api/download", methods=["POST"])
def api_download():
    body = request.get_json(silent=True) or {}
    url = (body.get("url") or "").strip()
    format_id = body.get("format_id", "")
    kind = body.get("kind", "video")

    if not engine.is_valid_url(url):
        return jsonify({"ok": False, "error": "invalid URL"}), 400
    if kind not in ("video", "audio"):
        kind = "video"

    job_id = uuid.uuid4().hex[:10]
    job_dir = config.DOWNLOAD_DIR / job_id
    job_dir.mkdir(parents=True, exist_ok=True)

    _downloads[job_id] = {"status": "downloading", "url": url}

    try:
        result = engine.download(url, format_id, kind, str(job_dir))
        if "error" in result:
            _downloads[job_id] = {"status": "error", "error": result["error"]}
            return jsonify({"ok": False, "error": result["error"]}), 400

        path = Path(result["path"])
        _downloads[job_id] = {"status": "done", "path": str(path), "filename": path.name,
                              "size": result["size"]}
        return jsonify({"ok": True, "job_id": job_id, "filename": path.name,
                        "size": result["size"], "ext": result.get("ext", "")})
    except Exception as e:
        _downloads[job_id] = {"status": "error", "error": str(e)}
        return jsonify({"ok": False, "error": str(e)}), 500


@app.route("/api/file/<job_id>")
def api_file(job_id):
    job = _downloads.get(job_id)
    if not job or job.get("status") != "done":
        return jsonify({"ok": False, "error": "not ready"}), 404
    path = Path(job["path"])
    if not path.exists():
        return jsonify({"ok": False, "error": "file expired"}), 404
    return send_file(str(path), as_attachment=True, download_name=path.name)


@app.route("/api/status")
def api_status():
    return jsonify({"ok": True, **engine.update_status()})


@app.route("/")
def index():
    return send_from_directory(str(WEB_DIR), "index.html")


@app.route("/<path:filename>")
def web_static(filename):
    if filename in ("", "index.html"):
        return send_from_directory(str(WEB_DIR), "index.html")
    return send_from_directory(str(WEB_DIR), filename)


def _boot():
    threading.Thread(target=engine.run_startup_upgrade, daemon=True).start()
    engine.start_updater()


_boot()


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", "10000")), debug=False)
