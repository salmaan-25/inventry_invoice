"""
Delivery Challan serializers — Phase 7.

DeliveryChallanItemReadSerializer — one dispatched line (snapshot display)
DeliveryChallanListSerializer      — compact list row
DeliveryChallanSerializer          — detail with items
DeliveryChallanCreateSerializer    — write payload
"""

from decimal import Decimal

from rest_framework import serializers

from apps.delivery.models import DeliveryChallan, DeliveryChallanItem
from apps.invoices.models import Invoice, InvoiceItem


class DeliveryChallanItemReadSerializer(serializers.ModelSerializer):
    """One dispatched invoice line, displayed from the invoice snapshots."""

    line_no = serializers.IntegerField(
        source="invoice_item.line_no",
        read_only=True,
    )
    product = serializers.IntegerField(
        source="invoice_item.product_id",
        read_only=True,
    )
    product_name = serializers.CharField(
        source="invoice_item.product_name",
        read_only=True,
    )
    product_code = serializers.CharField(
        source="invoice_item.product_code",
        read_only=True,
    )
    hsn_sac = serializers.CharField(
        source="invoice_item.hsn_sac",
        read_only=True,
    )
    unit_name = serializers.CharField(
        source="invoice_item.unit_name",
        read_only=True,
    )
    item_type = serializers.CharField(
        source="invoice_item.item_type",
        read_only=True,
    )

    class Meta:
        model = DeliveryChallanItem
        fields = [
            "id",
            "invoice_item",
            "line_no",
            "product",
            "product_name",
            "product_code",
            "hsn_sac",
            "unit_name",
            "item_type",
            "quantity",
        ]
        read_only_fields = fields


class DeliveryChallanListSerializer(serializers.ModelSerializer):
    """Compact challan list row — no items."""

    invoice_number = serializers.CharField(
        source="invoice.invoice_number",
        read_only=True,
        allow_null=True,
    )
    invoice_date = serializers.DateField(
        source="invoice.invoice_date",
        read_only=True,
    )
    customer = serializers.IntegerField(
        source="invoice.customer_id",
        read_only=True,
    )
    customer_name = serializers.CharField(
        source="invoice.customer.name",
        read_only=True,
    )
    created_by_name = serializers.CharField(
        source="created_by.full_name",
        read_only=True,
    )

    class Meta:
        model = DeliveryChallan
        fields = [
            "id",
            "invoice",
            "invoice_number",
            "invoice_date",
            "customer",
            "customer_name",
            "delivery_date",
            "delivered_by",
            "received_by",
            "created_by",
            "created_by_name",
            "created_at",
        ]
        read_only_fields = fields


class DeliveryChallanSerializer(DeliveryChallanListSerializer):
    """Full challan detail including its dispatched lines."""

    items = DeliveryChallanItemReadSerializer(many=True, read_only=True)

    class Meta(DeliveryChallanListSerializer.Meta):
        fields = DeliveryChallanListSerializer.Meta.fields + ["items"]
        read_only_fields = fields


# ---------------------------------------------------------------------------
# Write serializer
# ---------------------------------------------------------------------------

class DeliveryChallanItemWriteSerializer(serializers.Serializer):
    """One dispatched quantity in a create-challan payload."""

    invoice_item = serializers.PrimaryKeyRelatedField(
        queryset=InvoiceItem.objects.all()
    )
    quantity = serializers.DecimalField(
        max_digits=12,
        decimal_places=3,
        min_value=Decimal("0.001"),
    )


class DeliveryChallanCreateSerializer(serializers.Serializer):
    """
    Payload for POST /api/challans/.

    Invoice state, line ownership, item types and remaining quantities are
    checked in the service inside the transaction; the client cannot supply
    derived values.
    """

    invoice = serializers.PrimaryKeyRelatedField(
        queryset=Invoice.objects.all()
    )
    delivery_date = serializers.DateField()
    delivered_by = serializers.CharField(max_length=255)
    received_by = serializers.CharField(max_length=255)
    items = DeliveryChallanItemWriteSerializer(many=True)

    def validate_items(self, items: list) -> list:
        if not items:
            raise serializers.ValidationError(
                "At least one item is required."
            )

        seen_items = set()
        for item in items:
            invoice_item_id = item["invoice_item"].id
            if invoice_item_id in seen_items:
                raise serializers.ValidationError(
                    f"Invoice line #{invoice_item_id} appears more than once."
                )
            seen_items.add(invoice_item_id)
        return items
