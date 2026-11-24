"""
Payment and balance query helpers — Phase 6.

All derived amounts are calculated from allocations; nothing here is stored
on the invoice or customer.

The annotations are used by list endpoints so a page of rows does not trigger
one query per row (N+1).
"""

from decimal import Decimal

from django.db.models import DecimalField, OuterRef, Subquery, Sum, Value
from django.db.models.functions import Coalesce

from apps.common.constants import InvoiceStatus
from apps.invoices.models import Invoice
from apps.payments.models import PaymentAllocation

MONEY_FIELD = DecimalField(max_digits=14, decimal_places=2)
ZERO_MONEY = Value(Decimal("0.00"), output_field=MONEY_FIELD)


def annotate_invoice_paid(queryset):
    """Attach `paid_amount` (sum of allocations) to an Invoice queryset."""
    return queryset.annotate(
        paid_amount=Coalesce(
            Sum("allocations__amount"),
            ZERO_MONEY,
            output_field=MONEY_FIELD,
        )
    )


def annotate_customer_outstanding(queryset):
    """
    Attach `outstanding_amount` to a Customer queryset.

    Outstanding is the sum of `grand_total` minus allocations across the
    customer's ISSUED invoices. Two correlated subqueries are used so the
    invoice and allocation joins cannot multiply each other's rows.
    """
    invoice_totals = (
        Invoice.objects.filter(
            customer=OuterRef("pk"),
            status=InvoiceStatus.ISSUED,
        )
        .values("customer")
        .annotate(total=Sum("grand_total"))
        .values("total")
    )
    allocation_totals = (
        PaymentAllocation.objects.filter(
            invoice__customer=OuterRef("pk"),
            invoice__status=InvoiceStatus.ISSUED,
        )
        .values("invoice__customer")
        .annotate(total=Sum("amount"))
        .values("total")
    )
    return queryset.annotate(
        outstanding_amount=(
            Coalesce(
                Subquery(invoice_totals, output_field=MONEY_FIELD),
                ZERO_MONEY,
                output_field=MONEY_FIELD,
            )
            - Coalesce(
                Subquery(allocation_totals, output_field=MONEY_FIELD),
                ZERO_MONEY,
                output_field=MONEY_FIELD,
            )
        )
    )


def customer_outstanding_amount(customer_id: int) -> Decimal:
    """Calculate one customer's outstanding amount without annotations."""
    invoiced = (
        Invoice.objects.filter(
            customer_id=customer_id,
            status=InvoiceStatus.ISSUED,
        ).aggregate(total=Sum("grand_total"))["total"]
        or Decimal("0.00")
    )
    paid = (
        PaymentAllocation.objects.filter(
            invoice__customer_id=customer_id,
            invoice__status=InvoiceStatus.ISSUED,
        ).aggregate(total=Sum("amount"))["total"]
        or Decimal("0.00")
    )
    return invoiced - paid
