"""
Date-range helper — Section 3.2 / Phase 0.

parse_date_range(request) → (from_date: date, to_date: date)

Both ?from= and ?to= query parameters are required.
Both are inclusive.
Raises InvalidDateRangeError (HTTP 400) if:
  - either date is missing
  - either date cannot be parsed as YYYY-MM-DD
  - from_date is later than to_date
"""

import datetime
from typing import Tuple

from apps.common.exceptions import InvalidDateRangeError


DATE_FORMAT = "%Y-%m-%d"


def _parse_date(value: str, param_name: str) -> datetime.date:
    """Parse a YYYY-MM-DD string into a date object, raising
    InvalidDateRangeError on failure."""
    try:
        return datetime.datetime.strptime(value, DATE_FORMAT).date()
    except (ValueError, TypeError):
        raise InvalidDateRangeError(
            f"'{param_name}' must be a valid date in YYYY-MM-DD format."
        )


def parse_date_range(request) -> Tuple[datetime.date, datetime.date]:
    """
    Extract and validate ?from= and ?to= query parameters.

    Both parameters are required. from_date must not be after to_date.
    Returns an inclusive (from_date, to_date) tuple.
    """
    from_str = request.query_params.get("from", "").strip()
    to_str = request.query_params.get("to", "").strip()

    if not from_str:
        raise InvalidDateRangeError("The 'from' date is required.")
    if not to_str:
        raise InvalidDateRangeError("The 'to' date is required.")

    from_date = _parse_date(from_str, "from")
    to_date = _parse_date(to_str, "to")

    if from_date > to_date:
        raise InvalidDateRangeError(
            "The 'from' date cannot be later than the 'to' date."
        )

    return from_date, to_date
