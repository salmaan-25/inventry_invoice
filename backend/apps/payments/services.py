"""
Payment business logic — Phase 6.

create_payment(validated_data, user)
    Records a payment and its allocations in one transaction.

    Rules (D11 Path A):
      - amount > 0 and every allocation amount > 0.
      - allocations add up exactly to the payment amount.
      - every allocation targets an ISSUED invoice of the payment's customer.
      - an invoice appears once per payment.
      - the allocation cannot exceed the invoice's remaining balance.
      - a retry with the same client_token returns the existing payment.

    Target invoices are locked in id order before balances are checked, so
    concurrent payments cannot jointly over-allocate one invoice.
"""

import logging
from decimal import Decimal
from typing import Tuple

from django.db import IntegrityError, transaction
from django.db.models import Sum
from rest_framework.exceptions import ValidationError

from apps.common.constants import InvoiceStatus
from apps.common.decimals import format_money
from apps.common.exceptions import OverAllocationError
from apps.invoices.models import Invoice
from apps.payments.models import Payment, PaymentAllocation

logger = logging.getLogger(__name__)

ZERO = Decimal("0.00")


@transaction.atomic
def create_payment(validated_data: dict, user) -> Tuple[Payment, bool]:
    """
    Create a payment and its allocations.

    Returns ``(payment, created)``. ``created`` is False when the request is a
    retry carrying a client_token that already exists.
    """
    client_token = validated_data.get("client_token")

    # Fast path: a completed retry returns the original payment.
    if client_token:
        existing = Payment.objects.filter(client_token=client_token).first()
        if existing:
            return existing, False

    customer = validated_data["customer"]
    allocations_data = validated_data["allocations"]

    if not allocations_data:
        raise ValidationError(
            {"allocations": ["At least one allocation is required."]}
        )

    invoice_ids = sorted({alloc["invoice"].id for alloc in allocations_data})
    if len(invoice_ids) != len(allocations_data):
        raise ValidationError(
            {"allocations": ["Each invoice may appear only once per payment."]}
        )

    # Lock in id order to avoid deadlocks between concurrent payments.
    invoices = {
        invoice.id: invoice
        for invoice in Invoice.objects.select_for_update()
        .filter(id__in=invoice_ids)
        .order_by("id")
    }
    missing_ids = sorted(set(invoice_ids) - set(invoices))
    if missing_ids:
        raise ValidationError(
            {
                "allocations": [
                    f"Invoice {invoice_id} was not found."
                    for invoice_id in missing_ids
                ]
            }
        )

    # Another request with the same token may have committed while this one
    # waited for the invoice locks.
    if client_token:
        existing = Payment.objects.filter(client_token=client_token).first()
        if existing:
            return existing, False

    errors = []
    for allocation in allocations_data:
        invoice = invoices[allocation["invoice"].id]
        if allocation["amount"] <= 0:
            errors.append(
                f"Allocation to invoice #{invoice.id} must be greater than zero."
            )
        if invoice.status != InvoiceStatus.ISSUED:
            errors.append(
                f"Invoice #{invoice.id} is not issued and cannot receive a payment."
            )
        if invoice.customer_id != customer.id:
            errors.append(
                f"Invoice #{invoice.id} belongs to a different customer."
            )
    if errors:
        raise ValidationError({"allocations": errors})

    allocated_total = sum(
        (allocation["amount"] for allocation in allocations_data),
        ZERO,
    )
    if allocated_total != validated_data["amount"]:
        raise ValidationError(
            {
                "allocations": [
                    "Allocations must add up exactly to the payment amount."
                ]
            }
        )

    # Current paid totals for the locked invoices.
    paid_totals = {
        row["invoice_id"]: row["total"]
        for row in PaymentAllocation.objects.filter(invoice_id__in=invoice_ids)
        .values("invoice_id")
        .annotate(total=Sum("amount"))
    }

    over_allocated = []
    for allocation in allocations_data:
        invoice = invoices[allocation["invoice"].id]
        remaining = invoice.grand_total - paid_totals.get(invoice.id, ZERO)
        if allocation["amount"] > remaining:
            over_allocated.append(
                {
                    "invoice": invoice.id,
                    "invoice_number": invoice.invoice_number,
                    "balance_due": format_money(remaining),
                    "requested": format_money(allocation["amount"]),
                }
            )
    if over_allocated:
        raise OverAllocationError(details=over_allocated)

    payment_values = {
        "customer": customer,
        "payment_date": validated_data["payment_date"],
        "amount": validated_data["amount"],
        "method": validated_data["method"],
        "reference": validated_data.get("reference", ""),
        "note": validated_data.get("note", ""),
        "client_token": client_token,
        "received_by": user,
    }

    try:
        # The savepoint lets us recover from a concurrent duplicate token
        # without aborting the surrounding transaction.
        with transaction.atomic():
            payment = Payment.objects.create(**payment_values)
            PaymentAllocation.objects.bulk_create(
                [
                    PaymentAllocation(
                        payment=payment,
                        invoice=invoices[allocation["invoice"].id],
                        amount=allocation["amount"],
                    )
                    for allocation in allocations_data
                ]
            )

            # Update cached balance_amount on each affected invoice
            for allocation in allocations_data:
                inv = invoices[allocation["invoice"].id]
                new_paid = paid_totals.get(inv.id, ZERO) + allocation["amount"]
                inv.balance_amount = max(ZERO, inv.grand_total - new_paid)
                inv.save(update_fields=["balance_amount", "updated_at"])
    except IntegrityError:
        if client_token:
            existing = Payment.objects.filter(client_token=client_token).first()
            if existing:
                return existing, False
        raise

    logger.info(
        "Payment %d recorded by user %d for customer %d (%s)",
        payment.id,
        user.id,
        customer.id,
        payment.amount,
    )

    # Automatically sync recorded payment to OtherIncome
    try:
        from apps.other_income.services import sync_payment_record_income
        sync_payment_record_income(payment)
    except Exception as e:
        logger.warning("Failed to sync payment %d to other income: %s", payment.id, e)

    return payment, True
