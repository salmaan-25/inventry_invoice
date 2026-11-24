"""
Inventory models — Phase 4.

StockMovement
    An immutable record of every change to a product's stock.  Movements are
    written only by inventory.services.apply_stock_movement().

The nullable `invoice` foreign key is added by the Phase 5 migration, when the
Invoice model exists.
"""

from django.conf import settings
from django.db import models
from django.db.models import Q

from apps.common.constants import MovementType


class StockMovement(models.Model):
    """A single signed change to a product's stock."""

    objects = models.Manager()
    product = models.ForeignKey(
        "products.Product",
        on_delete=models.PROTECT,
        related_name="stock_movements",
    )
    movement_type = models.CharField(
        max_length=20,
        choices=MovementType.choices,
    )
    quantity_change = models.DecimalField(max_digits=12, decimal_places=3)
    balance_after = models.DecimalField(max_digits=12, decimal_places=3)
    reason = models.CharField(max_length=255, blank=True, default="")
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="stock_movements",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    # Added in Phase 5 migration: nullable FK to Invoice.
    invoice = models.ForeignKey(
        "invoices.Invoice",
        on_delete=models.PROTECT,
        related_name="stock_movements",
        null=True,
        blank=True,
    )

    class Meta:
        ordering = ["-created_at", "-id"]
        verbose_name = "Stock Movement"
        verbose_name_plural = "Stock Movements"
        constraints = [
            models.CheckConstraint(
                check=~Q(quantity_change=0),
                name="stock_movement_quantity_change_non_zero",
            ),
        ]

    def __str__(self) -> str:
        return (
            f"{self.product.code} {self.movement_type} "
            f"{self.quantity_change} -> {self.balance_after}"
        )
