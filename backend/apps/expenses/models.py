"""
Expense models — Phase 8.

ExpenseCategory: category name (unique). Seeded through Django admin:
  Rent, Electricity, Transport, Salary, Repairs, Other.

Expense: one expense record with date, category, amount, optional
  payment_method, paid_to, description, recorded_by, and timestamps.
"""

from django.conf import settings
from django.db import models

from apps.common.decimals import format_money


class ExpenseCategory(models.Model):
    """Expense category — unique name, managed through Django admin."""

    objects = models.Manager()
    name = models.CharField(max_length=100, unique=True)

    class Meta:
        verbose_name = "Expense Category"
        verbose_name_plural = "Expense Categories"

    def __str__(self) -> str:
        return self.name


class Expense(models.Model):
    """An expense recorded by staff."""

    objects = models.Manager()
    date = models.DateField()
    category = models.ForeignKey(
        ExpenseCategory,
        on_delete=models.PROTECT,
        related_name="expenses",
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
    paid_to = models.CharField(max_length=255, blank=True, default="")
    notes = models.TextField(blank=True, default="")
    recorded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="expenses_created",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-date", "-id"]
        verbose_name = "Expense"
        verbose_name_plural = "Expenses"

    def __str__(self) -> str:
        return f"Expense {self.id}: {self.category.name} — {format_money(self.amount)}"