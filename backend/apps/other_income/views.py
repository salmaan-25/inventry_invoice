"""
Other income views — Phase 9.

Endpoints:
  GET  /api/income-categories/       category list
  GET  /api/other-income/            list (search, category, date range,
                                        total_amount for all filtered records)
  POST /api/other-income/            create
  GET  /api/other-income/{id}/       detail
  PATCH /api/other-income/{id}/      partial update
  GET  /api/other-income/export/     ?from=&to= -> .xlsx download
"""

from datetime import date, datetime
from decimal import Decimal
from io import BytesIO

from django.db import transaction
from django.db.models import DecimalField, Sum, Value as Value_expr
from django.db.models.functions import Coalesce
from django.http import HttpResponse
from rest_framework import status
from rest_framework.exceptions import NotFound
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.common.dates import parse_date_range
from apps.common.exceptions import InvalidDateRangeError
from apps.common.pagination import StandardPagination
from apps.common.permissions import IsAdminOrStaff
from apps.common.exports import export_income_to_xlsx
from apps.other_income.models import OtherIncome, IncomeCategory
from apps.other_income.serializers import (
    IncomeCategorySerializer,
    OtherIncomeListSerializer,
    OtherIncomeDetailSerializer,
    OtherIncomeSerializer,
)


class IncomeCategoryListCreateView(APIView):
    """GET /api/income-categories/  — list categories
    POST /api/income-categories/  — create category (admin only)"""

    permission_classes = [IsAdminOrStaff]

    def get(self, request):
        qs = IncomeCategory.objects.order_by("name")
        serializer = IncomeCategorySerializer(qs, many=True)
        return Response(serializer.data)

    def post(self, request):
        serializer = IncomeCategorySerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(serializer.data, status=status.HTTP_201_CREATED)


# ---------------------------------------------------------------------------# Other income list / create# ---------------------------------------------------------------------------

class OtherIncomeListCreateView(APIView):
    """GET /api/other-income/  — paginated list with filters
      ?search=        (description, received_from)
      ?category=      (category id)
      ?from=          (inclusive date YYYY-MM-DD)
      ?to=            (inclusive date YYYY-MM-DD)
    Response adds: total_amount = sum of all filtered records (not just page)
    POST /api/other-income/  — create other income"""

    permission_classes = [IsAdminOrStaff]
    pagination_class = StandardPagination

    def get(self, request):
        qs = OtherIncome.objects.select_related("category", "recorded_by").order_by(
            "-date", "-id"
        )

        # --- search ---
        search = request.query_params.get("search", "").strip()
        if search:
            from django.db.models import Q
            qs = qs.filter(
                Q(description__icontains=search)
                | Q(received_from__icontains=search)
            )

        # --- category filter ---
        category_param = request.query_params.get("category", "").strip()
        if category_param:
            qs = qs.filter(category_id=category_param)

        # --- date range ---
        from_param = request.query_params.get("from", "").strip()
        to_param = request.query_params.get("to", "").strip()
        if from_param or to_param:
            from_date, to_date = parse_date_range(request)
            qs = qs.filter(date__gte=from_date, date__lte=to_date)

        # --- paginated page ---
        paginator = StandardPagination()
        page = paginator.paginate_queryset(qs, request)

        # --- total_amount for ALL filtered records (not just page) ---
        total_amount = qs.aggregate(
            total=Coalesce(
                Sum("amount"),
                Value_expr(Decimal("0.00"), output_field=DecimalField()),
            )
        )["total"]

        serializer = OtherIncomeListSerializer(page, many=True)
        response = paginator.get_paginated_response(serializer.data)
        response.data["total_amount"] = str(total_amount)
        return response

    @transaction.atomic
    def post(self, request):
        serializer = OtherIncomeSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        income = serializer.save(
            recorded_by=request.user,
        )
        out = OtherIncomeDetailSerializer(income)
        return Response(out.data, status=status.HTTP_201_CREATED)


# ---------------------------------------------------------------------------# Other income detail / update# ---------------------------------------------------------------------------

class OtherIncomeDetailView(APIView):
    """GET  /api/other-income/{id}/  — detail
    PATCH /api/other-income/{id}/  — partial update (admin only)"""

    permission_classes = [IsAdminOrStaff]

    def _get_income(self, pk):
        try:
            return OtherIncome.objects.select_related("category", "recorded_by").get(pk=pk)
        except OtherIncome.DoesNotExist:
            raise NotFound("Other income not found.")

    def get(self, request, pk):
        income = self._get_income(pk)
        serializer = OtherIncomeDetailSerializer(income)
        return Response(serializer.data)

    @transaction.atomic
    def patch(self, request, pk):
        income = self._get_income(pk)
        serializer = OtherIncomeSerializer(
            income,
            data=request.data,
            partial=True,
        )
        serializer.is_valid(raise_exception=True)
        income = serializer.save()
        out = OtherIncomeDetailSerializer(income)
        return Response(out.data)


# ---------------------------------------------------------------------------# Other income export (Excel)# ---------------------------------------------------------------------------

class OtherIncomeExportView(APIView):
    """GET /api/other-income/export/?from=YYYY-MM-DD&to=YYYY-MM-DD

    Returns an .xlsx workbook with the filtered other incomes.
    Anonymous access is denied (IsAdminOrStaff)."""

    permission_classes = [IsAdminOrStaff]

    def get(self, request):
        from_param = request.query_params.get("from", "").strip()
        to_param = request.query_params.get("to", "").strip()

        if not from_param or not to_param:
            raise InvalidDateRangeError(
                "Both 'from' and 'to' dates are required in YYYY-MM-DD format."
            )

        from_date, to_date = parse_date_range(request)
        qs = (
            OtherIncome.objects.select_related("category", "recorded_by")
            .filter(date__gte=from_date, date__lte=to_date)
            .order_by("date", "id")
        )

        # Generate the Excel workbook.
        wb = export_income_to_xlsx(qs)
        filename = f"other_income_{from_date.isoformat()}_to_{to_date.isoformat()}.xlsx"

        buffer = BytesIO()
        wb.save(buffer)
        response = HttpResponse(
            buffer.getvalue(),
            content_type=
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
        response["Content-Disposition"] = (
            f'attachment; filename="{filename}"'
        )
        return response