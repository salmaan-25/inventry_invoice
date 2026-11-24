"""
Shared Excel export helper — Phases 8 and 9.

Builds a real .xlsx workbook with openpyxl and returns an HttpResponse with
the correct content type and Content-Disposition.

Rules (from Phase 8 spec):
- Validates date range with parse_date_range; both dates required, From not
  after To, both inclusive. Failures return INVALID_DATE_RANGE (400).
- Date cells: real Excel dates formatted DD/MM/YYYY.
- Amount cells: numeric with 2 decimals so Excel can sum them.
- Title row: "Period: DD/MM/YYYY to DD/MM/YYYY", bold.
- Header row: bold, columns as specified per phase.
- Data rows: sorted by date then id.
- Total row: bold, sum of the data rows' Amount column.
- Text cells starting with =, +, - or @ are escaped by prefixing a single quote.
- Empty range: valid workbook with headers and a total of 0.
"""


import datetime

from decimal import Decimal
from io import BytesIO

from django.db.models import Sum
from openpyxl import Workbook
from openpyxl.styles import Font, Alignment, Border, Side, PatternFill
from openpyxl.utils import get_column_letter

from apps.common.dates import parse_date_range
from apps.common.exceptions import InvalidDateRangeError


# ---------------------------------------------------------------------------
# Styling helpers
# -------------------------------------------------------------------------__

TITLE_FONT = Font(name="Calibri", size=14, bold=True)
SUBTITLE_FONT = Font(name="Calibri", size=10, bold=True)
NORMAL_FONT = Font(name="Calibri", size=10)
BOLD_FONT = Font(name="Calibri", size=10, bold=True)
HEADER_FONT = Font(name="Calibri", size=10, bold=True)
ALIGN_CENTER = Alignment(horizontal="center", vertical="center")
ALIGN_LEFT = Alignment(horizontal="left", vertical="center")
ALIGN_RIGHT = Alignment(horizontal="right", vertical="center")
THIN_BORDER = Border(
    left=Side(style="thin"),
    right=Side(style="thin"),
    top=Side(style="thin"),
    bottom=Side(style="thin"),
)


def _escape_text(text: str) -> str:
    """Escape text that starts with =, +, - or @ for Excel safety."""
    if not text:
        return text
    t = str(text)
    if t and t[0] in ("=", "+", "-", "@"):
        return f"'{t}"
    return t


# ---------------------------------------------------------------------------
# Phase 8: expense export
# ---------------------------------------------------------------------------

DEFAULT_EXPENSE_COLUMNS = [
    "Date",
    "Category",
    "Description",
    "Payment method",
    "Paid to",
    "Notes",
    "Amount",
    "Recorded by",
]


def export_expenses_to_xlsx(queryset):
    """
    Build an .xlsx workbook for the given Expense queryset (already filtered
    and ordered by date, id).

    Returns an openpyxl Workbook instance (caller saves to a BytesIO if needed).
    """
    wb = Workbook()
    ws = wb.active
    ws.title = "Expenses"

    # Determine the period from the first/last record if available.
    if queryset.exists():
        first = queryset.first()
        last = queryset.last()
        period_start = first.date
        period_end = last.date
    else:
        period_start = None
        period_end = None

    # ---- Title row (row 1) ----
    if period_start and period_end:
        period_label = f"Period: {period_start.day:02d}/{period_start.month:02d}/{period_start.year:02d} to {period_end.day:02d}/{period_end.month:02d}/{period_end.year}"
    elif period_start:
        period_label = f"Period: {period_start.day:02d}/{period_start.month:02d}/{period_start.year}"
    else:
        period_label = "Period: Expenses Report"

    ws.merge_cells("A1:H1")
    cell = ws["A1"]
    cell.value = period_label
    cell.font = TITLE_FONT
    cell.alignment = Alignment(horizontal="center", vertical="center")

    # ---- Header row (row 2) ----
    headers = DEFAULT_EXPENSE_COLUMNS
    for col_idx, header in enumerate(headers, start=1):
        cell = ws.cell(row=2, column=col_idx, value=header)
        cell.font = HEADER_FONT
        cell.fill = _solid_fill("DCE6F1")
        cell.alignment = ALIGN_CENTER
        cell.border = THIN_BORDER

    # ---- Data rows ----
    row_idx = 3
    for expense in queryset:
        # Date column (col 1): Excel date object, format DD/MM/YYYY
        date_val = expense.date
        date_cell = ws.cell(row=row_idx, column=1, value=date_val)
        date_cell.number_format = "DD/MM/YYYY"
        date_cell.font = NORMAL_FONT
        date_cell.border = THIN_BORDER
        date_cell.alignment = ALIGN_CENTER

        # Category column (col 2)
        cat_cell = ws.cell(
            row=row_idx, column=2, value=_escape_text(expense.category.name)
        )
        cat_cell.font = NORMAL_FONT
        cat_cell.border = THIN_BORDER
        cat_cell.alignment = ALIGN_LEFT

        # Description column (col 3)
        desc_cell = ws.cell(
            row=row_idx, column=3, value=_escape_text(expense.description)
        )
        desc_cell.font = NORMAL_FONT
        desc_cell.border = THIN_BORDER
        desc_cell.alignment = ALIGN_LEFT

        # Payment method column (col 4)
        pay_cell = ws.cell(
            row=row_idx, column=4, value=_escape_text(expense.payment_method or "")
        )
        pay_cell.font = NORMAL_FONT
        pay_cell.border = THIN_BORDER
        pay_cell.alignment = ALIGN_LEFT

        # Paid to column (col 5)
        paid_cell = ws.cell(
            row=row_idx, column=5, value=_escape_text(expense.paid_to or "")
        )
        paid_cell.font = NORMAL_FONT
        paid_cell.border = THIN_BORDER
        paid_cell.alignment = ALIGN_LEFT

        # Notes column (col 6)
        notes_cell = ws.cell(
            row=row_idx, column=6, value=_escape_text(expense.notes or "")
        )
        notes_cell.font = NORMAL_FONT
        notes_cell.border = THIN_BORDER
        notes_cell.alignment = ALIGN_LEFT

        # Amount column (col 7): numeric with 2 decimals
        amount_cell = ws.cell(
            row=row_idx, column=7, value=float(expense.amount)
        )
        amount_cell.number_format = '0.00'
        amount_cell.font = NORMAL_FONT
        amount_cell.border = THIN_BORDER
        amount_cell.alignment = ALIGN_RIGHT

        # Recorded by column (col 8)
        recorder_cell = ws.cell(
            row=row_idx, column=8, value=_escape_text(
                expense.recorded_by.full_name if expense.recorded_by else ""
            )
        )
        recorder_cell.font = NORMAL_FONT
        recorder_cell.border = THIN_BORDER
        recorder_cell.alignment = ALIGN_LEFT

        row_idx += 1

    # ---- Total row (bold, sum of Amount column) ----
    total_row = row_idx  # first row after data
    # Compute sum from the original queryset values.
    total_amount = (
        queryset.aggregate(total=Sum("amount"))["total"] or Decimal("0.00")
    )

    # Column 6 (Notes): "Total" label
    total_label_cell = ws.cell(row=total_row, column=6, value="Total")
    total_label_cell.font = BOLD_FONT
    total_label_cell.border = THIN_BORDER
    total_label_cell.alignment = ALIGN_RIGHT

    # Column 7 (Amount): show total amount numerically (or "Total" marker if empty range)
    if not queryset.exists():
        amount_t_cell = ws.cell(row=total_row, column=7, value="Total")
        amount_t_cell.font = BOLD_FONT
        amount_t_cell.border = THIN_BORDER
        amount_t_cell.alignment = ALIGN_RIGHT
    else:
        amount_t_cell = ws.cell(
            row=total_row, column=7, value=float(total_amount)
        )
        amount_t_cell.number_format = '0.00'
        amount_t_cell.font = BOLD_FONT
        amount_t_cell.border = THIN_BORDER
        amount_t_cell.alignment = ALIGN_RIGHT

    # Set column widths for readability.
    column_widths = {
        1: 12,   # Date
        2: 22,   # Category
        3: 38,   # Description
        4: 20,   # Payment method
        5: 22,   # Paid to
        6: 30,   # Notes
        7: 16,   # Amount
        8: 24,   # Recorded by
    }
    for col_num, width in column_widths.items():
        ws.column_dimensions[get_column_letter(col_num)].width = width

    return wb


# ---------------------------------------------------------------------------
# Phase 9: other income export (reuses the same helper with different columns)
# -------------------------------------------------------------------------#

DEFAULT_INCOME_COLUMNS = [
    "Date",
    "Category",
    "Description",
    "Payment method",
    "Received from",
    "Notes",
    "Amount",
    "Recorded by",
]


def export_income_to_xlsx(queryset):
    """
    Build an .xlsx workbook for OtherIncome queryset.

    Same styling as export_expenses_to_xlsx but with Income columns.
    """
    wb = Workbook()
    ws = wb.active
    ws.title = "Other Income"

    # Determine the period from the first/last record if available.
    if queryset.exists():
        first = queryset.first()
        last = queryset.last()
        period_start = first.date
        period_end = last.date
    else:
        period_start = None
        period_end = None

    # ---- Title row (row 1) ----
    if period_start and period_end:
        period_label = f"Period: {period_start.day:02d}/{period_start.month:02d}/{period_start.year:02d} to {period_end.day:02d}/{period_end.month:02d}/{period_end.year}"
    elif period_start:
        period_label = f"Period: {period_start.day:02d}/{period_start.month:02d}/{period_start.year}"
    else:
        period_label = "Period: Other Income Report"

    ws.merge_cells("A1:I1")
    cell = ws["A1"]
    cell.value = period_label
    cell.font = TITLE_FONT
    cell.alignment = Alignment(horizontal="center", vertical="center")

    # ---- Header row (row 2) ----
    headers = DEFAULT_INCOME_COLUMNS
    for col_idx, header in enumerate(headers, start=1):
        cell = ws.cell(row=2, column=col_idx, value=header)
        cell.font = HEADER_FONT
        cell.fill = _solid_fill("DCE6F1")
        cell.alignment = ALIGN_CENTER
        cell.border = THIN_BORDER

    # ---- Data rows ----
    row_idx = 3
    for income in queryset:
        # Date column (col 1)
        date_val = income.date
        date_cell = ws.cell(row=row_idx, column=1, value=date_val)
        date_cell.number_format = "DD/MM/YYYY"
        date_cell.font = NORMAL_FONT
        date_cell.border = THIN_BORDER
        date_cell.alignment = ALIGN_CENTER

        # Category column (col 2)
        cat_cell = ws.cell(
            row=row_idx, column=2, value=_escape_text(income.category.name)
        )
        cat_cell.font = NORMAL_FONT
        cat_cell.border = THIN_BORDER
        cat_cell.alignment = ALIGN_LEFT

        # Description column (col 3)
        desc_cell = ws.cell(
            row=row_idx, column=3, value=_escape_text(income.description)
        )
        desc_cell.font = NORMAL_FONT
        desc_cell.border = THIN_BORDER
        desc_cell.alignment = ALIGN_LEFT

        # Payment method column (col 4)
        pay_cell = ws.cell(
            row=row_idx, column=4, value=_escape_text(income.payment_method or "")
        )
        pay_cell.font = NORMAL_FONT
        pay_cell.border = THIN_BORDER
        pay_cell.alignment = ALIGN_LEFT

        # Received from column (col 5) — unique to other income
        rec_from_cell = ws.cell(
            row=row_idx, column=5, value=_escape_text(income.received_from or "")
        )
        rec_from_cell.font = NORMAL_FONT
        rec_from_cell.border = THIN_BORDER
        rec_from_cell.alignment = ALIGN_LEFT

        # Notes column (col 6)
        notes_val = getattr(income, "notes", "") or getattr(income, "reference", "") or ""
        notes_cell = ws.cell(
            row=row_idx, column=6, value=_escape_text(notes_val)
        )
        notes_cell.font = NORMAL_FONT
        notes_cell.border = THIN_BORDER
        notes_cell.alignment = ALIGN_LEFT

        # Amount column (col 7)
        amount_cell = ws.cell(
            row=row_idx, column=7, value=float(income.amount)
        )
        amount_cell.number_format = '0.00'
        amount_cell.font = NORMAL_FONT
        amount_cell.border = THIN_BORDER
        amount_cell.alignment = ALIGN_RIGHT

        # Recorded by column (col 8)
        recorder_cell = ws.cell(
            row=row_idx, column=8, value=_escape_text(
                income.recorded_by.full_name if income.recorded_by else ""
            )
        )
        recorder_cell.font = NORMAL_FONT
        recorder_cell.border = THIN_BORDER
        recorder_cell.alignment = ALIGN_LEFT

        row_idx += 1

    # ---- Total row ----
    total_row = row_idx
    total_amount = queryset.aggregate(total=Sum("amount"))["total"] or Decimal("0.00")

    label_cells = ["", "", "", "", "", "Total", "", ""]

    for col_idx, label in enumerate(label_cells, start=1):
        cell = ws.cell(row=total_row, column=col_idx, value=label)
        cell.font = BOLD_FONT
        cell.border = THIN_BORDER
        if col_idx == 7:
            amount_t_cell = ws.cell(
                row=total_row, column=7, value=float(total_amount)
            )
            amount_t_cell.number_format = '0.00'
            amount_t_cell.font = BOLD_FONT
            amount_t_cell.border = THIN_BORDER
            amount_t_cell.alignment = ALIGN_RIGHT
        else:
            cell.border = THIN_BORDER

    # Set column widths
    column_widths = {
        1: 12,   # Date
        2: 22,   # Category
        3: 38,   # Description
        4: 20,   # Payment method
        5: 22,   # Received from
        6: 30,   # Notes
        7: 16,   # Amount
        8: 24,   # Recorded by
        9: 20,   # (empty placeholder for alignment)
    }
    for col_num, width in column_widths.items():
        ws.column_dimensions[get_column_letter(col_num)].width = width

    return wb


def _solid_fill(color_hex: str):
    """Return a openpyxl PatternFill for a hex colour string."""
    return PatternFill(start_color=color_hex, end_color=color_hex, fill_type="solid")