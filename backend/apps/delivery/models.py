"""
Delivery Challan models — Phase 7.

DeliveryChallan
    Records goods physically dispatched against an issued invoice. A challan
    never changes stock; issuing the invoice already made the stock movement.

DeliveryChallanItem
    One invoice line's dispatched quantity. The product name and unit are read
    from the InvoiceItem snapshot, so they stay historical.
"""

from django.conf import settings
from django.db import models
from django.db.models import Q


class DeliveryChallan(models.Model):
    """A dispatch document for an issued invoice."""

    objects = models.Manager()
    invoice = models.ForeignKey(
        "invoices.Invoice",
        on_delete=models.PROTECT,
        related_name="challans",
    )
    delivery_date = models.DateField()
    delivered_by = models.CharField(max_length=255)
    received_by = models.CharField(max_length=255)

    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="challans_created",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-delivery_date", "-id"]
        verbose_name = "Delivery Challan"
        verbose_name_plural = "Delivery Challans"

    def __str__(self) -> str:
        return f"Challan #{self.id} — Invoice #{self.invoice_id}"


class DeliveryChallanItem(models.Model):
    """One dispatched quantity on a challan."""

    objects = models.Manager()
    challan = models.ForeignKey(
        DeliveryChallan,
        on_delete=models.PROTECT,
        related_name="items",
    )
    invoice_item = models.ForeignKey(
        "invoices.InvoiceItem",
        on_delete=models.PROTECT,
        related_name="challan_items",
    )
    quantity = models.DecimalField(max_digits=12, decimal_places=3)

    class Meta:
        ordering = ["invoice_item__line_no", "id"]
        verbose_name = "Delivery Challan Item"
        verbose_name_plural = "Delivery Challan Items"
        constraints = [
            models.UniqueConstraint(
                fields=["challan", "invoice_item"],
                name="challanitem_unique_invoice_item",
            ),
            models.CheckConstraint(
                check=Q(quantity__gt=0),
                name="challanitem_quantity_positive",
            ),
        ]

    def __str__(self) -> str:
        return (
            f"Challan #{self.challan_id} — Invoice item "
            f"#{self.invoice_item_id}: {self.quantity}"
        )
