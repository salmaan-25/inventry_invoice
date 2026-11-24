"""
Application-wide constants — Section 3.2.

Enum strings are upper-case snake_case as required by the spec.
"""

from django.db import models


# ---------------------------------------------------------------------------
# User roles — Section 4
# ---------------------------------------------------------------------------

class Role(models.TextChoices):
    ADMIN = "ADMIN", "Admin"
    STAFF = "STAFF", "Staff"


# ---------------------------------------------------------------------------
# Product item types — Section 1.2 / Phase 4
# ---------------------------------------------------------------------------

class ItemType(models.TextChoices):
    GOODS = "GOODS", "Goods"
    GOODS_HARDWARE = "GOODS_HARDWARE", "Goods (Hardware)"
    SERVICE = "SERVICE", "Service"


# Item types whose stock is tracked (Phase 4 / Section 3.4).
STOCK_TRACKED_ITEM_TYPES = (ItemType.GOODS, ItemType.GOODS_HARDWARE)


# ---------------------------------------------------------------------------
# Stock movement types — Phase 4
# ---------------------------------------------------------------------------

class MovementType(models.TextChoices):
    OPENING = "OPENING", "Opening Stock"
    STOCK_IN = "STOCK_IN", "Stock In"
    ADJUSTMENT = "ADJUSTMENT", "Adjustment"
    SALE = "SALE", "Sale"


# ---------------------------------------------------------------------------
# Invoice status — Phase 5
# ---------------------------------------------------------------------------

class InvoiceStatus(models.TextChoices):
    DRAFT = "DRAFT", "Draft"
    ISSUED = "ISSUED", "Issued"


# ---------------------------------------------------------------------------
# Payment status (derived) — Phase 6
# ---------------------------------------------------------------------------

class PaymentStatus(models.TextChoices):
    UNPAID = "UNPAID", "Unpaid"
    PARTIALLY_PAID = "PARTIALLY_PAID", "Partially Paid"
    PAID = "PAID", "Paid"


# ---------------------------------------------------------------------------
# Delivery status (derived) — Phase 7
# ---------------------------------------------------------------------------

class DeliveryStatus(models.TextChoices):
    PENDING = "PENDING", "Pending"
    PARTIALLY_DELIVERED = "PARTIALLY_DELIVERED", "Partially Delivered"
    DELIVERED = "DELIVERED", "Delivered"


# ---------------------------------------------------------------------------
# Payment methods — Phase 6, 8, 9
# ---------------------------------------------------------------------------

class PaymentMethod(models.TextChoices):
    CASH = "CASH", "Cash"
    UPI = "UPI", "UPI"
    BANK_TRANSFER = "BANK_TRANSFER", "Bank Transfer"
    CHEQUE = "CHEQUE", "Cheque"


# ---------------------------------------------------------------------------
# Indian states and union territories list — Phase 3 (customer state field)
# Used to validate the `state` field on Customer.
# Source: official list of Indian states and UTs.
# ---------------------------------------------------------------------------

INDIAN_STATES_AND_UTS = [
    # States
    "Andhra Pradesh",
    "Arunachal Pradesh",
    "Assam",
    "Bihar",
    "Chhattisgarh",
    "Goa",
    "Gujarat",
    "Haryana",
    "Himachal Pradesh",
    "Jharkhand",
    "Karnataka",
    "Kerala",
    "Madhya Pradesh",
    "Maharashtra",
    "Manipur",
    "Meghalaya",
    "Mizoram",
    "Nagaland",
    "Odisha",
    "Punjab",
    "Rajasthan",
    "Sikkim",
    "Tamil Nadu",
    "Telangana",
    "Tripura",
    "Uttar Pradesh",
    "Uttarakhand",
    "West Bengal",
    # Union Territories
    "Andaman and Nicobar Islands",
    "Chandigarh",
    "Dadra and Nagar Haveli and Daman and Diu",
    "Delhi",
    "Jammu and Kashmir",
    "Ladakh",
    "Lakshadweep",
    "Puducherry",
]

# Choices tuple for model field
INDIAN_STATE_CHOICES = [(s, s) for s in INDIAN_STATES_AND_UTS]

# GST state codes used on invoices when the GSTIN is blank.
INDIAN_STATE_GST_CODES = {
    "Jammu and Kashmir": "01",
    "Himachal Pradesh": "02",
    "Punjab": "03",
    "Chandigarh": "04",
    "Uttarakhand": "05",
    "Haryana": "06",
    "Delhi": "07",
    "Rajasthan": "08",
    "Uttar Pradesh": "09",
    "Bihar": "10",
    "Sikkim": "11",
    "Arunachal Pradesh": "12",
    "Nagaland": "13",
    "Manipur": "14",
    "Mizoram": "15",
    "Tripura": "16",
    "Meghalaya": "17",
    "Assam": "18",
    "West Bengal": "19",
    "Jharkhand": "20",
    "Odisha": "21",
    "Chhattisgarh": "22",
    "Madhya Pradesh": "23",
    "Gujarat": "24",
    "Dadra and Nagar Haveli and Daman and Diu": "26",
    "Maharashtra": "27",
    "Karnataka": "29",
    "Goa": "30",
    "Lakshadweep": "31",
    "Kerala": "32",
    "Tamil Nadu": "33",
    "Puducherry": "34",
    "Andaman and Nicobar Islands": "35",
    "Telangana": "36",
    "Andhra Pradesh": "37",
    "Ladakh": "38",
}


def gst_state_code(state_name: str | None, gstin: str | None = None) -> str:
    """
    Return the two-digit GST state code for a document.

    The GSTIN prefix wins when it is present (it is the statutory value);
    otherwise the state name is looked up. Returns an empty string when
    neither is known.
    """
    if gstin and len(gstin) >= 2 and gstin[:2].isdigit():
        return gstin[:2]
    return INDIAN_STATE_GST_CODES.get((state_name or "").strip(), "")
