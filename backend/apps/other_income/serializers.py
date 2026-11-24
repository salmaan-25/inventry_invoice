"""
Other income serializers — Phase 9.

IncomeCategorySerializer       — read-only category list
OtherIncomeSerializer          — write/read for create/update
OtherIncomeListSerializer      — compact list row with total_amount
OtherIncomeDetailSerializer    — full detail with category name
"""

from rest_framework import serializers

from apps.other_income.models import OtherIncome, IncomeCategory


class IncomeCategorySerializer(serializers.ModelSerializer):
    """Read-only category list row."""

    class Meta:
        model = IncomeCategory
        fields = ["id", "name"]
        read_only_fields = fields


class OtherIncomeSerializer(serializers.ModelSerializer):
    """Write/read serializer for one other income."""

    recorded_by = serializers.ReadOnlyField()

    class Meta:
        model = OtherIncome
        fields = [
            "id",
            "date",
            "category",
            "description",
            "amount",
            "payment_method",
            "received_from",
            "reference",
            "recorded_by",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "created_at", "updated_at", "recorded_by"]


class OtherIncomeListSerializer(serializers.ModelSerializer):
    """Compact list row — includes category name."""

    category_name = serializers.CharField(
        source="category.name",
        read_only=True,
    )

    class Meta:
        model = OtherIncome
        fields = [
            "id",
            "date",
            "category",
            "category_name",
            "description",
            "payment_method",
            "received_from",
            "reference",
            "amount",
            "created_at",
        ]
        read_only_fields = fields


class OtherIncomeDetailSerializer(OtherIncomeListSerializer):
    """Full detail row."""

    recorded_by_name = serializers.CharField(
        source="recorded_by.full_name",
        read_only=True,
    )

    class Meta(OtherIncomeListSerializer.Meta):
        fields = OtherIncomeListSerializer.Meta.fields + ["recorded_by_name"]
        read_only_fields = fields