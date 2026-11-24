"""
Invoice serializers — Phase 5.

InvoiceItemReadSerializer   — read-only line detail
InvoiceItemWriteSerializer  — write validation for one line in create/update (supports manual lines)
InvoiceListSerializer       — compact list view with payment & delivery status
InvoiceDetailSerializer     — full detail including lines, dispatch metadata, advance/balance, snapshots
InvoiceCreateUpdateSerializer — write payload for create and PATCH (allows draft and issued edits)
InvoiceCalculateSerializer  — stateless preview payload
"""

from decimal import Decimal

from django.db.models import Sum
from rest_framework import serializers

from apps.common.constants import InvoiceStatus, PaymentStatus
from apps.common.decimals import format_money
from apps.customers.models import Customer
from apps.delivery.selectors import invoice_delivery_status
from apps.products.models import Product
from apps.invoices.models import Invoice, InvoiceItem


# ---------------------------------------------------------------------------
# Derived payment fields
# ---------------------------------------------------------------------------

def _invoice_paid_amount(invoice: Invoice) -> Decimal:
    """
    Sum of the invoice's allocations (including advance payments).
    """
    annotated = getattr(invoice, "paid_amount", None)
    if annotated is not None:
        return annotated
    total = invoice.allocations.aggregate(total=Sum("amount"))["total"]
    return total or Decimal("0.00")


def _invoice_balance_due(invoice: Invoice) -> Decimal:
    paid = _invoice_paid_amount(invoice)
    balance = invoice.grand_total - paid
    return max(Decimal("0.00"), balance)


def _invoice_payment_status(invoice: Invoice) -> str:
    paid = _invoice_paid_amount(invoice)
    if paid >= invoice.grand_total:
        return PaymentStatus.PAID
    if paid > 0:
        return PaymentStatus.PARTIALLY_PAID
    return PaymentStatus.UNPAID


class InvoicePaymentFieldsMixin(serializers.Serializer):
    """Read-only payment fields shared by the invoice list and detail rows."""

    paid_amount = serializers.SerializerMethodField()
    balance_due = serializers.SerializerMethodField()
    payment_status = serializers.SerializerMethodField()

    def get_paid_amount(self, invoice: Invoice) -> str:
        return format_money(_invoice_paid_amount(invoice))

    def get_balance_due(self, invoice: Invoice) -> str:
        return format_money(_invoice_balance_due(invoice))

    def get_payment_status(self, invoice: Invoice) -> str:
        return _invoice_payment_status(invoice)


class InvoiceDeliveryFieldsMixin(serializers.Serializer):
    """Read-only delivery field shared by the invoice list and detail rows."""

    delivery_status = serializers.SerializerMethodField()

    def get_delivery_status(self, invoice: Invoice) -> str | None:
        return invoice_delivery_status(invoice)


# ---------------------------------------------------------------------------
# Line serializers
# ---------------------------------------------------------------------------

class InvoiceItemReadSerializer(serializers.ModelSerializer):
    """Read-only representation of one invoice line."""

    description = serializers.CharField(source="product_name", read_only=True)

    class Meta:
        model = InvoiceItem
        fields = [
            "id",
            "line_no",
            "product",
            "product_name",
            "description",
            "product_code",
            "hsn_sac",
            "unit_name",
            "item_type",
            "gst_rate",
            "quantity",
            "rate",
            "line_total",
            "cgst_amount",
            "sgst_amount",
        ]
        read_only_fields = fields


class InvoiceItemWriteSerializer(serializers.Serializer):
    """
    Write validation for one line in create/update/calculate payloads.
    Supports both manual free-form line entry and optional product references.
    """

    product = serializers.PrimaryKeyRelatedField(
        queryset=Product.objects.all(),
        required=False,
        allow_null=True,
        default=None,
    )
    product_name = serializers.CharField(
        required=False,
        allow_blank=True,
        default="",
    )
    description = serializers.CharField(
        required=False,
        allow_blank=True,
        default="",
    )
    hsn_sac = serializers.CharField(
        required=False,
        allow_blank=True,
        default="",
    )
    unit_name = serializers.CharField(
        required=False,
        allow_blank=True,
        default="pcs",
    )
    gst_rate = serializers.DecimalField(
        max_digits=5,
        decimal_places=2,
        required=False,
        allow_null=True,
        default=None,
    )
    quantity = serializers.DecimalField(
        max_digits=12,
        decimal_places=3,
        min_value=Decimal("0.001"),
    )
    rate = serializers.DecimalField(
        max_digits=14,
        decimal_places=2,
        min_value=Decimal("0"),
        required=False,
        allow_null=True,
    )

    def validate(self, data: dict) -> dict:
        product = data.get("product")
        if product:
            if not product.is_active:
                raise serializers.ValidationError(
                    f"Product '{product.name}' is not active."
                )
            if data.get("rate") is None:
                data["rate"] = product.selling_price
            if not data.get("description") and not data.get("product_name"):
                data["description"] = product.name
            if not data.get("hsn_sac"):
                data["hsn_sac"] = product.hsn_sac
            if not data.get("unit_name") and product.unit:
                data["unit_name"] = product.unit.name
            if data.get("gst_rate") is None:
                data["gst_rate"] = product.gst_rate
        else:
            if data.get("rate") is None:
                data["rate"] = Decimal("0.00")
            if not data.get("description") and not data.get("product_name"):
                data["description"] = "Item"

        return data


# ---------------------------------------------------------------------------
# Invoice read serializers
# ---------------------------------------------------------------------------

class InvoiceListSerializer(
    InvoicePaymentFieldsMixin,
    InvoiceDeliveryFieldsMixin,
    serializers.ModelSerializer,
):
    """Compact invoice list row."""

    customer_name = serializers.CharField(
        source="customer.name",
        read_only=True,
    )

    class Meta:
        model = Invoice
        fields = [
            "id",
            "invoice_number",
            "customer",
            "customer_name",
            "invoice_date",
            "invoice_type",
            "status",
            "subtotal",
            "total_cgst",
            "total_sgst",
            "total_tax",
            "round_off",
            "grand_total",
            "advance_amount",
            "balance_amount",
            "paid_amount",
            "balance_due",
            "payment_status",
            "delivery_status",
            "e_way_bill_no",
            "destination",
            "motor_vehicle_no",
            "created_at",
            "updated_at",
        ]
        read_only_fields = fields


class InvoiceDetailSerializer(
    InvoicePaymentFieldsMixin,
    InvoiceDeliveryFieldsMixin,
    serializers.ModelSerializer,
):
    """Full invoice detail including lines, dispatch metadata, advance/balance, and snapshots."""

    items = InvoiceItemReadSerializer(many=True, read_only=True)
    customer_name = serializers.CharField(
        source="customer.name",
        read_only=True,
    )
    issued_by_name = serializers.CharField(
        source="issued_by.full_name",
        read_only=True,
        allow_null=True,
    )

    class Meta:
        model = Invoice
        fields = [
            "id",
            "invoice_number",
            "customer",
            "customer_name",
            "invoice_date",
            "invoice_type",
            "notes",
            "status",
            # Consignee (Ship To)
            "consignee_name",
            "consignee_address",
            "consignee_gstin",
            "consignee_state",
            "consignee_state_code",
            # Transport & Dispatch
            "e_way_bill_no",
            "delivery_note",
            "payment_terms",
            "reference_no_date",
            "other_references",
            "buyer_order_no",
            "order_date",
            "dispatch_doc_no",
            "delivery_note_date",
            "dispatched_through",
            "destination",
            "bill_of_lading_no",
            "motor_vehicle_no",
            "terms_of_delivery",
            # Totals & Advance
            "subtotal",
            "total_cgst",
            "total_sgst",
            "total_tax",
            "round_off",
            "grand_total",
            "advance_amount",
            "balance_amount",
            "paid_amount",
            "balance_due",
            "payment_status",
            "delivery_status",
            # Snapshots & Audit
            "business_snapshot",
            "customer_snapshot",
            "items",
            "created_by",
            "created_at",
            "updated_at",
            "issued_by",
            "issued_by_name",
            "issued_at",
        ]
        read_only_fields = fields


# ---------------------------------------------------------------------------
# Invoice write serializer (create / update)
# ---------------------------------------------------------------------------

class InvoiceCreateUpdateSerializer(serializers.Serializer):
    """
    Payload for POST (create) and PATCH (update).
    Works for both draft and issued invoices.
    """

    invoice_number = serializers.CharField(
        required=False,
        allow_blank=True,
        default="",
    )
    customer = serializers.PrimaryKeyRelatedField(
        queryset=Customer.objects.all(),
        required=True,
    )
    invoice_date = serializers.DateField(required=True)
    invoice_type = serializers.ChoiceField(
        choices=[("GST", "GST Invoice"), ("NON_GST", "Non-GST Invoice")],
        required=False,
        default="GST",
    )
    notes = serializers.CharField(
        required=False,
        allow_blank=True,
        default="",
    )

    # Consignee Details
    consignee_name = serializers.CharField(required=False, allow_blank=True, default="")
    consignee_address = serializers.CharField(required=False, allow_blank=True, default="")
    consignee_gstin = serializers.CharField(required=False, allow_blank=True, default="")
    consignee_state = serializers.CharField(required=False, allow_blank=True, default="Tamil Nadu")
    consignee_state_code = serializers.CharField(required=False, allow_blank=True, default="33")

    # Transport / Dispatch Metadata
    e_way_bill_no = serializers.CharField(required=False, allow_blank=True, default="")
    delivery_note = serializers.CharField(required=False, allow_blank=True, default="")
    payment_terms = serializers.CharField(required=False, allow_blank=True, default="")
    reference_no_date = serializers.CharField(required=False, allow_blank=True, default="")
    other_references = serializers.CharField(required=False, allow_blank=True, default="")
    buyer_order_no = serializers.CharField(required=False, allow_blank=True, default="")
    order_date = serializers.DateField(required=False, allow_null=True, default=None)
    dispatch_doc_no = serializers.CharField(required=False, allow_blank=True, default="")
    delivery_note_date = serializers.DateField(required=False, allow_null=True, default=None)
    dispatched_through = serializers.CharField(required=False, allow_blank=True, default="")
    destination = serializers.CharField(required=False, allow_blank=True, default="")
    bill_of_lading_no = serializers.CharField(required=False, allow_blank=True, default="")
    motor_vehicle_no = serializers.CharField(required=False, allow_blank=True, default="")
    terms_of_delivery = serializers.CharField(required=False, allow_blank=True, default="")

    # Advance Payment
    advance_amount = serializers.DecimalField(
        max_digits=14,
        decimal_places=2,
        required=False,
        default=Decimal("0.00"),
    )

    lines = InvoiceItemWriteSerializer(many=True, required=True)

    def validate_customer(self, customer: Customer) -> Customer:
        if not customer.is_active:
            raise serializers.ValidationError(
                f"Customer '{customer.name}' is not active."
            )
        return customer

    def validate_lines(self, lines: list) -> list:
        if not lines:
            raise serializers.ValidationError(
                "An invoice must have at least one line."
            )
        return lines


# ---------------------------------------------------------------------------
# Calculate (stateless preview) serializer
# ---------------------------------------------------------------------------

class InvoiceCalculateSerializer(serializers.Serializer):
    """
    Payload for POST /api/invoices/calculate/.
    Stateless preview calculation.
    """

    customer = serializers.PrimaryKeyRelatedField(
        queryset=Customer.objects.all(),
        required=False,
        allow_null=True,
    )
    invoice_type = serializers.ChoiceField(
        choices=[("GST", "GST Invoice"), ("NON_GST", "Non-GST Invoice")],
        required=False,
        default="GST",
    )
    advance_amount = serializers.DecimalField(
        max_digits=14,
        decimal_places=2,
        required=False,
        default=Decimal("0.00"),
    )
    lines = InvoiceItemWriteSerializer(many=True)
