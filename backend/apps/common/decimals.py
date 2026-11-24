"""
Decimal helpers — Section 3.2.

Money:    DecimalField(max_digits=14, decimal_places=2)
Quantity: DecimalField(max_digits=12, decimal_places=3)

API output: strings ("1250.00", "10.500").
API input:  accepts strings or numbers, converted to Decimal without passing
            through float (preserves exactness).
"""

import decimal
from decimal import Decimal, InvalidOperation


MONEY_DECIMAL_PLACES = 2
QUANTITY_DECIMAL_PLACES = 3


def to_decimal(value) -> Decimal:
    """
    Convert a string or numeric value to Decimal without float rounding.

    Raises decimal.InvalidOperation if the value cannot be converted.
    """
    if isinstance(value, Decimal):
        return value
    if isinstance(value, float):
        # Use string conversion to avoid float imprecision.
        return Decimal(str(value))
    return Decimal(value)


def parse_decimal(value) -> Decimal:
    """
    Parse an API input (string or number) into a Decimal.

    Returns a Decimal.  Raises ValueError with a friendly message if the
    value is not a valid decimal representation.
    """
    try:
        return to_decimal(value)
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise ValueError(f"'{value}' is not a valid decimal number.") from exc


def format_money(value: Decimal) -> str:
    """Format a Decimal as a money string with exactly 2 decimal places."""
    return f"{value:.{MONEY_DECIMAL_PLACES}f}"


def format_quantity(value: Decimal) -> str:
    """Format a Decimal as a quantity string with exactly 3 decimal places."""
    return f"{value:.{QUANTITY_DECIMAL_PLACES}f}"


# ---------------------------------------------------------------------------
# DRF serializer field helpers (used by serializers in later phases)
# ---------------------------------------------------------------------------


def decimal_field_kwargs_money():
    """Standard kwargs for a money DecimalField."""
    return {"max_digits": 14, "decimal_places": MONEY_DECIMAL_PLACES}


def decimal_field_kwargs_quantity():
    """Standard kwargs for a quantity DecimalField."""
    return {"max_digits": 12, "decimal_places": QUANTITY_DECIMAL_PLACES}
