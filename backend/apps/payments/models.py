"""
Payment models — Phase 6.

Payment
    A received payment. It is fully allocated to issued invoices (D11 Path A),
    so the sum of its allocations always equals `amount`.

PaymentAllocation
    One invoice's share of a payment. Payments and allocations are immutable
    in V1 (D12): there is no edit, delete, void, refund or receipt workflow.
"""

from django.conf import settings
from django.db import models
from django.db.models import Q

from apps.common.constants import PaymentMethod


class Payment(models.Model):
    """A payment received from a customer."""

    objects = models.Manager()
    customer = models.ForeignKey(
        "customers.Customer",
        on_delete=models.PROTECT,
        related_name="payments",
    )
    payment_date = models.DateField()
    amount = models.DecimalField(max_digits=14, decimal_places=2)
    method = models.CharField(
        max_length=20,
        choices=PaymentMethod.choices,
    )
    reference = models.CharField(max_length=255, blank=True, default="")
    note = models.TextField(blank=True, default="")

    # Client-supplied idempotency key. Unique when set so a retry cannot
    # create a second payment.
    client_token = models.UUIDField(null=True, blank=True, unique=True)

    received_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="payments_received",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-payment_date", "-id"]
        verbose_name = "Payment"
        verbose_name_plural = "Payments"
        constraints = [
            models.CheckConstraint(
                check=Q(amount__gt=0),
                name="payment_amount_positive",
            ),
        ]

    def __str__(self) -> str:
        return f"Payment #{self.id} — {self.customer_id} — {self.amount}"


class PaymentAllocation(models.Model):
    """The amount of one payment applied to one invoice."""

    objects = models.Manager()
    payment = models.ForeignKey(
        Payment,
        on_delete=models.PROTECT,
        related_name="allocations",
    )
    invoice = models.ForeignKey(
        "invoices.Invoice",
        on_delete=models.PROTECT,
        related_name="allocations",
    )
    amount = models.DecimalField(max_digits=14, decimal_places=2)

    class Meta:
        verbose_name = "Payment Allocation"
        verbose_name_plural = "Payment Allocations"
        constraints = [
            models.UniqueConstraint(
                fields=["payment", "invoice"],
                name="paymentallocation_unique_invoice",
            ),
            models.CheckConstraint(
                check=Q(amount__gt=0),
                name="paymentallocation_amount_positive",
            ),
        ]

    def __str__(self) -> str:
        return f"Payment #{self.payment_id} → Invoice #{self.invoice_id}: {self.amount}"
