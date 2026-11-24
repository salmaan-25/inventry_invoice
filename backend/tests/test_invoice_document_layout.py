"""
Invoice document layout tests — client sample (finalinv.pdf) alignment.

Covers the Phase 5B document contract added for the client's invoice format:
  - company settings expose the seller state and bank details used by the PDF
  - an issued invoice snapshots those fields
  - the rendered PDF is a single page and contains the template's grid fields
"""

from decimal import Decimal
from io import BytesIO

import pytest
from pypdf import PdfReader
from rest_framework import status

from apps.common.constants import ItemType
from apps.company.models import CompanySettings
from apps.customers.models import Customer, CustomerCodeCounter
from apps.invoices.models import Invoice
from apps.products.models import Product, ProductCodeCounter, Unit


pytestmark = pytest.mark.django_db

COMPANY_URL = "/api/settings/company/"
INVOICES_URL = "/api/invoices/"


@pytest.fixture(autouse=True)
def reference_data(db):
    """Create the units, counters and single company-settings row."""
    Unit.objects.get_or_create(name="pcs")
    ProductCodeCounter.objects.get_or_create(pk=1, defaults={"next_value": 1})
    CustomerCodeCounter.objects.get_or_create(pk=1, defaults={"next_value": 1})
    CompanySettings.objects.update_or_create(
        pk=1,
        defaults={
            "business_name": "Anifa Traders",
            "address": "No 1, Test Road, Chennai",
            "state": "Tamil Nadu",
            "phone": "044-12345678",
            "email": "billing@anifa.example.com",
            "gstin": "33AAAAA0000A1Z5",
        },
    )


def make_customer(**kwargs) -> Customer:
    counter = CustomerCodeCounter.objects.get(pk=1)
    defaults = {
        "code": f"C{counter.next_value:04d}",
        "name": "Layout Customer",
        "phone": "9876543210",
        "gstin": "33ABCDE1234F1Z5",
        "state": "Tamil Nadu",
        "billing_address": "12 Test Street, Chennai 600001",
        "is_active": True,
    }
    defaults.update(kwargs)
    counter.next_value += 1
    counter.save(update_fields=["next_value"])
    return Customer.objects.create(**defaults)


def make_product(**kwargs) -> Product:
    counter = ProductCodeCounter.objects.get(pk=1)
    defaults = {
        "code": f"P{counter.next_value:04d}",
        "name": "IMPORTED TEAK SAWN SIZES\n5X4\n259 PCS",
        "item_type": ItemType.GOODS,
        "unit": Unit.objects.get(name="pcs"),
        "selling_price": Decimal("44747.37"),
        "hsn_sac": "44072300",
        "gst_rate": Decimal("18.00"),
        "current_stock": Decimal("100.000"),
        "is_active": True,
    }
    defaults.update(kwargs)
    counter.next_value += 1
    counter.save(update_fields=["next_value"])
    return Product.objects.create(**defaults)


# ---------------------------------------------------------------------------
# Company settings
# ---------------------------------------------------------------------------

def test_company_settings_accept_and_return_document_fields(admin_client):
    response = admin_client.patch(
        COMPANY_URL,
        {
            "state": "Tamil Nadu",
            "bank_holder_name": "Anifa Traders",
            "bank_name": "State Bank of India",
            "bank_account_no": "1234567890123",
            "bank_ifsc": "SBIN0001234",
        },
        format="json",
    )
    assert response.status_code == status.HTTP_200_OK, response.data
    assert response.data["state"] == "Tamil Nadu"
    assert response.data["bank_name"] == "State Bank of India"

    read = admin_client.get(COMPANY_URL)
    assert read.status_code == status.HTTP_200_OK
    assert read.data["bank_holder_name"] == "Anifa Traders"
    assert read.data["bank_ifsc"] == "SBIN0001234"


# ---------------------------------------------------------------------------
# Snapshot
# ---------------------------------------------------------------------------

def test_issue_snapshots_seller_state_and_bank_details(admin_client):
    CompanySettings.objects.filter(pk=1).update(
        bank_holder_name="Anifa Traders",
        bank_name="State Bank of India",
        bank_account_no="1234567890123",
        bank_ifsc="SBIN0001234",
    )
    customer = make_customer()
    product = make_product()

    created = admin_client.post(
        INVOICES_URL,
        {
            "customer": customer.id,
            "invoice_date": "2026-11-21",
            "lines": [{"product": product.id, "quantity": "6.270", "rate": "44747.37"}],
        },
        format="json",
    )
    assert created.status_code == status.HTTP_201_CREATED, created.data
    invoice_id = created.data["id"]

    issued = admin_client.post(f"{INVOICES_URL}{invoice_id}/issue/")
    assert issued.status_code == status.HTTP_200_OK, issued.data

    invoice = Invoice.objects.get(pk=invoice_id)
    snapshot = invoice.business_snapshot or {}
    assert snapshot["state"] == "Tamil Nadu"
    assert snapshot["bank_holder_name"] == "Anifa Traders"
    assert snapshot["bank_account_no"] == "1234567890123"
    assert snapshot["bank_ifsc"] == "SBIN0001234"


# ---------------------------------------------------------------------------
# PDF layout
# ---------------------------------------------------------------------------

def test_pdf_matches_sample_grid_and_stays_on_one_page(admin_client):
    CompanySettings.objects.filter(pk=1).update(
        bank_holder_name="Anifa Traders",
        bank_name="State Bank of India",
        bank_account_no="1234567890123",
        bank_ifsc="SBIN0001234",
    )
    customer = make_customer()
    product = make_product()

    created = admin_client.post(
        INVOICES_URL,
        {
            "customer": customer.id,
            "invoice_date": "2026-11-21",
            "buyer_order_no": "PO-123",
            "order_date": "2026-11-01",
            "dispatch_doc_no": "DD-9",
            "delivery_note_date": "2026-11-20",
            "delivery_note": "DN-1",
            "payment_terms": "30 Days",
            "reference_no_date": "REF-1 01-11-26",
            "other_references": "Other ref",
            "dispatched_through": "Lorry",
            "destination": "Chennai",
            "bill_of_lading_no": "LR-77",
            "motor_vehicle_no": "TN 01 AB 1234",
            "terms_of_delivery": "FOB Chennai",
            "lines": [{"product": product.id, "quantity": "6.270", "rate": "44747.37"}],
        },
        format="json",
    )
    assert created.status_code == status.HTTP_201_CREATED, created.data
    invoice_id = created.data["id"]

    issued = admin_client.post(f"{INVOICES_URL}{invoice_id}/issue/")
    assert issued.status_code == status.HTTP_200_OK, issued.data

    response = admin_client.get(f"{INVOICES_URL}{invoice_id}/document/")
    assert response.status_code == status.HTTP_200_OK
    assert response["Content-Type"] == "application/pdf"
    assert response.content.startswith(b"%PDF-")

    reader = PdfReader(BytesIO(response.content))
    assert len(reader.pages) == 1

    text = reader.pages[0].extract_text()

    # Invoice grid from finalinv.pdf
    for label in [
        "GST INVOICE",
        "(ORIGINAL FOR RECIPIENT)",
        "Invoice No.",
        "Dated",
        "Delivery Note",
        "Mode/Terms of Payment",
        "Reference No. & Date.",
        "Other References",
        "Buyer's Order No.",
        "Dispatch Doc No.",
        "Delivery Note Date",
        "Dispatched through",
        "Destination",
        "Bill of Lading/LR-RR No.",
        "Motor Vehicle No.",
        "Terms of Delivery",
        "Description of Goods",
        "HSN/SAC",
        "GST",
        "Quantity",
        "Rate",
        "Amount",
        "Amount Chargeable (in words)",
        "Taxable",
        "CGST",
        "SGST/UTGST",
        "Tax Amount (in words)",
        "Declaration",
        "Company's Bank Details",
        "Authorised Signatory",
    ]:
        assert label in text, f"missing template label: {label}"

    # Values supplied on the invoice
    for value in [
        "PO-123",
        "DD-9",
        "LR-77",
        "TN 01 AB 1234",
        "FOB Chennai",
    ]:
        assert value in text, f"missing invoice value: {value}"

    # The stored totals are printed with Indian digit grouping
    from apps.invoices.document import format_indian_currency

    invoice = Invoice.objects.get(pk=invoice_id)
    assert format_indian_currency(invoice.subtotal) in text
    assert format_indian_currency(invoice.grand_total) in text

    # Rupee sign is embedded and extracted correctly
    assert "\u20b9" in text


def test_long_invoice_flows_onto_extra_pages(admin_client):
    """A 50-line invoice paginates cleanly instead of overflowing silently."""
    customer = make_customer()
    products = [
        make_product(name=f"Long invoice item {index}")
        for index in range(1, 51)
    ]

    created = admin_client.post(
        INVOICES_URL,
        {
            "customer": customer.id,
            "invoice_date": "2026-11-21",
            "lines": [
                {"product": product.id, "quantity": "1.000", "rate": "100.00"}
                for product in products
            ],
        },
        format="json",
    )
    assert created.status_code == status.HTTP_201_CREATED, created.data
    invoice_id = created.data["id"]

    issued = admin_client.post(f"{INVOICES_URL}{invoice_id}/issue/")
    assert issued.status_code == status.HTTP_200_OK, issued.data

    response = admin_client.get(f"{INVOICES_URL}{invoice_id}/document/")
    assert response.status_code == status.HTTP_200_OK

    reader = PdfReader(BytesIO(response.content))
    assert len(reader.pages) >= 2

    first_text = reader.pages[0].extract_text()
    last_text = reader.pages[-1].extract_text()

    # Header grid is on page 1; the totals footer completes on the last page.
    assert "GST INVOICE" in first_text
    assert "Description of Goods" in first_text
    assert "Amount Chargeable (in words)" in last_text
    assert "Company's Bank Details" in last_text
    assert "Authorised Signatory" in last_text
