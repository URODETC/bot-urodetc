from __future__ import annotations


class VpnToolError(Exception):
    """Base error exposed by the VPN management tool."""


class VpnConfigurationError(VpnToolError):
    pass


class VpnValidationError(VpnToolError):
    pass


class VpnNotFoundError(VpnToolError):
    pass


class VpnAuthenticationError(VpnToolError):
    pass


class VpnRateLimitError(VpnToolError):
    pass


class VpnTemporaryError(VpnToolError):
    pass


class VpnExternalServiceError(VpnToolError):
    pass
