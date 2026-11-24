"""Invoice URL patterns — Phase 5."""

from django.urls import path

from apps.invoices.views import (
    InvoiceAwaitingDispatchView,
    InvoiceCalculateView,
    InvoiceDetailView,
    InvoiceDispatchSummaryView,
    InvoiceDocumentView,
    InvoiceIssueView,
    InvoiceItemAwaitingDispatchView,
    InvoiceListCreateView,
    InvoicePaymentsView,
)

urlpatterns = [
    path("invoices/", InvoiceListCreateView.as_view(), name="invoice-list-create"),
    path(
        "invoices/awaiting-dispatch/",
        InvoiceAwaitingDispatchView.as_view(),
        name="invoice-awaiting-dispatch",
    ),
    path(
        "invoices/<int:pk>/awaiting-dispatch/",
        InvoiceItemAwaitingDispatchView.as_view(),
        name="invoice-awaiting-dispatch-detail",
    ),
    path("invoices/calculate/", InvoiceCalculateView.as_view(), name="invoice-calculate"),
    path("invoices/<int:pk>/", InvoiceDetailView.as_view(), name="invoice-detail"),
    path("invoices/<int:pk>/issue/", InvoiceIssueView.as_view(), name="invoice-issue"),
    path("invoices/<int:pk>/document/", InvoiceDocumentView.as_view(), name="invoice-document"),
    path("invoices/<int:pk>/payments/", InvoicePaymentsView.as_view(), name="invoice-payments"),
    path(
        "invoices/<int:pk>/dispatch-summary/",
        InvoiceDispatchSummaryView.as_view(),
        name="invoice-dispatch-summary",
    ),
]
