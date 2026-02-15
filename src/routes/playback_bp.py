"""Playback progress tracking routes."""

from flask import Blueprint, current_app, jsonify, request

playback_bp = Blueprint("playback", __name__)


def _server():
    return current_app.config["server"]


def _current_username() -> str:
    """Get the current user's username (falls back to 'anonymous')."""
    user = getattr(request, "current_user", None)
    return user.get("username", "anonymous") if user else "anonymous"


@playback_bp.route("/api/media/<media_id>/progress")
def api_get_progress(media_id):
    """Get saved playback position for a media item."""
    prog = _server().app_state.get_playback_progress(media_id, _current_username())
    if prog:
        return jsonify(prog)
    return jsonify({"position_seconds": 0, "duration_seconds": 0, "finished": 0})


@playback_bp.route("/api/media/<media_id>/progress", methods=["PUT"])
def api_save_progress(media_id):
    """Save playback position for a media item."""
    data = request.get_json()
    if not data:
        return jsonify({"error": "No data"}), 400
    _server().app_state.save_playback_progress(
        media_id=media_id,
        position_seconds=float(data.get("position", 0)),
        duration_seconds=float(data.get("duration", 0)),
        username=_current_username(),
    )
    return jsonify({"status": "saved"})


@playback_bp.route("/api/media/<media_id>/progress", methods=["DELETE"])
def api_clear_progress(media_id):
    """Clear playback progress (mark as unwatched)."""
    _server().app_state.clear_playback_progress(media_id, _current_username())
    return jsonify({"status": "cleared"})


@playback_bp.route("/api/continue-watching")
def api_continue_watching():
    """Get list of in-progress media for current user."""
    srv = _server()
    items = srv.app_state.get_in_progress_media(_current_username())
    safe = srv._safe_items(items)
    for i, item in enumerate(items):
        safe[i]["progress_position"] = item.get("progress_position", 0)
        safe[i]["progress_duration"] = item.get("progress_duration", 0)
    return jsonify({"items": safe})
