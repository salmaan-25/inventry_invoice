"""Customer URL patterns — Phase 3, extended in Phase 6."""

from django.urls import path

from apps.customers.views import (
    CustomerDetailView,
    CustomerInvoicesView,
    CustomerListCreateView,
    CustomerOpenInvoicesView,
    CustomerPaymentsView,
    CustomerStatementView,
)

urlpatterns = [
    path("customers/", CustomerListCreateView.as_view(), name="customer-list-create"),
    path("customers/<int:pk>/", CustomerDetailView.as_view(), name="customer-detail"),
    path(
        "customers/<int:pk>/invoices/",
        CustomerInvoicesView.as_view(),
        name="customer-invoices",
    ),
    path(
        "customers/<int:pk>/open-invoices/",
        CustomerOpenInvoicesView.as_view(),
        name="customer-open-invoices",
    ),
    path(
        "customers/<int:pk>/payments/",
        CustomerPaymentsView.as_view(),
        name="customer-payments",
    ),
    path(
        "customers/<int:pk>/statement/",
        CustomerStatementView.as_view(),
        name="customer-statement",
    ),
]
