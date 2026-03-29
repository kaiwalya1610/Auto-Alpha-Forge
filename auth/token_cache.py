"""
Token caching and validation utilities.
"""

import os
import json
from datetime import datetime
from typing import Optional, Dict, Any
import requests


class TokenCache:
    """Handles token storage, loading, and validation."""

    def __init__(self, cache_file: str = "enctoken_cache.json"):
        """
        Initialize token cache.

        Args:
            cache_file: Path to cache file
        """
        self.cache_file = cache_file

    def save(
        self,
        user_id: str,
        auth_method: str,
        enctoken: Optional[str] = None,
        access_token: Optional[str] = None,
        kite_user_id: Optional[str] = None
    ) -> bool:
        """
        Save tokens to cache file.

        Args:
            user_id: Zerodha user ID
            auth_method: 'oauth' or 'enctoken'
            enctoken: Enctoken (if using enctoken method)
            access_token: OAuth access token (if using OAuth)
            kite_user_id: Kite user ID for WebSocket

        Returns:
            True if saved successfully
        """
        if not enctoken and not access_token:
            print("⚠️ No token to save!")
            return False

        cache_data = {
            "auth_method": auth_method,
            "user_id": user_id,
            "saved_at": datetime.now().isoformat()
        }

        if enctoken:
            cache_data["enctoken"] = enctoken
        if access_token:
            cache_data["access_token"] = access_token
        if kite_user_id:
            cache_data["kite_user_id"] = kite_user_id

        try:
            with open(self.cache_file, 'w') as f:
                json.dump(cache_data, f, indent=2)
            print(f"💾 Token saved to {self.cache_file}")
            return True
        except Exception as e:
            print(f"⚠️ Failed to save token: {e}")
            return False

    def load(self, user_id: str, auth_method: str) -> Optional[Dict[str, Any]]:
        """
        Load tokens from cache file.

        Args:
            user_id: Expected user ID (safety check)
            auth_method: 'oauth' or 'enctoken'

        Returns:
            Cache data dict or None if not found/invalid
        """
        try:
            if not os.path.exists(self.cache_file):
                return None

            with open(self.cache_file, 'r') as f:
                cache_data = json.load(f)

            # Validate user ID matches
            if cache_data.get('user_id') != user_id:
                print("⚠️ Cached token is for different user. Ignoring.")
                return None

            # Check if required token exists
            if auth_method == "oauth" and 'access_token' not in cache_data:
                return None
            elif auth_method == "enctoken" and 'enctoken' not in cache_data:
                return None

            return cache_data

        except Exception as e:
            print(f"⚠️ Failed to load token: {e}")
            return None

    def validate_token(
        self,
        session: requests.Session,
        headers: Dict[str, str],
        validation_url: str,
        auth_method: str = "enctoken",
        kite_instance=None
    ) -> bool:
        """
        Validate if token is still active.

        Args:
            session: Requests session
            headers: Auth headers
            validation_url: API endpoint to test token
            auth_method: 'oauth' or 'enctoken'
            kite_instance: KiteConnect instance (for OAuth validation)

        Returns:
            True if token is valid
        """
        # For OAuth: check daily expiry first
        if auth_method == "oauth":
            if not self._check_oauth_expiry():
                return False

            # Try SDK validation if available
            if kite_instance:
                try:
                    profile = kite_instance.profile()
                    return profile is not None
                except Exception as e:
                    print(f"⚠️ OAuth token validation failed: {e}")
                    return False

        # Fallback: direct API validation
        try:
            response = session.get(validation_url, headers=headers, timeout=5)
            return response.status_code == 200
        except Exception as e:
            print(f"⚠️ Token validation failed: {e}")
            return False

    def _check_oauth_expiry(self) -> bool:
        """Check if OAuth token is from today (tokens expire daily)."""
        try:
            if not os.path.exists(self.cache_file):
                return False

            with open(self.cache_file, 'r') as f:
                cache_data = json.load(f)

            saved_at = cache_data.get("saved_at", "")
            if saved_at:
                saved_datetime = datetime.fromisoformat(saved_at)
                saved_date = saved_datetime.date()
                today = datetime.now().date()

                if saved_date < today:
                    print(f"⚠️ Access token expired (saved: {saved_date}, today: {today})")
                    return False
            return True

        except Exception as e:
            print(f"⚠️ Failed to check token expiry: {e}")
            return True  # Continue to API validation as fallback