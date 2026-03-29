"""
HTTP session management with retry strategy.
"""

import requests
from urllib3.util.retry import Retry
from requests.adapters import HTTPAdapter


class SessionManager:
    """Manages HTTP session with automatic retry strategy."""

    @staticmethod
    def create_session(
        retries: int = 5,
        backoff_factor: float = 1.0,
        status_forcelist: list = None
    ) -> requests.Session:
        """
        Create a requests session with retry strategy.

        Args:
            retries: Total number of retry attempts
            backoff_factor: Backoff multiplier for retry delays
            status_forcelist: HTTP status codes to retry on

        Returns:
            Configured requests.Session
        """
        if status_forcelist is None:
            status_forcelist = [429, 500, 502, 503, 504]

        session = requests.Session()

        retry_strategy = Retry(
            total=retries,
            backoff_factor=backoff_factor,
            status_forcelist=status_forcelist,
            allowed_methods=["HEAD", "GET", "OPTIONS", "POST"]
        )

        adapter = HTTPAdapter(max_retries=retry_strategy)
        session.mount("https://", adapter)
        session.mount("http://", adapter)

        return session