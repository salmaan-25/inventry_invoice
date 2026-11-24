"""
Invoice views — Phase 5, extended in Phases 6 and 7.

GET    /api/invoices/            list (search, status, customer, date range,
                                 payment_status)
POST   /api/invoices/            create draft
GET    /api/invoices/{id}/       detail with lines and snapshots
PATCH  /api/invoices/{id}/       edit draft
POST   /api/invoices/calculate/  stateless preview — saves nothing
POST   /api/invoices/{id}/issue/ issue the draft
GET    /api/invoices/{id}/document/ printable PDF document
GET    /api/invoices/{id}/payments/ payments allocated to the invoice
GET    /api/invoices/{id}/dispatch-summary/ per-line dispatched and remaining
GET    /api/invoices/awaiting-dispatch/ issued invoices with goods remaining
"""

from decimal import Decimal
from django.db import transaction
from django.db.models import F, Sum
from django.http import HttpResponse
from rest_framework import status
from rest_framework.exceptions import NotFound
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.common.constants import (
    STOCK_TRACKED_ITEM_TYPES,
    DeliveryStatus,
    InvoiceStatus,
    PaymentStatus,
)
from apps.common.dates import parse_date_range
from apps.common.decimals import format_quantity
from apps.common.exceptions import InvalidStateError
from apps.common.pagination import StandardPagination
from apps.common.permissions import IsAdminOrStaff
from apps.delivery.selectors import (
    annotate_invoice_delivery,
    annotate_invoice_item_dispatched,
    invoice_delivery_status,
)
from apps.invoices.models import Invoice, InvoiceItem
from apps.invoices.serializers import (
    InvoiceCalculateSerializer,
    InvoiceCreateUpdateSerializer,
    InvoiceDetailSerializer,
    InvoiceListSerializer,
)
from apps.invoices.services import (
    _recalculate_draft,
    calculate_invoice,
    issue_invoice,
    sync_invoice_advance_payment,
    _build_business_snapshot,
    _build_customer_snapshot,
)
from apps.payments.models import Payment
from apps.payments.serializers import InvoicePaymentSerializer
from apps.payments.selectors import annotate_invoice_paid


# ---------------------------------------------------------------------------
# List / Create
# ---------------------------------------------------------------------------

class InvoiceListCreateView(APIView):
    """
    GET  /api/invoices/  — paginated list
    POST /api/invoices/  — create draft
    """

    permission_classes = [IsAdminOrStaff]

    def get(self, request):
        qs = annotate_invoice_delivery(
            annotate_invoice_paid(
                Invoice.objects.select_related(
                    "customer", "created_by", "issued_by"
                )
                .prefetch_related("items")
                .order_by("-invoice_date", "-id")
            )
        )

        # Filters
        search = request.query_params.get("search", "").strip()
        if search:
            from django.db.models import Q
            qs = qs.filter(
                Q(customer__name__icontains=search)
                | Q(invoice_number__icontains=search)
            )

        status_param = request.query_params.get("status", "").strip().upper()
        if status_param:
            qs = qs.filter(status=status_param)

        payment_status_param = (
            request.query_params.get("payment_status", "").strip().upper()
        )
        if payment_status_param:
            if payment_status_param == PaymentStatus.UNPAID:
                qs = qs.filter(paid_amount=0, grand_total__gt=0)
            elif payment_status_param == PaymentStatus.PARTIALLY_PAID:
                qs = qs.filter(
                    paid_amount__gt=0,
                    paid_amount__lt=F("grand_total"),
                )
            elif payment_status_param == PaymentStatus.PAID:
                qs = qs.filter(paid_amount__gte=F("grand_total"))
            else:
                qs = qs.none()

        delivery_status_param = (
            request.query_params.get("delivery_status", "").strip().upper()
        )
        if delivery_status_param:
            if delivery_status_param in DeliveryStatus.values:
                qs = qs.filter(delivery_status=delivery_status_param)
            else:
                qs = qs.none()

        customer_param = request.query_params.get("customer", "").strip()
        if customer_param:
            qs = qs.filter(customer_id=customer_param)

        from_param = request.query_params.get("from", "").strip()
        to_param = request.query_params.get("to", "").strip()
        if from_param or to_param:
            from_date, to_date = parse_date_range(request)
            qs = qs.filter(invoice_date__gte=from_date, invoice_date__lte=to_date)

        paginator = StandardPagination()
        page = paginator.paginate_queryset(qs, request)
        serializer = InvoiceListSerializer(page, many=True)
        return paginator.get_paginated_response(serializer.data)

    @transaction.atomic
    def post(self, request):
        serializer = InvoiceCreateUpdateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        manual_inv_no = data.get("invoice_number", "").strip() if data.get("invoice_number") else ""

        invoice = Invoice.objects.create(
            invoice_number=manual_inv_no or None,
            customer=data["customer"],
            invoice_date=data["invoice_date"],
            notes=data.get("notes", ""),
            invoice_type=data.get("invoice_type", "GST"),
            advance_amount=data.get("advance_amount", Decimal("0.00")),
            # Consignee
            consignee_name=data.get("consignee_name", ""),
            consignee_address=data.get("consignee_address", ""),
            consignee_gstin=data.get("consignee_gstin", ""),
            consignee_state=data.get("consignee_state", "Tamil Nadu"),
            consignee_state_code=data.get("consignee_state_code", "33"),
            # Dispatch
            e_way_bill_no=data.get("e_way_bill_no", ""),
            delivery_note=data.get("delivery_note", ""),
            payment_terms=data.get("payment_terms", ""),
            reference_no_date=data.get("reference_no_date", ""),
            other_references=data.get("other_references", ""),
            buyer_order_no=data.get("buyer_order_no", ""),
            order_date=data.get("order_date"),
            dispatch_doc_no=data.get("dispatch_doc_no", ""),
            delivery_note_date=data.get("delivery_note_date"),
            dispatched_through=data.get("dispatched_through", ""),
            destination=data.get("destination", ""),
            bill_of_lading_no=data.get("bill_of_lading_no", ""),
            motor_vehicle_no=data.get("motor_vehicle_no", ""),
            terms_of_delivery=data.get("terms_of_delivery", ""),
            created_by=request.user,
        )

        for line_no, line_data in enumerate(data["lines"], start=1):
            product = line_data.get("product")
            desc = line_data.get("description") or line_data.get("product_name") or (product.name if product else "Item")
            hsn = line_data.get("hsn_sac") or (product.hsn_sac if product else "")
            unit = line_data.get("unit_name") or (product.unit.name if product and product.unit else "pcs")
            gst_rate = line_data.get("gst_rate") if line_data.get("gst_rate") is not None else (product.gst_rate if product else None)
            code = product.code if product else ""
            item_type = product.item_type if product else "GOODS"

            item = InvoiceItem(
                invoice=invoice,
                line_no=line_no,
                product=product,
                product_name=desc,
                product_code=code,
                hsn_sac=hsn,
                unit_name=unit,
                item_type=item_type,
                gst_rate=gst_rate,
                quantity=line_data["quantity"],
                rate=line_data["rate"],
            )
            item.save()

        _recalculate_draft(invoice)
        if manual_inv_no:
            invoice.invoice_number = manual_inv_no
            invoice.save(update_fields=["invoice_number"])
        sync_invoice_advance_payment(invoice, request.user)
        invoice.refresh_from_db()
        out = InvoiceDetailSerializer(invoice)
        return Response(out.data, status=status.HTTP_201_CREATED)


# ---------------------------------------------------------------------------
# Detail / Update
# ---------------------------------------------------------------------------

class InvoiceDetailView(APIView):
    """
    GET   /api/invoices/{id}/  — detail
    PATCH /api/invoices/{id}/  — edit draft
    """

    permission_classes = [IsAdminOrStaff]

    def _get_invoice(self, pk):
        try:
            return annotate_invoice_delivery(
                annotate_invoice_paid(
                    Invoice.objects.select_related(
                        "customer", "created_by", "issued_by"
                    ).prefetch_related("items__product__unit")
                )
            ).get(pk=pk)
        except Invoice.DoesNotExist:
            raise NotFound("Invoice not found.")

    def get(self, request, pk):
        invoice = self._get_invoice(pk)
        return Response(InvoiceDetailSerializer(invoice).data)

    @transaction.atomic
    def patch(self, request, pk):
        try:
            invoice = Invoice.objects.select_for_update().get(pk=pk)
        except Invoice.DoesNotExist:
            raise NotFound("Invoice not found.")

        serializer = InvoiceCreateUpdateSerializer(data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        if "invoice_number" in data:
            val = (data["invoice_number"] or "").strip()
            if val:
                invoice.invoice_number = val
        if "customer" in data:
            invoice.customer = data["customer"]
        if "invoice_date" in data:
            invoice.invoice_date = data["invoice_date"]
        if "notes" in data:
            invoice.notes = data["notes"]
        if "invoice_type" in data:
            invoice.invoice_type = data["invoice_type"]
        if "advance_amount" in data:
            invoice.advance_amount = data["advance_amount"]

        for field in [
            "consignee_name", "consignee_address", "consignee_gstin",
            "consignee_state", "consignee_state_code", "e_way_bill_no",
            "delivery_note", "payment_terms", "reference_no_date",
            "other_references", "buyer_order_no", "order_date",
            "dispatch_doc_no", "delivery_note_date", "dispatched_through",
            "destination", "bill_of_lading_no", "motor_vehicle_no",
            "terms_of_delivery",
        ]:
            if field in data:
                setattr(invoice, field, data[field])

        invoice.save()

        # Replace lines if provided
        if "lines" in data:
            invoice.items.all().delete()
            for line_no, line_data in enumerate(data["lines"], start=1):
                product = line_data.get("product")
                desc = line_data.get("description") or line_data.get("product_name") or (product.name if product else "Item")
                hsn = line_data.get("hsn_sac") or (product.hsn_sac if product else "")
                unit = line_data.get("unit_name") or (product.unit.name if product and product.unit else "pcs")
                gst_rate = line_data.get("gst_rate") if line_data.get("gst_rate") is not None else (product.gst_rate if product else None)
                code = product.code if product else ""
                item_type = product.item_type if product else "GOODS"

                item = InvoiceItem(
                    invoice=invoice,
                    line_no=line_no,
                    product=product,
                    product_name=desc,
                    product_code=code,
                    hsn_sac=hsn,
                    unit_name=unit,
                    item_type=item_type,
                    gst_rate=gst_rate,
                    quantity=line_data["quantity"],
                    rate=line_data["rate"],
                )
                item.save()

        _recalculate_draft(invoice)

        # If issued, refresh snapshots too
        if invoice.status == InvoiceStatus.ISSUED:
            from apps.company.models import CompanySettings
            comp = CompanySettings.objects.first()
            if comp:
                invoice.business_snapshot = _build_business_snapshot(comp)
            invoice.customer_snapshot = _build_customer_snapshot(invoice.customer)
            invoice.save(update_fields=["business_snapshot", "customer_snapshot"])

        sync_invoice_advance_payment(invoice, request.user)

        invoice.refresh_from_db()
        # Reload with prefetch for response.
        invoice = annotate_invoice_delivery(
            annotate_invoice_paid(
                Invoice.objects.select_related(
                    "customer", "created_by", "issued_by"
                ).prefetch_related("items__product__unit")
            )
        ).get(pk=pk)
        return Response(InvoiceDetailSerializer(invoice).data)


# ---------------------------------------------------------------------------
# Calculate (stateless preview)
# ---------------------------------------------------------------------------

class InvoiceCalculateView(APIView):
    """
    POST /api/invoices/calculate/

    Returns calculated totals for the given payload. Saves nothing.
    """

    permission_classes = [IsAdminOrStaff]

    def post(self, request):
        serializer = InvoiceCalculateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        inv_type = data.get("invoice_type", "GST")
        is_gst = (inv_type != "NON_GST")
        advance_amount = data.get("advance_amount", Decimal("0.00"))

        lines_data = []
        for line in data["lines"]:
            prod = line.get("product")
            gst_rate = line.get("gst_rate") if line.get("gst_rate") is not None else (prod.gst_rate if prod else None)
            lines_data.append({
                "quantity": line["quantity"],
                "rate": line["rate"],
                "gst_rate": gst_rate if is_gst else None,
            })

        calc = calculate_invoice(lines_data, is_gst_invoice=is_gst, advance_amount=advance_amount)

        # Build response with line details.
        response_lines = []
        for idx, line in enumerate(data["lines"]):
            line_calc = calc["lines"][idx]
            prod = line.get("product")
            desc = line.get("description") or line.get("product_name") or (prod.name if prod else "Item")
            unit = line.get("unit_name") or (prod.unit.name if prod and prod.unit else "pcs")
            hsn = line.get("hsn_sac") or (prod.hsn_sac if prod else "")
            gst_rate = line.get("gst_rate") if line.get("gst_rate") is not None else (prod.gst_rate if prod else None)

            response_lines.append(
                {
                    "product": prod.id if prod else None,
                    "product_name": desc,
                    "description": desc,
                    "unit_name": unit,
                    "hsn_sac": hsn,
                    "gst_rate": str(gst_rate) if gst_rate is not None else None,
                    "quantity": str(line["quantity"]),
                    "rate": str(line["rate"]),
                    "line_total": str(line_calc["line_total"]),
                    "cgst_amount": str(line_calc["cgst_amount"]),
                    "sgst_amount": str(line_calc["sgst_amount"]),
                }
            )

        return Response(
            {
                "is_gst_invoice": is_gst,
                "invoice_type": inv_type,
                "lines": response_lines,
                "subtotal": str(calc["subtotal"]),
                "total_cgst": str(calc["total_cgst"]),
                "total_sgst": str(calc["total_sgst"]),
                "total_tax": str(calc["total_tax"]),
                "round_off": str(calc["round_off"]),
                "grand_total": str(calc["grand_total"]),
                "advance_amount": str(calc["advance_amount"]),
                "balance_amount": str(calc["balance_amount"]),
            }
        )


# ---------------------------------------------------------------------------
# Issue
# ---------------------------------------------------------------------------

class InvoiceIssueView(APIView):
    """
    POST /api/invoices/{id}/issue/

    Issues a draft invoice. Idempotent — a second call returns the invoice
    unchanged.
    """

    permission_classes = [IsAdminOrStaff]

    def post(self, request, pk):
        try:
            invoice = issue_invoice(pk, request.user)
        except Invoice.DoesNotExist:
            raise NotFound("Invoice not found.")

        invoice = annotate_invoice_delivery(
            annotate_invoice_paid(
                Invoice.objects.select_related(
                    "customer", "created_by", "issued_by"
                ).prefetch_related("items__product__unit")
            )
        ).get(pk=pk)
        return Response(InvoiceDetailSerializer(invoice).data)


# ---------------------------------------------------------------------------
# Document (PDF)
# ---------------------------------------------------------------------------

class InvoiceDocumentView(APIView):
    """
    GET /api/invoices/{id}/document/

    Returns the invoice as a PDF.  Issued invoices render from snapshots;
    drafts render from live data and are watermarked "DRAFT".
    """

    permission_classes = [IsAdminOrStaff]

    def get(self, request, pk):
        try:
            invoice = (
                Invoice.objects.select_related("customer", "created_by", "issued_by")
                .prefetch_related("items__product__unit")
                .get(pk=pk)
            )
        except Invoice.DoesNotExist:
            raise NotFound("Invoice not found.")

        from apps.invoices.document import render_invoice_pdf
        pdf_bytes = render_invoice_pdf(invoice)

        response = HttpResponse(pdf_bytes, content_type="application/pdf")
        response["Content-Disposition"] = (
            f'inline; filename="invoice_{invoice.id}.pdf"'
        )
        return response


# ---------------------------------------------------------------------------
# Payments allocated to an invoice (Phase 6)
# ---------------------------------------------------------------------------

class InvoicePaymentsView(APIView):
    """
    GET /api/invoices/{id}/payments/

    Payments allocated to this invoice, newest first. `allocated_amount` is
    the part of each payment applied to this invoice.
    """

    permission_classes = [IsAdminOrStaff]

    def get(self, request, pk):
        if not Invoice.objects.filter(pk=pk).exists():
            raise NotFound("Invoice not found.")

        qs = (
            Payment.objects.filter(allocations__invoice_id=pk)
            .select_related("customer", "received_by")
            .annotate(allocated_amount=Sum("allocations__amount"))
            .order_by("-payment_date", "-id")
        )

        paginator = StandardPagination()
        page = paginator.paginate_queryset(qs, request)
        serializer = InvoicePaymentSerializer(page, many=True)
        return paginator.get_paginated_response(serializer.data)


# ---------------------------------------------------------------------------
# Delivery summary and awaiting dispatch (Phase 7)
# ---------------------------------------------------------------------------

class InvoiceDispatchSummaryView(APIView):
    """
    GET /api/invoices/{id}/dispatch-summary/

    Per invoice line: invoiced, dispatched and remaining quantities. Every
    line is listed; `dispatchable` is false for service lines, whose
    mathematical remaining quantity is still shown.
    """

    permission_classes = [IsAdminOrStaff]

    def get(self, request, pk):
        try:
            invoice = annotate_invoice_delivery(
                Invoice.objects.select_related("customer")
            ).get(pk=pk)
        except Invoice.DoesNotExist:
            raise NotFound("Invoice not found.")

        items = annotate_invoice_item_dispatched(
            invoice.items.all()
        ).order_by("line_no")

        lines = []
        for item in items:
            lines.append(
                {
                    "invoice_item": item.id,
                    "line_no": item.line_no,
                    "product": item.product_id,
                    "product_name": item.product_name,
                    "product_code": item.product_code,
                    "hsn_sac": item.hsn_sac,
                    "unit_name": item.unit_name,
                    "item_type": item.item_type,
                    "dispatchable": (
                        item.item_type in STOCK_TRACKED_ITEM_TYPES
                    ),
                    "invoiced_quantity": format_quantity(item.quantity),
                    "dispatched_quantity": format_quantity(
                        item.dispatched_quantity
                    ),
                    "remaining_quantity": format_quantity(
                        item.remaining_quantity
                    ),
                }
            )

        return Response(
            {
                "invoice": invoice.id,
                "invoice_number": invoice.invoice_number,
                "invoice_date": invoice.invoice_date,
                "status": invoice.status,
                "customer": invoice.customer_id,
                "customer_name": invoice.customer.name,
                "delivery_status": invoice_delivery_status(invoice),
                "items": lines,
            }
        )


class InvoiceAwaitingDispatchView(APIView):
    """
    GET /api/invoices/awaiting-dispatch/

    Issued invoices that still have at least one stock-tracked line with
    quantity left to dispatch, oldest first.
    """

    permission_classes = [IsAdminOrStaff]

    def get(self, request):
        qs = annotate_invoice_delivery(
            annotate_invoice_paid(
                Invoice.objects.filter(status=InvoiceStatus.ISSUED).select_related(
                    "customer"
                )
            )
        ).filter(
            delivery_status__in=[
                DeliveryStatus.PENDING,
                DeliveryStatus.PARTIALLY_DELIVERED,
            ]
        ).order_by("invoice_date", "id")

        paginator = StandardPagination()
        page = paginator.paginate_queryset(qs, request)
        serializer = InvoiceListSerializer(page, many=True)
        return paginator.get_paginated_response(serializer.data)


class InvoiceItemAwaitingDispatchView(APIView):
    """
    GET /api/invoices/{id}/awaiting-dispatch/

    Returns stock-tracked goods lines for the specified invoice with their invoiced,
    dispatched, and remaining quantities.
    """

    permission_classes = [IsAdminOrStaff]

    def get(self, request, pk):
        try:
            invoice = annotate_invoice_delivery(
                Invoice.objects.select_related("customer")
            ).get(pk=pk)
        except Invoice.DoesNotExist:
            raise NotFound("Invoice not found.")

        items = annotate_invoice_item_dispatched(
            invoice.items.filter(item_type__in=STOCK_TRACKED_ITEM_TYPES)
        ).order_by("line_no")

        return Response(
            [
                {
                    "invoice_item_id": item.id,
                    "product_name": item.product_name,
                    "unit": item.unit_name,
                    "invoiced_quantity": format_quantity(item.quantity),
                    "already_dispatched": format_quantity(item.dispatched_quantity),
                    "remaining_quantity": format_quantity(item.remaining_quantity),
                }
                for item in items
            ]
        )
