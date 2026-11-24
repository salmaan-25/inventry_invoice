"""
Delivery Challan views — Phase 7.

GET  /api/challans/               list (invoice, customer, date range)
POST /api/challans/               create
GET  /api/challans/{id}/          detail with items
GET  /api/challans/{id}/document/ printable PDF

Challans are immutable in V1 (D14): there is no PATCH or DELETE.
"""

from django.http import HttpResponse
from rest_framework import status
from rest_framework.exceptions import NotFound
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.common.dates import parse_date_range
from apps.common.pagination import StandardPagination
from apps.common.permissions import IsAdminOrStaff
from apps.delivery.models import DeliveryChallan
from apps.delivery.serializers import (
    DeliveryChallanCreateSerializer,
    DeliveryChallanListSerializer,
    DeliveryChallanSerializer,
)
from apps.delivery.services import create_challan


def _get_challan(pk: int) -> DeliveryChallan:
    try:
        return (
            DeliveryChallan.objects.select_related(
                "invoice__customer", "created_by"
            )
            .prefetch_related("items__invoice_item")
            .get(pk=pk)
        )
    except DeliveryChallan.DoesNotExist:
        raise NotFound("Delivery challan not found.")


class DeliveryChallanListCreateView(APIView):
    """
    GET  /api/challans/  — paginated list
    POST /api/challans/  — create a challan for an issued invoice
    """

    permission_classes = [IsAdminOrStaff]

    def get(self, request):
        qs = (
            DeliveryChallan.objects.select_related(
                "invoice__customer", "created_by"
            )
            .order_by("-delivery_date", "-id")
        )

        invoice_param = request.query_params.get("invoice", "").strip()
        if invoice_param:
            qs = (
                qs.filter(invoice_id=int(invoice_param))
                if invoice_param.isdigit()
                else qs.none()
            )

        customer_param = request.query_params.get("customer", "").strip()
        if customer_param:
            qs = (
                qs.filter(invoice__customer_id=int(customer_param))
                if customer_param.isdigit()
                else qs.none()
            )

        from_param = request.query_params.get("from", "").strip()
        to_param = request.query_params.get("to", "").strip()
        if from_param or to_param:
            from_date, to_date = parse_date_range(request)
            qs = qs.filter(
                delivery_date__gte=from_date,
                delivery_date__lte=to_date,
            )

        paginator = StandardPagination()
        page = paginator.paginate_queryset(qs, request)
        serializer = DeliveryChallanListSerializer(page, many=True)
        return paginator.get_paginated_response(serializer.data)

    def post(self, request):
        serializer = DeliveryChallanCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        challan = create_challan(serializer.validated_data, request.user)
        challan = _get_challan(challan.pk)
        return Response(
            DeliveryChallanSerializer(challan).data,
            status=status.HTTP_201_CREATED,
        )


class DeliveryChallanDetailView(APIView):
    """GET /api/challans/{id}/ — detail with items."""

    permission_classes = [IsAdminOrStaff]

    def get(self, request, pk):
        challan = _get_challan(pk)
        return Response(DeliveryChallanSerializer(challan).data)


class DeliveryChallanDocumentView(APIView):
    """
    GET /api/challans/{id}/document/

    Returns the challan as a PDF. The document uses the invoice item and
    business snapshots, so it never changes when products or settings change.
    """

    permission_classes = [IsAdminOrStaff]

    def get(self, request, pk):
        challan = _get_challan(pk)

        from apps.delivery.document import render_challan_pdf

        pdf_bytes = render_challan_pdf(challan)
        response = HttpResponse(pdf_bytes, content_type="application/pdf")
        response["Content-Disposition"] = (
            f'inline; filename="challan_{challan.id}.pdf"'
        )
        return response
