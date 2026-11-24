"""
Invoice models — Phase 5.

Invoice
    Master record. `status` starts as DRAFT. The `issue` service transitions
    it to ISSUED and sets the snapshots, issued_by, and issued_at.

InvoiceItem
    One line of an invoice. Snapshots are written when the line is first
    created and refreshed at issue time.
"""

from decimal import Decimal

from django.conf import settings
from django.db import models

from apps.common.constants import InvoiceStatus


class Invoice(models.Model):
    """An invoice created by a staff member for a customer."""

    objects = models.Manager()
    # -- Identity --
    # invoice_number is null until D8 is resolved; using internal id for now.
    invoice_number = models.CharField(
        max_length=50,
        blank=True,
        null=True,
        unique=True,
    )

    # -- Relationships --
    customer = models.ForeignKey(
        "customers.Customer",
        on_delete=models.PROTECT,
        related_name="invoices",
    )

    # -- Header --
    invoice_date = models.DateField()
    notes = models.TextField(blank=True, default="")
    invoice_type = models.CharField(
        max_length=20,
        choices=[("GST", "GST Invoice"), ("NON_GST", "Non-GST Invoice")],
        default="GST",
    )

    # -- Consignee (Ship To) Details --
    consignee_name = models.CharField(max_length=255, blank=True, default="")
    consignee_address = models.TextField(blank=True, default="")
    consignee_gstin = models.CharField(max_length=15, blank=True, default="")
    consignee_state = models.CharField(max_length=50, blank=True, default="Tamil Nadu")
    consignee_state_code = models.CharField(max_length=10, blank=True, default="33")

    # -- Transport & Dispatch Metadata --
    e_way_bill_no = models.CharField(max_length=50, blank=True, default="")
    delivery_note = models.CharField(max_length=100, blank=True, default="")
    payment_terms = models.CharField(max_length=100, blank=True, default="")
    reference_no_date = models.CharField(max_length=100, blank=True, default="")
    other_references = models.CharField(max_length=100, blank=True, default="")
    buyer_order_no = models.CharField(max_length=100, blank=True, default="")
    order_date = models.DateField(null=True, blank=True)
    dispatch_doc_no = models.CharField(max_length=100, blank=True, default="")
    delivery_note_date = models.DateField(null=True, blank=True)
    dispatched_through = models.CharField(max_length=100, blank=True, default="")
    destination = models.CharField(max_length=100, blank=True, default="")
    bill_of_lading_no = models.CharField(max_length=100, blank=True, default="")
    motor_vehicle_no = models.CharField(max_length=50, blank=True, default="")
    terms_of_delivery = models.TextField(blank=True, default="")

    # -- Status --
    status = models.CharField(
        max_length=10,
        choices=InvoiceStatus.choices,
        default=InvoiceStatus.DRAFT,
    )

    # -- Calculated totals (set by calculate_invoice, refreshed at issue) --
    subtotal = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        default=Decimal("0.00"),
    )
    total_cgst = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        default=Decimal("0.00"),
        help_text="Total CGST across all lines (for GST invoices).",
    )
    total_sgst = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        default=Decimal("0.00"),
        help_text="Total SGST across all lines (for GST invoices).",
    )
    total_tax = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        default=Decimal("0.00"),
        help_text="total_cgst + total_sgst.",
    )
    round_off = models.DecimalField(
        max_digits=6,
        decimal_places=2,
        default=Decimal("0.00"),
        help_text="Rounding adjustment (can be negative) so grand_total is a whole rupee.",
    )
    grand_total = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        default=Decimal("0.00"),
        help_text="subtotal + total_tax + round_off.",
    )
    advance_amount = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        default=Decimal("0.00"),
        help_text="Advance amount paid by customer at invoice creation.",
    )
    balance_amount = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        default=Decimal("0.00"),
        help_text="grand_total - advance_amount.",
    )

    # -- Snapshots (set at issue) --
    business_snapshot = models.JSONField(null=True, blank=True, default=None)
    customer_snapshot = models.JSONField(null=True, blank=True, default=None)

    # -- Audit --
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="invoices_created",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    issued_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="invoices_issued",
        null=True,
        blank=True,
    )
    issued_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-invoice_date", "-id"]
        verbose_name = "Invoice"
        verbose_name_plural = "Invoices"

    def __str__(self) -> str:
        num = self.invoice_number or f"#{self.id}"
        return f"Invoice {num} — {self.customer_id}"

    @property
    def is_gst_invoice(self) -> bool:
        """True when the invoice is a GST invoice."""
        if self.invoice_type == "NON_GST":
            return False
        if self.invoice_type == "GST":
            return True
        if self.total_tax and self.total_tax > 0:
            return True
        if self.customer_snapshot and self.customer_snapshot.get("gstin"):
            return True
        return self.items.filter(gst_rate__isnull=False).exists()


class InvoiceItem(models.Model):
    """One line of an invoice."""

    objects = models.Manager()
    invoice = models.ForeignKey(
        Invoice,
        on_delete=models.PROTECT,
        related_name="items",
    )
    line_no = models.PositiveIntegerField(help_text="1-based display order.")

    # -- Product reference (optional, allows manual line items) --
    product = models.ForeignKey(
        "products.Product",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="invoice_items",
    )

    # -- Snapshots (copied or entered directly at line creation) --
    product_name = models.TextField(default="", help_text="Product name / multiline description.")
    product_code = models.CharField(max_length=20, default="")
    hsn_sac = models.CharField(max_length=20, blank=True, default="")
    unit_name = models.CharField(max_length=50, default="")
    item_type = models.CharField(max_length=20, default="")
    gst_rate = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        null=True,
        blank=True,
        help_text="Snapshot of product GST rate at the time the line was saved.",
    )

    # -- Amounts --
    quantity = models.DecimalField(max_digits=12, decimal_places=3)
    rate = models.DecimalField(max_digits=14, decimal_places=2)
    line_total = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        default=Decimal("0.00"),
        help_text="quantity × rate, calculated by the backend.",
    )
    # Per-line tax amounts (computed from gst_rate when line is on a GST invoice)
    cgst_amount = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        default=Decimal("0.00"),
    )
    sgst_amount = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        default=Decimal("0.00"),
    )

    class Meta:
        ordering = ["line_no"]
        verbose_name = "Invoice Item"
        verbose_name_plural = "Invoice Items"
        constraints = [
            models.UniqueConstraint(
                fields=["invoice", "line_no"],
                name="invoiceitem_unique_line_no",
            ),
        ]

    def __str__(self) -> str:
        return f"Invoice {self.invoice_id} line {self.line_no}: {self.product_name}"
