"""
Customer models — Phase 3.

CustomerCodeCounter
    Singleton (pk=1) used to generate sequential customer codes safely under
    concurrent requests.  Always access with select_for_update() inside an
    atomic block.

Customer
    Core customer entity.  `code` is auto-generated (C0001, C0002, …) and is
    read-only after creation.
"""

from django.db import models

from apps.common.constants import INDIAN_STATE_CHOICES


# ---------------------------------------------------------------------------
# Code-generation counter
# ---------------------------------------------------------------------------

class CustomerCodeCounter(models.Model):
    objects = models.Manager()
    next_value = models.PositiveIntegerField(default=1)

    class Meta:
        verbose_name = "Customer Code Counter"


# ---------------------------------------------------------------------------
# Customer
# ---------------------------------------------------------------------------

class Customer(models.Model):
    """Core customer record."""

    objects = models.Manager()
    code = models.CharField(max_length=10, unique=True, editable=False)
    name = models.CharField(max_length=255)
    phone = models.CharField(max_length=20, blank=True, default="")
    gstin = models.CharField(max_length=15, blank=True, default="")
    state = models.CharField(
        max_length=100,
        choices=INDIAN_STATE_CHOICES,
        blank=True,
        default="",
    )
    billing_address = models.TextField(blank=True, default="")
    is_active = models.BooleanField(default=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["name"]
        verbose_name = "Customer"
        verbose_name_plural = "Customers"

    def __str__(self) -> str:
        return f"{self.code} - {self.name}"
