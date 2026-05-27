# -*- coding: utf-8 -*-
import time
import httpx
import spacetrack
from typing import Optional, Dict, Any
from src.api.base_client import BaseAPIClient
from src.utils.logger import logger

class SpaceTrackClient(BaseAPIClient):
    def __init__(self):
        super().__init__(base_url="https://www.space-track.org")
        self._client: Optional[spacetrack.SpaceTrackClient] = None

    def authenticate(self, username: str, password: str) -> bool:
        try:
            logger.info(f"Space-Track: Authenticating {username}...")
            # Custom httpx client with extended timeout for large catalog queries
            httpx_client = httpx.Client(
                timeout=httpx.Timeout(connect=10.0, read=120.0, write=10.0, pool=10.0)
            )
            st = spacetrack.SpaceTrackClient(
                identity=username, password=password, httpx_client=httpx_client
            )
            # Professional Fix: Mimic browser headers to bypass server blocks
            st.client.headers['User-Agent'] = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
            st.boxscore()  # Verify
            self._client = st
            return True
        except Exception as e:
            logger.error(f"Space-Track Login Error: {e}")
            # Cleanup: close the httpx client if auth failed
            if 'httpx_client' in locals():
                httpx_client.close()
            return False

    def get_gp_data(self, query_class: str, filters: Dict[str, Any]) -> Any:
        if not self._client:
            return None

        max_retries = 3
        for attempt in range(1, max_retries + 1):
            try:
                # --- STEP 1: Dynamically Fetch Allowed Predicates ---
                logger.debug(f"Fetching allowed predicates for class '{query_class}'...")
                try:
                    allowed_predicates = self._client.get_predicates(query_class)
                    allowed_keys = {p.name for p in allowed_predicates}
                    logger.debug(f"Allowed keys for '{query_class}': {sorted(list(allowed_keys))}")
                except Exception as e:
                    logger.error(f"Could not fetch predicates for class '{query_class}': {e}. Proceeding without validation.")
                    allowed_keys = set(filters.keys())
                    allowed_keys.add('format')

                # --- STEP 2: Filter the Query to Only Valid Keys ---
                clean_filters = {}
                for key, value in filters.items():
                    key_lower = key.lower()
                    if key_lower in allowed_keys:
                        clean_filters[key_lower] = value
                    else:
                        logger.warning(f"Filter '{key}' is NOT VALID for class '{query_class}' and will be ignored.")
                
                clean_filters['format'] = 'tle'
                
                logger.info(f"Executing query on class '{query_class}' with filters: {clean_filters}")
                return self._client.generic_request(query_class, **clean_filters)
            except (httpx.ReadTimeout, httpx.ConnectTimeout, TimeoutError) as e:
                if attempt < max_retries:
                    wait = attempt * 2  # 2s, 4s, 6s backoff
                    logger.warning(f"Space-Track Query timeout (attempt {attempt}/{max_retries}): {e}. Retrying in {wait}s...")
                    time.sleep(wait)
                else:
                    logger.error(f"Space-Track Query failed after {max_retries} attempts: {e}")
                    return None
            except Exception as e:
                logger.error(f"Space-Track Query failed: {e}")
                return None
        return None

