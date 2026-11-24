"""
Dashboard views — Phase 10.

Provides a single endpoint returning all dashboard figures:
  GET /api/dashboard/
"""

from datetime import date, timedelta
from decimal import Decimal

from django.db.models import Count, DecimalField, F, Sum, Value as Value_expr
from django.db.models.functions import Coalesce
from django.utils import timezone

from rest_framework.response import Response
from rest_framework.views import APIView

from apps.invoices.models import Invoice
from apps.invoices.serializers import _invoice_payment_status
from apps.payments.models import Payment
from apps.products.models import Product
from apps.expenses.models import Expense
from apps.other_income.models import OtherIncome


def _today_kolkata():
    """Return today's date in Asia/Kolkata timezone."""
    return timezone.localdate()


def _this_month_start_end():
    """Return (month_start, month_end) for the calendar month of today."""
    today = _today_kolkata()
    month_start = today.replace(day=1)
    # last day of month
    if today.month == 12:
        month_end = today.replace(month=12, day=31)
    else:
        month_end = today.replace(month=today.month + 1, day=1) - timedelta(days=1)
    return month_start, month_end


# ---------------------------------------------------------------------------
# Dashboard API
# ---------------------------------------------------------------------------

class DashboardAPIView(APIView):
    """
    GET /api/dashboard/ — All dashboard values.

    Anonymous access is allowed (per Phase 10 spec: ``| Any |``).
    """

    def get(self, request):
        today = _today_kolkata()
        month_start, month_end = _this_month_start_end()

        _money_zero = Value_expr(Decimal("0.00"), output_field=DecimalField())

        # ---- today_sales ----
        # sum of grand_total of ISSUED invoices with invoice_date = today
        today_sales = (
            Invoice.objects.filter(
                status="ISSUED", invoice_date=today,
            )
            .aggregate(total=Coalesce(Sum("grand_total"), _money_zero))
            ["total"]
        )

        # ---- month_sales ----
        # sum and count of ISSUED invoices with invoice_date in this month
        month_sales_result = (
            Invoice.objects.filter(
                status="ISSUED",
                invoice_date__gte=month_start,
                invoice_date__lte=month_end,
            )
            .aggregate(
                amount=Coalesce(Sum("grand_total"), _money_zero),
                count=Count("id"),
            )
        )
        month_sales_amount = month_sales_result["amount"]
        month_sales_count = month_sales_result["count"]

        # ---- month_payments_received ----
        # sum of payments with payment_date in this month
        month_payments_received = (
            Payment.objects.filter(
                payment_date__gte=month_start, payment_date__lte=month_end,
            )
            .aggregate(total=Coalesce(Sum("amount"), _money_zero))
            ["total"]
        )

        # ---- outstanding_amount ----
        # Proxy: sum of grand_total for ISSUED invoices.
        # (Full payment-offset computation is deferred to a future phase.)
        outstanding_amount = (
            Invoice.objects.filter(status="ISSUED")
            .aggregate(total=Coalesce(Sum("grand_total"), _money_zero))
            ["total"]
        )

        # ---- stock ----
        # count of active Goods/Goods-Hardware products, and how many are low-stock
        stock_qs = Product.objects.filter(
            is_active=True,
            item_type__in=["GOODS", "GOODS_HARDWARE"],
        )
        tracked_product_count = stock_qs.count()
        low_stock_count = stock_qs.filter(
            current_stock__lte=F("reorder_level"),
        ).count()

        # ---- open_challans_to_dispatch ----
        # Placeholder: delivery challan dispatch-status tracking not yet implemented in V1.
        open_challans_to_dispatch = 0

        # ---- month_expenses ----
        month_expenses = (
            Expense.objects.filter(
                date__gte=month_start, date__lte=month_end,
            )
            .aggregate(total=Coalesce(Sum("amount"), _money_zero))
            ["total"]
        )

        # ---- month_other_income ----
        month_other_income = (
            OtherIncome.objects.filter(
                date__gte=month_start, date__lte=month_end,
            )
            .aggregate(total=Coalesce(Sum("amount"), _money_zero))
            ["total"]
        )

        # ---- recent_invoices ----
        # last 5 issued invoices (by issued_at)
        recent_invoices = (
            Invoice.objects.filter(status="ISSUED")
            .select_related("customer")
            .order_by("-issued_at")[:5]
        )

        recent_invoices_data = []
        for inv in recent_invoices:
            recent_invoices_data.append({
                "id": inv.id,
                "invoice_number": inv.invoice_number,
                "invoice_date": str(inv.invoice_date) if inv.invoice_date else None,
                "customer_name": inv.customer.name if inv.customer else "",
                "grand_total": str(inv.grand_total) if inv.grand_total else "0.00",
                "payment_status": _invoice_payment_status(inv),
            })

        # ---- low_stock_products ----
        low_stock_products = []
        for p in stock_qs.filter(current_stock__lte=F("reorder_level")):
            low_stock_products.append({
                "id": p.id,
                "name": p.name,
                "current_stock": str(p.current_stock),
                "reorder_level": str(p.reorder_level) if p.reorder_level else "0.000",
                "unit": p.unit.name if p.unit else "",
            })
        # Sort by current_stock ascending (lowest stock first)
        low_stock_products.sort(key=lambda x: float(x["current_stock"]))

        response_data = {
            "as_of": today.isoformat(),
            "today_sales": str(today_sales),
            "month_sales": {
                "amount": str(month_sales_amount),
                "invoice_count": month_sales_count,
            },
            "month_payments_received": str(month_payments_received),
            "outstanding_amount": str(outstanding_amount),
            "stock": {
                "tracked_product_count": tracked_product_count,
                "low_stock_count": low_stock_count,
            },
            "month_expenses": str(month_expenses),
            "month_other_income": str(month_other_income),
            "open_challans_to_dispatch": open_challans_to_dispatch,
            "recent_invoices": recent_invoices_data,
            "low_stock_products": low_stock_products,
        }

        return Response(response_data)
