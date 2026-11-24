"""Payment URL patterns — Phase 6."""

from django.urls import path

from apps.payments.views import PaymentDetailView, PaymentListCreateView

urlpatterns = [
    path("payments/", PaymentListCreateView.as_view(), name="payment-list-create"),
    path("payments/<int:pk>/", PaymentDetailView.as_view(), name="payment-detail"),
]
