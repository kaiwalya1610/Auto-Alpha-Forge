"""
Simple Zerodha authentication - supports enctoken and OAuth.
"""

import os
from typing import Optional
from dotenv import load_dotenv
from kiteconnect import KiteConnect

from .session_manager import SessionManager
from .token_cache import TokenCache
from .enctoken_login import (
    login_with_enctoken,
    create_enctoken_headers,
    fetch_user_profile
)
from .oauth_login import (
    login_with_oauth,
    create_oauth_headers,
    fetch_user_profile_oauth
)


class ZerodhaLogin:
    """
    Simple Zerodha authentication handler.

    Supports two methods:
    1. Enctoken (automatic TOTP login)
    2. OAuth (KiteConnect SDK)
    """

    def __init__(
        self,
        auth_method: str = "enctoken",
        auto_login: bool = False,
        cache_file: str = "enctoken_cache.json"
    ):
        """
        Initialize authentication.

        Args:
            auth_method: 'enctoken' or 'oauth'
            auto_login: Automatically attempt login
            cache_file: Path to token cache file
        """
        load_dotenv()

        # Basic setup
        self.auth_method = auth_method
        self.user_id = os.getenv("USER_ID")
        self.api_key = os.getenv("API_KEY")  # Store API key as instance attribute
        self.session = SessionManager.create_session()
        self.cache = TokenCache(cache_file)

        # Auth state
        self.enctoken: Optional[str] = None
        self.access_token: Optional[str] = None
        self.kite: Optional[KiteConnect] = None
        self.kite_user_id: Optional[str] = None
        self.headers: Optional[dict] = None     

        # Validate required env vars
        if not self.user_id:
            raise ValueError("[ERROR] USER_ID not found in environment")

        # Auto-login if requested
        if auto_login:
            self.smart_login()

    def smart_login(self) -> dict:
        """
        Smart login: tries cache first, then fresh login.

        Returns:
            Auth headers dict
        """
        # Try to load from cache
        cached = self.cache.load(self.user_id, self.auth_method)

        if cached:
            print("[CACHE] Found cached token, validating...")
            if self._restore_from_cache(cached):
                print("[OK] Using cached token")
                return self.headers

        # Cache miss or invalid - do fresh login
        print("[LOGIN] Performing fresh login...")
        return self.login()

    def login(self) -> dict:
        """
        Perform fresh login.

        Returns:
            Auth headers dict
        """
        if self.auth_method == "enctoken":
            return self._login_enctoken()
        elif self.auth_method == "oauth":
            return self._login_oauth()
        else:
            raise ValueError(f"[ERROR] Invalid auth_method: {self.auth_method}")

    def _login_enctoken(self) -> dict:
        """Login using enctoken method."""
        # Get credentials from env
        password = os.getenv("USER_PASSWORD")
        totp_key = os.getenv("TOTP_KEY")
        login_url = os.getenv("LOGIN_URL", "https://kite.zerodha.com/api/login")
        twofa_url = os.getenv("TWOFA_URL", "https://kite.zerodha.com/api/twofa")

        if not all([password, totp_key]):
            raise ValueError("[ERROR] USER_PASSWORD and TOTP_KEY required for enctoken auth")

        # Do login
        self.enctoken = login_with_enctoken(
            self.session,
            self.user_id,
            password,
            totp_key,
            login_url,
            twofa_url
        )

        # Create headers
        self.headers = create_enctoken_headers(self.enctoken)

        # Fetch user profile
        profile = fetch_user_profile(self.session, self.enctoken)
        self.kite_user_id = profile['user_id']

        # Save to cache
        self.cache.save(
            self.user_id,
            "enctoken",
            enctoken=self.enctoken,
            kite_user_id=self.kite_user_id
        )

        return self.headers

    def _login_oauth(self) -> dict:
        """Login using OAuth method."""
        # Get credentials from env
        api_secret = os.getenv("API_SECRET")
        request_token = os.getenv("REQUEST_TOKEN")  # Optional

        if not all([self.api_key, api_secret]):
            raise ValueError("[ERROR] API_KEY and API_SECRET required for OAuth")

        # Do OAuth login
        self.kite, self.access_token = login_with_oauth(
            self.api_key,
            api_secret,
            request_token
        )

        # Create headers
        self.headers = create_oauth_headers(self.access_token, self.api_key)

        # Fetch user profile
        profile = fetch_user_profile_oauth(self.kite)
        self.kite_user_id = profile['user_id']

        # Save to cache
        self.cache.save(
            self.user_id,
            "oauth",
            access_token=self.access_token,
            kite_user_id=self.kite_user_id
        )

        return self.headers

    def _restore_from_cache(self, cached: dict) -> bool:
        """
        Restore auth state from cache and validate.

        Args:
            cached: Cached data dict

        Returns:
            True if successfully restored
        """
        if self.auth_method == "enctoken":
            self.enctoken = cached.get('enctoken')
            self.headers = create_enctoken_headers(self.enctoken)
            self.kite_user_id = cached.get('kite_user_id')

            # Validate token
            validation_url = "https://kite.zerodha.com/oms/user/profile"
            if self.cache.validate_token(
                self.session,
                self.headers,
                validation_url,
                "enctoken"
            ):
                return True

        elif self.auth_method == "oauth":
            self.access_token = cached.get('access_token')

            if not self.api_key:
                return False

            self.headers = create_oauth_headers(self.access_token, self.api_key)
            self.kite_user_id = cached.get('kite_user_id')

            # Recreate KiteConnect instance
            self.kite = KiteConnect(api_key=self.api_key)
            self.kite.set_access_token(self.access_token)

            # Validate token
            validation_url = "https://api.kite.trade/user/profile"
            if self.cache.validate_token(
                self.session,
                self.headers,
                validation_url,
                "oauth",
                self.kite
            ):
                return True

        return False

    # === Public API (backward compatible) ===

    def get_enctoken(self) -> str:
        """Get enctoken (for enctoken auth) or access_token (for OAuth)."""
        if self.auth_method == "enctoken":
            if not self.enctoken:
                self.smart_login()
            return self.enctoken
        else:
            if not self.access_token:
                self.smart_login()
            return self.access_token

    def get_headers(self) -> dict:
        """Get auth headers."""
        if not self.headers:
            self.smart_login()
        return self.headers

    def get_session(self):
        """Get HTTP session."""
        return self.session

    def get_kite_instance(self) -> Optional[KiteConnect]:
        """Get KiteConnect instance (OAuth only)."""
        if self.auth_method != "oauth":
            raise ValueError("[ERROR] KiteConnect instance only available with OAuth")
        if not self.kite:
            self.smart_login()
        return self.kite

    def get_websocket_token(self) -> str:
        """
        Get WebSocket token in format: token&user_id=XXXXX

        Works for both enctoken and OAuth.
        """
        if not self.kite_user_id:
            self.smart_login()

        token = self.enctoken if self.auth_method == "enctoken" else self.access_token
        return f"{token}&user_id={self.kite_user_id}"

    def refresh_token(self):
        """Force fresh login (invalidate cache)."""
        print("[RETRY] Refreshing token...")
        return self.login()