"""
Simple enctoken-based authentication.
"""

import requests
from typing import Optional
from .totp_helper import TOTPHelper


def login_with_enctoken(
    session: requests.Session,
    user_id: str,
    password: str,
    totp_key: str,
    login_url: str,
    twofa_url: str
) -> str:
    """
    Login and get enctoken.

    Args:
        session: HTTP session
        user_id: Zerodha user ID
        password: Zerodha password
        totp_key: TOTP secret key
        login_url: Login endpoint
        twofa_url: 2FA endpoint

    Returns:
        enctoken string

    Raises:
        ValueError: If login fails
    """
    # Step 1: Submit credentials
    print("[AUTH] Logging in with credentials...")
    login_data = {"user_id": user_id, "password": password}

    try:
        login_response = session.post(login_url, data=login_data, timeout=10)
        login_response.raise_for_status()
        login_json = login_response.json()
    except Exception as e:
        raise ValueError(f"[ERROR] Login failed: {e}")

    if login_json.get("status") != "success":
        error_msg = login_json.get("message", "Unknown error")
        raise ValueError(f"[ERROR] Login failed: {error_msg}")

    request_id = login_json.get("data", {}).get("request_id")
    if not request_id:
        raise ValueError("[ERROR] Failed to get request_id from login response")

    # Step 2: Submit TOTP
    print("[TOTP] Submitting TOTP code...")
    totp_helper = TOTPHelper(totp_key)
    totp_code = totp_helper.generate()

    twofa_data = {
        "user_id": user_id,
        "request_id": request_id,
        "twofa_value": totp_code
    }

    try:
        twofa_response = session.post(twofa_url, data=twofa_data, timeout=10)
        twofa_response.raise_for_status()
    except Exception as e:
        raise ValueError(f"[ERROR] 2FA failed: {e}")

    # Step 3: Extract enctoken from cookies
    enctoken = twofa_response.cookies.get("enctoken")
    if not enctoken:
        raise ValueError("[ERROR] Failed to get enctoken from cookies")

    print("[OK] Login successful!")
    return enctoken


def create_enctoken_headers(enctoken: str) -> dict:
    """
    Create headers for API requests using enctoken.

    Args:
        enctoken: The enctoken

    Returns:
        Dict with Authorization header
    """
    return {
        "Authorization": f"enctoken {enctoken}",
        "Content-Type": "application/json"
    }


def fetch_user_profile(session: requests.Session, enctoken: str) -> dict:
    """
    Fetch user profile to get kite_user_id.

    Args:
        session: HTTP session
        enctoken: Authentication token

    Returns:
        User profile dict with user_id

    Raises:
        ValueError: If fetch fails
    """
    url = "https://kite.zerodha.com/oms/user/profile"
    headers = create_enctoken_headers(enctoken)

    try:
        response = session.get(url, headers=headers, timeout=5)
        response.raise_for_status()
        data = response.json()

        if 'data' in data and 'user_id' in data['data']:
            return data['data']
        else:
            raise ValueError("[ERROR] No user_id in profile response")
    except Exception as e:
        raise ValueError(f"[ERROR] Failed to fetch profile: {e}")
