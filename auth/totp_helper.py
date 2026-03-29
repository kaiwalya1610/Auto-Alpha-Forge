"""
TOTP code generation helper.
"""

import pyotp


class TOTPHelper:
    """Generates TOTP codes for 2FA."""

    def __init__(self, totp_key: str):
        """
        Initialize TOTP helper.

        Args:
            totp_key: Base32 encoded TOTP secret key
        """
        self.totp = pyotp.TOTP(totp_key)

    def generate(self) -> str:
        """Generate current TOTP code."""
        return self.totp.now()