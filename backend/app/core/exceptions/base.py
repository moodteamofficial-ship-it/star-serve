"""Centralized domain exceptions — mapped to safe API envelopes."""

from typing import Any


class StarServeError(Exception):
    """Base application error."""

    code: str = "INTERNAL_ERROR"
    http_status: int = 500
    message: str = "An unexpected error occurred"

    def __init__(
        self,
        message: str | None = None,
        *,
        details: list[Any] | None = None,
        code: str | None = None,
    ) -> None:
        self.message = message or self.__class__.message
        self.details = details or []
        if code:
            self.code = code
        super().__init__(self.message)


class AuthenticationError(StarServeError):
    code = "AUTHENTICATION_ERROR"
    http_status = 401
    message = "Authentication is required"


class AuthorizationError(StarServeError):
    code = "AUTHORIZATION_ERROR"
    http_status = 403
    message = "You do not have permission to perform this action"


class ValidationAppError(StarServeError):
    code = "VALIDATION_ERROR"
    http_status = 422
    message = "The request contains invalid information"


class TenantAccessError(StarServeError):
    code = "TENANT_ACCESS_DENIED"
    http_status = 403
    message = "Access to this tenant resource is denied"


class TenantSuspendedError(StarServeError):
    code = "TENANT_SUSPENDED"
    http_status = 403
    message = "This tenant is suspended and cannot perform business operations"


class ResourceNotFoundError(StarServeError):
    code = "RESOURCE_NOT_FOUND"
    http_status = 404
    message = "The requested resource was not found"


class ConflictError(StarServeError):
    code = "CONFLICT"
    http_status = 409
    message = "The request conflicts with the current state"


class RateLimitError(StarServeError):
    code = "RATE_LIMIT_EXCEEDED"
    http_status = 429
    message = "Too many requests. Please try again later."


class ExternalServiceError(StarServeError):
    code = "EXTERNAL_SERVICE_ERROR"
    http_status = 502
    message = "An upstream service is temporarily unavailable"


class InsuranceProviderUnavailableError(ExternalServiceError):
    code = "INSURANCE_PROVIDER_UNAVAILABLE"
    http_status = 503
    message = "The insurance service is temporarily unavailable. Please try again shortly."


class PaymentError(StarServeError):
    code = "PAYMENT_ERROR"
    http_status = 402
    message = "Payment processing failed"


class IdempotencyConflictError(ConflictError):
    code = "IDEMPOTENCY_CONFLICT"
    message = "A conflicting idempotent request is already in progress"


class SystemUnavailableError(StarServeError):
    """Platform master switch is off — DB is source of truth."""

    code = "SYSTEM_UNAVAILABLE"
    http_status = 503
    message = "The platform is temporarily switched off"


class ServiceDisabledError(StarServeError):
    """A capability toggle is off in system_settings."""

    code = "SERVICE_DISABLED"
    http_status = 503
    message = "This service is temporarily disabled"
