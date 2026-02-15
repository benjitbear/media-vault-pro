"""Tests for TMDBClient — search, title cleaning, image download, disambiguation."""

import pytest
from unittest.mock import patch, MagicMock
from src.clients.tmdb_client import TMDBClient


@pytest.fixture
def client():
    return TMDBClient(api_key="fake-key")


@pytest.fixture
def client_no_key():
    return TMDBClient(api_key=None)


# ── search_tmdb ──────────────────────────────────────────────────


class TestSearchTmdb:
    def test_no_api_key_returns_none(self, client_no_key):
        assert client_no_key.search_tmdb("The Matrix") is None

    @patch("requests.get")
    def test_successful_search(self, mock_get, client):
        search_resp = MagicMock()
        search_resp.json.return_value = {"results": [{"id": 603, "title": "The Matrix"}]}
        detail_resp = MagicMock()
        detail_resp.json.return_value = {
            "title": "The Matrix",
            "original_title": "The Matrix",
            "release_date": "1999-03-31",
            "overview": "A hacker...",
            "runtime": 136,
            "genres": [{"name": "Action"}],
            "vote_average": 8.7,
            "poster_path": "/poster.jpg",
            "backdrop_path": "/backdrop.jpg",
            "belongs_to_collection": {"name": "The Matrix Collection"},
        }
        credits_resp = MagicMock()
        credits_resp.json.return_value = {
            "crew": [
                {"name": "Lana Wachowski", "job": "Director"},
                {"name": "Editor", "job": "Editor"},
            ],
            "cast": [{"name": f"Actor{i}"} for i in range(12)],
        }
        mock_get.side_effect = [search_resp, detail_resp, credits_resp]

        result = client.search_tmdb("The_Matrix")
        assert result is not None
        assert result["title"] == "The Matrix"
        assert result["year"] == "1999"
        assert result["runtime_minutes"] == 136
        assert result["director"] == "Lana Wachowski"
        assert len(result["cast"]) == 10
        assert result["collection_name"] == "The Matrix Collection"
        assert result["genres"] == ["Action"]

    @patch("requests.get")
    def test_no_results_tries_fallback(self, mock_get, client):
        empty_resp = MagicMock()
        empty_resp.json.return_value = {"results": []}
        fallback_resp = MagicMock()
        fallback_resp.json.return_value = {"results": []}
        mock_get.side_effect = [empty_resp, fallback_resp]

        result = client.search_tmdb("SOME_DVD_2023_DISC1")
        assert result is None
        assert mock_get.call_count == 2

    @patch("requests.get")
    def test_fallback_finds_result(self, mock_get, client):
        empty_resp = MagicMock()
        empty_resp.json.return_value = {"results": []}
        fallback_resp = MagicMock()
        fallback_resp.json.return_value = {"results": [{"id": 100, "title": "Some Movie"}]}
        detail_resp = MagicMock()
        detail_resp.json.return_value = {
            "title": "Some Movie",
            "original_title": "Some",
            "release_date": "2023-01-01",
            "overview": "",
            "runtime": 90,
            "genres": [],
            "vote_average": 6.0,
            "poster_path": None,
            "backdrop_path": None,
            "belongs_to_collection": None,
        }
        credits_resp = MagicMock()
        credits_resp.json.return_value = {"crew": [], "cast": []}
        mock_get.side_effect = [empty_resp, fallback_resp, detail_resp, credits_resp]

        result = client.search_tmdb("SOME_DVD_2023_DISC1")
        assert result is not None
        assert result["title"] == "Some Movie"
        assert result["director"] is None
        assert result["cast"] == []

    @patch("requests.get")
    def test_no_collection(self, mock_get, client):
        search_resp = MagicMock()
        search_resp.json.return_value = {"results": [{"id": 1}]}
        detail_resp = MagicMock()
        detail_resp.json.return_value = {
            "title": "Solo",
            "original_title": "Solo",
            "release_date": "",
            "overview": "",
            "runtime": 100,
            "genres": [],
            "vote_average": 5.0,
            "poster_path": None,
            "backdrop_path": None,
            "belongs_to_collection": None,
        }
        credits_resp = MagicMock()
        credits_resp.json.return_value = {}
        mock_get.side_effect = [search_resp, detail_resp, credits_resp]

        result = client.search_tmdb("Solo")
        assert result["year"] is None
        assert result["collection_name"] is None

    @patch("requests.get")
    def test_request_exception_returns_none(self, mock_get, client):
        mock_get.side_effect = Exception("Network error")
        result = client.search_tmdb("Anything")
        assert result is None

    @patch("requests.get")
    def test_search_with_year(self, mock_get, client):
        search_resp = MagicMock()
        search_resp.json.return_value = {"results": [{"id": 42}]}
        detail_resp = MagicMock()
        detail_resp.json.return_value = {
            "title": "Movie",
            "original_title": "Movie",
            "release_date": "2020-06-15",
            "overview": "",
            "runtime": 120,
            "genres": [],
            "vote_average": 7.0,
            "poster_path": None,
            "backdrop_path": None,
            "belongs_to_collection": None,
        }
        credits_resp = MagicMock()
        credits_resp.json.return_value = {}
        mock_get.side_effect = [search_resp, detail_resp, credits_resp]

        result = client.search_tmdb("Movie", year=2020)
        assert result["year"] == "2020"
        call_params = mock_get.call_args_list[0][1]["params"]
        assert call_params["year"] == 2020


# ── Title cleaning ───────────────────────────────────────────────


class TestCleanSearchTitle:
    def test_underscores_to_spaces(self, client):
        assert "The Matrix" in client._clean_search_title("The_Matrix")

    def test_strips_disc_noise(self, client):
        result = client._clean_search_title("MOVIE_DISC_1_DVD")
        assert "DISC" not in result.upper()
        assert "DVD" not in result.upper()

    def test_strips_region_and_format(self, client):
        result = client._clean_search_title("MOVIE_WIDESCREEN_REGION_1_NTSC")
        assert "WIDESCREEN" not in result.upper()
        assert "NTSC" not in result.upper()

    def test_strips_timestamps(self, client):
        result = client._clean_search_title("Movie_20231115_143022")
        assert "20231115" not in result

    def test_preserves_valid_year(self, client):
        result = client._clean_search_title("Movie Title 2020")
        assert "2020" in result

    def test_strips_invalid_trailing_number(self, client):
        result = client._clean_search_title("Movie Title 9999")
        assert "9999" not in result

    def test_empty_after_stripping_returns_original(self, client):
        result = client._clean_search_title("DVD")
        assert result

    def test_bluray_noise(self, client):
        result = client._clean_search_title("Movie BLU RAY Special Edition")
        assert "BLU" not in result.upper()
        assert "SPECIAL" not in result.upper()


class TestAggressiveCleanTitle:
    def test_removes_numbers(self, client):
        result = client._aggressive_clean_title("Movie123_Title456")
        assert "123" not in result
        assert "456" not in result

    def test_keeps_short_words(self, client):
        result = client._aggressive_clean_title("I Am A Title")
        assert "I" in result.split()
        assert "A" in result.split()

    def test_returns_original_on_empty(self, client):
        result = client._aggressive_clean_title("123_456")
        assert result


# ── Pick best match ──────────────────────────────────────────────


class TestPickBestTmdbMatch:
    def test_no_runtime_hint_returns_first(self, client):
        results = [{"id": 1}, {"id": 2}]
        assert client._pick_best_tmdb_match(results, {}) == 1

    def test_single_result_no_hint(self, client):
        results = [{"id": 42}]
        assert client._pick_best_tmdb_match(results, {}) == 42

    @patch("requests.get")
    def test_runtime_disambiguation(self, mock_get, client):
        results = [{"id": 1}, {"id": 2}, {"id": 3}]
        for runtime in [90, 135, 200]:
            resp = MagicMock()
            resp.json.return_value = {"runtime": runtime}
        detail_responses = []
        for runtime in [90, 135, 200]:
            resp = MagicMock()
            resp.json.return_value = {"runtime": runtime}
            detail_responses.append(resp)
        mock_get.side_effect = detail_responses

        best = client._pick_best_tmdb_match(results, {"estimated_runtime_min": 130})
        assert best == 2  # closest to 130 min

    @patch("requests.get")
    def test_runtime_disambiguation_handles_fetch_error(self, mock_get, client):
        results = [{"id": 1}, {"id": 2}]
        ok_resp = MagicMock()
        ok_resp.json.return_value = {"runtime": 120}
        mock_get.side_effect = [ok_resp, Exception("fail")]

        best = client._pick_best_tmdb_match(results, {"estimated_runtime_min": 120})
        assert best == 1


# ── Image download ───────────────────────────────────────────────


class TestDownloadImage:
    def test_empty_path_returns_false(self, client):
        assert client._download_image("", "/out.jpg") is False
        assert client._download_image(None, "/out.jpg") is False

    @patch("requests.get")
    def test_successful_download(self, mock_get, client, tmp_path):
        from PIL import Image
        import io

        img = Image.new("RGB", (10, 10), color="red")
        buf = io.BytesIO()
        img.save(buf, format="JPEG")
        img_resp = MagicMock()
        img_resp.content = buf.getvalue()
        mock_get.return_value = img_resp

        out = tmp_path / "poster.jpg"
        assert client._download_image("/test.jpg", str(out)) is True
        assert out.exists()

    @patch("requests.get")
    def test_download_failure_returns_false(self, mock_get, client, tmp_path):
        mock_get.side_effect = Exception("timeout")
        assert client._download_image("/x.jpg", str(tmp_path / "x.jpg")) is False

    def test_download_poster_delegates(self, client):
        with patch.object(client, "_download_image", return_value=True) as m:
            assert client.download_poster("/p.jpg", "/out.jpg") is True
            m.assert_called_once_with("/p.jpg", "/out.jpg", size="w500")

    def test_download_backdrop_delegates(self, client):
        with patch.object(client, "_download_image", return_value=True) as m:
            assert client.download_backdrop("/b.jpg", "/out.jpg") is True
            m.assert_called_once_with("/b.jpg", "/out.jpg", size="w1280")
