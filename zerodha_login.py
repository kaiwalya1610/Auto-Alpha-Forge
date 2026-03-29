"""
Zerodha authentication - Simple and modular.

This is a backward-compatible wrapper around the new auth package.
All real logic is in the auth/ directory.
"""

# Re-export the ZerodhaLogin class from auth package
# This maintains backward compatibility
from auth.zerodha_login import ZerodhaLogin

__all__ = ['ZerodhaLogin']


# Quick test when run directly
if __name__ == "__main__":
    print("🧪 Testing Zerodha authentication...")

    # Test enctoken method
    print("\n--- Testing Enctoken Method ---")
    auth = ZerodhaLogin(auth_method="enctoken", auto_login=True)
    print(f"✅ Enctoken: {auth.get_enctoken()[:20]}...")
    print(f"✅ Headers: {list(auth.get_headers().keys())}")
    print(f"✅ WebSocket token: {auth.get_websocket_token()[:30]}...")

    # Test OAuth method with Playwright automation
    print("\n--- Testing OAuth Method (Playwright Auto-Login) ---")
    try:
        # Check if required credentials are available
        import os
        from dotenv import load_dotenv
        load_dotenv()
        
        required_vars = ["API_KEY", "API_SECRET", "USER_ID", "USER_PASSWORD", "TOTP_KEY"]
        missing = [var for var in required_vars if not os.getenv(var)]
        
        if missing:
            print(f"⚠️ Missing env vars: {', '.join(missing)}")
            print("ℹ️ Skipping OAuth auto-login test (requires all credentials)")
        else:
            print("✅ All credentials found - testing Playwright automation...")
            auth_oauth = ZerodhaLogin(auth_method="oauth", auto_login=True)
            print(f"✅ OAuth Access Token: {auth_oauth.get_enctoken()[:30]}...")
            print(f"✅ Headers: {list(auth_oauth.get_headers().keys())}")
            print(f"✅ WebSocket token: {auth_oauth.get_websocket_token()[:30]}...")
            print(f"✅ KiteConnect instance: {auth_oauth.get_kite_instance() is not None}")
            
    except ImportError as e:
        if "playwright" in str(e).lower():
            print("⚠️ Playwright not installed - OAuth auto-login requires Playwright")
            print("ℹ️ Install with: pip install playwright && playwright install chromium")
        else:
            print(f"⚠️ Import error: {e}")
    except ValueError as e:
        print(f"⚠️ Configuration error: {e}")
    except Exception as e:
        print(f"⚠️ OAuth test failed: {e}")
        print("ℹ️ This might be due to:")
        print("   - Missing Playwright installation")
        print("   - Invalid credentials")
        print("   - Network/timeout issues")
        print("   - Browser automation failure")

    print("\n✅ All tests complete!")