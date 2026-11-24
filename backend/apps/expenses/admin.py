from django.contrib import admin

from apps.expenses.models import Expense, ExpenseCategory


@admin.register(ExpenseCategory)
class ExpenseCategoryAdmin(admin.ModelAdmin):
    list_display = ("name",)
    search_fields = ("name",)


@admin.register(Expense)
class ExpenseAdmin(admin.ModelAdmin):
    list_display = (
        "date",
        "category",
        "amount",
        "payment_method",
        "paid_to",
        "recorded_by",
        "created_at",
    )
    list_filter = ("category", "payment_method", "date")
    search_fields = ("description", "paid_to", "notes")
    ordering = ("-date", "-id")
