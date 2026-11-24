"""
Expense serializers — Phase 8.

ExpenseCategorySerializer       — read-only category list
ExpenseSerializer               — write/read for create/update
ExpenseListSerializer           — compact list row with total_amount
ExpenseDetailSerializer         — full detail with category name and recorder name
"""

from rest_framework import serializers

from apps.expenses.models import Expense, ExpenseCategory


class ExpenseCategorySerializer(serializers.ModelSerializer):
    """Category serializer — used for both list (read) and create (write)."""

    class Meta:
        model = ExpenseCategory
        fields = ["id", "name"]
        read_only_fields = ["id"]


class ExpenseSerializer(serializers.ModelSerializer):
    """Write/read serializer for one expense."""

    recorded_by = serializers.ReadOnlyField()

    class Meta:
        model = Expense
        fields = [
            "id",
            "date",
            "category",
            "description",
            "amount",
            "payment_method",
            "paid_to",
            "recorded_by",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "created_at", "updated_at", "recorded_by"]


class ExpenseListSerializer(serializers.ModelSerializer):
    """Compact list row — includes category name and total_amount annotation."""

    category_name = serializers.CharField(
        source="category.name",
        read_only=True,
    )

    class Meta:
        model = Expense
        fields = [
            "id",
            "date",
            "category",
            "category_name",
            "description",
            "payment_method",
            "paid_to",
            "amount",
            "created_at",
        ]
        read_only_fields = fields


class ExpenseDetailSerializer(ExpenseListSerializer):
    """Full detail row."""

    recorded_by_name = serializers.CharField(
        source="recorded_by.full_name",
        read_only=True,
    )

    class Meta(ExpenseListSerializer.Meta):
        fields = ExpenseListSerializer.Meta.fields + ["recorded_by_name"]
        read_only_fields = fields