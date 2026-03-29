"""
Simple OAuth-based authentication.
Supports both manual and automated (Playwright) login.
"""

import os
from kiteconnect import KiteConnect
from typing import Optional


def login_with_oauth(
    api_key: str,
    api_secret: str,
    request_token: Optional[str] = None,
    auto_login: bool = True
) -> tuple[KiteConnect, str]:
    """
    Login using OAuth and get access token.

    Args:
        api_key: Kite API key
        api_secret: Kite API secret
        request_token: OAuth request token (if available)
        auto_login: Use Playwright to automate browser login (requires credentials in env)

    Returns:
        Tuple of (KiteConnect instance, access_token)

    Raises:
        ValueError: If OAuth flow fails
    """
    kite = KiteConnect(api_key=api_key)

    if not request_token:
        login_url = kite.login_url()

        # Try automated login if credentials available
        if auto_login and _has_credentials():
            request_token = _automated_login(login_url)
        else:
            # Fallback to manual
            print(f"[URL] Please visit this URL to authorize:\n{login_url}")
            request_token = input("Enter the request_token from redirect URL: ").strip()

    # Generate session
    try:
        data = kite.generate_session(request_token, api_secret=api_secret)
        access_token = data["access_token"]
        kite.set_access_token(access_token)
        print("[OK] OAuth login successful!")
        return kite, access_token
    except Exception as e:
        raise ValueError(f"[ERROR] OAuth session generation failed: {e}")


def _has_credentials() -> bool:
    """Check if credentials for auto-login are available."""
    return all([
        os.getenv("USER_ID"),
        os.getenv("USER_PASSWORD"),
        os.getenv("TOTP_KEY")
    ])


def _automated_login(login_url: str) -> str:
    """Perform automated login using Playwright."""
    from .playwright_login import automate_oauth_login

    user_id = os.getenv("USER_ID")
    password = os.getenv("USER_PASSWORD")
    totp_key = os.getenv("TOTP_KEY")
    redirect_url = os.getenv("REDIRECT_URL", "http://127.0.0.1")
    headless = os.getenv("HEADLESS_LOGIN", "false").lower() == "true"

    return automate_oauth_login(
        login_url=login_url,
        user_id=user_id,
        password=password,
        totp_key=totp_key,
        redirect_url=redirect_url,
        headless=headless
    )


def create_oauth_headers(access_token: str, api_key: str) -> dict:
    """
    Create headers for API requests using OAuth access token.

    Args:
        access_token: OAuth access token
        api_key: Kite API key

    Returns:
        Dict with Authorization and X-Kite-Version headers
    """
    return {
        "Authorization": f"token {api_key}:{access_token}",
        "X-Kite-Version": "3",
        "Content-Type": "application/json"
    }


def fetch_user_profile_oauth(kite: KiteConnect) -> dict:
    """
    Fetch user profile using KiteConnect SDK.

    Args:
        kite: Authenticated KiteConnect instance

    Returns:
        User profile dict

    Raises:
        ValueError: If fetch fails
    """
    try:
        profile = kite.profile()
        return profile
    except Exception as e:
        raise ValueError(f"[ERROR] Failed to fetch profile: {e}")