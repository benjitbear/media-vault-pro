"""
Web server for browsing and streaming the media library.
Features: WebSocket (Socket.IO), auth, library caching, range requests,
job management, collections, metadata editing, download, dark mode.
"""
import hashlib
import json
import os
import re
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from flask import (
    Flask, render_template, jsonify, request, redirect,
    send_file, Response, make_response
)
from flask_socketio import SocketIO, emit

from .app_state import AppState
from .utils import load_config, setup_logger, format_size, format_time, configure_notifications


def generate_media_id(file_path: str) -> str:
    """Generate a stable, deterministic media ID from file path"""
    return hashlib.sha256(file_path.encode()).hexdigest()[:12]


class MediaServer:
    """Web server for media library access with WebSocket support"""

    def __init__(self, config_path: str = "config.json", app_state: AppState = None):
        self.config = load_config(config_path)
        debug_mode = self.config.get('logging', {}).get('debug', False)
        self.logger = setup_logger('web_server', 'web_server.log', debug=debug_mode)
        self.app_state = app_state or AppState()

        # Configure notification suppression from config
        notify_enabled = self.config.get('automation', {}).get('notification_enabled', True)
        configure_notifications(notify_enabled)

        # Seed default users from config
        default_users = self.config.get('auth', {}).get('default_users', [])
        if default_users:
            self.app_state.seed_default_users(default_users)

        self.library_path = Path(self.config['output']['base_directory'])
        self.metadata_path = Path('/Users/poppemacmini/Media/data/metadata')
        self.thumbnails_path = Path('/Users/poppemacmini/Media/data/thumbnails')

        template_dir = str(Path(__file__).parent / 'templates')
        self.app = Flask(__name__, template_folder=template_dir)
        self.app.secret_key = os.urandom(32).hex()

        self.socketio = SocketIO(self.app, cors_allowed_origins="*", async_mode='threading')
        self.app_state.set_socketio(self.socketio)

        # Library cache
        self._cache = None
        self._cache_time = 0
        self._cache_ttl = self.config.get('library_cache', {}).get('ttl_seconds', 300)

        self._setup_auth()
        self._setup_routes()
        self._setup_socketio()

        self.logger.info("MediaServer initialized with WebSocket support")

    def _auth_config(self) -> dict:
        return self.config.get('auth', {'enabled': False})

    # ── Auth Middleware ───────────────────────────────────────────

    def _setup_auth(self):
        """Setup authentication middleware and security headers"""

        @self.app.before_request
        def check_auth():
            auth_conf = self._auth_config()
            if not auth_conf.get('enabled', False):
                return None

            # Skip auth for login page and socket.io
            if request.path in ('/login',) or request.path.startswith('/socket.io'):
                return None

            # Check session cookie
            session_token = request.cookies.get('session_token')
            if session_token:
                session_info = self.app_state.validate_session(session_token)
                if session_info:
                    # Attach user info to request context
                    request.current_user = session_info
                    return None

            # Not authenticated
            if request.path.startswith('/api/'):
                return jsonify({'error': 'Unauthorized'}), 401
            return redirect('/login')

        @self.app.after_request
        def security_headers(response):
            response.headers['X-Content-Type-Options'] = 'nosniff'
            response.headers['X-Frame-Options'] = 'SAMEORIGIN'
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
        """Perform actual library scan and sync results to SQLite"""
        media_items = []

        if not self.library_path.exists():
            self.logger.warning(f"Library path does not exist: {self.library_path}")
            return media_items

        video_extensions = {'.mp4', '.mkv', '.avi', '.m4v', '.mov'}
        scanned_ids = set()

        for file_path in self.library_path.rglob('*'):
            if file_path.suffix.lower() not in video_extensions:
                continue

            try:
                stat = file_path.stat()
            except OSError:
                continue

            media_id = generate_media_id(str(file_path))
            scanned_ids.add(media_id)

            item = {
                'id': media_id,
                'title': file_path.stem,
                'filename': file_path.name,
                'file_path': str(file_path),
                'file_size': stat.st_size,
                'size_formatted': format_size(stat.st_size),
                'created_at': datetime.fromtimestamp(stat.st_ctime).isoformat(),
                'modified_at': datetime.fromtimestamp(stat.st_mtime).isoformat(),
            }

            # Load metadata JSON
            metadata_file = self.metadata_path / f"{file_path.stem}.json"
            if metadata_file.exists():
                try:
                    with open(metadata_file, 'r') as f:
                        metadata = json.load(f)
                    if 'tmdb' in metadata:
                        tmdb = metadata['tmdb']
                        item['title'] = tmdb.get('title', item['title'])
                        item['year'] = tmdb.get('year')
                        item['overview'] = tmdb.get('overview')
                        item['rating'] = tmdb.get('rating')
                        item['genres'] = tmdb.get('genres', [])
                        item['director'] = tmdb.get('director')
                        item['cast'] = tmdb.get('cast', [])
                        item['tmdb_id'] = tmdb.get('tmdb_id')
                        item['collection_name'] = tmdb.get('collection_name')
                    item['has_metadata'] = True
                except Exception as e:
                    self.logger.error(f"Error loading metadata for {file_path}: {e}")

            # Check for poster
            poster_file = self.thumbnails_path / f"{file_path.stem}_poster.jpg"
            if poster_file.exists():
                item['poster_path'] = str(poster_file)

            # Sync to SQLite
            self.app_state.upsert_media(item)
            media_items.append(item)

        # Remove stale entries (files deleted from disk)
        existing_ids = self.app_state.get_media_ids()
        for stale_id in existing_ids - scanned_ids:
            self.app_state.delete_media(stale_id)

        media_items.sort(key=lambda x: x.get('title', '').lower())
        self.logger.info(f"Scanned library: found {len(media_items)} items")
        return media_items

    def _safe_items(self, items: List[Dict]) -> List[Dict]:
        """Strip internal paths from items before sending to client"""
        safe = []
        for item in items:
            d = {k: v for k, v in item.items() if k not in ('file_path', 'poster_path')}
            d['has_poster'] = bool(item.get('poster_path'))
            safe.append(d)
        return safe

    # ── Range Request Support ────────────────────────────────────

    def _send_file_partial(self, file_path: str, mimetype: str = 'video/mp4'):
        """Send file with HTTP range request support for video seeking"""
        file_size = os.path.getsize(file_path)
        range_header = request.headers.get('Range')

        if range_header:
            match = re.match(r'bytes=(\d+)-(\d*)', range_header)
            if match:
                byte_start = int(match.group(1))
                byte_end = int(match.group(2)) if match.group(2) else file_size - 1
                byte_end = min(byte_end, file_size - 1)
                length = byte_end - byte_start + 1

                with open(file_path, 'rb') as f:
                    f.seek(byte_start)
                    data = f.read(length)

                resp = Response(data, 206, mimetype=mimetype, direct_passthrough=True)
                resp.headers['Content-Range'] = f'bytes {byte_start}-{byte_end}/{file_size}'
                resp.headers['Accept-Ranges'] = 'bytes'
                resp.headers['Content-Length'] = str(length)
                return resp

        resp = make_response(send_file(file_path, mimetype=mimetype))
        resp.headers['Accept-Ranges'] = 'bytes'
        return resp

    # ── Routes ───────────────────────────────────────────────────

    def _setup_routes(self):
        """Setup all Flask routes"""

        # ─── Pages ───

        @self.app.route('/')
        def index():
            return render_template(
                'index.html',
                library_name=self.config['web_server']['library_name'],
                auth_enabled=self._auth_config().get('enabled', False)
            )

        @self.app.route('/login', methods=['GET', 'POST'])
        def login():
            if request.method == 'POST':
                username = request.form.get('username', '').strip()
                password = request.form.get('password', '')
                auth_conf = self._auth_config()

                user = self.app_state.verify_user(username, password)
                if user:
                    session_token = self.app_state.create_session(
                        username=username,
                        hours=auth_conf.get('session_hours', 24)
                    )
                    response = redirect('/')
                    response.set_cookie(
                        'session_token', session_token,
                        httponly=True, samesite='Lax',
                        max_age=auth_conf.get('session_hours', 24) * 3600
                    )
                    self.logger.info(f"User logged in: {username}")
                    return response
                return render_template('login.html', error='Invalid username or password')
            return render_template('login.html')

        @self.app.route('/logout')
        def logout():
            response = redirect('/login')
            response.delete_cookie('session_token')
            return response

        # ─── Library API ───

        @self.app.route('/api/library')
        def api_library():
            items = self.scan_library()
            safe = self._safe_items(items)
            return jsonify({'count': len(safe), 'items': safe})

        @self.app.route('/api/media/<media_id>')
        def api_media(media_id):
            item = self.app_state.get_media(media_id)
            if not item:
                self.scan_library()
                item = self.app_state.get_media(media_id)
            if item:
                safe = {k: v for k, v in item.items() if k not in ('file_path', 'poster_path')}
                safe['has_poster'] = bool(item.get('poster_path'))
                return jsonify(safe)
            return jsonify({'error': 'Not found'}), 404

        @self.app.route('/api/stream/<media_id>')
        def api_stream(media_id):
            item = self.app_state.get_media(media_id)
            if not item:
                self.scan_library()
                item = self.app_state.get_media(media_id)
            if item and item.get('file_path') and os.path.exists(item['file_path']):
                return self._send_file_partial(item['file_path'])
            return jsonify({'error': 'Not found'}), 404

        @self.app.route('/api/download/<media_id>')
        def api_download(media_id):
            item = self.app_state.get_media(media_id)
            if not item:
                self.scan_library()
                item = self.app_state.get_media(media_id)
            if item and item.get('file_path') and os.path.exists(item['file_path']):
                return send_file(
                    item['file_path'],
                    as_attachment=True,
                    download_name=item.get('filename', 'video.mp4')
                )
            return jsonify({'error': 'Not found'}), 404

        @self.app.route('/api/poster/<media_id>')
        def api_poster(media_id):
            item = self.app_state.get_media(media_id)
            if not item:
                self.scan_library()
                item = self.app_state.get_media(media_id)
            if item and item.get('poster_path') and os.path.exists(item['poster_path']):
                return send_file(item['poster_path'], mimetype='image/jpeg')
            return '', 404

        @self.app.route('/api/search')
        def api_search():
            query = request.args.get('q', '').strip()
            if not query:
                items = self.scan_library()
            else:
                self.scan_library()  # ensure DB is populated
                items = self.app_state.search_media(query.lower())
            safe = self._safe_items(items)
            return jsonify({'query': query, 'count': len(safe), 'items': safe})

        @self.app.route('/api/scan', methods=['POST'])
        def api_scan():
            items = self.scan_library(force=True)
            self.app_state.broadcast('library_updated', {'count': len(items)})
            return jsonify({'status': 'completed', 'count': len(items)})

        # ─── Metadata Editing ───

        @self.app.route('/api/media/<media_id>/metadata', methods=['PUT'])
        def api_update_metadata(media_id):
            data = request.get_json()
            if not data:
                return jsonify({'error': 'No data provided'}), 400

            success = self.app_state.update_media_metadata(media_id, data)
            if not success:
                return jsonify({'error': 'Media not found or no valid fields'}), 404

            # Also update the metadata JSON file on disk
            item = self.app_state.get_media(media_id)
            if item:
                stem = Path(item.get('filename', '')).stem
                metadata_file = self.metadata_path / f"{stem}.json"
                if metadata_file.exists():
                    try:
                        with open(metadata_file, 'r') as f:
                            file_meta = json.load(f)
                        if 'tmdb' not in file_meta:
                            file_meta['tmdb'] = {}

                        field_map = {
                            'title': 'title', 'year': 'year', 'overview': 'overview',
                            'director': 'director', 'rating': 'rating',
                            'genres': 'genres', 'cast_members': 'cast'
                        }
                        for api_key, tmdb_key in field_map.items():
                            if api_key in data:
                                file_meta['tmdb'][tmdb_key] = data[api_key]

                        with open(metadata_file, 'w') as f:
                            json.dump(file_meta, f, indent=2, ensure_ascii=False)
                    except Exception as e:
                        self.logger.error(f"Error updating metadata file: {e}")

            self._cache = None  # Invalidate cache
            return jsonify({'status': 'updated'})

        # ─── Jobs API ───

        @self.app.route('/api/jobs')
        def api_jobs():
            jobs = self.app_state.get_all_jobs()
            return jsonify({'jobs': jobs})

        @self.app.route('/api/jobs', methods=['POST'])
        def api_create_job():
            data = request.get_json()
            if not data or 'source_path' not in data:
                return jsonify({'error': 'source_path required'}), 400

            job_id = self.app_state.create_job(
                title=data.get('title', Path(data['source_path']).name),
                source_path=data['source_path'],
                title_number=data.get('title_number', 1)
            )
            return jsonify({'id': job_id, 'status': 'queued'}), 201

        @self.app.route('/api/jobs/<job_id>', methods=['DELETE'])
        def api_cancel_job(job_id):
            if self.app_state.cancel_job(job_id):
                return jsonify({'status': 'cancelled'})
            return jsonify({'error': 'Cannot cancel this job'}), 400

        @self.app.route('/api/jobs/<job_id>/retry', methods=['POST'])
        def api_retry_job(job_id):
            new_id = self.app_state.retry_job(job_id)
            if new_id:
                return jsonify({'id': new_id, 'status': 'queued'}), 201
            return jsonify({'error': 'Cannot retry this job'}), 400

        # ─── Collections API ───

        @self.app.route('/api/collections')
        def api_collections():
            collections = self.app_state.get_all_collections()
            # Sanitize paths in collection items
            for col in collections:
                col['items'] = self._safe_items(col.get('items', []))
            return jsonify({'collections': collections})

        @self.app.route('/api/collections/<name>', methods=['PUT'])
        def api_update_collection(name):
            data = request.get_json()
            if not data or 'media_ids' not in data:
                return jsonify({'error': 'media_ids required'}), 400
            self.app_state.update_collection(name, data['media_ids'])
            return jsonify({'status': 'updated'})

        @self.app.route('/api/collections/<name>', methods=['DELETE'])
        def api_delete_collection(name):
            if self.app_state.delete_collection(name):
                return jsonify({'status': 'deleted'})
            return jsonify({'error': 'Collection not found'}), 404

        # ─── User Management API (admin only) ───

        def _require_admin():
            """Check that the current request is from an admin user"""
            user = getattr(request, 'current_user', None)
            if not user or user.get('role') != 'admin':
                return False
            return True

        @self.app.route('/api/users')
        def api_users():
            if not _require_admin():
                return jsonify({'error': 'Admin access required'}), 403
            users = self.app_state.list_users()
            return jsonify({'users': users})

        @self.app.route('/api/users', methods=['POST'])
        def api_create_user():
            if not _require_admin():
                return jsonify({'error': 'Admin access required'}), 403
            data = request.get_json()
            if not data or not data.get('username') or not data.get('password'):
                return jsonify({'error': 'username and password required'}), 400
            role = data.get('role', 'user')
            if role not in ('admin', 'user'):
                return jsonify({'error': 'role must be admin or user'}), 400
            if self.app_state.create_user(data['username'], data['password'], role):
                return jsonify({'status': 'created', 'username': data['username']}), 201
            return jsonify({'error': 'User already exists'}), 409

        @self.app.route('/api/users/<username>', methods=['DELETE'])
        def api_delete_user(username):
            if not _require_admin():
                return jsonify({'error': 'Admin access required'}), 403
            # Prevent deleting yourself
            current = getattr(request, 'current_user', {})
            if current.get('username') == username:
                return jsonify({'error': 'Cannot delete your own account'}), 400
            if self.app_state.delete_user(username):
                return jsonify({'status': 'deleted'})
            return jsonify({'error': 'User not found'}), 404

        @self.app.route('/api/users/<username>/password', methods=['PUT'])
        def api_update_password(username):
            """Admin can change any password; users can change their own"""
            current = getattr(request, 'current_user', {})
            if current.get('role') != 'admin' and current.get('username') != username:
                return jsonify({'error': 'Forbidden'}), 403
            data = request.get_json()
            if not data or not data.get('password'):
                return jsonify({'error': 'password required'}), 400
            if self.app_state.update_user_password(username, data['password']):
                return jsonify({'status': 'updated'})
            return jsonify({'error': 'User not found'}), 404

        @self.app.route('/api/me')
        def api_me():
            """Get current user info"""
            user = getattr(request, 'current_user', None)
            if user:
                return jsonify(user)
            return jsonify({'username': None, 'role': 'anonymous'})

    # ── WebSocket ────────────────────────────────────────────────

    def _setup_socketio(self):
        """Setup WebSocket event handlers"""

        @self.socketio.on('connect')
        def handle_connect():
            auth_conf = self._auth_config()
            if auth_conf.get('enabled', False):
                token = request.cookies.get('session_token')
                if not token or not self.app_state.validate_session(token):
                    return False  # Reject connection

            self.logger.debug("WebSocket client connected")

            # Send current active job state if any
            active_job = self.app_state.get_active_job()
            if active_job:
                emit('job_update', active_job)

        @self.socketio.on('disconnect')
        def handle_disconnect():
            self.logger.debug("WebSocket client disconnected")

        @self.socketio.on('request_library')
        def handle_request_library():
            items = self.scan_library()
            safe = self._safe_items(items)
            emit('library_data', {'count': len(safe), 'items': safe})

    # ── Server Start ─────────────────────────────────────────────

    def run(self, host: str = None, port: int = None):
        """Start the web server with WebSocket support"""
        host = host or self.config['web_server']['host']
        port = port or self.config['web_server']['port']

        self.logger.info(f"Starting web server on {host}:{port}")

        print(f"\n🌐 Media Server starting...")
        print(f"📚 Library: {self.library_path}")
        print(f"🔗 URL: http://{host if host != '0.0.0.0' else 'localhost'}:{port}")
        print(f"🔌 WebSocket: enabled")
        print(f"🔒 Auth: {'enabled' if self._auth_config().get('enabled') else 'disabled'}")
        print(f"\nPress Ctrl+C to stop\n")

        # Initial library scan
        self.scan_library(force=True)

        self.socketio.run(
            self.app, host=host, port=int(port),
            debug=False, allow_unsafe_werkzeug=True
        )


def main():
    """Standalone entry point for the web server only"""
    import argparse

    parser = argparse.ArgumentParser(description='Start media library web server')
    parser.add_argument('--host', help='Host address')
    parser.add_argument('--port', type=int, help='Port number')
    parser.add_argument('--config', default='config.json', help='Path to config file')
    args = parser.parse_args()

    app_state = AppState()
    server = MediaServer(config_path=args.config, app_state=app_state)
    server.run(host=args.host, port=args.port)


if __name__ == '__main__':
    main()
