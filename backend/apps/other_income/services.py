"""
Other income services — syncing invoice advance and recorded payments to OtherIncome.
"""

import logging
from decimal import Decimal
from typing import Optional

from django.contrib.auth import get_user_model
from apps.other_income.models import OtherIncome, IncomeCategory

logger = logging.getLogger(__name__)

INVOICE_INCOME_CATEGORY = "Invoice Payment"


def get_invoice_income_category() -> IncomeCategory:
    """Get or create the category used for invoice-derived income."""
    category, _ = IncomeCategory.objects.get_or_create(name=INVOICE_INCOME_CATEGORY)
    return category


def sync_invoice_advance_income(invoice, user=None) -> Optional[OtherIncome]:
    """
    Sync advance payment of an invoice to OtherIncome.

    Rules:
    - If advance_amount > 0, creates or updates an OtherIncome record with
      reference 'ADVANCE-INV-{invoice.id}'.
    - If advance_amount <= 0, deletes any existing OtherIncome with that reference.
    - Money is only recorded as income when actually received (advance > 0).
    """
    ref_tag = f"ADVANCE-INV-{invoice.id}"
    adv = invoice.advance_amount or Decimal("0.00")

    if adv <= Decimal("0.00"):
        OtherIncome.objects.filter(reference=ref_tag).delete()
        return None

    category = get_invoice_income_category()
    rec_user = user or getattr(invoice, "created_by", None)
    if not rec_user or not getattr(rec_user, "id", None):
        User = get_user_model()
        rec_user = User.objects.filter(is_superuser=True).first() or User.objects.first()

    inv_label = invoice.invoice_number or str(invoice.id)
    cust_name = invoice.customer.name if invoice.customer else "Customer"

    income, _ = OtherIncome.objects.update_or_create(
        reference=ref_tag,
        defaults={
            "date": invoice.invoice_date,
            "category": category,
            "description": f"Advance payment for Invoice #{inv_label}",
            "amount": adv,
            "payment_method": "CASH",
            "received_from": cust_name,
            "recorded_by": rec_user,
        },
    )
    logger.info("Synced advance income for invoice %s: %s", inv_label, adv)
    return income


def sync_payment_record_income(payment) -> Optional[OtherIncome]:
    """
    Sync a recorded payment (from /api/payments/) to OtherIncome.

    Rules:
    - Ignores payments with reference starting with 'ADVANCE-INV-'
      (those are already managed by sync_invoice_advance_income).
    - Creates or updates an OtherIncome record with reference 'PAYMENT-{payment.id}'.
    - Description includes invoice numbers from allocations.
    """
    if payment.reference and payment.reference.startswith("ADVANCE-INV-"):
        return None

    if payment.amount <= Decimal("0.00"):
        return None

    ref_tag = f"PAYMENT-{payment.id}"
    category = get_invoice_income_category()

    allocs = payment.allocations.select_related("invoice").all()
    if allocs.exists():
        inv_nums = ", ".join([f"#{a.invoice.invoice_number or a.invoice.id}" for a in allocs])
        desc = f"Payment received for Invoice {inv_nums}"
    else:
        desc = payment.note or f"Payment from {payment.customer.name if payment.customer else 'Customer'}"

    cust_name = payment.customer.name if payment.customer else "Customer"
    rec_user = payment.received_by
    if not rec_user or not getattr(rec_user, "id", None):
        User = get_user_model()
        rec_user = User.objects.filter(is_superuser=True).first() or User.objects.first()

    income, _ = OtherIncome.objects.update_or_create(
        reference=ref_tag,
        defaults={
            "date": payment.payment_date,
            "category": category,
            "description": desc,
            "amount": payment.amount,
            "payment_method": payment.method or "CASH",
            "received_from": cust_name,
            "recorded_by": rec_user,
        },
    )
    logger.info("Synced payment record income for payment %d: %s", payment.id, payment.amount)
    return income
