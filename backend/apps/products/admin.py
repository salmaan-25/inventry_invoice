from django.contrib import admin

from apps.products.models import Product, Unit, ProductCodeCounter


@admin.register(Unit)
class UnitAdmin(admin.ModelAdmin):
    list_display = ("name",)
    search_fields = ("name",)
    ordering = ("name",)


@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    list_display = (
        "code",
        "name",
        "item_type",
        "unit",
        "selling_price",
        "current_stock",
        "gst_rate",
        "is_active",
    )
    list_filter = ("item_type", "is_active", "unit")
    search_fields = ("code", "name", "description", "hsn_sac")
    ordering = ("name",)


@admin.register(ProductCodeCounter)
class ProductCodeCounterAdmin(admin.ModelAdmin):
    list_display = ("next_value",)
