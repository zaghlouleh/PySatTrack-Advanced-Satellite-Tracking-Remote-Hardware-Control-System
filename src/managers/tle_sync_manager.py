# -*- coding: utf-8 -*-
import os
import time
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from typing import Dict, List

from src.utils.logger import logger
from src.utils.config import DEFAULT_TLE_SOURCES
from src.managers.data_manager import DataManager
from src.api.spacetrack_client import SpaceTrackClient


class TleSyncManager:
    """Handles TLE source downloads, caching, and mirror retry logic."""

    def __init__(self, data_manager: DataManager, spacetrack_client: SpaceTrackClient):
        self.data_manager = data_manager
        self.st_client = spacetrack_client
        self.session = requests.Session()

        retry = Retry(
            total=2,
            backoff_factor=1,
            status_forcelist=[429, 500, 502, 503, 504],
            allowed_methods=frozenset(["GET"]),
        )
        adapter = HTTPAdapter(max_retries=retry)
        self.session.mount("https://", adapter)
        self.session.mount("http://", adapter)
        self.session.headers.update({
            "User-Agent": "PySatTrack/5.0 (+https://github.com)"
        })

    def _is_cache_fresh(self, filepath: str, cache_days: int) -> bool:
        if not os.path.exists(filepath):
            return False
        try:
            return (time.time() - os.path.getmtime(filepath)) < (cache_days * 86400)
        except OSError as e:
            logger.warning(f"TLE cache check failed for {filepath}: {e}")
            return False

    def _download_url(self, url: str, save_path: str) -> bool:
        try:
            with self.session.get(url, stream=True, timeout=(15, 300)) as response:
                response.raise_for_status()
                os.makedirs(os.path.dirname(save_path), exist_ok=True)
                with open(save_path, "wb") as f:
                    for chunk in response.iter_content(chunk_size=8192):
                        if chunk:
                            f.write(chunk)
            logger.info(f"Downloaded TLE file from {url}")
            return True
        except requests.RequestException as e:
            logger.warning(f"TLE download failed from {url}: {e}")
            return False

    def _download_spacetrack_source(self, source_info: Dict) -> bool:
        if not self.st_client._client:
            logger.error("Space-Track client is not authenticated.")
            return False

        lines = self.st_client.get_gp_data(
            source_info.get("query_class"),
            source_info.get("query_filters", {}),
        )
        if not lines:
            logger.error("Space-Track download returned no TLE lines.")
            return False

        save_path = self.data_manager.get_tle_path(source_info["filename"])
        try:
            with open(save_path, "w", encoding="utf-8") as f:
                if isinstance(lines, (list, tuple)):
                    f.write("\n".join(line.strip() for line in lines if line))
                else:
                    f.write(str(lines))
            logger.info(f"Saved Space-Track file to {save_path}")
            return True
        except Exception as e:
            logger.error(f"Could not save Space-Track file {save_path}: {e}")
            return False

    def download_source(self, source_key: str) -> bool:
        source_info = DEFAULT_TLE_SOURCES[source_key]
        save_path = self.data_manager.get_tle_path(source_info["filename"])
        cache_days = source_info.get("cache_days", 1)

        if self._is_cache_fresh(save_path, cache_days):
            logger.info(f"Using cached TLE file: {save_path}")
            return True

        if source_info.get("auth_required") == "space-track":
            return self._download_spacetrack_source(source_info)

        urls = source_info.get("url", [])
        if isinstance(urls, str):
            urls = [urls]

        for url in urls:
            if self._download_url(url, save_path):
                return True

        logger.error(f"All mirrors failed for TLE source '{source_key}'.")
        return False

    def download_sources(self, selected_sources: List[str]) -> List[str]:
        downloaded_paths = []
        for source_key in selected_sources:
            if self.download_source(source_key):
                filename = DEFAULT_TLE_SOURCES[source_key]["filename"]
                downloaded_paths.append(self.data_manager.get_tle_path(filename))
        return downloaded_paths
