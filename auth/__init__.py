"""
Zerodha authentication package.

Simple modular authentication system supporting OAuth and enctoken methods.
"""

from .zerodha_login import ZerodhaLogin

__all__ = ['ZerodhaLogin']