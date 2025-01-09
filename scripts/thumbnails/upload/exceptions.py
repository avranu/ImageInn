"""
"""
from __future__ import annotations
from scripts.exceptions import AppError

class AuthenticationError(AppError):
    pass

class ConfigurationError(AppError):
    pass
