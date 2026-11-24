"""
apps.common — shared utilities used by every domain app.

Modules
-------
pagination   — StandardPagination (page-number, default 20, max 100)
exceptions   — custom DRF exception handler (Section 3.6 error shape)
permissions  — IsAdmin, IsAdminOrStaff convenience classes
decimals     — safe Decimal I/O helpers
dates        — parse_date_range for inclusive From/To filtering
constants    — application-wide enum values and lookup lists
"""
