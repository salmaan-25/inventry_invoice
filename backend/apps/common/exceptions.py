"""
Custom DRF exception handler — Section 3.6.

Every error response has this shape:

    {
        "code":    "ERROR_CODE",
        "message": "Human readable summary",
        "fields":  { "field_name": ["message", ...] },
        "details": []
    }

HTTP status → code mapping:

    400  VALIDATION_ERROR    — invalid input; `fields` has per-field messages
    400  INVALID_DATE_RANGE  — from date after to date, or missing date
    401  NOT_AUTHENTICATED   — not signed in
    403  PERMISSION_DENIED   — signed in but not allowed
    404  NOT_FOUND           — object does not exist
    409  INVALID_STATE       — action not allowed in current state
    409  INSUFFICIENT_STOCK  — stock too low
    409  OVER_ALLOCATION     — payment/invoice over-allocated
    409  OVER_DISPATCH       — dispatch above remaining
    429  THROTTLED           — rate limit reached
    500  SERVER_ERROR        — unexpected error
"""

import logging

from django.core.exceptions import PermissionDenied as DjangoPermissionDenied
from django.http import Http404
from rest_framework import status
from rest_framework.exceptions import (
    AuthenticationFailed,
    MethodNotAllowed,
    NotAuthenticated,
    NotFound,
    PermissionDenied,
    Throttled,
    ValidationError,
)
from rest_framework.response import Response
from rest_framework.views import exception_handler as drf_exception_handler

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Custom application exceptions
# ---------------------------------------------------------------------------


class AppError(Exception):
    """Base class for all application-level errors that map to a known HTTP
    response.  Subclasses set ``status_code``, ``code``, and optionally
    ``details``."""

    status_code = status.HTTP_400_BAD_REQUEST
    code = "APP_ERROR"
    default_message = "An error occurred."

    def __init__(self, message: str | None = None, details: list | None = None):
        self.message = message or self.default_message
        self.details = details or []
        super().__init__(self.message)


class InvalidDateRangeError(AppError):
    status_code = status.HTTP_400_BAD_REQUEST
    code = "INVALID_DATE_RANGE"
    default_message = "Invalid date range."


class InvalidStateError(AppError):
    status_code = status.HTTP_409_CONFLICT
    code = "INVALID_STATE"
    default_message = "This action is not allowed in the current state."


class InvalidStockOperationError(AppError):
    """A stock operation was requested that the inventory rules do not allow
    (for example a zero change or a movement for a Service product)."""

    status_code = status.HTTP_400_BAD_REQUEST
    code = "VALIDATION_ERROR"
    default_message = "This stock operation is not allowed."


class InsufficientStockError(AppError):
    """``details`` must be a list of dicts with keys:
    product, name, available, required."""

    status_code = status.HTTP_409_CONFLICT
    code = "INSUFFICIENT_STOCK"
    default_message = "One or more products have insufficient stock."


class OverAllocationError(AppError):
    status_code = status.HTTP_409_CONFLICT
    code = "OVER_ALLOCATION"
    default_message = "The allocation exceeds the remaining balance."


class OverDispatchError(AppError):
    status_code = status.HTTP_409_CONFLICT
    code = "OVER_DISPATCH"
    default_message = "The dispatch quantity exceeds the remaining quantity."


# ---------------------------------------------------------------------------
# Error response builder
# ---------------------------------------------------------------------------


def _error_response(
    code: str,
    message: str,
    fields: dict | None = None,
    details: list | None = None,
    http_status: int = status.HTTP_400_BAD_REQUEST,
) -> Response:
    return Response(
        {
            "code": code,
            "message": message,
            "fields": fields or {},
            "details": details or [],
        },
        status=http_status,
    )


# ---------------------------------------------------------------------------
# Exception handler registered in REST_FRAMEWORK settings
# ---------------------------------------------------------------------------


def custom_exception_handler(exc, context):  # noqa: C901
    """
    Maps both DRF exceptions and our custom AppError subclasses to the
    uniform error response shape defined in Section 3.6.
    """

    # --- Application errors -----------------------------------------------

    if isinstance(exc, AppError):
        return _error_response(
            code=exc.code,
            message=exc.message,
            details=exc.details,
            http_status=exc.status_code,
        )

    # --- Django Http404 / PermissionDenied --------------------------------

    if isinstance(exc, Http404):
        return _error_response(
            "NOT_FOUND",
            "The requested resource was not found.",
            http_status=status.HTTP_404_NOT_FOUND,
        )

    if isinstance(exc, DjangoPermissionDenied):
        return _error_response(
            "PERMISSION_DENIED",
            "You do not have permission to perform this action.",
            http_status=status.HTTP_403_FORBIDDEN,
        )

    # --- DRF exceptions ---------------------------------------------------

    # Let DRF normalise the exception first so we always have a Response.
    response = drf_exception_handler(exc, context)

    if response is None:
        # Unexpected / unhandled exception — log it and return 500.
        logger.exception("Unhandled exception in view: %s", exc)
        return _error_response(
            "SERVER_ERROR",
            "An unexpected error occurred. Please try again later.",
            http_status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )

    if isinstance(exc, (NotAuthenticated, AuthenticationFailed)):
        return _error_response(
            "NOT_AUTHENTICATED",
            "Authentication credentials were not provided or are invalid.",
            http_status=status.HTTP_401_UNAUTHORIZED,
        )

    if isinstance(exc, PermissionDenied):
        return _error_response(
            "PERMISSION_DENIED",
            "You do not have permission to perform this action.",
            http_status=status.HTTP_403_FORBIDDEN,
        )

    if isinstance(exc, NotFound):
        return _error_response(
            "NOT_FOUND",
            "The requested resource was not found.",
            http_status=status.HTTP_404_NOT_FOUND,
        )

    if isinstance(exc, Throttled):
        return _error_response(
            "THROTTLED",
            f"Request was throttled. Try again in {exc.wait} seconds." if exc.wait else "Too many requests.",
            http_status=status.HTTP_429_TOO_MANY_REQUESTS,
        )

    if isinstance(exc, MethodNotAllowed):
        return _error_response(
            "VALIDATION_ERROR",
            f"Method '{exc.args[0]}' not allowed.",
            http_status=status.HTTP_405_METHOD_NOT_ALLOWED,
        )

    if isinstance(exc, ValidationError):
        # DRF ValidationError detail can be a dict (field-level), a list, or
        # a string.  Normalise it into our `fields` dict.
        detail = exc.detail
        fields: dict = {}
        message = "Invalid input."

        if isinstance(detail, dict):
            for field, messages in detail.items():
                fields[field] = [
                    str(m) for m in (messages if isinstance(messages, list) else [messages])
                ]
            # Provide a general message from the first field's first error.
            first_messages = next(iter(fields.values()), [])
            if first_messages:
                message = first_messages[0]
        elif isinstance(detail, list):
            # Non-field errors arrive as a list.
            non_field = [str(m) for m in detail]
            fields["non_field_errors"] = non_field
            if non_field:
                message = non_field[0]
        else:
            message = str(detail)

        return _error_response(
            "VALIDATION_ERROR",
            message,
            fields=fields,
            http_status=response.status_code,
        )

    # Fallback: preserve the HTTP status but wrap in the standard shape.
    return _error_response(
        "SERVER_ERROR",
        "An unexpected error occurred.",
        http_status=response.status_code,
    )
