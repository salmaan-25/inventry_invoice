"""
Other income models — Phase 9.

IncomeCategory: category name (unique). Seeded through Django admin:
  Scrap sale, Commission, Interest, Other.

OtherIncome: one other income record with date, category, amount, optional
  payment_method, received_from, description, recorded_by, and timestamps.
"""

from django.conf import settings
from django.db import models


class IncomeCategory(models.Model):
    """Income category — unique name, managed through Django admin."""

    objects = models.Manager()
    name = models.CharField(max_length=100, unique=True)

    class Meta:
        verbose_name = "Income Category"
        verbose_name_plural = "Income Categories"

    def __str__(self) -> str:
        return self.name


class OtherIncome(models.Model):
    """A recorded other income item."""

    objects = models.Manager()
    date = models.DateField()
    category = models.ForeignKey(
        IncomeCategory,
        on_delete=models.PROTECT,
        related_name="incomes",
    )
    description = models.TextField(blank=True, default="")
    amount = models.DecimalField(
        max_digits=14,
        decimal_places=2,
    )
    payment_method = models.CharField(
        max_length=20,
        blank=True,
        default="",
    )
    received_from = models.CharField(max_length=255, blank=True, default="")
    reference = models.CharField(max_length=100, blank=True, default="", db_index=True)
    recorded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="incomes_created",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-date", "-id"]
        verbose_name = "Other Income"
        verbose_name_plural = "Other Incomes"

    def __str__(self) -> str:
        return f"Other Income {self.id}: {self.category.name} — {self.amount}"