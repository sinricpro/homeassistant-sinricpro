"""Exceptions for the SinricPro integration."""
from __future__ import annotations


class SinricProError(Exception):
    """Base exception for SinricPro errors."""


class SinricProAuthenticationError(SinricProError):
    """Authentication failed - invalid or expired API key."""


class SinricProConnectionError(SinricProError):
    """Connection to SinricPro API failed."""


class SinricProTimeoutError(SinricProError):
    """Request to SinricPro API timed out."""


class SinricProRateLimitError(SinricProError):
    """Rate limit exceeded."""

    def __init__(self, message: str, retry_after: int | None = None) -> None:
        """Initialize rate limit error.

        Args:
            message: Error message.
            retry_after: Number of seconds to wait before retrying.
        """
        super().__init__(message)
        self.retry_after = retry_after


class SinricProDeviceNotFoundError(SinricProError):
    """Device not found."""


class SinricProDeviceOfflineError(SinricProError):
    """Device is offline and cannot be controlled."""


class SinricProApiError(SinricProError):
    """Generic API error with status code."""

    def __init__(self, message: str, status_code: int) -> None:
        """Initialize API error.

        Args:
            message: Error message.
            status_code: HTTP status code.
        """
        super().__init__(message)
        self.status_code = status_code
