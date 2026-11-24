from django.contrib import admin

from apps.other_income.models import OtherIncome, IncomeCategory


@admin.register(IncomeCategory)
class IncomeCategoryAdmin(admin.ModelAdmin):
    list_display = ("name",)
    search_fields = ("name",)


@admin.register(OtherIncome)
class OtherIncomeAdmin(admin.ModelAdmin):
    list_display = (
        "date",
        "category",
        "amount",
        "payment_method",
        "received_from",
        "reference",
        "recorded_by",
        "created_at",
    )
    list_filter = ("category", "payment_method", "date")
    search_fields = ("description", "received_from", "reference")
    ordering = ("-date", "-id")
