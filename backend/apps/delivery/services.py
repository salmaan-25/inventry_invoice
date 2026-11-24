"""
Delivery business logic — Phase 7.

create_challan(validated_data, user)
    Records a dispatch against an issued invoice in one transaction.

    Rules:
      - the invoice must be ISSUED.
      - at least one line is required and each line appears once.
      - only stock-tracked lines (Goods and Goods (Hardware)) are dispatchable.
      - every quantity is > 0 and cannot exceed the line's remaining quantity.
      - a challan never creates a stock movement or changes current stock.

    The invoice row and its lines are locked in id order before remaining
    quantities are checked, so two simultaneous challans cannot jointly
    over-dispatch one line.
"""

import logging
from decimal import Decimal

from django.db import transaction
from django.db.models import Sum
from rest_framework.exceptions import ValidationError

from apps.common.constants import (
    STOCK_TRACKED_ITEM_TYPES,
    InvoiceStatus,
)
from apps.common.decimals import format_quantity
from apps.common.exceptions import InvalidStateError, OverDispatchError
from apps.delivery.models import DeliveryChallan, DeliveryChallanItem
from apps.invoices.models import Invoice, InvoiceItem

logger = logging.getLogger(__name__)

ZERO = Decimal("0.000")


@transaction.atomic
def create_challan(validated_data: dict, user) -> DeliveryChallan:
    """Create a delivery challan and its item rows."""
    invoice_id = validated_data["invoice"].id
    try:
        invoice = (
            Invoice.objects.select_for_update()
            .select_related("customer")
            .get(pk=invoice_id)
        )
    except Invoice.DoesNotExist:
        raise ValidationError({"invoice": ["Invoice not found."]})

    if invoice.status != InvoiceStatus.ISSUED:
        raise InvalidStateError(
            "Only ISSUED invoices can receive a delivery challan."
        )

    items_data = validated_data["items"]
    if not items_data:
        raise ValidationError(
            {"items": ["At least one item is required."]}
        )

    item_ids = [line["invoice_item"].id for line in items_data]
    if len(set(item_ids)) != len(item_ids):
        raise ValidationError(
            {"items": ["Each invoice line may appear only once per challan."]}
        )

    # Lock the invoice's lines in id order to avoid deadlocks between
    # concurrent challans for the same invoice.
    locked_items = {
        item.id: item
        for item in InvoiceItem.objects.select_for_update()
        .filter(invoice=invoice, id__in=sorted(item_ids))
        .order_by("id")
    }
    missing_ids = sorted(set(item_ids) - set(locked_items))
    if missing_ids:
        raise ValidationError(
            {
                "items": [
                    f"Invoice line {item_id} was not found on invoice "
                    f"#{invoice.id}."
                    for item_id in missing_ids
                ]
            }
        )

    errors = []
    for line in items_data:
        item = locked_items[line["invoice_item"].id]
        if item.item_type not in STOCK_TRACKED_ITEM_TYPES:
            errors.append(
                f"Invoice line {item.line_no} is a service and cannot be "
                "dispatched."
            )
        if line["quantity"] <= 0:
            errors.append(
                f"Invoice line {item.line_no} quantity must be greater than "
                "zero."
            )
    if errors:
        raise ValidationError({"items": errors})

    # Dispatched totals for the locked lines.
    dispatched_totals = {
        row["invoice_item_id"]: row["total"]
        for row in DeliveryChallanItem.objects.filter(
            invoice_item_id__in=item_ids
        )
        .values("invoice_item_id")
        .annotate(total=Sum("quantity"))
    }

    over_dispatched = []
    for line in items_data:
        item = locked_items[line["invoice_item"].id]
        remaining = item.quantity - dispatched_totals.get(item.id, ZERO)
        if line["quantity"] > remaining:
            over_dispatched.append(
                {
                    "invoice_item": item.id,
                    "line_no": item.line_no,
                    "product_name": item.product_name,
                    "remaining": format_quantity(remaining),
                    "requested": format_quantity(line["quantity"]),
                }
            )
    if over_dispatched:
        raise OverDispatchError(details=over_dispatched)

    challan = DeliveryChallan.objects.create(
        invoice=invoice,
        delivery_date=validated_data["delivery_date"],
        delivered_by=validated_data["delivered_by"],
        received_by=validated_data["received_by"],
        created_by=user,
    )
    DeliveryChallanItem.objects.bulk_create(
        [
            DeliveryChallanItem(
                challan=challan,
                invoice_item=locked_items[line["invoice_item"].id],
                quantity=line["quantity"],
            )
            for line in items_data
        ]
    )

    logger.info(
        "Challan %d created by user %d for invoice %d",
        challan.id,
        user.id,
        invoice.id,
    )
    return challan
