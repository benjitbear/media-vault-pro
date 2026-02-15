"""User management routes (admin-only where noted)."""

from flask import Blueprint, current_app, jsonify, request

users_bp = Blueprint("users", __name__)


def _server():
    return current_app.config["server"]


def _require_admin() -> bool:
    """Check that the current request is from an admin user."""
    user = getattr(request, "current_user", None)
    return bool(user and user.get("role") == "admin")


@users_bp.route("/api/users")
def api_users():
    """List all users (admin only)."""
    if not _require_admin():
        return jsonify({"error": "Admin access required"}), 403
    users = _server().app_state.list_users()
    return jsonify({"users": users})


@users_bp.route("/api/users", methods=["POST"])
def api_create_user():
    """Create a new user account (admin only)."""
    if not _require_admin():
        return jsonify({"error": "Admin access required"}), 403
    data = request.get_json()
    if not data or not data.get("username") or not data.get("password"):
        return jsonify({"error": "username and password required"}), 400
    role = data.get("role", "user")
    if role not in ("admin", "user"):
        return jsonify({"error": "role must be admin or user"}), 400
    if _server().app_state.create_user(data["username"], data["password"], role):
        return jsonify({"status": "created", "username": data["username"]}), 201
    return jsonify({"error": "User already exists"}), 409


@users_bp.route("/api/users/<username>", methods=["DELETE"])
def api_delete_user(username):
    """Delete a user account (admin only, cannot delete self)."""
    if not _require_admin():
        return jsonify({"error": "Admin access required"}), 403
    current = getattr(request, "current_user", {})
    if current.get("username") == username:
        return jsonify({"error": "Cannot delete your own account"}), 400
    if _server().app_state.delete_user(username):
        return jsonify({"status": "deleted"})
    return jsonify({"error": "User not found"}), 404


@users_bp.route("/api/users/<username>/password", methods=["PUT"])
def api_update_password(username):
    """Admin can change any password; users can change their own."""
    current = getattr(request, "current_user", {})
    if current.get("role") != "admin" and current.get("username") != username:
        return jsonify({"error": "Forbidden"}), 403
    data = request.get_json()
    if not data or not data.get("password"):
        return jsonify({"error": "password required"}), 400
    if _server().app_state.update_user_password(username, data["password"]):
        return jsonify({"status": "updated"})
    return jsonify({"error": "User not found"}), 404


@users_bp.route("/api/me")
def api_me():
    """Get current user info."""
    user = getattr(request, "current_user", None)
    if user:
        return jsonify(user)
    return jsonify({"username": None, "role": "anonymous"})
