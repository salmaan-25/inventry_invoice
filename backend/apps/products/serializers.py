"""
Product serializers — Phase 4.

ProductSerializer handles list, detail, create and partial update.  It also
accepts the create-only `opening_stock` field.  Stock can never be edited
through this serializer; `current_stock` is read-only.
"""

from decimal import Decimal

from rest_framework import serializers

from apps.common.constants import ItemType
from apps.products.models import Product, Unit


class UnitSerializer(serializers.ModelSerializer):
    """Read-only representation of a measurement unit."""

    class Meta:
        model = Unit
        fields = ["id", "name"]
        read_only_fields = ["id", "name"]


class ProductSerializer(serializers.ModelSerializer):
    """Serializer for Product — list, detail, create and partial update."""

    opening_stock = serializers.DecimalField(
        max_digits=12,
        decimal_places=3,
        min_value=Decimal("0"),
        write_only=True,
        required=False,
    )
    selling_price = serializers.DecimalField(
        max_digits=14,
        decimal_places=2,
        min_value=Decimal("0"),
        required=False,
    )
    gst_rate = serializers.DecimalField(
        max_digits=5,
        decimal_places=2,
        min_value=Decimal("0"),
        max_value=Decimal("100"),
        required=False,
        allow_null=True,
    )
    reorder_level = serializers.DecimalField(
        max_digits=12,
        decimal_places=3,
        min_value=Decimal("0"),
        required=False,
        allow_null=True,
    )
    tracks_stock = serializers.BooleanField(read_only=True)
    is_low_stock = serializers.BooleanField(read_only=True)

    class Meta:
        model = Product
        fields = [
            "id",
            "code",
            "name",
            "description",
            "item_type",
            "unit",
            "selling_price",
            "hsn_sac",
            "gst_rate",
            "reorder_level",
            "current_stock",
            "is_active",
            "tracks_stock",
            "is_low_stock",
            "opening_stock",
            "created_at",
            "updated_at",
        ]
        read_only_fields = [
            "id",
            "current_stock",
            "tracks_stock",
            "is_low_stock",
            "created_at",
            "updated_at",
        ]
        extra_kwargs = {
            "code": {"required": False, "allow_blank": True},
            "description": {"required": False, "allow_blank": True},
            "hsn_sac": {"required": False, "allow_blank": True},
        }

    def validate(self, attrs):
        """
        Enforce the item-type and opening-stock rules that span fields.

        - Opening stock is accepted only when a product is created.
        - Service products cannot have opening stock or a reorder level.
        - Once a product has any stock movement, its type cannot be changed
          to or from SERVICE.  GOODS <-> GOODS_HARDWARE stays allowed.
        """
        item_type = attrs.get(
            "item_type",
            getattr(self.instance, "item_type", None),
        )

        if self.instance is None:
            if item_type == ItemType.SERVICE:
                if "opening_stock" in self.initial_data:
                    raise serializers.ValidationError(
                        {
                            "opening_stock": (
                                "Service products cannot have opening stock."
                            )
                        }
                    )
                if attrs.get("reorder_level") is not None:
                    raise serializers.ValidationError(
                        {
                            "reorder_level": (
                                "Service products cannot have a reorder level."
                            )
                        }
                    )
            return attrs

        if "opening_stock" in self.initial_data:
            raise serializers.ValidationError(
                {
                    "opening_stock": (
                        "Opening stock can only be set when the product is "
                        "created. Use stock-in or adjust to change stock."
                    )
                }
            )

        previous_item_type = self.instance.item_type
        if (
            item_type != previous_item_type
            and ItemType.SERVICE in (previous_item_type, item_type)
            and self.instance.stock_movements.exists()
        ):
            raise serializers.ValidationError(
                {
                    "item_type": (
                        "The item type cannot be changed to or from SERVICE "
                        "after the product has stock movements."
                    )
                }
            )

        resulting_reorder_level = attrs.get(
            "reorder_level",
            self.instance.reorder_level,
        )
        if item_type == ItemType.SERVICE and resulting_reorder_level is not None:
            raise serializers.ValidationError(
                {
                    "reorder_level": (
                        "Service products cannot have a reorder level."
                    )
                }
            )

        return attrs


class StockInSerializer(serializers.Serializer):
    """Input for POST /api/products/{id}/stock-in/."""

    quantity = serializers.DecimalField(max_digits=12, decimal_places=3)
    reason = serializers.CharField(
        max_length=255,
        required=False,
        allow_blank=True,
        default="",
    )

    def validate_quantity(self, value):
        if value <= 0:
            raise serializers.ValidationError(
                "Quantity must be greater than zero."
            )
        return value


class AdjustmentSerializer(serializers.Serializer):
    """Input for POST /api/products/{id}/adjust/."""

    quantity_change = serializers.DecimalField(
        max_digits=12,
        decimal_places=3,
    )
    reason = serializers.CharField(max_length=255, allow_blank=False)

    def validate_quantity_change(self, value):
        if value == 0:
            raise serializers.ValidationError(
                "Quantity change must not be zero."
            )
        return value
