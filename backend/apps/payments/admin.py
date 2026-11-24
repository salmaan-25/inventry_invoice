from django.contrib import admin

from apps.payments.models import Payment, PaymentAllocation


class PaymentAllocationInline(admin.TabularInline):
    model = PaymentAllocation
    fields = ("invoice", "amount")
    extra = 0
    can_delete = False


@admin.register(Payment)
class PaymentAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "customer",
        "payment_date",
        "amount",
        "method",
        "reference",
        "received_by",
        "created_at",
    )
    list_filter = ("method", "payment_date", "created_at")
    search_fields = (
        "customer__name",
        "customer__code",
        "reference",
        "note",
    )
    ordering = ("-payment_date", "-id")
    inlines = [PaymentAllocationInline]


@admin.register(PaymentAllocation)
class PaymentAllocationAdmin(admin.ModelAdmin):
    list_display = ("payment", "invoice", "amount")
    search_fields = ("payment__customer__name", "invoice__invoice_number")
