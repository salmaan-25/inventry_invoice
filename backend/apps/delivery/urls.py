"""Delivery Challan URL patterns — Phase 7."""

from django.urls import path

from apps.delivery.views import (
    DeliveryChallanDetailView,
    DeliveryChallanDocumentView,
    DeliveryChallanListCreateView,
)

urlpatterns = [
    path(
        "challans/",
        DeliveryChallanListCreateView.as_view(),
        name="challan-list-create",
    ),
    path(
        "challans/<int:pk>/",
        DeliveryChallanDetailView.as_view(),
        name="challan-detail",
    ),
    path(
        "challans/<int:pk>/document/",
        DeliveryChallanDocumentView.as_view(),
        name="challan-document",
    ),
]
