"""Job queue management routes."""

from pathlib import Path

from flask import Blueprint, current_app, jsonify, request

jobs_bp = Blueprint("jobs", __name__)


def _server():
    return current_app.config["server"]


@jobs_bp.route("/api/jobs")
def api_jobs():
    """List all jobs, newest first."""
    jobs = _server().app_state.get_all_jobs()
    return jsonify({"jobs": jobs})


@jobs_bp.route("/api/jobs", methods=["POST"])
def api_create_job():
    """Create a new rip job from a disc source path."""
    data = request.get_json()
    if not data or "source_path" not in data:
        return jsonify({"error": "source_path required"}), 400

    job_id = _server().app_state.create_job(
        title=data.get("title", Path(data["source_path"]).name),
        source_path=data["source_path"],
        title_number=data.get("title_number", 1),
    )
    return jsonify({"id": job_id, "status": "queued"}), 201


@jobs_bp.route("/api/jobs/<job_id>", methods=["DELETE"])
def api_cancel_job(job_id):
    """Cancel a queued or encoding job."""
    if _server().app_state.cancel_job(job_id):
        return jsonify({"status": "cancelled"})
    return jsonify({"error": "Cannot cancel this job"}), 400


@jobs_bp.route("/api/jobs/<job_id>/retry", methods=["POST"])
def api_retry_job(job_id):
    """Retry a failed or cancelled job."""
    new_id = _server().app_state.retry_job(job_id)
    if new_id:
        return jsonify({"id": new_id, "status": "queued"}), 201
    return jsonify({"error": "Cannot retry this job"}), 400
