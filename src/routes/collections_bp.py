"""Collection and playlist routes."""

from flask import Blueprint, jsonify, request, current_app

collections_bp = Blueprint("collections", __name__)


def _server():
    return current_app.config["server"]


@collections_bp.route("/api/collections")
def api_collections():
    """List all collections with their media items."""
    srv = _server()
    collections = srv.app_state.get_all_collections()
    for col in collections:
        col["items"] = srv._safe_items(col.get("items", []))
    return jsonify({"collections": collections})


@collections_bp.route("/api/collections/<name>", methods=["PUT"])
def api_update_collection(name):
    """Create or update a collection by name."""
    srv = _server()
    data = request.get_json()
    if not data:
        return jsonify({"error": "Request body required"}), 400
    media_ids = data.get("media_ids", [])
    description = data.get("description")
    collection_type = data.get("collection_type")

    existing = srv.app_state.get_collection_by_name(name)
    if existing:
        col_id = existing["id"]
        if description is not None or collection_type is not None:
            srv.app_state.update_collection_metadata(
                col_id, description=description, collection_type=collection_type
            )
    else:
        col_id = srv.app_state.create_collection(
            name, description=description or "", collection_type=collection_type or "collection"
        )

    if media_ids:
        srv.app_state.update_collection(name, media_ids)
    return jsonify({"status": "updated"})


@collections_bp.route("/api/collections/<name>", methods=["DELETE"])
def api_delete_collection(name):
    """Delete a collection by name."""
    if _server().app_state.delete_collection(name):
        return jsonify({"status": "deleted"})
    return jsonify({"error": "Collection not found"}), 404


@collections_bp.route("/api/collections/<int:col_id>/items")
def api_collection_items(col_id):
    """Get ordered media items for a collection (for queue playback)."""
    srv = _server()
    media = srv.app_state.get_collection_items(col_id)
    safe = srv._safe_items(media)
    return jsonify({"items": safe})
