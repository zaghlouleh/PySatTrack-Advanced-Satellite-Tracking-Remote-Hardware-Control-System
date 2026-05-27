# -*- coding: utf-8 -*-
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from src.utils.logger import logger

class BaseAPIClient:
    """Base class for all API interactions with built-in retry logic."""
    
    def __init__(self, base_url: str = ""):
        self.base_url = base_url
        self.session = requests.Session()
        
        # Configure robust retry strategy
        retry_strategy = Retry(
            total=3,
            backoff_factor=1,
            status_forcelist=[429, 500, 502, 503, 504],
            allowed_methods=["HEAD", "GET", "OPTIONS"]
        )
        
        adapter = HTTPAdapter(max_retries=retry_strategy)
        self.session.mount("https://", adapter)
        self.session.mount("http://", adapter)
        
        # Default headers to mimic a browser
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
                          'AppleWebKit/537.36 (KHTML, like Gecko) '
                          'Chrome/107.0.0.0 Safari/537.36'
        })

    def _get(self, endpoint: str, params: dict = None, timeout: tuple = (10, 30)):
        """Helper method for GET requests with consistent error handling."""
        url = f"{self.base_url}{endpoint}" if self.base_url else endpoint
        try:
            response = self.session.get(url, params=params, timeout=timeout)
            response.raise_for_status()
            return response.json()
        except requests.exceptions.HTTPError as e:
            logger.error(f"HTTP Error for {url}: {e}")
            if response.status_code == 403:
                logger.error("Access forbidden (403). Check API keys or IP restrictions.")
        except requests.exceptions.RequestException as e:
            logger.error(f"Network error accessing {url}: {e}")
        except Exception as e:
            logger.exception(f"Unexpected error during API call to {url}:")
        return None