"""
Web server for browsing and streaming the media library.
Features: WebSocket (Socket.IO), auth, library caching, range requests,
job management, collections, metadata editing, download, dark mode.
"""

import json
import os
import re
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List

from flask import (
    Flask,
    render_template,
    jsonify,
    request,
    redirect,
    Response,
)
from flask_socketio import SocketIO, emit

from .app_state import AppState
from .constants import ALL_MEDIA_EXTENSIONS, LIBRARY_SKIP_DIRS
from .config import load_config
from .services.library_scanner import LibraryScannerService
from .utils import (
    setup_logger,
    format_size,
    configure_notifications,
    detect_media_type,
    generate_media_id,
)
from .routes import (
    media_bp,
    jobs_bp,
    collections_bp,
    users_bp,
    content_bp,
    podcasts_bp,
    playback_bp,
)


class MediaServer:
    """Web server for media library access with WebSocket support"""

    def __init__(
        self,
        config: Dict[str, Any] = None,
        *,
        config_path: str = None,
        app_state: AppState = None,
    ):
        """Initialise the Flask web server.

        Args:
            config: Pre-loaded configuration dict (preferred).
            config_path: Path to the JSON config file (backward compat).
            app_state: Optional pre-existing AppState instance.
                Created automatically if not provided.
        """
        self.config = config if config is not None else load_config(config_path or "config.json")
        debug_mode = self.config.get("logging", {}).get("debug", False)
        self.logger = setup_logger("web_server", "web_server.log", debug=debug_mode)
        self.app_state = app_state or AppState()

        # Configure notification suppression from config
        notify_enabled = self.config.get("automation", {}).get("notification_enabled", True)
        configure_notifications(notify_enabled)

        # Seed default users only if DB is empty AND env-supplied initial creds exist
        if not self.app_state.has_users():
            init_admin_user = os.environ.get("INIT_ADMIN_USER", "")
            init_admin_pass = os.environ.get("INIT_ADMIN_PASS", "")
            if init_admin_user and init_admin_pass:
                self.app_state.create_user(init_admin_user, init_admin_pass, "admin")
                self.logger.info("Seeded initial admin user: %s", init_admin_user)

        self.library_path = Path(self.config["output"]["base_directory"])

        from .utils import get_data_dir

        data_dir = get_data_dir()
        self.metadata_path = data_dir / "metadata"
        self.thumbnails_path = data_dir / "thumbnails"
        self.metadata_path.mkdir(parents=True, exist_ok=True)
        self.thumbnails_path.mkdir(parents=True, exist_ok=True)

        # Business logic service for library scanning
        self._scanner = LibraryScannerService(
            library_path=self.library_path,
            metadata_path=self.metadata_path,
            thumbnails_path=self.thumbnails_path,
            app_state=self.app_state,
        )

        template_dir = str(Path(__file__).parent / "templates")
        static_dir = str(Path(__file__).parent / "static")
        self.app = Flask(__name__, template_folder=template_dir, static_folder=static_dir)
        # Use a persistent secret key from env (falls back to random per-restart)
        self.app.secret_key = os.environ.get("FLASK_SECRET_KEY", os.urandom(32).hex())

        # Restrict CORS to configured origins, default to same-origin
        cors_origins = os.environ.get("CORS_ALLOWED_ORIGINS", "").strip()
        if cors_origins:
            allowed_origins = [o.strip() for o in cors_origins.split(",")]
        else:
            allowed_origins = "*"  # local dev default — override in production
        self.socketio = SocketIO(
            self.app, cors_allowed_origins=allowed_origins, async_mode="threading"
        )

        # Enforce max upload size at the Flask level
        max_mb = self.config.get("uploads", {}).get("max_upload_size_mb", 4096)
        self.app.config["MAX_CONTENT_LENGTH"] = max_mb * 1024 * 1024
        self.app_state.set_socketio(self.socketio)

        # Library cache
        self._cache = None
        self._cache_time = 0
        self._cache_ttl = self.config.get("library_cache", {}).get("ttl_seconds", 300)

        self._setup_auth()
        self._setup_page_routes()
        self._register_blueprints()
        self._setup_socketio()

        self.logger.info("MediaServer initialized with WebSocket support")

    def _auth_config(self) -> dict:
        return self.config.get("auth", {"enabled": False})

    # ── Auth Middleware ───────────────────────────────────────────

    def _setup_auth(self):
        """Setup authentication middleware and security headers"""

        @self.app.before_request
        def check_auth():
            auth_conf = self._auth_config()
            if not auth_conf.get("enabled", False):
                return None

            # Skip auth for login page and socket.io
            if request.path in ("/login",) or request.path.startswith("/socket.io"):
                return None

            # Check session cookie
            session_token = request.cookies.get("session_token")
            if session_token:
                session_info = self.app_state.validate_session(session_token)
                if session_info:
                    # Attach user info to request context
                    request.current_user = session_info
                    return None

            # Not authenticated
            if request.path.startswith("/api/"):
                return jsonify({"error": "Unauthorized"}), 401
            return redirect("/login")

        @self.app.after_request
        def security_headers(response):
            response.headers["X-Content-Type-Options"] = "nosniff"
            response.headers["X-Frame-Options"] = "SAMEORIGIN"
            response.headers["X-XSS-Protection"] = "1; mode=block"
            response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
            response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
            # CSP: allow inline styles/scripts (needed for current SPA) + CDN
            response.headers["Content-Security-Policy"] = (
                "default-src 'self'; "
                "script-src 'self' 'unsafe-inline' https://cdn.tailwindcss.com "
                "https://cdnjs.cloudflare.com; "
                "style-src 'self' 'unsafe-inline'; "
                "img-src 'self' data: https://image.tmdb.org; "
                "connect-src 'self' ws: wss:; "
                "media-src 'self'; "
                "font-src 'self'"
            )
            return response

    # ── Library Scanning ─────────────────────────────────────────

    def scan_library(self, force: bool = False) -> List[Dict[str, Any]]:
        """Scan and cache the media library"""
        now = time.time()
        if not force and self._cache is not None and (now - self._cache_time < self._cache_ttl):
            return self._cache

        items = self._do_scan()
        self._cache = items
        self._cache_time = now
        return items

    def _do_scan(self) -> List[Dict[str, Any]]:
        """Delegate library scanning to the service layer."""
        return self._scanner.scan()

    def _safe_items(self, items: List[Dict]) -> List[Dict]:
        """Strip internal paths from items before sending to client"""
        safe = []
        for item in items:
            d = {k: v for k, v in item.items() if k not in ("file_path", "poster_path")}
            d["has_poster"] = bool(item.get("poster_path"))
            safe.append(d)
        return safe

    # ── Range Request Support ────────────────────────────────────

    def _send_file_partial(self, file_path: str, mimetype: str = "video/mp4"):
        """Send file with HTTP range request support and chunked streaming.
        Streams data in 256KB chunks so playback can begin immediately
        without loading the entire file into memory."""
        CHUNK_SIZE = 256 * 1024  # 256 KB
        file_size = os.path.getsize(file_path)
        range_header = request.headers.get("Range")

        if range_header:
            match = re.match(r"bytes=(\d+)-(\d*)", range_header)
            if match:
                byte_start = int(match.group(1))
                byte_end = int(match.group(2)) if match.group(2) else file_size - 1
                byte_end = min(byte_end, file_size - 1)
                length = byte_end - byte_start + 1

                def generate_range():
                    with open(file_path, "rb") as f:
                        f.seek(byte_start)
                        remaining = length
                        while remaining > 0:
                            chunk = f.read(min(CHUNK_SIZE, remaining))
                            if not chunk:
                                break
                            remaining -= len(chunk)
                            yield chunk

                resp = Response(generate_range(), 206, mimetype=mimetype, direct_passthrough=True)
                resp.headers["Content-Range"] = f"bytes {byte_start}-{byte_end}/{file_size}"
                resp.headers["Accept-Ranges"] = "bytes"
                resp.headers["Content-Length"] = str(length)
                return resp

        # Full file — also stream in chunks
        def generate_full():
            with open(file_path, "rb") as f:
                while True:
                    chunk = f.read(CHUNK_SIZE)
                    if not chunk:
                        break
                    yield chunk

        resp = Response(generate_full(), 200, mimetype=mimetype, direct_passthrough=True)
        resp.headers["Accept-Ranges"] = "bytes"
        resp.headers["Content-Length"] = str(file_size)
        return resp

    # ── Routes ───────────────────────────────────────────────────

    def _setup_page_routes(self):
        """Setup page routes (index, login, logout)"""

        @self.app.route("/")
        def index():
            return render_template(
                "index.html",
                library_name=self.config["web_server"]["library_name"],
                auth_enabled=self._auth_config().get("enabled", False),
            )

        @self.app.route("/login", methods=["GET", "POST"])
        def login():
            # First-run setup: if no users exist, show setup form
            needs_setup = (
                self._auth_config().get("enabled", False) and not self.app_state.has_users()
            )

            if request.method == "POST":
                username = request.form.get("username", "").strip()
                password = request.form.get("password", "")
                auth_conf = self._auth_config()

                if needs_setup:
                    # Create the initial admin account
                    if not username or not password:
                        return render_template(
                            "login.html",
                            error="Username and password are required",
                            setup_mode=True,
                        )
                    self.app_state.create_user(username, password, "admin")
                    self.logger.info("Initial admin account created: %s", username)
                    needs_setup = False
                    # Fall through to normal login with the new credentials

                user = self.app_state.verify_user(username, password)
                if user:
                    session_token = self.app_state.create_session(
                        username=username, hours=auth_conf.get("session_hours", 24)
                    )
                    response = redirect("/")
                    is_secure = os.environ.get("SECURE_COOKIES", "").lower() in ("1", "true", "yes")
                    response.set_cookie(
                        "session_token",
                        session_token,
                        httponly=True,
                        samesite="Lax",
                        secure=is_secure,
                        max_age=auth_conf.get("session_hours", 24) * 3600,
                    )
                    self.logger.info("User logged in: %s", username)
                    return response
                return render_template(
                    "login.html", error="Invalid username or password", setup_mode=needs_setup
                )
            return render_template("login.html", setup_mode=needs_setup)

        @self.app.route("/logout")
        def logout():
            # Invalidate the session server-side before clearing the cookie
            session_token = request.cookies.get("session_token")
            if session_token:
                self.app_state.invalidate_session(session_token)
            response = redirect("/login")
            response.delete_cookie("session_token")
            return response

    def _register_blueprints(self):
        """Register domain-specific Blueprints and expose server on app."""
        self.app.config["server"] = self
        for bp in (
            media_bp,
            jobs_bp,
            collections_bp,
            users_bp,
            content_bp,
            podcasts_bp,
            playback_bp,
        ):
            self.app.register_blueprint(bp)

    # ── WebSocket ────────────────────────────────────────────────

    def _setup_socketio(self):
        """Setup WebSocket event handlers"""

        @self.socketio.on("connect")
        def handle_connect():
            auth_conf = self._auth_config()
            if auth_conf.get("enabled", False):
                token = request.cookies.get("session_token")
                if not token or not self.app_state.validate_session(token):
                    return False  # Reject connection

            self.logger.debug("WebSocket client connected")

            # Send current active job state if any
            active_job = self.app_state.get_active_job()
            if active_job:
                emit("job_update", active_job)

        @self.socketio.on("disconnect")
        def handle_disconnect():
            self.logger.debug("WebSocket client disconnected")

        @self.socketio.on("request_library")
        def handle_request_library():
            items = self.scan_library()
            safe = self._safe_items(items)
            emit("library_data", {"count": len(safe), "items": safe})

    # ── Server Start ─────────────────────────────────────────────

    def run(self, host: str = None, port: int = None):
        """Start the web server with WebSocket support"""
        host = host or self.config["web_server"]["host"]
        port = port or self.config["web_server"]["port"]

        self.logger.info("Starting web server on %s:%s", host, port)

        print("\n🌐 Media Server starting...")
        print(f"📚 Library: {self.library_path}")
        print(f"🔗 URL: http://{host if host != '0.0.0.0' else 'localhost'}:{port}")
        print("🔌 WebSocket: enabled")
        auth_on = self._auth_config().get("enabled")
        print(f"🔒 Auth: {'enabled' if auth_on else 'disabled'}")
        print("\nPress Ctrl+C to stop\n")

        # Initial library scan
        self.scan_library(force=True)

        self.socketio.run(
            self.app, host=host, port=int(port), debug=False, allow_unsafe_werkzeug=True
        )


def main():
    """Standalone entry point for the web server only"""
    import argparse

    parser = argparse.ArgumentParser(description="Start media library web server")
    parser.add_argument("--host", help="Host address")
    parser.add_argument("--port", type=int, help="Port number")
    parser.add_argument("--config", default="config.json", help="Path to config file")
    args = parser.parse_args()

    app_state = AppState()
    server = MediaServer(config_path=args.config, app_state=app_state)
    server.run(host=args.host, port=args.port)


if __name__ == "__main__":
    main()
