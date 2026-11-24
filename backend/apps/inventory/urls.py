"""Inventory URL patterns — Phase 4."""

from django.urls import path

from apps.inventory.views import StockMovementListView

urlpatterns = [
    path(
        "stock-movements/",
        StockMovementListView.as_view(),
        name="stock-movement-list",
    ),
]
