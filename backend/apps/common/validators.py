"""
Shared validators.

GSTIN validation is shared by company settings (Phase 2) and customers
(Phase 3): 15 characters, pattern
``^\\d{2}[A-Z]{5}\\d{4}[A-Z][1-9A-Z]Z[0-9A-Z]$``.
"""

import re

from django.core.exceptions import ValidationError

GSTIN_PATTERN = re.compile(r"^\d{2}[A-Z]{5}\d{4}[A-Z][1-9A-Z]Z[0-9A-Z]$")
GSTIN_LENGTH = 15


def validate_gstin(value: str) -> str:
    """
    Validate an Indian GSTIN and return it without surrounding whitespace.

    An empty value is allowed because GSTIN is optional. Any other value must
    match the 15-character GSTIN format exactly.
    """
    value = (value or "").strip()
    if not value:
        return ""
    if len(value) != GSTIN_LENGTH or not GSTIN_PATTERN.match(value):
        raise ValidationError("Enter a valid 15-character GSTIN.")
    return value
