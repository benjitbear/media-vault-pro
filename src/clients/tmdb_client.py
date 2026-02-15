"""TMDB (The Movie Database) API client."""

import re
from typing import Any, Dict, Optional

from ..utils import setup_logger


class TMDBClient:
    """Search TMDB for movie metadata and download posters / backdrops."""

    def __init__(self, api_key: Optional[str] = None) -> None:
        """Initialise the TMDB client.

        Args:
            api_key: TMDB API key. If ``None``, metadata lookups
                will be skipped.
        """
        self.api_key = api_key
        self.logger = setup_logger("tmdb_client", "metadata.log")

    # ── Public API ───────────────────────────────────────────────

    def search_tmdb(
        self, title: str, year: Optional[int] = None, disc_hints: Optional[Dict[str, Any]] = None
    ) -> Optional[Dict[str, Any]]:
        """
        Search TMDB for movie metadata.
        Uses disc_hints (runtime, title count, disc label) to improve matching.

        Returns:
            Movie metadata dict or None.
        """
        if not self.api_key:
            self.logger.warning("TMDB API key not configured")
            return None

        disc_hints = disc_hints or {}
        clean_title = self._clean_search_title(title)
        self.logger.info("Searching TMDB for: '%s' (raw: '%s')", clean_title, title)

        try:
            import requests

            search_url = "https://api.themoviedb.org/3/search/movie"
            params: Dict[str, Any] = {
                "api_key": self.api_key,
                "query": clean_title,
            }
            if year:
                params["year"] = year

            response = requests.get(search_url, params=params, timeout=10)
            response.raise_for_status()
            results = response.json().get("results", [])

            if not results:
                fallback_title = self._aggressive_clean_title(title)
                if fallback_title != clean_title:
                    self.logger.info("Retrying TMDB with fallback title: '%s'", fallback_title)
                    params["query"] = fallback_title
                    response = requests.get(search_url, params=params, timeout=10)
                    response.raise_for_status()
                    results = response.json().get("results", [])

            if not results:
                self.logger.info("No TMDB results for: %s", title)
                return None

            movie_id = self._pick_best_tmdb_match(results, disc_hints)

            # Fetch detailed information
            detail_url = f"https://api.themoviedb.org/3/movie/{movie_id}"
            credits_url = f"https://api.themoviedb.org/3/movie/{movie_id}/credits"

            movie_data = requests.get(
                detail_url, params={"api_key": self.api_key}, timeout=10
            ).json()
            credits_data = requests.get(
                credits_url, params={"api_key": self.api_key}, timeout=10
            ).json()

            metadata: Dict[str, Any] = {
                "title": movie_data.get("title"),
                "original_title": movie_data.get("original_title"),
                "year": (
                    movie_data.get("release_date", "")[:4]
                    if movie_data.get("release_date")
                    else None
                ),
                "overview": movie_data.get("overview"),
                "runtime_minutes": movie_data.get("runtime"),
                "genres": [g["name"] for g in movie_data.get("genres", [])],
                "rating": movie_data.get("vote_average"),
                "tmdb_id": movie_id,
                "poster_path": movie_data.get("poster_path"),
                "backdrop_path": movie_data.get("backdrop_path"),
                "collection_name": None,
            }

            if movie_data.get("belongs_to_collection"):
                metadata["collection_name"] = movie_data["belongs_to_collection"].get("name")

            if "crew" in credits_data:
                directors = [c["name"] for c in credits_data["crew"] if c["job"] == "Director"]
                metadata["director"] = directors[0] if directors else None

            if "cast" in credits_data:
                metadata["cast"] = [c["name"] for c in credits_data["cast"][:10]]

            self.logger.info("Found TMDB match: %s (%s)", metadata["title"], metadata["year"])
            return metadata

        except Exception as e:
            self.logger.error("Error searching TMDB: %s", e)
            return None

    def download_poster(self, poster_path: str, output_path: str) -> bool:
        """Download movie poster from TMDB."""
        return self._download_image(poster_path, output_path, size="w500")

    def download_backdrop(self, backdrop_path: str, output_path: str) -> bool:
        """Download movie backdrop/fanart from TMDB."""
        return self._download_image(backdrop_path, output_path, size="w1280")

    # ── Title Cleaning ───────────────────────────────────────────

    def _clean_search_title(self, raw_title: str) -> str:
        """
        Clean a raw disc volume name into a reasonable search query.
        Handles common disc naming patterns like underscores, disc markers,
        trailing timestamps, region codes, etc.
        """
        title = raw_title.replace("_", " ")

        noise_patterns = [
            r"\bDISC\s*\d*\b",
            r"\bDVD\b",
            r"\bBLU\s*RAY\b",
            r"\bBD\b",
            r"\bCD\s*\d*\b",
            r"\bVOL(UME)?\s*\d*\b",
            r"\bWIDESCREEN\b",
            r"\bFULLSCREEN\b",
            r"\bSPECIAL\s*EDITION\b",
            r"\bREGION\s*\d\b",
            r"\bNTSC\b",
            r"\bPAL\b",
            r"\bTHE\s*MOVIE\b",
        ]
        for pat in noise_patterns:
            title = re.sub(pat, "", title, flags=re.IGNORECASE)

        title = re.sub(r"\b\d{8}[\s_]\d{6}\b", "", title)

        match = re.search(r"\b(\d{4})\s*$", title)
        if match:
            num = int(match.group(1))
            if num < 1900 or num > 2099:
                title = title[: match.start()]

        title = re.sub(r"\s+", " ", title).strip()
        return title if title else raw_title.replace("_", " ").strip()

    def _aggressive_clean_title(self, raw_title: str) -> str:
        """More aggressive title cleaning as a fallback."""
        title = raw_title.replace("_", " ")
        title = re.sub(r"[^a-zA-Z\s]", "", title)
        words = [w for w in title.split() if len(w) > 1 or w.upper() in ("I", "A")]
        return " ".join(words).strip() if words else raw_title

    # ── Internals ────────────────────────────────────────────────

    def _pick_best_tmdb_match(self, results: list, disc_hints: Dict[str, Any]) -> int:
        """Pick the best TMDB result using disc hints for disambiguation."""
        estimated_runtime = disc_hints.get("estimated_runtime_min")

        if not estimated_runtime or len(results) <= 1:
            return results[0]["id"]

        best_id = results[0]["id"]
        best_diff = float("inf")

        for r in results[:5]:
            import requests

            try:
                detail = requests.get(
                    f"https://api.themoviedb.org/3/movie/{r['id']}",
                    params={"api_key": self.api_key},
                    timeout=5,
                ).json()
                tmdb_runtime = detail.get("runtime", 0)
                if tmdb_runtime:
                    diff = abs(tmdb_runtime - estimated_runtime)
                    self.logger.debug(
                        f"  TMDB match '{detail.get('title')}' runtime={tmdb_runtime}, "
                        f"disc≈{estimated_runtime}, diff={diff}"
                    )
                    if diff < best_diff:
                        best_diff = diff
                        best_id = r["id"]
            except Exception as e:
                self.logger.debug("Failed to fetch TMDB detail for id=%s: %s", r.get("id"), e)

        self.logger.info("Selected TMDB ID %s (runtime diff: %s min)", best_id, best_diff)
        return best_id

    def _download_image(self, image_path: str, output_path: str, size: str = "w500") -> bool:
        """Download an image (poster or backdrop) from TMDB."""
        if not image_path:
            return False
        try:
            import requests
            from PIL import Image
            from io import BytesIO

            url = f"https://image.tmdb.org/t/p/{size}{image_path}"
            response = requests.get(url, timeout=10)
            response.raise_for_status()

            image = Image.open(BytesIO(response.content))
            image.save(output_path)

            self.logger.info("Downloaded TMDB image to: %s", output_path)
            return True

        except Exception as e:
            self.logger.error("Error downloading TMDB image: %s", e)
            return False
