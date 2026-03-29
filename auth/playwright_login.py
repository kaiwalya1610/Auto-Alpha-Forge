"""
Playwright-based browser automation for Zerodha OAuth login.
Automates: user_id → password → TOTP → capture request_token
"""

import re
from typing import Optional
from urllib.parse import urlparse, parse_qs
from .totp_helper import TOTPHelper


def automate_oauth_login(
    login_url: str,
    user_id: str,
    password: str,
    totp_key: str,
    redirect_url: str = "http://127.0.0.1",
    headless: bool = False,
    timeout: int = 60000
) -> str:
    """
    Automate Zerodha OAuth login using Playwright.

    Args:
        login_url: Kite login URL (from kite.login_url())
        user_id: Zerodha user ID
        password: Zerodha password
        totp_key: TOTP secret key for 2FA
        redirect_url: Expected redirect URL prefix (set in Kite app settings)
        headless: Run browser in headless mode
        timeout: Max wait time in ms

    Returns:
        request_token extracted from redirect URL

    Raises:
        ValueError: If login fails or request_token not found
    """
    try:
        from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeout
    except ImportError:
        raise ImportError(
            "[ERROR] Playwright not installed. Run: pip install playwright && playwright install chromium"
        )

    print("[START] Starting automated OAuth login...")

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=headless)
        page = browser.new_page()
        page.set_default_timeout(timeout)

        try:
            # Step 1: Navigate to login page
            print("[NAV] Navigating to Kite login...")
            page.goto(login_url, wait_until="networkidle")

            # Step 2: Fill credentials
            print("[AUTH] Entering credentials...")
            page.fill('input[type="text"]', user_id)
            page.fill('input[type="password"]', password)
            page.click('button[type="submit"]')

            # Step 3: Wait for TOTP page and fill
            print("[TOTP] Entering TOTP...")
            # TOTP input has type="number" and id="userid" (confusingly named)
            totp_selector = 'input[type="number"]#userid'
            page.wait_for_selector(totp_selector, state="visible")

            totp_helper = TOTPHelper(totp_key)
            totp_code = totp_helper.generate()
            print(f"[CODE] Generated TOTP: {totp_code}")
            
            # Type TOTP slowly - Zerodha auto-submits after 6 digits
            page.type(totp_selector, totp_code, delay=50)
            # Don't click submit - form auto-submits after 6 digits!

            # Step 4: Wait for redirect with request_token
            print("[WAIT] Waiting for redirect...")
            
            # Strategy: Listen for ANY request to the redirect URL (even if it fails)
            # This is more reliable than wait_for_url() which might throw on connection refused
            # without updating page.url
            captured_token = {"value": None}

            def handle_request(request):
                if "request_token=" in request.url:
                    token = _extract_request_token(request.url)
                    if token:
                        print(f"[MATCH] Intercepted request with token: {request.url[:60]}...")
                        captured_token["value"] = token

            page.on("request", handle_request)

            # Wait for the token to be captured
            # We poll manually because wait_for_url might fail fast on connection refused
            for _ in range(20):  # Wait up to 10 seconds (20 * 0.5s)
                if captured_token["value"]:
                    break
                page.wait_for_timeout(500)
            
            # Cleanup listener
            page.remove_listener("request", handle_request)

            if captured_token["value"]:
                request_token = captured_token["value"]
                print("[OK] Got request_token via request interception!")
                return request_token
            
            # Fallback: Check current URL (if we missed the event but nav happened)
            current_url = page.url
            print(f"[URL] Final Page URL: {current_url[:80]}...")
            request_token = _extract_request_token(current_url)

            if not request_token:
                raise ValueError(f"[ERROR] No request_token found. Stuck at: {current_url}")

            return request_token

            print("[OK] Got request_token!")
            return request_token

        except PlaywrightTimeout:
            raise ValueError("[ERROR] Login timed out - check credentials or TOTP")
        except Exception as e:
            raise ValueError(f"[ERROR] Login failed: {e}")
        finally:
            browser.close()


def _extract_request_token(url: str) -> Optional[str]:
    """Extract request_token from redirect URL."""
    parsed = urlparse(url)
    params = parse_qs(parsed.query)
    tokens = params.get("request_token", [])
    return tokens[0] if tokens else None

