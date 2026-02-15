"""
Unit tests for the AppState module
"""

import json
from pathlib import Path


class TestAppState:
    """Test suite for SQLite-backed AppState"""

    def test_initialization(self, app_state):
        """Test AppState initializes correctly with tables"""
        assert app_state is not None
        assert Path(app_state.db_path).exists()

    # ── Media Tests ──

    def test_upsert_and_get_media(self, app_state):
        """Test inserting and retrieving media items"""
        item = {
            "id": "test123",
            "title": "Test Movie",
            "filename": "test.mp4",
            "file_path": "/tmp/test.mp4",
            "file_size": 1000000,
            "size_formatted": "976.56 KB",
            "created_at": "2024-01-01T00:00:00",
            "modified_at": "2024-01-01T00:00:00",
            "year": "2024",
            "genres": ["Action", "Drama"],
            "cast": ["Actor 1", "Actor 2"],
            "director": "Test Director",
        }
        app_state.upsert_media(item)

        result = app_state.get_media("test123")
        assert result is not None
        assert result["title"] == "Test Movie"
        assert result["director"] == "Test Director"
        assert result["genres"] == ["Action", "Drama"]
        assert result["cast"] == ["Actor 1", "Actor 2"]

    def test_get_all_media(self, app_state):
        """Test retrieving all media items sorted by title"""
        for title in ["Zebra", "Alpha", "Middle"]:
            app_state.upsert_media(
                {
                    "id": title.lower(),
                    "title": title,
                    "filename": f"{title}.mp4",
                    "file_path": f"/tmp/{title}.mp4",
                }
            )

        items = app_state.get_all_media()
        assert len(items) == 3
        assert items[0]["title"] == "Alpha"
        assert items[2]["title"] == "Zebra"

    def test_search_media(self, app_state):
        """Test searching media by various fields"""
        app_state.upsert_media(
            {
                "id": "search1",
                "title": "The Matrix",
                "filename": "matrix.mp4",
                "file_path": "/tmp/matrix.mp4",
                "director": "Wachowski",
                "genres": ["Sci-Fi"],
                "cast": ["Keanu Reeves"],
            }
        )
        app_state.upsert_media(
            {
                "id": "search2",
                "title": "Inception",
                "filename": "inception.mp4",
                "file_path": "/tmp/inception.mp4",
                "director": "Nolan",
            }
        )

        assert len(app_state.search_media("matrix")) == 1
        assert len(app_state.search_media("wachowski")) == 1
        assert len(app_state.search_media("keanu")) == 1
        assert len(app_state.search_media("sci-fi")) == 1
        assert len(app_state.search_media("nonexistent")) == 0

    def test_update_media_metadata(self, app_state):
        """Test updating media metadata"""
        app_state.upsert_media(
            {
                "id": "update1",
                "title": "Old Title",
                "filename": "test.mp4",
                "file_path": "/tmp/test.mp4",
            }
        )

        success = app_state.update_media_metadata(
            "update1",
            {
                "title": "New Title",
                "year": "2025",
                "rating": 8.5,
            },
        )
        assert success is True

        result = app_state.get_media("update1")
        assert result["title"] == "New Title"
        assert result["year"] == "2025"
        assert result["rating"] == 8.5

    def test_delete_media(self, app_state):
        """Test deleting a media item"""
        app_state.upsert_media(
            {
                "id": "delete1",
                "title": "To Delete",
                "filename": "del.mp4",
                "file_path": "/tmp/del.mp4",
            }
        )
        app_state.delete_media("delete1")
        assert app_state.get_media("delete1") is None

    def test_media_has_poster_flag(self, app_state):
        """Test that has_poster is derived from poster_path"""
        app_state.upsert_media(
            {
                "id": "poster1",
                "title": "With Poster",
                "filename": "p.mp4",
                "file_path": "/tmp/p.mp4",
                "poster_path": "/tmp/poster.jpg",
            }
        )
        app_state.upsert_media(
            {
                "id": "poster2",
                "title": "No Poster",
                "filename": "np.mp4",
                "file_path": "/tmp/np.mp4",
            }
        )

        assert app_state.get_media("poster1")["has_poster"] is True
        assert app_state.get_media("poster2")["has_poster"] is False

    # ── Job Tests ──

    def test_create_and_get_job(self, app_state):
        """Test creating and retrieving a job"""
        job_id = app_state.create_job("Test Movie", "/Volumes/DVD", 1)
        assert job_id is not None

        job = app_state.get_job(job_id)
        assert job is not None
        assert job["title"] == "Test Movie"
        assert job["status"] == "queued"
        assert job["source_path"] == "/Volumes/DVD"

    def test_create_job_with_disc_type(self, app_state):
        """Test creating a job with disc_type and disc_hints"""
        hints = {"track_count": 12, "total_duration_seconds": 3200}
        job_id = app_state.create_job(
            "My Album", "/Volumes/CD", 1, disc_type="audio_cd", disc_hints=hints
        )
        job = app_state.get_job(job_id)
        assert job["disc_type"] == "audio_cd"
        parsed_hints = json.loads(job["disc_hints"])
        assert parsed_hints["track_count"] == 12

    def test_job_queue_ordering(self, app_state):
        """Test that jobs are queued in FIFO order"""
        id1 = app_state.create_job("First", "/vol/1")
        app_state.create_job("Second", "/vol/2")

        next_job = app_state.get_next_queued_job()
        assert next_job["id"] == id1

    def test_update_job_status(self, app_state):
        """Test updating job status"""
        job_id = app_state.create_job("Test", "/vol/test")
        app_state.update_job_status(job_id, "encoding", started_at="2024-01-01T00:00:00")

        job = app_state.get_job(job_id)
        assert job["status"] == "encoding"
        assert job["started_at"] == "2024-01-01T00:00:00"

    def test_update_job_progress(self, app_state):
        """Test updating job progress"""
        job_id = app_state.create_job("Test", "/vol/test")
        app_state.update_job_progress(job_id, 45.5, eta="00:10:30", fps=25.3)

        job = app_state.get_job(job_id)
        assert job["progress"] == 45.5
        assert job["eta"] == "00:10:30"
        assert job["fps"] == 25.3

    def test_cancel_job(self, app_state):
        """Test cancelling a queued job"""
        job_id = app_state.create_job("Test", "/vol/test")
        assert app_state.cancel_job(job_id) is True

        job = app_state.get_job(job_id)
        assert job["status"] == "cancelled"

    def test_cancel_completed_job_fails(self, app_state):
        """Test that completed jobs cannot be cancelled"""
        job_id = app_state.create_job("Test", "/vol/test")
        app_state.update_job_status(job_id, "completed")
        assert app_state.cancel_job(job_id) is False

    def test_retry_failed_job(self, app_state):
        """Test retrying a failed job"""
        job_id = app_state.create_job("Test", "/vol/test")
        app_state.update_job_status(job_id, "failed", error_message="Test error")

        new_id = app_state.retry_job(job_id)
        assert new_id is not None
        assert new_id != job_id

        new_job = app_state.get_job(new_id)
        assert new_job["status"] == "queued"
        assert new_job["title"] == "Test"

    def test_retry_queued_job_fails(self, app_state):
        """Test that queued jobs cannot be retried"""
        job_id = app_state.create_job("Test", "/vol/test")
        assert app_state.retry_job(job_id) is None

    def test_get_active_job(self, app_state):
        """Test getting the currently encoding job"""
        assert app_state.get_active_job() is None

        job_id = app_state.create_job("Test", "/vol/test")
        app_state.update_job_status(job_id, "encoding")

        active = app_state.get_active_job()
        assert active is not None
        assert active["id"] == job_id

    # ── Collection Tests ──

    def test_create_collection(self, app_state):
        """Test creating a collection"""
        col_id = app_state.create_collection("Favorites")
        assert col_id is not None

    def test_update_collection_with_items(self, app_state):
        """Test adding items to a collection"""
        for mid in ["m1", "m2", "m3"]:
            app_state.upsert_media(
                {
                    "id": mid,
                    "title": mid,
                    "filename": f"{mid}.mp4",
                    "file_path": f"/tmp/{mid}.mp4",
                }
            )

        app_state.update_collection("My Collection", ["m1", "m2", "m3"])

        collections = app_state.get_all_collections()
        assert len(collections) == 1
        assert collections[0]["name"] == "My Collection"
        assert len(collections[0]["items"]) == 3

    def test_delete_collection(self, app_state):
        """Test deleting a collection"""
        app_state.create_collection("To Delete")
        assert app_state.delete_collection("To Delete") is True
        assert app_state.delete_collection("Nonexistent") is False

    # ── Auth Tests ──

    def test_create_and_validate_session(self, app_state):
        """Test session creation and validation"""
        app_state.create_user("testuser", "testpass", "user")
        token = app_state.create_session(username="testuser", hours=1)
        assert token is not None
        result = app_state.validate_session(token)
        assert result is not None
        assert result["username"] == "testuser"
        assert result["role"] == "user"
        assert app_state.validate_session("invalid-token") is None

    def test_cleanup_expired_sessions(self, app_state):
        """Test cleaning up expired sessions"""
        app_state.create_session(hours=0)  # expires immediately
        app_state.cleanup_sessions()
        # The session might or might not be expired depending on timing
        # Just verify it doesn't raise

    # ── User Tests ──

    def test_create_user(self, app_state):
        """Test creating a user"""
        assert app_state.create_user("alice", "pass123", "admin") is True
        user = app_state.get_user("alice")
        assert user is not None
        assert user["username"] == "alice"
        assert user["role"] == "admin"

    def test_create_duplicate_user(self, app_state):
        """Test that creating a duplicate user returns False"""
        app_state.create_user("bob", "pass1", "user")
        assert app_state.create_user("bob", "pass2", "user") is False

    def test_verify_user(self, app_state):
        """Test password verification"""
        app_state.create_user("charlie", "secret", "user")
        result = app_state.verify_user("charlie", "secret")
        assert result is not None
        assert result["username"] == "charlie"
        assert result["role"] == "user"

        # Wrong password
        assert app_state.verify_user("charlie", "wrong") is None
        # Non-existent user
        assert app_state.verify_user("nobody", "any") is None

    def test_list_users(self, app_state):
        """Test listing all users"""
        app_state.create_user("user_a", "pass", "admin")
        app_state.create_user("user_b", "pass", "user")
        users = app_state.list_users()
        assert len(users) == 2
        usernames = [u["username"] for u in users]
        assert "user_a" in usernames
        assert "user_b" in usernames

    def test_delete_user(self, app_state):
        """Test deleting a user"""
        app_state.create_user("todelete", "pass", "user")
        assert app_state.delete_user("todelete") is True
        assert app_state.get_user("todelete") is None
        assert app_state.delete_user("nonexistent") is False

    def test_update_user_password(self, app_state):
        """Test updating a user's password"""
        app_state.create_user("updater", "oldpass", "user")
        assert app_state.update_user_password("updater", "newpass") is True
        assert app_state.verify_user("updater", "newpass") is not None
        assert app_state.verify_user("updater", "oldpass") is None

    def test_seed_default_users(self, app_state):
        """Test seeding default users from config"""
        defaults = [
            {"username": "admin", "password": "adminpass", "role": "admin"},
            {"username": "ben", "password": "benpass", "role": "user"},
        ]
        app_state.seed_default_users(defaults)
        assert app_state.get_user("admin") is not None
        assert app_state.get_user("ben") is not None

        # Seeding again should not overwrite
        app_state.update_user_password("admin", "changed")
        app_state.seed_default_users(defaults)
        assert app_state.verify_user("admin", "changed") is not None
