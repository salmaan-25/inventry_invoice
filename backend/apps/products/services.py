"""
Product business logic — Phase 4.

Product creation and opening stock are one atomic operation.  Product codes
are generated from a locked counter row so concurrent creates cannot produce
duplicate codes.
"""

from django.db import transaction

from apps.common.constants import MovementType
from apps.products.models import Product, ProductCodeCounter


def _generate_code(counter_value: int) -> str:
    """Format an integer as a product code: 1 → 'P0001'."""
    return f"P{counter_value:04d}"


@transaction.atomic
def create_product(validated_data: dict, user) -> Product:
    """
    Create a Product and, for goods, its opening stock movement.

    A blank or missing `code` is generated from the ProductCodeCounter
    singleton.  A caller-supplied code is kept as-is (its uniqueness is
    enforced by the serializer and the database).
    """
    data = dict(validated_data)
    opening_stock = data.pop("opening_stock", None)

    code = (data.get("code") or "").strip()
    if not code:
        ProductCodeCounter.objects.get_or_create(
            pk=1,
            defaults={"next_value": 1},
        )
        counter = ProductCodeCounter.objects.select_for_update().get(pk=1)

        # Skip any codes that were supplied manually through the API.
        while True:
            code = _generate_code(counter.next_value)
            counter.next_value += 1
            if not Product.objects.filter(code=code).exists():
                break

        counter.save(update_fields=["next_value"])

    data["code"] = code
    product = Product.objects.create(**data)

    if opening_stock is not None and opening_stock > 0:
        # Imported here to keep the products/inventory modules free of a
        # module-level import cycle.
        from apps.inventory.services import apply_stock_movement

        apply_stock_movement(
            product.id,
            opening_stock,
            MovementType.OPENING,
            "Opening stock",
            user,
        )
        product.refresh_from_db()

    return product


def update_product(instance: Product, validated_data: dict) -> Product:
    """Apply a partial update to a product.  Never changes stock."""
    data = dict(validated_data)
    data.pop("opening_stock", None)

    # A blank code on PATCH keeps the existing code instead of erasing it.
    if "code" in data and not (data.get("code") or "").strip():
        data.pop("code")

    for attr, value in data.items():
        setattr(instance, attr, value)
    instance.save()
    return instance
