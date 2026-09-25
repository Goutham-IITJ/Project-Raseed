class DomainError(Exception):
    """Safe application-boundary error; never includes SQL or provider details."""

    status_code = 422
    code = "validation_error"
    message = "Invalid canonical record."


class NotFound(DomainError):
    status_code = 404
    code = "not_found"
    message = "Resource not found."


class Conflict(DomainError):
    status_code = 409
    code = "conflict"
    message = "A conflicting record already exists."


class InvalidReference(DomainError):
    message = "A referenced record is unavailable."
