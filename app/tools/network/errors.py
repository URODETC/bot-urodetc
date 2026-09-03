from __future__ import annotations


class NetworkToolError(Exception):
    """Base error for the network diagnostics tool."""


class ValidationError(NetworkToolError):
    """User supplied a value that is not a valid host/domain/IP."""


class LookupTimeoutError(NetworkToolError):
    """The upstream provider took too long to answer."""


class LookupFailedError(NetworkToolError):
    """The upstream provider returned an error or malformed data."""


class NotFoundError(NetworkToolError):
    """No data could be found for the requested target."""
