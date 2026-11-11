"""Domain error hierarchy and safe API error mapping.

Error messages returned to clients never contain credential material or
internal exception detail.  The full exception is logged server-side with a
correlation id.
"""

from __future__ import annotations


class HumisenseError(Exception):
    """Base class for all domain errors."""

    status_code = 500
    code = "internal_error"

    def __init__(self, message: str, *, detail: dict | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.detail = detail or {}


class NotFoundError(HumisenseError):
    status_code = 404
    code = "not_found"


class ValidationError(HumisenseError):
    status_code = 422
    code = "validation_error"


class ConflictError(HumisenseError):
    status_code = 409
    code = "conflict"


class AuthorizationError(HumisenseError):
    status_code = 403
    code = "forbidden"


class AuthenticationError(HumisenseError):
    status_code = 401
    code = "unauthenticated"


class TenantIsolationError(AuthorizationError):
    """Raised when a resource belongs to another tenant.

    Returned as 404 to the caller so that resource existence is not leaked
    across tenants, while the audit log records the real reason.
    """

    status_code = 404
    code = "not_found"


class EgressBlockedError(HumisenseError):
    """Raised when a connector tries to reach a blocked or private host."""

    status_code = 400
    code = "egress_blocked"


class ConnectorError(HumisenseError):
    status_code = 502
    code = "connector_error"


class ConnectorAuthError(ConnectorError):
    status_code = 401
    code = "connector_auth_failed"


class ConnectorRateLimited(ConnectorError):
    status_code = 429
    code = "connector_rate_limited"

    def __init__(self, message: str, *, retry_after: float | None = None, detail: dict | None = None):
        super().__init__(message, detail=detail)
        self.retry_after = retry_after


class ConnectorTransientError(ConnectorError):
    """Retryable connector failure (timeout, 5xx, connection reset)."""

    status_code = 502
    code = "connector_transient_error"


class ConfigurationError(HumisenseError):
    status_code = 500
    code = "configuration_error"
