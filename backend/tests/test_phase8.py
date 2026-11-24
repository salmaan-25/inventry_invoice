"""
Phase 8 tests — Expenses and Excel export.

Test groups:
    1. Expense category and expense CRUD, list filters, search, total_amount
    2. Expense export: empty range, one-day, boundary dates, multi-day, invalid range
    3. Authentication: anonymous cannot export; staff and admin can
"""

import datetime

import pytest
from decimal import Decimal
from rest_framework import status
from rest_framework.test import APIClient

from apps.accounts.models import User
from apps.common.constants import Role
from apps.common.exceptions import InvalidDateRangeError
from apps.expenses.models import Expense, ExpenseCategory
from apps.products.models import Unit
from apps.common.constants import ItemType

EXPENSE_CATEGORIES_URL = "/api/expense-categories/"
EXPENSES_URL = "/api/expenses/"
EXPENSE_EXPORT_URL = "/api/expenses/export/"

pytestmark = pytest.mark.django_db


# ---------------------------------------------------------------------------
# Fixtures & helpers
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def reference_data(db):
    """Ensure units and that expense categories are seeded."""
    Unit.objects.get_or_create(name="hour")
    # Seed expense categories if missing
    for name in ["Rent", "Electricity", "Transport", "Salary", "Repairs", "Other"]:
        ExpenseCategory.objects.get_or_create(name=name)


def make_expense_category(name="Rent"):
    obj, _ = ExpenseCategory.objects.get_or_create(name=name)
    return obj


def make_expense(
    client,
    *,
    category_name="Rent",
    date=None,
    amount="100.00",
    payment_method="CASH",
    paid_to="",
    description="",
):
    """Create an expense via the API."""
    if date is None:
        date = datetime.date.today()
    cat = ExpenseCategory.objects.get(name=category_name)
    payload = {
        "date": date.isoformat(),
        "category": cat.id,
        "amount": amount,
        "payment_method": payment_method,
        "paid_to": paid_to,
        "description": description,
    }
    return client.post(EXPENSES_URL, payload, format="json")


# ===========================================================================
# 1. Category and expense CRUD
# ===========================================================================

def test_expense_category_list_create(staff_client):
    # List
    response = staff_client.get(EXPENSE_CATEGORIES_URL)
    assert response.status_code == status.HTTP_200_OK
    assert any(c["name"] == "Rent" for c in response.data)

    # Create
    response = staff_client.post(
        EXPENSE_CATEGORIES_URL, {"name": "New Category"}, format="json"
    )
    assert response.status_code == status.HTTP_201_CREATED


def test_expense_list_create(staff_client):
    # Create a few expenses
    make_expense(staff_client, category_name="Rent", amount="200.00")
    make_expense(staff_client, category_name="Electricity", amount="150.50")
    make_expense(staff_client, category_name="Transport", amount="50.00")

    # List
    response = staff_client.get(EXPENSES_URL)
    assert response.status_code == status.HTTP_200_OK
    assert len(response.data["results"]) == 3
    assert response.data["total_amount"] == "400.50"


def test_expense_filter_by_category(staff_client):
    make_expense(staff_client, category_name="Rent", amount="100.00")
    make_expense(staff_client, category_name="Electricity", amount="200.00")

    response = staff_client.get(f"{EXPENSES_URL}?category={ExpenseCategory.objects.get(name='Rent').id}")
    assert response.status_code == status.HTTP_200_OK
    assert len(response.data["results"]) == 1
    assert response.data["results"][0]["category_name"] == "Rent"
    assert response.data["total_amount"] == "100.00"


def test_expense_filter_by_date_range(staff_client):
    today = datetime.date.today()
    make_expense(staff_client, category_name="Rent", date=today, amount="100.00")
    make_expense(staff_client, category_name="Electricity", date=today - datetime.timedelta(days=5), amount="50.00")

    response = staff_client.get(f"{EXPENSES_URL}?from={today}&to={today}")
    assert response.status_code == status.HTTP_200_OK
    assert len(response.data["results"]) == 1
    assert response.data["total_amount"] == "100.00"


def test_expense_search(staff_client):
    make_expense(staff_client, category_name="Rent", amount="200.00", description="Office rent for HQ")
    make_expense(staff_client, category_name="Electricity", description="Monthly power bill")

    response = staff_client.get(f"{EXPENSES_URL}?search=HQ")
    assert response.status_code == status.HTTP_200_OK
    assert len(response.data["results"]) == 1
    assert response.data["total_amount"] == "200.00"  # only the "HQ" one


# ===========================================================================
# 2. Expense export
# ===========================================================================

def test_export_empty_range(staff_client):
    response = staff_client.get(EXPENSE_EXPORT_URL, {"from": "2026-12-01", "to": "2026-12-31"})
    assert response.status_code == status.HTTP_200_OK
    assert "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet" in response["Content-Type"]
    assert "attachment" in response["Content-Disposition"]
    filename = "expenses_2026-12-01_to_2026-12-31.xlsx"
    assert filename in response["Content-Disposition"]

    # Verify it's a valid workbook (openpyxl can read it)
    from io import BytesIO
    from openpyxl import load_workbook
    wb = load_workbook(BytesIO(response.content))
    assert "Expenses" in wb.sheetnames
    ws = wb["Expenses"]
    # Header row exists
    assert ws["A1"].value.startswith("Period:")
    # Total row exists
    assert ws.cell(row=3, column=7).value == "Total"


def test_export_one_day_range(staff_client):
    today = datetime.date.today()
    make_expense(staff_client, category_name="Rent", date=today, amount="100.00")

    response = staff_client.get(EXPENSE_EXPORT_URL, {"from": today.isoformat(), "to": today.isoformat()})
    assert response.status_code == status.HTTP_200_OK
    assert response["Content-Type"].startswith("application/vnd")

    from io import BytesIO
    from openpyxl import load_workbook
    wb = load_workbook(BytesIO(response.content))
    ws = wb["Expenses"]
    # Should have header + 1 data row + total row = 3 rows (row 1 = title, row 2 = header, row 3 = data, row 4 = total)
    assert ws.max_row >= 4


def test_export_boundary_dates(staff_client):
    today = datetime.date.today()
    make_expense(staff_client, category_name="Rent", date=today, amount="100.00")
    make_expense(staff_client, category_name="Electricity", date=today - datetime.timedelta(days=1), amount="50.00")
    make_expense(staff_client, category_name="Transport", date=today + datetime.timedelta(days=1), amount="75.00")

    # Only the today expense should be in range
    response = staff_client.get(EXPENSE_EXPORT_URL, {"from": today.isoformat(), "to": today.isoformat()})
    assert response.status_code == status.HTTP_200_OK
    from openpyxl import load_workbook
    from io import BytesIO
    wb = load_workbook(BytesIO(response.content))
    ws = wb["Expenses"]
    # Data rows: only the today expense (row 3), total should be 100.00
    assert Decimal(str(ws.cell(row=3, column=7).value)) == Decimal("100.00")


def test_export_multi_day_range(staff_client):
    today = datetime.date.today()
    make_expense(staff_client, category_name="Rent", date=today, amount="100.00")
    make_expense(staff_client, category_name="Electricity", date=today - datetime.timedelta(days=2), amount="60.00")
    make_expense(staff_client, category_name="Transport", date=today - datetime.timedelta(days=5), amount="30.00")

    response = staff_client.get(EXPENSE_EXPORT_URL, {"from": (today - datetime.timedelta(days=5)).isoformat(), "to": today.isoformat()})
    assert response.status_code == status.HTTP_200_OK
    from openpyxl import load_workbook
    from io import BytesIO
    wb = load_workbook(BytesIO(response.content))
    ws = wb["Expenses"]
    # 3 data rows + header + title + total
    assert ws.max_row >= 5


def test_export_invalid_range_rejected(staff_client):
    response = staff_client.get(EXPENSE_EXPORT_URL, {"from": "2026-12-31", "to": "2026-12-01"})
    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert response.data["code"] == "INVALID_DATE_RANGE"


def test_export_missing_dates_rejected(staff_client):
    response = staff_client.get(EXPENSE_EXPORT_URL, {"from": "2026-12-01"})
    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert response.data["code"] == "INVALID_DATE_RANGE"


# ===========================================================================
# 3. Authentication
# ===========================================================================

def test_export_anonymous_rejected(anon_client):
    response = anon_client.get(EXPENSE_EXPORT_URL, {"from": "2026-12-01", "to": "2026-12-31"})
    assert response.status_code in (status.HTTP_401_UNAUTHORIZED, status.HTTP_403_FORBIDDEN)


def test_export_staff_and_admin(staff_client, admin_client):
    today = datetime.date.today()
    make_expense(staff_client, category_name="Rent", date=today, amount="100.00")

    # Staff can export
    response = staff_client.get(EXPENSE_EXPORT_URL, {"from": today.isoformat(), "to": today.isoformat()})
    assert response.status_code == status.HTTP_200_OK

    # Admin can export
    response = admin_client.get(EXPENSE_EXPORT_URL, {"from": today.isoformat(), "to": today.isoformat()})
    assert response.status_code == status.HTTP_200_OK