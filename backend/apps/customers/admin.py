from django.contrib import admin

from apps.customers.models import Customer, CustomerCodeCounter
from apps.invoices.models import Invoice


class InvoiceInline(admin.TabularInline):
    model = Invoice
    fields = (
        "invoice_number",
        "invoice_date",
        "invoice_type",
        "status",
        "grand_total",
        "advance_amount",
        "balance_amount",
    )
    readonly_fields = fields
    extra = 0
    can_delete = False
    show_change_link = True


@admin.register(Customer)
class CustomerAdmin(admin.ModelAdmin):
    list_display = (
        "code",
        "name",
        "phone",
        "gstin",
        "state",
        "is_active",
        "total_invoices_count",
        "created_at",
    )
    list_filter = ("is_active", "state", "created_at")
    search_fields = ("code", "name", "phone", "gstin", "billing_address")
    ordering = ("name",)
    readonly_fields = ("code", "created_at", "updated_at")
    inlines = [InvoiceInline]

    fieldsets = (
        (None, {"fields": ("code", "name", "is_active")}),
        ("Contact & Tax Info", {"fields": ("phone", "gstin", "state", "billing_address")}),
        ("Timestamps", {"fields": ("created_at", "updated_at")}),
    )

    @admin.display(description="Invoices")
    def total_invoices_count(self, obj: Customer) -> int:
        return obj.invoices.count()


@admin.register(CustomerCodeCounter)
class CustomerCodeCounterAdmin(admin.ModelAdmin):
    list_display = ("next_value",)
