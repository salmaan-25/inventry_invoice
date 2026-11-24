"""
Product views — Phase 4.

Endpoints:
    GET    /api/units/                       unit list
    GET    /api/products/                    list (search + filters)
    POST   /api/products/                    create (optional opening_stock)
    GET    /api/products/{id}/               detail
    PATCH  /api/products/{id}/               partial update (not stock)
    POST   /api/products/{id}/stock-in/      add stock
    POST   /api/products/{id}/adjust/        signed stock adjustment
"""

from django.db.models import F, Q
from drf_spectacular.utils import extend_schema
from rest_framework import status
from rest_framework.generics import (
    ListAPIView,
    ListCreateAPIView,
    RetrieveUpdateAPIView,
    get_object_or_404,
)
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.common.constants import MovementType, STOCK_TRACKED_ITEM_TYPES
from apps.common.pagination import StandardPagination
from apps.common.permissions import IsAdminOrStaff
from apps.inventory.services import apply_stock_movement
from apps.products.models import Product, Unit
from apps.products.serializers import (
    AdjustmentSerializer,
    ProductSerializer,
    StockInSerializer,
    UnitSerializer,
)
from apps.products.services import create_product, update_product


class UnitListView(ListAPIView):
    """GET /api/units/ — every measurement unit, ordered by name."""

    serializer_class = UnitSerializer
    permission_classes = [IsAdminOrStaff]
    pagination_class = StandardPagination
    queryset = Unit.objects.order_by("name")


class ProductListCreateView(ListCreateAPIView):
    """
    GET  /api/products/  — paginated list with optional ?search=, ?item_type=,
                           ?is_active= and ?low_stock=true. Filters combine.
    POST /api/products/  — create a product; optional write-only opening_stock.
    """

    serializer_class = ProductSerializer
    permission_classes = [IsAdminOrStaff]
    pagination_class = StandardPagination

    def get_queryset(self):
        qs = Product.objects.select_related("unit").order_by("name", "id")

        # --- search (name, code — case-insensitive) ---
        search = self.request.query_params.get("search", "").strip()
        if search:
            qs = qs.filter(
                Q(name__icontains=search) | Q(code__icontains=search)
            )

        # --- item_type filter ---
        item_type = self.request.query_params.get("item_type", "").strip().upper()
        if item_type:
            qs = qs.filter(item_type=item_type)

        # --- is_active filter ---
        is_active_param = self.request.query_params.get("is_active")
        if is_active_param is not None:
            if is_active_param.lower() in ("true", "1"):
                qs = qs.filter(is_active=True)
            elif is_active_param.lower() in ("false", "0"):
                qs = qs.filter(is_active=False)

        # --- low_stock filter ---
        low_stock = self.request.query_params.get("low_stock", "").strip().lower()
        if low_stock in ("true", "1"):
            qs = qs.filter(
                item_type__in=STOCK_TRACKED_ITEM_TYPES,
                reorder_level__isnull=False,
                current_stock__lte=F("reorder_level"),
            )

        return qs

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        product = create_product(serializer.validated_data, request.user)
        out = self.get_serializer(product)
        return Response(out.data, status=status.HTTP_201_CREATED)


class ProductDetailView(RetrieveUpdateAPIView):
    """
    GET   /api/products/{id}/  — retrieve a product
    PATCH /api/products/{id}/  — partial update (stock is read-only)

    PUT and DELETE are disabled.
    """

    serializer_class = ProductSerializer
    permission_classes = [IsAdminOrStaff]
    queryset = Product.objects.select_related("unit").all()
    http_method_names = ["get", "patch", "head", "options"]

    def partial_update(self, request, *args, **kwargs):
        instance = self.get_object()
        serializer = self.get_serializer(
            instance,
            data=request.data,
            partial=True,
        )
        serializer.is_valid(raise_exception=True)
        product = update_product(instance, serializer.validated_data)
        out = self.get_serializer(product)
        return Response(out.data)


class ProductStockInView(APIView):
    """POST /api/products/{id}/stock-in/ — {quantity, reason?}."""

    permission_classes = [IsAdminOrStaff]

    @extend_schema(
        tags=["Products"],
        request=StockInSerializer,
        responses=ProductSerializer,
    )
    def post(self, request, pk, *args, **kwargs):
        product = get_object_or_404(Product, pk=pk)
        serializer = StockInSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        apply_stock_movement(
            product.id,
            serializer.validated_data["quantity"],
            MovementType.STOCK_IN,
            serializer.validated_data.get("reason", ""),
            request.user,
        )
        product.refresh_from_db()

        return Response(ProductSerializer(product).data)


class ProductAdjustView(APIView):
    """POST /api/products/{id}/adjust/ — {quantity_change, reason}."""

    permission_classes = [IsAdminOrStaff]

    @extend_schema(
        tags=["Products"],
        request=AdjustmentSerializer,
        responses=ProductSerializer,
    )
    def post(self, request, pk, *args, **kwargs):
        product = get_object_or_404(Product, pk=pk)
        serializer = AdjustmentSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        apply_stock_movement(
            product.id,
            serializer.validated_data["quantity_change"],
            MovementType.ADJUSTMENT,
            serializer.validated_data["reason"],
            request.user,
        )
        product.refresh_from_db()

        return Response(ProductSerializer(product).data)
