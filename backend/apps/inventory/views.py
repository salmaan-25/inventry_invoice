"""
Inventory views — Phase 4.

Endpoint:
    GET /api/stock-movements/ — list with ?product=, ?item_type=,
                                ?movement_type=, ?from= and ?to= filters.
"""

from rest_framework.exceptions import ValidationError
from rest_framework.generics import ListAPIView

from apps.common.dates import parse_date_range
from apps.common.pagination import StandardPagination
from apps.common.permissions import IsAdminOrStaff
from apps.inventory.models import StockMovement
from apps.inventory.serializers import StockMovementSerializer


class StockMovementListView(ListAPIView):
    """Paginated, filtered stock movement ledger (newest first)."""

    serializer_class = StockMovementSerializer
    permission_classes = [IsAdminOrStaff]
    pagination_class = StandardPagination

    def get_queryset(self):
        qs = StockMovement.objects.select_related(
            "product",
            "created_by",
        ).order_by("-created_at", "-id")

        product_id = self.request.query_params.get("product", "").strip()
        if product_id:
            try:
                product_id = int(product_id)
            except (TypeError, ValueError):
                raise ValidationError(
                    {"product": ["Enter a valid product id."]}
                )
            qs = qs.filter(product_id=product_id)

        item_type = self.request.query_params.get("item_type", "").strip().upper()
        if item_type:
            qs = qs.filter(product__item_type=item_type)

        movement_type = (
            self.request.query_params.get("movement_type", "").strip().upper()
        )
        if movement_type:
            qs = qs.filter(movement_type=movement_type)

        from_str = self.request.query_params.get("from", "").strip()
        to_str = self.request.query_params.get("to", "").strip()
        if from_str or to_str:
            from_date, to_date = parse_date_range(self.request)
            qs = qs.filter(created_at__date__range=(from_date, to_date))

        return qs
