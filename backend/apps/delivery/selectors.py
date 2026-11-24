"""
Delivery query helpers — Phase 7.

Delivery status and remaining quantities are never stored. They are derived
from the invoice lines and the quantities already dispatched on challans.

The annotations are used by list endpoints so a page of invoices does not
trigger one query per row (N+1). Subqueries are used instead of joins so the
delivery totals cannot multiply an invoice's payment allocations (and vice
versa).
"""

from decimal import Decimal

from django.db.models import (
    Case,
    CharField,
    Count,
    DecimalField,
    F,
    IntegerField,
    OuterRef,
    Subquery,
    Sum,
    Value,
    When,
)
from django.db.models.functions import Coalesce

from apps.common.constants import (
    STOCK_TRACKED_ITEM_TYPES,
    DeliveryStatus,
)
from apps.delivery.models import DeliveryChallanItem
from apps.invoices.models import InvoiceItem

QUANTITY_FIELD = DecimalField(max_digits=12, decimal_places=3)
ZERO_QUANTITY = Value(Decimal("0.000"), output_field=QUANTITY_FIELD)
DELIVERY_STATUS_FIELD = CharField(max_length=25, null=True)


def _stock_line_count_subquery():
    return (
        InvoiceItem.objects.filter(
            invoice=OuterRef("pk"),
            item_type__in=STOCK_TRACKED_ITEM_TYPES,
        )
        .values("invoice")
        .annotate(total=Count("id"))
        .values("total")
    )


def _stock_invoiced_quantity_subquery():
    return (
        InvoiceItem.objects.filter(
            invoice=OuterRef("pk"),
            item_type__in=STOCK_TRACKED_ITEM_TYPES,
        )
        .values("invoice")
        .annotate(total=Sum("quantity"))
        .values("total")
    )


def _stock_dispatched_quantity_subquery():
    return (
        DeliveryChallanItem.objects.filter(
            invoice_item__invoice=OuterRef("pk"),
            invoice_item__item_type__in=STOCK_TRACKED_ITEM_TYPES,
        )
        .values("invoice_item__invoice")
        .annotate(total=Sum("quantity"))
        .values("total")
    )


def annotate_invoice_delivery(queryset):
    """
    Attach `delivery_status` to an Invoice queryset.

    The value is one of ``PENDING``, ``PARTIALLY_DELIVERED`` or ``DELIVERED``,
    or ``None`` when the invoice has no stock-tracked lines. The intermediate
    annotations are private to this helper.
    """
    return (
        queryset.annotate(
            _stock_line_count=Coalesce(
                Subquery(
                    _stock_line_count_subquery(),
                    output_field=IntegerField(),
                ),
                Value(0),
                output_field=IntegerField(),
            ),
            _stock_invoiced_quantity=Coalesce(
                Subquery(
                    _stock_invoiced_quantity_subquery(),
                    output_field=QUANTITY_FIELD,
                ),
                ZERO_QUANTITY,
                output_field=QUANTITY_FIELD,
            ),
            _stock_dispatched_quantity=Coalesce(
                Subquery(
                    _stock_dispatched_quantity_subquery(),
                    output_field=QUANTITY_FIELD,
                ),
                ZERO_QUANTITY,
                output_field=QUANTITY_FIELD,
            ),
        )
        .annotate(
            delivery_status=Case(
                When(
                    _stock_line_count=0,
                    then=Value(None, output_field=DELIVERY_STATUS_FIELD),
                ),
                When(
                    _stock_dispatched_quantity__gte=F(
                        "_stock_invoiced_quantity"
                    ),
                    then=Value(
                        DeliveryStatus.DELIVERED,
                        output_field=DELIVERY_STATUS_FIELD,
                    ),
                ),
                When(
                    _stock_dispatched_quantity__gt=0,
                    then=Value(
                        DeliveryStatus.PARTIALLY_DELIVERED,
                        output_field=DELIVERY_STATUS_FIELD,
                    ),
                ),
                default=Value(
                    DeliveryStatus.PENDING,
                    output_field=DELIVERY_STATUS_FIELD,
                ),
                output_field=DELIVERY_STATUS_FIELD,
            )
        )
    )


def annotate_invoice_item_dispatched(queryset):
    """
    Attach `dispatched_quantity` and `remaining_quantity` to an InvoiceItem
    queryset. Service lines also get a mathematical remaining quantity, but
    callers must check `item_type` before allowing a dispatch.
    """
    dispatched_subquery = (
        DeliveryChallanItem.objects.filter(invoice_item=OuterRef("pk"))
        .values("invoice_item")
        .annotate(total=Sum("quantity"))
        .values("total")
    )
    return queryset.annotate(
        dispatched_quantity=Coalesce(
            Subquery(dispatched_subquery, output_field=QUANTITY_FIELD),
            ZERO_QUANTITY,
            output_field=QUANTITY_FIELD,
        ),
    ).annotate(
        remaining_quantity=F("quantity") - F("dispatched_quantity"),
    )


def invoice_delivery_status(invoice) -> str | None:
    """
    Return one invoice's delivery status.

    Uses the queryset annotation when present; otherwise calculates it with
    two aggregate queries (single-object responses).
    """
    if "delivery_status" in invoice.__dict__:
        return invoice.__dict__["delivery_status"]

    stock_items = invoice.items.filter(
        item_type__in=STOCK_TRACKED_ITEM_TYPES
    )
    if not stock_items.exists():
        return None

    invoiced = (
        stock_items.aggregate(total=Sum("quantity"))["total"]
        or Decimal("0.000")
    )
    dispatched = (
        DeliveryChallanItem.objects.filter(
            invoice_item__invoice=invoice,
            invoice_item__item_type__in=STOCK_TRACKED_ITEM_TYPES,
        ).aggregate(total=Sum("quantity"))["total"]
        or Decimal("0.000")
    )

    if dispatched <= 0:
        return DeliveryStatus.PENDING
    if dispatched >= invoiced:
        return DeliveryStatus.DELIVERED
    return DeliveryStatus.PARTIALLY_DELIVERED
