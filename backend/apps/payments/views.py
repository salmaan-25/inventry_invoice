"""
Payment views — Phase 6.

GET  /api/payments/       list (customer, method, date range, search)
POST /api/payments/       record a payment with allocations
GET  /api/payments/{id}/  detail with allocations

Payments are immutable in V1 (D12): there is no PATCH or DELETE.
"""

from django.db.models import Q
from rest_framework import status
from rest_framework.exceptions import NotFound
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.common.dates import parse_date_range
from apps.common.pagination import StandardPagination
from apps.common.permissions import IsAdminOrStaff
from apps.payments.models import Payment
from apps.payments.serializers import (
    PaymentCreateSerializer,
    PaymentListSerializer,
    PaymentSerializer,
)
from apps.payments.services import create_payment


class PaymentListCreateView(APIView):
    """
    GET  /api/payments/  — paginated list
    POST /api/payments/  — record a payment
    """

    permission_classes = [IsAdminOrStaff]

    def get(self, request):
        qs = Payment.objects.select_related("customer", "received_by").order_by(
            "-payment_date", "-id"
        )

        customer_param = request.query_params.get("customer", "").strip()
        if customer_param:
            qs = qs.filter(customer_id=customer_param)

        method_param = request.query_params.get("method", "").strip().upper()
        if method_param:
            qs = qs.filter(method=method_param)

        from_param = request.query_params.get("from", "").strip()
        to_param = request.query_params.get("to", "").strip()
        if from_param or to_param:
            from_date, to_date = parse_date_range(request)
            qs = qs.filter(payment_date__gte=from_date, payment_date__lte=to_date)

        search = request.query_params.get("search", "").strip()
        if search:
            qs = qs.filter(
                Q(reference__icontains=search)
                | Q(customer__name__icontains=search)
            )

        paginator = StandardPagination()
        page = paginator.paginate_queryset(qs, request)
        serializer = PaymentListSerializer(page, many=True)
        return paginator.get_paginated_response(serializer.data)

    def post(self, request):
        serializer = PaymentCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        payment, created = create_payment(serializer.validated_data, request.user)

        payment = (
            Payment.objects.select_related("customer", "received_by")
            .prefetch_related("allocations__invoice")
            .get(pk=payment.pk)
        )
        return Response(
            PaymentSerializer(payment).data,
            status=status.HTTP_201_CREATED if created else status.HTTP_200_OK,
        )


class PaymentDetailView(APIView):
    """GET /api/payments/{id}/ — payment detail with allocations."""

    permission_classes = [IsAdminOrStaff]

    def get(self, request, pk):
        try:
            payment = (
                Payment.objects.select_related("customer", "received_by")
                .prefetch_related("allocations__invoice")
                .get(pk=pk)
            )
        except Payment.DoesNotExist:
            raise NotFound("Payment not found.")

        return Response(PaymentSerializer(payment).data)
