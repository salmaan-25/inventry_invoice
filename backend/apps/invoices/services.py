"""
Invoice business logic — Phase 5.

Two public functions:

calculate_invoice(lines_data, is_gst_invoice, advance_amount)
    Pure calculation — returns line totals, tax, roundoff, and balance.
    This is the ONLY place that computes totals.

issue_invoice(invoice_id, user)
    Transitions a DRAFT invoice to ISSUED in one transaction:
    1. Lock the invoice row.
    2. Validate customer is active.
    3. Recalculate totals and snapshots.
    4. Sync advance payment allocation.
    5. Mark ISSUED.
    (Stock deduction is decoupled as requested: user manages stock manually in Inventory).
"""

import logging
from decimal import ROUND_HALF_UP, Decimal
from typing import List

from django.db import transaction
from django.utils import timezone

from apps.common.constants import InvoiceStatus, ItemType
from apps.common.decimals import format_money, format_quantity, to_decimal
from apps.common.exceptions import InvalidStateError
from apps.company.models import CompanySettings
from apps.customers.models import Customer
from apps.invoices.models import Invoice, InvoiceItem

logger = logging.getLogger(__name__)

TWO_PLACES = Decimal("0.01")
ZERO = Decimal("0.00")


# ---------------------------------------------------------------------------
# Calculation service
# ---------------------------------------------------------------------------

def calculate_invoice(
    lines_data: List[dict],
    is_gst_invoice: bool = True,
    advance_amount: Decimal = Decimal("0.00"),
) -> dict:
    """
    Pure calculation: given line dicts, compute totals, tax, and balance due.

    Each line dict can contain:
        quantity    (Decimal or string)
        rate        (Decimal or string)
        gst_rate    (Decimal or None)
    """
    computed_lines = []
    subtotal = ZERO
    total_cgst = ZERO
    total_sgst = ZERO

    for idx, line in enumerate(lines_data, start=1):
        qty = to_decimal(line["quantity"])
        rate = to_decimal(line["rate"])
        line_total = (qty * rate).quantize(TWO_PLACES, rounding=ROUND_HALF_UP)

        gst_rate = line.get("gst_rate")
        cgst_amount = ZERO
        sgst_amount = ZERO

        if is_gst_invoice and gst_rate is not None:
            gst_rate_dec = to_decimal(gst_rate)
            half_rate = (gst_rate_dec / 2).quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP)
            cgst_amount = (line_total * half_rate / 100).quantize(TWO_PLACES, rounding=ROUND_HALF_UP)
            sgst_amount = cgst_amount  # Intra-state CGST == SGST

        subtotal += line_total
        total_cgst += cgst_amount
        total_sgst += sgst_amount

        computed_lines.append(
            {
                "line_no": idx,
                "line_total": line_total,
                "cgst_amount": cgst_amount,
                "sgst_amount": sgst_amount,
            }
        )

    total_tax = total_cgst + total_sgst
    raw_total = subtotal + total_tax

    rounded = raw_total.quantize(Decimal("1"), rounding=ROUND_HALF_UP)
    round_off = rounded - raw_total
    grand_total = raw_total + round_off

    adv = to_decimal(advance_amount) if advance_amount is not None else ZERO
    balance_amount = max(ZERO, grand_total - adv)

    return {
        "lines": computed_lines,
        "subtotal": subtotal.quantize(TWO_PLACES),
        "total_cgst": total_cgst.quantize(TWO_PLACES),
        "total_sgst": total_sgst.quantize(TWO_PLACES),
        "total_tax": total_tax.quantize(TWO_PLACES),
        "round_off": round_off.quantize(TWO_PLACES),
        "grand_total": grand_total.quantize(TWO_PLACES),
        "advance_amount": adv.quantize(TWO_PLACES),
        "balance_amount": balance_amount.quantize(TWO_PLACES),
    }


# ---------------------------------------------------------------------------
# Snapshots & Advance sync
# ---------------------------------------------------------------------------

def _build_business_snapshot(company: CompanySettings) -> dict:
    """Capture a point-in-time copy of company settings for the invoice."""
    return {
        "business_name": company.business_name,
        "address": company.address,
        "state": company.state,
        "phone": company.phone,
        "email": company.email,
        "gstin": company.gstin,
        "logo": company.logo.name if company.logo else None,
        "bank_holder_name": company.bank_holder_name,
        "bank_name": company.bank_name,
        "bank_account_no": company.bank_account_no,
        "bank_ifsc": company.bank_ifsc,
    }


def _build_customer_snapshot(customer: Customer) -> dict:
    """Capture a point-in-time copy of customer details for the invoice."""
    return {
        "code": customer.code,
        "name": customer.name,
        "phone": customer.phone,
        "gstin": customer.gstin,
        "state": customer.state,
        "billing_address": customer.billing_address,
    }


def _build_line_snapshot(item: InvoiceItem) -> dict:
    """Capture product snapshot fields from a live product if present, or keep item fields."""
    if item.product:
        product = item.product
        return {
            "product_name": item.product_name or product.name,
            "product_code": item.product_code or product.code,
            "hsn_sac": item.hsn_sac or product.hsn_sac,
            "unit_name": item.unit_name or (product.unit.name if product.unit else "pcs"),
            "item_type": item.item_type or product.item_type,
            "gst_rate": str(item.gst_rate) if item.gst_rate is not None else (str(product.gst_rate) if product.gst_rate is not None else None),
        }
    return {
        "product_name": item.product_name,
        "product_code": item.product_code or "",
        "hsn_sac": item.hsn_sac or "",
        "unit_name": item.unit_name or "pcs",
        "item_type": item.item_type or "GOODS",
        "gst_rate": str(item.gst_rate) if item.gst_rate is not None else None,
    }


def sync_invoice_advance_payment(invoice: Invoice, user) -> None:
    """
    Ensure an advance payment record and allocation exist when advance_amount > 0.
    Keeps customer balance, open invoices, and payment ledger perfectly aligned.
    """
    from apps.payments.models import Payment, PaymentAllocation
    from apps.common.constants import PaymentMethod

    adv = invoice.advance_amount or Decimal("0.00")
    ref_tag = f"ADVANCE-INV-{invoice.id}"
    existing_payment = Payment.objects.filter(reference=ref_tag).first()

    if adv > 0:
        if existing_payment:
            existing_payment.amount = adv
            existing_payment.payment_date = invoice.invoice_date
            existing_payment.save(update_fields=["amount", "payment_date"])
            alloc = existing_payment.allocations.filter(invoice=invoice).first()
            if alloc:
                alloc.amount = adv
                alloc.save(update_fields=["amount"])
            else:
                PaymentAllocation.objects.create(payment=existing_payment, invoice=invoice, amount=adv)
        else:
            payment = Payment.objects.create(
                customer=invoice.customer,
                payment_date=invoice.invoice_date,
                amount=adv,
                method=PaymentMethod.CASH,
                reference=ref_tag,
                note=f"Advance payment for invoice #{invoice.invoice_number or invoice.id}",
                received_by=user or invoice.created_by,
            )
            PaymentAllocation.objects.create(payment=payment, invoice=invoice, amount=adv)
    else:
        if existing_payment:
            existing_payment.allocations.all().delete()
            existing_payment.delete()

    # Automatically keep OtherIncome in sync (only when advance money received)
    try:
        from apps.other_income.services import sync_invoice_advance_income
        sync_invoice_advance_income(invoice, user)
    except Exception as e:
        logger.warning("Failed to sync invoice advance income for invoice %s: %s", invoice.id, e)


def _recalculate_draft(invoice: Invoice) -> None:
    """
    Recalculate and save totals for an invoice (draft or issued).
    """
    items = list(invoice.items.all())
    is_gst = (invoice.invoice_type != "NON_GST")

    lines_data = [
        {
            "quantity": item.quantity,
            "rate": item.rate,
            "gst_rate": item.gst_rate if is_gst else None,
        }
        for item in items
    ]
    calc = calculate_invoice(
        lines_data,
        is_gst_invoice=is_gst,
        advance_amount=invoice.advance_amount,
    )

    for idx, item in enumerate(items):
        line_calc = calc["lines"][idx]
        item.line_total = line_calc["line_total"]
        item.cgst_amount = line_calc["cgst_amount"]
        item.sgst_amount = line_calc["sgst_amount"]
        item.save(update_fields=["line_total", "cgst_amount", "sgst_amount"])

    invoice.subtotal = calc["subtotal"]
    invoice.total_cgst = calc["total_cgst"]
    invoice.total_sgst = calc["total_sgst"]
    invoice.total_tax = calc["total_tax"]
    invoice.round_off = calc["round_off"]
    invoice.grand_total = calc["grand_total"]
    invoice.advance_amount = calc["advance_amount"]
    invoice.balance_amount = calc["balance_amount"]
    invoice.save(update_fields=[
        "subtotal", "total_cgst", "total_sgst",
        "total_tax", "round_off", "grand_total",
        "advance_amount", "balance_amount", "updated_at",
    ])


# ---------------------------------------------------------------------------
# Issue service
# ---------------------------------------------------------------------------

@transaction.atomic
def issue_invoice(invoice_id: int, user) -> Invoice:
    """
    Transition a DRAFT invoice to ISSUED in one atomic transaction.
    Stock deduction is decoupled (managed manually by user).
    """
    invoice = (
        Invoice.objects.select_for_update()
        .select_related("customer", "created_by")
        .get(pk=invoice_id)
    )

    if invoice.status == InvoiceStatus.ISSUED:
        return invoice

    if invoice.status != InvoiceStatus.DRAFT:
        raise InvalidStateError("Only DRAFT invoices can be issued.")

    customer = invoice.customer
    if not customer.is_active:
        raise InvalidStateError(
            f"Customer '{customer.name}' is inactive and cannot be invoiced."
        )

    items = list(invoice.items.all())
    if not items:
        raise InvalidStateError("An invoice must have at least one line to be issued.")

    # Validate linked products if any
    for item in items:
        if item.product and not item.product.is_active:
            raise InvalidStateError(
                f"Product '{item.product.name}' on line {item.line_no} is inactive."
            )

    is_gst = (invoice.invoice_type != "NON_GST")
    lines_data = [
        {
            "quantity": item.quantity,
            "rate": item.rate,
            "gst_rate": item.gst_rate if is_gst else None,
        }
        for item in items
    ]
    calc = calculate_invoice(
        lines_data,
        is_gst_invoice=is_gst,
        advance_amount=invoice.advance_amount,
    )

    # Save snapshots
    company = CompanySettings.objects.first()
    business_snapshot = _build_business_snapshot(company) if company else {}
    customer_snapshot = _build_customer_snapshot(customer)

    for idx, item in enumerate(items):
        snapshot = _build_line_snapshot(item)
        line_calc = calc["lines"][idx]
        item.product_name = snapshot["product_name"]
        item.product_code = snapshot["product_code"]
        item.hsn_sac = snapshot["hsn_sac"]
        item.unit_name = snapshot["unit_name"]
        item.item_type = snapshot["item_type"]
        item.gst_rate = to_decimal(snapshot["gst_rate"]) if snapshot["gst_rate"] is not None else None
        item.line_total = line_calc["line_total"]
        item.cgst_amount = line_calc["cgst_amount"]
        item.sgst_amount = line_calc["sgst_amount"]
        item.save(update_fields=[
            "product_name", "product_code", "hsn_sac",
            "unit_name", "item_type", "gst_rate",
            "line_total", "cgst_amount", "sgst_amount",
        ])

    invoice.subtotal = calc["subtotal"]
    invoice.total_cgst = calc["total_cgst"]
    invoice.total_sgst = calc["total_sgst"]
    invoice.total_tax = calc["total_tax"]
    invoice.round_off = calc["round_off"]
    invoice.grand_total = calc["grand_total"]
    invoice.advance_amount = calc["advance_amount"]
    invoice.balance_amount = calc["balance_amount"]
    invoice.business_snapshot = business_snapshot
    invoice.customer_snapshot = customer_snapshot

    invoice.status = InvoiceStatus.ISSUED
    invoice.issued_by = user
    invoice.issued_at = timezone.now()
    if not invoice.invoice_number:
        invoice.invoice_number = f"{invoice.id}"
    invoice.save(update_fields=[
        "subtotal", "total_cgst", "total_sgst",
        "total_tax", "round_off", "grand_total",
        "advance_amount", "balance_amount",
        "business_snapshot", "customer_snapshot",
        "status", "issued_by", "issued_at", "invoice_number", "updated_at",
    ])

    sync_invoice_advance_payment(invoice, user)

    logger.info("Invoice %d issued by user %d", invoice.id, user.id)
    return invoice
