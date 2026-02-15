"""Content ingestion routes: upload, download, articles, books."""

import uuid
from datetime import datetime
from pathlib import Path

from flask import Blueprint, current_app, jsonify, request

from ..utils import detect_media_type, format_size, generate_media_id

content_bp = Blueprint("content", __name__)


def _server():
    return current_app.config["server"]


# ── Upload ───────────────────────────────────────────────────────


@content_bp.route("/api/upload", methods=["POST"])
def api_upload():
    """Upload one or more files to the library."""
    srv = _server()
    upload_cfg = srv.config.get("uploads", {})
    if not upload_cfg.get("enabled", True):
        return jsonify({"error": "Uploads disabled"}), 403

    max_mb = upload_cfg.get("max_upload_size_mb", 4096)
    upload_dir = Path(upload_cfg.get("upload_directory", str(srv.library_path / "uploads")))
    upload_dir.mkdir(parents=True, exist_ok=True)

    files = request.files.getlist("files")
    if not files:
        return jsonify({"error": "No files provided"}), 400

    results = []
    for f in files:
        if not f.filename:
            continue
        safe_name = Path(f.filename).name

        content_length = request.content_length
        if content_length and content_length > max_mb * 1024 * 1024:
            results.append({"file": safe_name, "error": "File too large"})
            continue

        dest = upload_dir / safe_name
        counter = 2
        while dest.exists():
            stem = Path(safe_name).stem
            suffix = Path(safe_name).suffix
            dest = upload_dir / f"{stem} ({counter}){suffix}"
            counter += 1

        f.save(str(dest))
        fsize = dest.stat().st_size
        if fsize > max_mb * 1024 * 1024:
            dest.unlink()
            results.append({"file": safe_name, "error": "File too large"})
            continue

        media_id = generate_media_id(str(dest))
        media_type = detect_media_type(dest.name)
        item = {
            "id": media_id,
            "title": dest.stem,
            "filename": dest.name,
            "file_path": str(dest),
            "file_size": fsize,
            "size_formatted": format_size(fsize),
            "created_at": datetime.now().isoformat(),
            "modified_at": datetime.now().isoformat(),
            "media_type": media_type,
        }
        srv.app_state.upsert_media(item)
        results.append({"file": dest.name, "id": media_id, "media_type": media_type})

    srv._cache = None
    srv.app_state.broadcast("library_updated", {})
    return jsonify({"uploaded": results}), 201


# ── Content Downloads ────────────────────────────────────────────


@content_bp.route("/api/downloads", methods=["POST"])
def api_download_content():
    """Queue a URL for download (YouTube, etc.)."""
    data = request.get_json()
    if not data or not data.get("url"):
        return jsonify({"error": "url required"}), 400
    url = data["url"]
    title = data.get("title", url)
    job_id = _server().app_state.create_job(title=title, source_path=url, job_type="download")
    return jsonify({"id": job_id, "status": "queued"}), 201


@content_bp.route("/api/articles", methods=["POST"])
def api_archive_article():
    """Archive a web article."""
    data = request.get_json()
    if not data or not data.get("url"):
        return jsonify({"error": "url required"}), 400
    url = data["url"]
    title = data.get("title", url)
    job_id = _server().app_state.create_job(title=title, source_path=url, job_type="article")
    return jsonify({"id": job_id, "status": "queued"}), 201


@content_bp.route("/api/books", methods=["POST"])
def api_add_book():
    """Catalogue a book (file upload or metadata)."""
    data = request.get_json()
    if not data or not data.get("title"):
        return jsonify({"error": "title required"}), 400
    book_id = str(uuid.uuid4())[:8]
    item = {
        "id": book_id,
        "title": data["title"],
        "filename": data.get("filename", ""),
        "file_path": data.get("file_path", ""),
        "file_size": 0,
        "size_formatted": "0 B",
        "created_at": datetime.now().isoformat(),
        "modified_at": datetime.now().isoformat(),
        "media_type": "document",
        "source_url": data.get("url"),
        "artist": data.get("author"),
        "year": data.get("year"),
        "overview": data.get("description"),
    }
    _server().app_state.upsert_media(item)
    return jsonify({"id": book_id, "status": "added"}), 201
