"""
Stock movement serializers — Phase 4.

Movements are read-only through the API; they are created only by the stock
service.
"""

from rest_framework import serializers

from apps.inventory.models import StockMovement


class StockMovementSerializer(serializers.ModelSerializer):
    """Read-only representation of a stock movement."""

    class Meta:
        model = StockMovement
        fields = [
            "id",
            "product",
            "movement_type",
            "quantity_change",
            "balance_after",
            "reason",
            "created_by",
            "created_at",
        ]
        read_only_fields = fields
