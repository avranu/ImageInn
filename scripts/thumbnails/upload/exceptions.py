"""
"""
from __future__ import annotations
from scripts.exceptions import AppException

class AuthenticationError(AppException):
    pass

class ConfigurationError(AppException):
    pass