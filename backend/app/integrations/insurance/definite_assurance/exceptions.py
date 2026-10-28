"""Definite Assurance integration exceptions."""

from app.core.exceptions import ExternalServiceError, InsuranceProviderUnavailableError, ValidationAppError


class DefiniteAssuranceError(ExternalServiceError):
    code = "DEFINITE_ASSURANCE_ERROR"
    message = "The insurance provider returned an error"


class DefiniteAssuranceAuthError(DefiniteAssuranceError):
    code = "INSURANCE_PROVIDER_AUTH_ERROR"
    http_status = 502
    message = "Insurance provider authentication failed"


class DefiniteAssuranceValidationError(ValidationAppError):
    code = "INSURANCE_PROVIDER_VALIDATION_ERROR"
    message = "The insurance provider rejected the request"


class DefiniteAssuranceUnavailable(InsuranceProviderUnavailableError):
    code = "INSURANCE_PROVIDER_UNAVAILABLE"
