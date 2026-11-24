"""
Payment serializers — Phase 6.

PaymentListSerializer        — compact list row
PaymentSerializer            — detail with allocations
InvoicePaymentSerializer     — payment history for one invoice
PaymentCreateSerializer      — write payload with allocations
PaymentAllocationReadSerializer — one allocation row
"""

from decimal import Decimal

from rest_framework import serializers

from apps.common.constants import InvoiceStatus, PaymentMethod
from apps.customers.models import Customer
from apps.invoices.models import Invoice
from apps.payments.models import Payment, PaymentAllocation


class PaymentAllocationReadSerializer(serializers.ModelSerializer):
    """One invoice's share of a payment."""

    invoice_number = serializers.CharField(
        source="invoice.invoice_number",
        read_only=True,
        allow_null=True,
    )
    invoice_date = serializers.DateField(
        source="invoice.invoice_date",
        read_only=True,
    )
    grand_total = serializers.DecimalField(
        source="invoice.grand_total",
        max_digits=14,
        decimal_places=2,
        read_only=True,
    )

    class Meta:
        model = PaymentAllocation
        fields = [
            "id",
            "invoice",
            "invoice_number",
            "invoice_date",
            "grand_total",
            "amount",
        ]
        read_only_fields = fields


class PaymentListSerializer(serializers.ModelSerializer):
    """Compact payment list row — no allocations."""

    customer_name = serializers.CharField(
        source="customer.name",
        read_only=True,
    )
    received_by_name = serializers.CharField(
        source="received_by.full_name",
        read_only=True,
    )

    class Meta:
        model = Payment
        fields = [
            "id",
            "customer",
            "customer_name",
            "payment_date",
            "amount",
            "method",
            "reference",
            "note",
            "client_token",
            "received_by",
            "received_by_name",
            "created_at",
        ]
        read_only_fields = fields


class PaymentSerializer(PaymentListSerializer):
    """Full payment detail including its allocations."""

    allocations = PaymentAllocationReadSerializer(many=True, read_only=True)

    class Meta(PaymentListSerializer.Meta):
        fields = PaymentListSerializer.Meta.fields + ["allocations"]
        read_only_fields = fields


class InvoicePaymentSerializer(PaymentListSerializer):
    """Payment row for an invoice's payment history."""

    allocated_amount = serializers.DecimalField(
        max_digits=14,
        decimal_places=2,
        read_only=True,
    )

    class Meta(PaymentListSerializer.Meta):
        fields = PaymentListSerializer.Meta.fields + ["allocated_amount"]
        read_only_fields = fields


# ---------------------------------------------------------------------------
# Write serializers
# ---------------------------------------------------------------------------

class PaymentAllocationWriteSerializer(serializers.Serializer):
    """One allocation in a create-payment payload."""

    invoice = serializers.PrimaryKeyRelatedField(
        queryset=Invoice.objects.all()
    )
    amount = serializers.DecimalField(
        max_digits=14,
        decimal_places=2,
        min_value=Decimal("0.01"),
    )


class PaymentCreateSerializer(serializers.Serializer):
    """
    Payload for POST /api/payments/.

    The backend validates invoice ownership, invoice state and remaining
    balances; the client cannot supply derived totals.
    """

    customer = serializers.PrimaryKeyRelatedField(
        queryset=Customer.objects.all()
    )
    payment_date = serializers.DateField()
    amount = serializers.DecimalField(
        max_digits=14,
        decimal_places=2,
        min_value=Decimal("0.01"),
    )
    method = serializers.ChoiceField(choices=PaymentMethod.choices)
    reference = serializers.CharField(
        max_length=255,
        required=False,
        allow_blank=True,
        default="",
    )
    note = serializers.CharField(
        required=False,
        allow_blank=True,
        default="",
    )
    client_token = serializers.UUIDField(
        required=False,
        allow_null=True,
        default=None,
    )
    allocations = PaymentAllocationWriteSerializer(many=True)

    def validate_allocations(self, allocations: list) -> list:
        if not allocations:
            raise serializers.ValidationError(
                "At least one allocation is required."
            )

        seen_invoices = set()
        for allocation in allocations:
            invoice_id = allocation["invoice"].id
            if invoice_id in seen_invoices:
                raise serializers.ValidationError(
                    f"Invoice #{invoice_id} appears more than once."
                )
            seen_invoices.add(invoice_id)
        return allocations

    def validate(self, data: dict) -> dict:
        customer = data["customer"]
        allocations = data["allocations"]

        allocated_total = sum(
            (allocation["amount"] for allocation in allocations),
            Decimal("0.00"),
        )
        if allocated_total != data["amount"]:
            raise serializers.ValidationError(
                {
                    "allocations": [
                        "Allocations must add up exactly to the payment amount."
                    ]
                }
            )

        errors = []
        for allocation in allocations:
            invoice = allocation["invoice"]
            if invoice.status != InvoiceStatus.ISSUED:
                errors.append(
                    f"Invoice #{invoice.id} is not issued and cannot receive a payment."
                )
            elif invoice.customer_id != customer.id:
                errors.append(
                    f"Invoice #{invoice.id} belongs to a different customer."
                )
        if errors:
            raise serializers.ValidationError({"allocations": errors})

        return data
