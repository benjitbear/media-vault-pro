"""Library / media routes: browse, stream, download, search, scan, metadata."""

import json
import os
from pathlib import Path

from flask import Blueprint, current_app, jsonify, request, send_file

media_bp = Blueprint("media", __name__)


def _server():
    """Return the MediaServer instance stored on the app."""
    return current_app.config["server"]


# ── Library ──────────────────────────────────────────────────────


@media_bp.route("/api/library")
def api_library():
    """Return all media items in the library."""
    srv = _server()
    items = srv.scan_library()
    safe = srv._safe_items(items)
    return jsonify({"count": len(safe), "items": safe})


@media_bp.route("/api/media/<media_id>")
def api_media(media_id):
    """Return full metadata for a single media item."""
    srv = _server()
    item = srv.app_state.get_media(media_id)
    if not item:
        srv.scan_library()
        item = srv.app_state.get_media(media_id)
    if item:
        safe = {k: v for k, v in item.items() if k not in ("file_path", "poster_path")}
        safe["has_poster"] = bool(item.get("poster_path"))
        return jsonify(safe)
    return jsonify({"error": "Not found"}), 404


@media_bp.route("/api/stream/<media_id>")
def api_stream(media_id):
    """Stream a media file with HTTP range-request support."""
    srv = _server()
    item = srv.app_state.get_media(media_id)
    if not item:
        srv.scan_library()
        item = srv.app_state.get_media(media_id)
    if item and item.get("file_path") and os.path.exists(item["file_path"]):
        ext = Path(item["file_path"]).suffix.lower()
        from ..constants import MIME_TYPES

        mimetype = MIME_TYPES.get(ext, "application/octet-stream")
        return srv._send_file_partial(item["file_path"], mimetype=mimetype)
    return jsonify({"error": "Not found"}), 404


@media_bp.route("/api/download/<media_id>")
def api_download(media_id):
    """Download a media file as an attachment."""
    srv = _server()
    item = srv.app_state.get_media(media_id)
    if not item:
        srv.scan_library()
        item = srv.app_state.get_media(media_id)
    if item and item.get("file_path") and os.path.exists(item["file_path"]):
        return send_file(
            item["file_path"], as_attachment=True, download_name=item.get("filename", "video.mp4")
        )
    return jsonify({"error": "Not found"}), 404


@media_bp.route("/api/poster/<media_id>")
def api_poster(media_id):
    """Serve the poster image for a media item."""
    srv = _server()
    item = srv.app_state.get_media(media_id)
    if not item:
        srv.scan_library()
        item = srv.app_state.get_media(media_id)
    if item and item.get("poster_path") and os.path.exists(item["poster_path"]):
        return send_file(item["poster_path"], mimetype="image/jpeg")
    return "", 404


@media_bp.route("/api/search")
def api_search():
    """Search media by title, director, cast, or genres."""
    srv = _server()
    query = request.args.get("q", "").strip()
    if not query:
        items = srv.scan_library()
    else:
        srv.scan_library()  # ensure DB is populated
        items = srv.app_state.search_media(query.lower())
    safe = srv._safe_items(items)
    return jsonify({"query": query, "count": len(safe), "items": safe})


@media_bp.route("/api/scan", methods=["POST"])
def api_scan():
    """Force a library re-scan from the filesystem."""
    srv = _server()
    items = srv.scan_library(force=True)
    srv.app_state.broadcast("library_updated", {"count": len(items)})
    return jsonify({"status": "completed", "count": len(items)})


# ── Media Identification ─────────────────────────────────────────


@media_bp.route("/api/media/<media_id>/identify", methods=["POST"])
def api_identify_media(media_id):
    """Identify or re-identify a media item via TMDB.

    Optional JSON body:
        title: User-supplied title (overrides filename parsing).
        year:  User-supplied year (overrides guessit).

    If no body is provided, the service parses the filename automatically.
    Returns the enriched media item on success.
    """
    srv = _server()
    item = srv.app_state.get_media(media_id)
    if not item:
        return jsonify({"error": "Media not found"}), 404

    file_path = item.get("file_path", "")
    if not file_path or not os.path.exists(file_path):
        return jsonify({"error": "File not found on disk"}), 404

    data = request.get_json(silent=True) or {}
    title_override = data.get("title")
    year_override = data.get("year")
    if year_override is not None:
        try:
            year_override = int(year_override)
        except (ValueError, TypeError):
            year_override = None

    from ..services.media_identifier import MediaIdentifierService

    identifier = MediaIdentifierService(
        config=srv.config,
        app_state=srv.app_state,
    )
    result = identifier.identify_file(
        file_path,
        title_override=title_override,
        year_override=year_override,
        media_id=media_id,
    )

    if not result:
        return jsonify({"error": "Identification failed"}), 500

    srv._cache = None
    safe = {k: v for k, v in result.items() if k not in ("file_path", "poster_path")}
    safe["has_poster"] = bool(result.get("poster_path"))
    return jsonify({"status": "identified", "item": safe})


# ── Metadata Editing ─────────────────────────────────────────────


@media_bp.route("/api/media/<media_id>/metadata", methods=["PUT"])
def api_update_metadata(media_id):
    """Update metadata fields for a media item."""
    srv = _server()
    data = request.get_json()
    if not data:
        return jsonify({"error": "No data provided"}), 400

    success = srv.app_state.update_media_metadata(media_id, data)
    if not success:
        return jsonify({"error": "Media not found or no valid fields"}), 404

    # Also update the metadata JSON file on disk
    item = srv.app_state.get_media(media_id)
    if item:
        stem = Path(item.get("filename", "")).stem
        metadata_file = srv.metadata_path / f"{stem}.json"
        if metadata_file.exists():
            try:
                with open(metadata_file, "r") as f:
                    file_meta = json.load(f)
                if "tmdb" not in file_meta:
                    file_meta["tmdb"] = {}

                field_map = {
                    "title": "title",
                    "year": "year",
                    "overview": "overview",
                    "director": "director",
                    "rating": "rating",
                    "genres": "genres",
                    "cast_members": "cast",
                }
                for api_key, tmdb_key in field_map.items():
                    if api_key in data:
                        file_meta["tmdb"][tmdb_key] = data[api_key]

                with open(metadata_file, "w") as f:
                    json.dump(file_meta, f, indent=2, ensure_ascii=False)
            except Exception as e:
                srv.logger.error("Error updating metadata file: %s", e)

    srv._cache = None  # Invalidate cache
    return jsonify({"status": "updated"})


# ── Stats ────────────────────────────────────────────────────────


@media_bp.route("/api/stats")
def api_stats():
    """Library statistics."""
    srv = _server()
    media = srv.app_state.get_all_media()
    by_type = {}
    total_size = 0
    for m in media:
        mt = m.get("media_type", "video")
        by_type[mt] = by_type.get(mt, 0) + 1
        total_size += m.get("file_size", 0)
    pods = srv.app_state.get_all_podcasts()
    collections = srv.app_state.get_all_collections()

    from ..utils import format_size

    return jsonify(
        {
            "total_items": len(media),
            "by_type": by_type,
            "total_size": total_size,
            "total_size_formatted": format_size(total_size),
            "podcasts": len(pods),
            "collections": len(collections),
        }
    )
