"""Product URL patterns — Phase 4."""

from django.urls import path

from apps.products.views import (
    ProductAdjustView,
    ProductDetailView,
    ProductListCreateView,
    ProductStockInView,
    UnitListView,
)

urlpatterns = [
    path("units/", UnitListView.as_view(), name="unit-list"),
    path("products/", ProductListCreateView.as_view(), name="product-list-create"),
    path("products/<int:pk>/", ProductDetailView.as_view(), name="product-detail"),
    path(
        "products/<int:pk>/stock-in/",
        ProductStockInView.as_view(),
        name="product-stock-in",
    ),
    path(
        "products/<int:pk>/adjust/",
        ProductAdjustView.as_view(),
        name="product-adjust",
    ),
]
