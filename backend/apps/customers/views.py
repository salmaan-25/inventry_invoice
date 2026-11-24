"""
Customer views — Phase 3, extended in Phase 6.

Endpoints:
    GET    /api/customers/                   list (search, is_active filter)
    POST   /api/customers/                   create
    GET    /api/customers/{id}/              detail
    PATCH  /api/customers/{id}/              partial update
    GET    /api/customers/{id}/open-invoices/ issued invoices with a balance
    GET    /api/customers/{id}/payments/     the customer's payments
    GET    /api/customers/{id}/statement/    debit/credit entries with balance
"""

from decimal import Decimal

from django.db.models import F, Q
from rest_framework import status
from rest_framework.exceptions import NotFound
from rest_framework.generics import ListCreateAPIView, RetrieveUpdateAPIView
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.common.constants import InvoiceStatus
from apps.common.decimals import format_money
from apps.common.pagination import StandardPagination
from apps.common.permissions import IsAdminOrStaff
from apps.customers.models import Customer
from apps.customers.serializers import CustomerSerializer
from apps.customers.services import create_customer, update_customer
from apps.delivery.selectors import annotate_invoice_delivery
from apps.invoices.models import Invoice
from apps.invoices.serializers import InvoiceListSerializer
from apps.payments.models import Payment
from apps.payments.serializers import PaymentListSerializer
from apps.payments.selectors import (
    annotate_customer_outstanding,
    annotate_invoice_paid,
)


class CustomerListCreateView(ListCreateAPIView):
    """
    GET  /api/customers/   – paginated list with optional ?search= and ?is_active=
    POST /api/customers/   – create a new customer
    """

    serializer_class = CustomerSerializer
    permission_classes = [IsAdminOrStaff]
    pagination_class = StandardPagination

    def get_queryset(self):
        qs = Customer.objects.order_by("name")

        # --- is_active filter ---
        is_active_param = self.request.query_params.get("is_active")
        if is_active_param is not None:
            if is_active_param.lower() in ("true", "1"):
                qs = qs.filter(is_active=True)
            elif is_active_param.lower() in ("false", "0"):
                qs = qs.filter(is_active=False)

        # --- search filter (name, phone, code — case-insensitive) ---
        search = self.request.query_params.get("search", "").strip()
        if search:
            qs = qs.filter(
                Q(name__icontains=search)
                | Q(phone__icontains=search)
                | Q(code__icontains=search)
            )

        return annotate_customer_outstanding(qs)

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        customer = create_customer(serializer.validated_data)
        out = self.get_serializer(customer)
        return Response(out.data, status=status.HTTP_201_CREATED)


class CustomerDetailView(RetrieveUpdateAPIView):
    """
    GET   /api/customers/{id}/  – retrieve a single customer
    PATCH /api/customers/{id}/  – partial update (including deactivation)

    PUT is disabled (405).
    """

    serializer_class = CustomerSerializer
    permission_classes = [IsAdminOrStaff]
    queryset = annotate_customer_outstanding(Customer.objects.all())
    http_method_names = ["get", "patch", "head", "options"]

    def partial_update(self, request, *args, **kwargs):
        instance = self.get_object()
        serializer = self.get_serializer(instance, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        customer = update_customer(instance, serializer.validated_data)
        out = self.get_serializer(customer)
        return Response(out.data)


# ---------------------------------------------------------------------------
# Phase 6 — customer open invoices, payments and statement
# ---------------------------------------------------------------------------

def _get_customer(pk: int) -> Customer:
    try:
        return Customer.objects.get(pk=pk)
    except Customer.DoesNotExist:
        raise NotFound("Customer not found.")


class CustomerOpenInvoicesView(APIView):
    """
    GET /api/customers/{id}/open-invoices/

    Issued invoices of the customer that still have a balance, oldest first.
    """

    permission_classes = [IsAdminOrStaff]

    def get(self, request, pk):
        customer = _get_customer(pk)

        qs = annotate_invoice_delivery(
            annotate_invoice_paid(
                Invoice.objects.filter(
                    customer=customer,
                    status=InvoiceStatus.ISSUED,
                )
                .select_related("customer")
                .order_by("invoice_date", "id")
            )
        ).filter(paid_amount__lt=F("grand_total"))

        paginator = StandardPagination()
        page = paginator.paginate_queryset(qs, request)
        serializer = InvoiceListSerializer(page, many=True)
        return paginator.get_paginated_response(serializer.data)


class CustomerInvoicesView(APIView):
    """
    GET /api/customers/{id}/invoices/

    All invoices of the customer (issued, draft, open, settled), newest first.
    """

    permission_classes = [IsAdminOrStaff]

    def get(self, request, pk):
        customer = _get_customer(pk)

        qs = annotate_invoice_delivery(
            annotate_invoice_paid(
                Invoice.objects.filter(customer=customer)
                .select_related("customer", "created_by", "issued_by")
                .prefetch_related("items")
                .order_by("-invoice_date", "-id")
            )
        )

        status_param = request.query_params.get("status", "").strip().upper()
        if status_param:
            qs = qs.filter(status=status_param)

        paginator = StandardPagination()
        page = paginator.paginate_queryset(qs, request)
        serializer = InvoiceListSerializer(page, many=True)
        return paginator.get_paginated_response(serializer.data)


class CustomerPaymentsView(APIView):
    """GET /api/customers/{id}/payments/ — the customer's payments."""

    permission_classes = [IsAdminOrStaff]

    def get(self, request, pk):
        customer = _get_customer(pk)

        qs = (
            Payment.objects.filter(customer=customer)
            .select_related("customer", "received_by")
            .order_by("-payment_date", "-id")
        )

        paginator = StandardPagination()
        page = paginator.paginate_queryset(qs, request)
        serializer = PaymentListSerializer(page, many=True)
        return paginator.get_paginated_response(serializer.data)


def _build_statement_entries(customer: Customer) -> list:
    """
    Build running-balance entries for one customer.

    An issued invoice is a debit on its invoice date; a payment is a credit on
    its payment date. Equal dates are ordered by creation time.
    """
    entries = []

    invoices = Invoice.objects.filter(
        customer=customer,
        status=InvoiceStatus.ISSUED,
    ).order_by("invoice_date", "id")
    for invoice in invoices:
        entries.append(
            {
                "sort_key": (
                    invoice.invoice_date,
                    invoice.created_at,
                    0,
                    invoice.id,
                ),
                "date": invoice.invoice_date,
                "type": "INVOICE",
                "reference": invoice.invoice_number or f"#{invoice.id}",
                "description": "Invoice",
                "debit": invoice.grand_total,
                "credit": Decimal("0.00"),
                "invoice_id": invoice.id,
                "payment_id": None,
            }
        )

    payments = Payment.objects.filter(customer=customer).order_by(
        "payment_date", "id"
    )
    for payment in payments:
        entries.append(
            {
                "sort_key": (
                    payment.payment_date,
                    payment.created_at,
                    1,
                    payment.id,
                ),
                "date": payment.payment_date,
                "type": "PAYMENT",
                "reference": payment.reference or f"#{payment.id}",
                "description": f"Payment ({payment.get_method_display()})",
                "debit": Decimal("0.00"),
                "credit": payment.amount,
                "invoice_id": None,
                "payment_id": payment.id,
            }
        )

    entries.sort(key=lambda entry: entry["sort_key"])

    balance = Decimal("0.00")
    results = []
    for entry in entries:
        balance += entry["debit"] - entry["credit"]
        results.append(
            {
                "date": entry["date"].isoformat(),
                "type": entry["type"],
                "reference": entry["reference"],
                "description": entry["description"],
                "debit": format_money(entry["debit"]),
                "credit": format_money(entry["credit"]),
                "balance": format_money(balance),
                "invoice_id": entry["invoice_id"],
                "payment_id": entry["payment_id"],
            }
        )
    return results


class CustomerStatementView(APIView):
    """
    GET /api/customers/{id}/statement/

    Debits (issued invoices) and credits (payments) with a running balance.
    The final balance equals the customer's outstanding amount.
    """

    permission_classes = [IsAdminOrStaff]

    def get(self, request, pk):
        customer = _get_customer(pk)
        entries = _build_statement_entries(customer)

        paginator = StandardPagination()
        page = paginator.paginate_queryset(entries, request)
        return paginator.get_paginated_response(page)
