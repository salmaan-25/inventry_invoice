from django.contrib import admin

from apps.invoices.models import Invoice, InvoiceItem


class InvoiceItemInline(admin.TabularInline):
    model = InvoiceItem
    fields = (
        "line_no",
        "product_name",
        "hsn_sac",
        "quantity",
        "unit_name",
        "rate",
        "gst_rate",
        "line_total",
        "cgst_amount",
        "sgst_amount",
    )
    extra = 0


@admin.register(Invoice)
class InvoiceAdmin(admin.ModelAdmin):
    list_display = (
        "invoice_number",
        "customer",
        "invoice_date",
        "invoice_type",
        "status",
        "grand_total",
        "advance_amount",
        "balance_amount",
        "created_by",
        "created_at",
    )
    list_filter = ("status", "invoice_type", "invoice_date", "created_at")
    search_fields = (
        "invoice_number",
        "customer__name",
        "customer__code",
        "customer__phone",
        "consignee_name",
        "motor_vehicle_no",
        "e_way_bill_no",
    )
    date_hierarchy = "invoice_date"
    ordering = ("-invoice_date", "-id")
    readonly_fields = ("created_at", "updated_at", "issued_at")
    inlines = [InvoiceItemInline]

    fieldsets = (
        (
            "Basic Information",
            {
                "fields": (
                    "invoice_number",
                    "customer",
                    "invoice_date",
                    "invoice_type",
                    "status",
                    "notes",
                )
            },
        ),
        (
            "Consignee (Ship To)",
            {
                "classes": ("collapse",),
                "fields": (
                    "consignee_name",
                    "consignee_address",
                    "consignee_gstin",
                    "consignee_state",
                    "consignee_state_code",
                ),
            },
        ),
        (
            "Transport & Dispatch Details",
            {
                "classes": ("collapse",),
                "fields": (
                    "e_way_bill_no",
                    "delivery_note",
                    "payment_terms",
                    "reference_no_date",
                    "other_references",
                    "buyer_order_no",
                    "order_date",
                    "dispatch_doc_no",
                    "delivery_note_date",
                    "dispatched_through",
                    "destination",
                    "bill_of_lading_no",
                    "motor_vehicle_no",
                    "terms_of_delivery",
                ),
            },
        ),
        (
            "Financial Totals",
            {
                "fields": (
                    "subtotal",
                    "total_cgst",
                    "total_sgst",
                    "total_tax",
                    "round_off",
                    "grand_total",
                    "advance_amount",
                    "balance_amount",
                ),
            },
        ),
        (
            "Snapshots & Audit",
            {
                "classes": ("collapse",),
                "fields": (
                    "created_by",
                    "created_at",
                    "updated_at",
                    "issued_by",
                    "issued_at",
                    "business_snapshot",
                    "customer_snapshot",
                ),
            },
        ),
    )


@admin.register(InvoiceItem)
class InvoiceItemAdmin(admin.ModelAdmin):
    list_display = (
        "invoice",
        "line_no",
        "product_name",
        "quantity",
        "unit_name",
        "rate",
        "line_total",
    )
    search_fields = (
        "product_name",
        "invoice__invoice_number",
        "hsn_sac",
    )
    list_filter = ("unit_name",)
