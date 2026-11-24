"""
Expense views — Phase 8.

Endpoints:
  GET  /api/expense-categories/       category list
  GET  /api/expenses/                 list (search, category, date range,
                                        total_amount for all filtered records)
  POST /api/expenses/                 create
  GET  /api/expenses/{id}/            detail
  PATCH /api/expenses/{id}/           update
  GET  /api/expenses/export/          ?from=&to= -> .xlsx download
"""

from datetime import date, datetime
from decimal import Decimal

from django.db import models, transaction
from django.db.models import Sum, Value as Value_expr, DecimalField
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
from apps.expenses.models import Expense, ExpenseCategory
from apps.expenses.serializers import (
    ExpenseCategorySerializer,
    ExpenseListSerializer,
    ExpenseDetailSerializer,
    ExpenseSerializer,
)
from apps.common.exports import export_expenses_to_xlsx
from apps.common.decimals import format_money
from io import BytesIO


class ExpenseCategoryListCreateView(APIView):
    """
    GET /api/expense-categories/  — list categories
    POST /api/expense-categories/  — create category (admin only)
    """

    permission_classes = [IsAdminOrStaff]

    def get(self, request):
        qs = ExpenseCategory.objects.order_by("name")
        serializer = ExpenseCategorySerializer(qs, many=True)
        return Response(serializer.data)

    def post(self, request):
        serializer = ExpenseCategorySerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(serializer.data, status=status.HTTP_201_CREATED)


# ---------------------------------------------------------------------------
# Expense list / create
# ---------------------------------------------------------------------------

class ExpenseListCreateView(APIView):
    """
    GET /api/expenses/  — paginated list with filters
      ?search=        (description, paid_to)
      ?category=      (category id)
      ?from=          (inclusive date YYYY-MM-DD)
      ?to=            (inclusive date YYYY-MM-DD)
    Response adds: total_amount = sum of all filtered records (not just page)
    POST /api/expenses/  — create expense
    """

    permission_classes = [IsAdminOrStaff]
    pagination_class = StandardPagination

    def get(self, request):
        qs = Expense.objects.select_related("category", "recorded_by").order_by(
            "-date", "-id"
        )

        # --- search ---
        search = request.query_params.get("search", "").strip()
        if search:
            from django.db.models import Q
            qs = qs.filter(
                Q(description__icontains=search)
                | Q(paid_to__icontains=search)
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

        serializer = ExpenseListSerializer(page, many=True)
        response = paginator.get_paginated_response(serializer.data)
        response.data["total_amount"] = str(total_amount)
        return response

    @transaction.atomic
    def post(self, request):
        serializer = ExpenseSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        expense = serializer.save(
            recorded_by=request.user,
        )
        out = ExpenseDetailSerializer(expense)
        return Response(out.data, status=status.HTTP_201_CREATED)


# ---------------------------------------------------------------------------
# Expense detail / update
# ---------------------------------------------------------------------------

class ExpenseDetailView(APIView):
    """
    GET  /api/expenses/{id}/  — detail
    PATCH /api/expenses/{id}/  — partial update (admin only)
    """

    permission_classes = [IsAdminOrStaff]

    def _get_expense(self, pk):
        try:
            return Expense.objects.select_related("category", "recorded_by").get(pk=pk)
        except Expense.DoesNotExist:
            raise NotFound("Expense not found.")

    def get(self, request, pk):
        expense = self._get_expense(pk)
        serializer = ExpenseDetailSerializer(expense)
        return Response(serializer.data)

    @transaction.atomic
    def patch(self, request, pk):
        expense = self._get_expense(pk)
        serializer = ExpenseSerializer(
            expense,
            data=request.data,
            partial=True,
        )
        serializer.is_valid(raise_exception=True)
        expense = serializer.save()
        out = ExpenseDetailSerializer(expense)
        return Response(out.data)


# ---------------------------------------------------------------------------
# Expense export (Excel)
# ---------------------------------------------------------------------------

class ExpenseExportView(APIView):
    """
    GET /api/expenses/export/?from=YYYY-MM-DD&to=YYYY-MM-DD

    Returns an .xlsx workbook with the filtered expenses.
    Anonymous access is denied (IsAdminOrStaff).
    """

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
            Expense.objects.select_related("category", "recorded_by")
            .filter(date__gte=from_date, date__lte=to_date)
            .order_by("date", "id")
        )

        # Generate the Excel workbook.
        wb = export_expenses_to_xlsx(qs)
        filename = f"expenses_{from_date.isoformat()}_to_{to_date.isoformat()}.xlsx"

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