"""
Product catalogue models — Phase 4.

Unit
    Measurement units (pcs, bag, kg, ...).  Seeded by a data migration and
    managed through the Django admin (D6).

ProductCodeCounter
    Singleton (pk=1) used to generate sequential product codes safely under
    concurrent requests.  Always access with select_for_update() inside an
    atomic block.

Product
    Catalogue item with one of three item types.  Goods and Goods (Hardware)
    are stock-tracked; Service is never stock-tracked.  `current_stock` is
    written only by inventory.services.apply_stock_movement().
"""

from decimal import Decimal

from django.db import models
from django.db.models import Q

from apps.common.constants import ItemType, STOCK_TRACKED_ITEM_TYPES


# ---------------------------------------------------------------------------
# Unit
# ---------------------------------------------------------------------------

class Unit(models.Model):
    """Measurement unit for a product."""

    objects = models.Manager()
    name = models.CharField(max_length=50, unique=True)

    class Meta:
        ordering = ["name"]
        verbose_name = "Unit"
        verbose_name_plural = "Units"

    def __str__(self) -> str:
        return self.name


# ---------------------------------------------------------------------------
# Code-generation counter
# ---------------------------------------------------------------------------

class ProductCodeCounter(models.Model):
    objects = models.Manager()
    next_value = models.PositiveIntegerField(default=1)

    class Meta:
        verbose_name = "Product Code Counter"


# ---------------------------------------------------------------------------
# Product
# ---------------------------------------------------------------------------

class Product(models.Model):
    """Catalogue item."""

    objects = models.Manager()
    code = models.CharField(max_length=20, unique=True)
    name = models.CharField(max_length=255)
    description = models.TextField(blank=True, default="")
    item_type = models.CharField(max_length=20, choices=ItemType.choices)
    unit = models.ForeignKey(
        Unit,
        on_delete=models.PROTECT,
        related_name="products",
    )
    selling_price = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        default=Decimal("0.00"),
    )
    hsn_sac = models.CharField(max_length=20, blank=True, default="")
    gst_rate = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        null=True,
        blank=True,
    )
    reorder_level = models.DecimalField(
        max_digits=12,
        decimal_places=3,
        null=True,
        blank=True,
    )
    current_stock = models.DecimalField(
        max_digits=12,
        decimal_places=3,
        default=Decimal("0.000"),
        editable=False,
    )
    is_active = models.BooleanField(default=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["name", "id"]
        verbose_name = "Product"
        verbose_name_plural = "Products"
        constraints = [
            models.CheckConstraint(
                check=Q(item_type__in=ItemType.values),
                name="product_item_type_valid",
            ),
            models.CheckConstraint(
                check=Q(selling_price__gte=0),
                name="product_selling_price_non_negative",
            ),
            models.CheckConstraint(
                check=Q(current_stock__gte=0),
                name="product_current_stock_non_negative",
            ),
            models.CheckConstraint(
                check=Q(gst_rate__isnull=True)
                | Q(gst_rate__gte=0, gst_rate__lte=100),
                name="product_gst_rate_range",
            ),
            models.CheckConstraint(
                check=Q(reorder_level__isnull=True) | Q(reorder_level__gte=0),
                name="product_reorder_level_non_negative",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.code} - {self.name}"

    @property
    def tracks_stock(self) -> bool:
        """True for Goods and Goods (Hardware), false for Service."""
        return self.item_type in STOCK_TRACKED_ITEM_TYPES

    @property
    def is_low_stock(self) -> bool:
        """True when a stock-tracked product has a reorder level and its
        current stock is at or below that level."""
        return (
            self.tracks_stock
            and self.reorder_level is not None
            and self.current_stock <= self.reorder_level
        )
