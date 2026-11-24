"""Management command — verify stored stock against the movement ledger."""

from decimal import Decimal

from django.core.management.base import BaseCommand, CommandError
from django.db.models import Sum
from django.db.models.functions import Coalesce

from apps.common.constants import STOCK_TRACKED_ITEM_TYPES
from apps.common.decimals import format_quantity
from apps.products.models import Product


class Command(BaseCommand):
    help = (
        "Compare each stock-tracked product's stored current_stock with the "
        "sum of its stock movement quantity_change values. Exits non-zero if "
        "any mismatch is found."
    )

    def handle(self, *args, **options):
        products = (
            Product.objects.filter(item_type__in=STOCK_TRACKED_ITEM_TYPES)
            .annotate(
                movement_total=Coalesce(
                    Sum("stock_movements__quantity_change"),
                    Decimal("0.000"),
                )
            )
            .order_by("id")
        )

        mismatches = []
        for product in products.iterator():
            if product.current_stock != product.movement_total:
                mismatches.append(
                    (
                        product.id,
                        product.code,
                        product.name,
                        product.current_stock,
                        product.movement_total,
                    )
                )

        if mismatches:
            for product_id, code, name, stored, calculated in mismatches:
                self.stderr.write(
                    self.style.ERROR(
                        f"MISMATCH product={product_id} code={code} "
                        f"name={name!r} stored={format_quantity(stored)} "
                        f"movements={format_quantity(calculated)}"
                    )
                )
            raise CommandError(
                f"Stock consistency check failed for {len(mismatches)} "
                "product(s)."
            )

        self.stdout.write(
            self.style.SUCCESS(
                "Stock consistency check passed: stored stock matches the "
                "movement ledger for all tracked products."
            )
        )
