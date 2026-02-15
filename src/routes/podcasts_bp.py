"""Podcast subscription and episode routes."""

from flask import Blueprint, jsonify, request, current_app

podcasts_bp = Blueprint("podcasts", __name__)


def _server():
    return current_app.config["server"]


@podcasts_bp.route("/api/podcasts")
def api_podcasts():
    """List all podcast subscriptions."""
    pods = _server().app_state.get_all_podcasts()
    return jsonify({"podcasts": pods})


@podcasts_bp.route("/api/podcasts", methods=["POST"])
def api_add_podcast():
    """Subscribe to a new podcast feed."""
    data = request.get_json()
    if not data or not data.get("feed_url"):
        return jsonify({"error": "feed_url required"}), 400
    pod_id = _server().app_state.add_podcast(
        feed_url=data["feed_url"],
        title=data.get("title", ""),
        author=data.get("author", ""),
        description=data.get("description", ""),
        artwork_url=data.get("artwork_url"),
    )
    if pod_id:
        return jsonify({"id": pod_id, "status": "subscribed"}), 201
    return jsonify({"error": "Podcast already subscribed"}), 409


@podcasts_bp.route("/api/podcasts/<pod_id>", methods=["DELETE"])
def api_delete_podcast(pod_id):
    """Unsubscribe from a podcast."""
    if _server().app_state.delete_podcast(pod_id):
        return jsonify({"status": "deleted"})
    return jsonify({"error": "Not found"}), 404


@podcasts_bp.route("/api/podcasts/<pod_id>/episodes")
def api_podcast_episodes(pod_id):
    """List episodes for a podcast."""
    episodes = _server().app_state.get_episodes(pod_id)
    return jsonify({"episodes": episodes})


# ── Playlist Import ──────────────────────────────────────────────


@podcasts_bp.route("/api/import/playlist", methods=["POST"])
def api_import_playlist():
    """Import a Spotify/Apple Music playlist as a collection."""
    srv = _server()
    data = request.get_json()
    if not data or not data.get("url"):
        return jsonify({"error": "url required"}), 400
    url = data["url"]
    name = data.get("name", "Imported Playlist")
    col_id = srv.app_state.create_collection(
        name=name, description=f"Imported from {url}", collection_type="playlist"
    )
    job_id = srv.app_state.create_job(title=name, source_path=url, job_type="playlist_import")
    return jsonify({"collection_id": col_id, "job_id": job_id, "status": "queued"}), 201
