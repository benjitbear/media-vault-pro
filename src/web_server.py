"""
Web server for browsing and streaming the media library
"""
import os
import json
from pathlib import Path
from typing import List, Dict, Any
from flask import Flask, render_template_string, jsonify, send_file, request, Response
from datetime import datetime

from .utils import load_config, setup_logger, format_size, format_time


class MediaServer:
    """Web server for media library access"""
    
    def __init__(self, config_path: str = "config.json"):
        """
        Initialize the MediaServer
        
        Args:
            config_path: Path to configuration file
        """
        self.config = load_config(config_path)
        self.logger = setup_logger('web_server', 'web_server.log')
        
        self.library_path = Path(self.config['output']['base_directory'])
        self.metadata_path = self.library_path.parent / 'data' / 'metadata'
        self.thumbnails_path = self.library_path.parent / 'data' / 'thumbnails'
        
        self.app = Flask(__name__)
        self.setup_routes()
        
        self.logger.info("MediaServer initialized")
    
    def scan_library(self) -> List[Dict[str, Any]]:
        """
        Scan the media library directory
        
        Returns:
            List of media items
        """
        media_items = []
        
        if not self.library_path.exists():
            self.logger.warning(f"Library path does not exist: {self.library_path}")
            return media_items
        
        # Scan for video files
        video_extensions = {'.mp4', '.mkv', '.avi', '.m4v', '.mov'}
        
        for file_path in self.library_path.rglob('*'):
            if file_path.suffix.lower() in video_extensions:
                # Get file info
                stat = file_path.stat()
                
                item = {
                    'id': str(hash(file_path)),
                    'title': file_path.stem,
                    'filename': file_path.name,
                    'path': str(file_path),
                    'size': stat.st_size,
                    'size_formatted': format_size(stat.st_size),
                    'created': datetime.fromtimestamp(stat.st_ctime).isoformat(),
                    'modified': datetime.fromtimestamp(stat.st_mtime).isoformat()
                }
                
                # Try to load metadata
                metadata_file = self.metadata_path / f"{file_path.stem}.json"
                if metadata_file.exists():
                    try:
                        with open(metadata_file, 'r') as f:
                            metadata = json.load(f)
                            item['metadata'] = metadata
                            
                            # Extract useful fields to top level
                            if 'tmdb' in metadata:
                                tmdb = metadata['tmdb']
                                item['title'] = tmdb.get('title', item['title'])
                                item['year'] = tmdb.get('year')
                                item['overview'] = tmdb.get('overview')
                                item['rating'] = tmdb.get('rating')
                                item['genres'] = tmdb.get('genres', [])
                                item['director'] = tmdb.get('director')
                                item['cast'] = tmdb.get('cast', [])
                    except Exception as e:
                        self.logger.error(f"Error loading metadata for {file_path}: {e}")
                
                # Check for poster
                poster_file = self.thumbnails_path / f"{file_path.stem}_poster.jpg"
                if poster_file.exists():
                    item['poster'] = str(poster_file)
                
                media_items.append(item)
        
        # Sort by title
        media_items.sort(key=lambda x: x['title'].lower())
        
        self.logger.info(f"Scanned library: found {len(media_items)} items")
        return media_items
    
    def setup_routes(self):
        """Setup Flask routes"""
        
        @self.app.route('/')
        def index():
            """Main library page"""
            return render_template_string(HTML_TEMPLATE, 
                                         library_name=self.config['web_server']['library_name'])
        
        @self.app.route('/api/library')
        def api_library():
            """Get library contents"""
            items = self.scan_library()
            return jsonify({
                'count': len(items),
                'items': items
            })
        
        @self.app.route('/api/media/<media_id>')
        def api_media(media_id):
            """Get specific media details"""
            items = self.scan_library()
            for item in items:
                if item['id'] == media_id:
                    return jsonify(item)
            return jsonify({'error': 'Not found'}), 404
        
        @self.app.route('/api/stream/<media_id>')
        def api_stream(media_id):
            """Stream video file"""
            items = self.scan_library()
            for item in items:
                if item['id'] == media_id:
                    file_path = item['path']
                    if os.path.exists(file_path):
                        return send_file(file_path, mimetype='video/mp4')
            return jsonify({'error': 'Not found'}), 404
        
        @self.app.route('/api/poster/<media_id>')
        def api_poster(media_id):
            """Get poster image"""
            items = self.scan_library()
            for item in items:
                if item['id'] == media_id and 'poster' in item:
                    poster_path = item['poster']
                    if os.path.exists(poster_path):
                        return send_file(poster_path, mimetype='image/jpeg')
            return '', 404
        
        @self.app.route('/api/search')
        def api_search():
            """Search library"""
            query = request.args.get('q', '').lower()
            items = self.scan_library()
            
            if not query:
                return jsonify({'items': items})
            
            # Search in title, director, cast, genres
            results = []
            for item in items:
                if query in item['title'].lower():
                    results.append(item)
                elif 'director' in item and item['director'] and query in item['director'].lower():
                    results.append(item)
                elif 'cast' in item and any(query in actor.lower() for actor in item.get('cast', [])):
                    results.append(item)
                elif 'genres' in item and any(query in genre.lower() for genre in item.get('genres', [])):
                    results.append(item)
            
            return jsonify({
                'query': query,
                'count': len(results),
                'items': results
            })
        
        @self.app.route('/api/scan')
        def api_scan():
            """Trigger library rescan"""
            items = self.scan_library()
            return jsonify({
                'status': 'completed',
                'count': len(items)
            })
    
    def run(self, host: str = None, port: int = None):
        """
        Start the web server
        
        Args:
            host: Host address (default from config)
            port: Port number (default from config)
        """
        host = host or self.config['web_server']['host']
        port = port or self.config['web_server']['port']
        
        self.logger.info(f"Starting web server on {host}:{port}")
        
        print(f"🌐 Media Server starting...")
        print(f"📚 Library: {self.library_path}")
        print(f"🔗 URL: http://{host if host != '0.0.0.0' else 'localhost'}:{port}")
        print(f"\nPress Ctrl+C to stop\n")
        
        self.app.run(host=host, port=port, debug=False)


# HTML Template for the web interface
HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{{ library_name }}</title>
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body {
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            background: #1a1a1a;
            color: #fff;
            padding: 20px;
        }
        .header {
            text-align: center;
            padding: 40px 20px;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            border-radius: 10px;
            margin-bottom: 30px;
        }
        .header h1 { font-size: 2.5em; margin-bottom: 10px; }
        .header p { opacity: 0.9; }
        .search-bar {
            max-width: 600px;
            margin: 0 auto 30px;
            position: relative;
        }
        .search-bar input {
            width: 100%;
            padding: 15px 20px;
            font-size: 16px;
            border: none;
            border-radius: 25px;
            background: #2a2a2a;
            color: #fff;
        }
        .media-grid {
            display: grid;
            grid-template-columns: repeat(auto-fill, minmax(200px, 1fr));
            gap: 20px;
            max-width: 1400px;
            margin: 0 auto;
        }
        .media-item {
            background: #2a2a2a;
            border-radius: 10px;
            overflow: hidden;
            cursor: pointer;
            transition: transform 0.2s;
        }
        .media-item:hover { transform: translateY(-5px); }
        .media-poster {
            width: 100%;
            height: 300px;
            background: #333;
            display: flex;
            align-items: center;
            justify-content: center;
            font-size: 60px;
        }
        .media-poster img {
            width: 100%;
            height: 100%;
            object-fit: cover;
        }
        .media-info {
            padding: 15px;
        }
        .media-title {
            font-size: 1.1em;
            font-weight: 600;
            margin-bottom: 5px;
            white-space: nowrap;
            overflow: hidden;
            text-overflow: ellipsis;
        }
        .media-meta {
            font-size: 0.9em;
            color: #999;
        }
        .loading {
            text-align: center;
            padding: 50px;
            font-size: 1.2em;
        }
        .empty {
            text-align: center;
            padding: 100px 20px;
        }
        .empty h2 { margin-bottom: 10px; opacity: 0.5; }
        .modal {
            display: none;
            position: fixed;
            top: 0;
            left: 0;
            width: 100%;
            height: 100%;
            background: rgba(0,0,0,0.9);
            z-index: 1000;
            overflow-y: auto;
        }
        .modal-content {
            max-width: 1000px;
            margin: 50px auto;
            background: #2a2a2a;
            border-radius: 10px;
            overflow: hidden;
        }
        .modal-video {
            width: 100%;
            background: #000;
        }
        .modal-info {
            padding: 30px;
        }
        .modal-close {
            position: absolute;
            top: 20px;
            right: 20px;
            font-size: 40px;
            color: #fff;
            cursor: pointer;
            z-index: 1001;
        }
    </style>
</head>
<body>
    <div class="header">
        <h1>🎬 {{ library_name }}</h1>
        <p id="library-count">Loading library...</p>
    </div>
    
    <div class="search-bar">
        <input type="text" id="search" placeholder="🔍 Search movies..." onkeyup="searchLibrary()">
    </div>
    
    <div id="media-grid" class="media-grid">
        <div class="loading">Loading your library...</div>
    </div>
    
    <div id="modal" class="modal" onclick="closeModal()">
        <span class="modal-close">×</span>
        <div class="modal-content" onclick="event.stopPropagation()">
            <video id="modal-video" class="modal-video" controls></video>
            <div class="modal-info" id="modal-info"></div>
        </div>
    </div>
    
    <script>
        let libraryData = [];
        
        async function loadLibrary() {
            try {
                const response = await fetch('/api/library');
                const data = await response.json();
                libraryData = data.items;
                displayLibrary(libraryData);
                document.getElementById('library-count').textContent = 
                    `${data.count} movie${data.count !== 1 ? 's' : ''} in your collection`;
            } catch (error) {
                document.getElementById('media-grid').innerHTML = 
                    '<div class="empty"><h2>Error loading library</h2></div>';
            }
        }
        
        function displayLibrary(items) {
            const grid = document.getElementById('media-grid');
            
            if (items.length === 0) {
                grid.innerHTML = `
                    <div class="empty">
                        <h2>📀 No media found</h2>
                        <p>Insert a disc to start building your library</p>
                    </div>
                `;
                return;
            }
            
            grid.innerHTML = items.map(item => `
                <div class="media-item" onclick="showMedia('${item.id}')">
                    <div class="media-poster">
                        ${item.poster ? 
                            `<img src="/api/poster/${item.id}" alt="${item.title}">` : 
                            '🎬'}
                    </div>
                    <div class="media-info">
                        <div class="media-title">${item.title}</div>
                        <div class="media-meta">
                            ${item.year || ''} ${item.size_formatted ? '• ' + item.size_formatted : ''}
                        </div>
                    </div>
                </div>
            `).join('');
        }
        
        function searchLibrary() {
            const query = document.getElementById('search').value.toLowerCase();
            if (!query) {
                displayLibrary(libraryData);
                return;
            }
            
            const filtered = libraryData.filter(item => 
                item.title.toLowerCase().includes(query) ||
                (item.director && item.director.toLowerCase().includes(query)) ||
                (item.cast && item.cast.some(actor => actor.toLowerCase().includes(query))) ||
                (item.genres && item.genres.some(genre => genre.toLowerCase().includes(query)))
            );
            
            displayLibrary(filtered);
        }
        
        async function showMedia(id) {
            try {
                const response = await fetch(`/api/media/${id}`);
                const item = await response.json();
                
                const modal = document.getElementById('modal');
                const video = document.getElementById('modal-video');
                const info = document.getElementById('modal-info');
                
                video.src = `/api/stream/${id}`;
                
                info.innerHTML = `
                    <h2>${item.title} ${item.year ? `(${item.year})` : ''}</h2>
                    ${item.rating ? `<p>⭐ ${item.rating}/10</p>` : ''}
                    ${item.director ? `<p><strong>Director:</strong> ${item.director}</p>` : ''}
                    ${item.cast ? `<p><strong>Cast:</strong> ${item.cast.slice(0, 5).join(', ')}</p>` : ''}
                    ${item.genres ? `<p><strong>Genres:</strong> ${item.genres.join(', ')}</p>` : ''}
                    ${item.overview ? `<p style="margin-top: 15px;">${item.overview}</p>` : ''}
                    <p style="margin-top: 15px; color: #666;"><strong>File:</strong> ${item.filename}</p>
                `;
                
                modal.style.display = 'block';
            } catch (error) {
                console.error('Error loading media:', error);
            }
        }
        
        function closeModal() {
            const modal = document.getElementById('modal');
            const video = document.getElementById('modal-video');
            video.pause();
            video.src = '';
            modal.style.display = 'none';
        }
        
        // Load library on page load
        loadLibrary();
    </script>
</body>
</html>
"""


def main():
    """Main entry point"""
    import argparse
    
    parser = argparse.ArgumentParser(description='Start media library web server')
    parser.add_argument('--host', help='Host address')
    parser.add_argument('--port', type=int, help='Port number')
    parser.add_argument('--config', default='config.json', help='Path to config file')
    
    args = parser.parse_args()
    
    server = MediaServer(config_path=args.config)
    server.run(host=args.host, port=args.port)


if __name__ == '__main__':
    main()
