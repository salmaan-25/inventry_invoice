"""
Phone number validator — Phase 3.

Strips spaces and hyphens before validating so that common formats such as
+91 98765-43210 are accepted.  Returns the cleaned value on success.
"""

import re

from django.core.exceptions import ValidationError

_PHONE_RE = re.compile(r"^\+?[0-9]{10,15}$")


def validate_phone(value: str) -> str:
    """
    Strip spaces and hyphens then verify the phone number is 10–15 digits
    with an optional leading '+'.

    Returns the cleaned (stripped) value.
    Raises ValidationError if the format is invalid.
    """
    cleaned = re.sub(r"[\s\-]", "", value or "")
    if cleaned and not _PHONE_RE.match(cleaned):
        raise ValidationError(
            "Enter a valid phone number (10–15 digits, optional leading +)."
        )
    return cleaned
