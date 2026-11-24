"""
Inventory business logic — Phase 4.

`apply_stock_movement` is the only function allowed to change
`Product.current_stock`.  It locks the product row, rejects invalid changes,
and writes the matching StockMovement record in the same transaction.
"""

from decimal import InvalidOperation

from django.db import transaction

from apps.common.constants import ItemType, MovementType
from apps.common.decimals import format_quantity, to_decimal
from apps.common.exceptions import (
    InsufficientStockError,
    InvalidStockOperationError,
)
from apps.inventory.models import StockMovement
from apps.products.models import Product


@transaction.atomic
def apply_stock_movement(
    product_id: int,
    change,
    movement_type: str,
    reason: str,
    user,
    invoice=None,
) -> StockMovement:
    """
    Apply a signed stock change to one product and record the movement.

    The product row is locked with SELECT FOR UPDATE for the duration of the
    transaction, so concurrent movements cannot oversell stock.  When called
    from inside an existing atomic block this joins that transaction.

    Raises InvalidStockOperationError for zero changes, unknown movement
    types, Service products, or missing adjustment reasons.  Raises
    InsufficientStockError when the resulting balance would be negative.

    `invoice` is part of the final Phase 5 signature; the invoice foreign key
    is added in the Phase 5 migration, so it is not accepted yet.
    """
    try:
        change = to_decimal(change)
    except (InvalidOperation, TypeError, ValueError):
        raise InvalidStockOperationError(
            "Stock change must be a valid decimal quantity."
        )

    if change == 0:
        raise InvalidStockOperationError("Stock change must not be zero.")

    if movement_type not in MovementType.values:
        raise InvalidStockOperationError("Unknown stock movement type.")

    if movement_type == MovementType.ADJUSTMENT and not (reason or "").strip():
        raise InvalidStockOperationError(
            "A reason is required for a stock adjustment."
        )

    product = Product.objects.select_for_update().get(pk=product_id)

    if product.item_type == ItemType.SERVICE:
        raise InvalidStockOperationError("Service products do not track stock.")

    new_balance = product.current_stock + change

    if new_balance < 0:
        raise InsufficientStockError(
            details=[
                {
                    "product": product.id,
                    "name": product.name,
                    "available": format_quantity(product.current_stock),
                    "required": format_quantity(abs(change)),
                }
            ]
        )

    product.current_stock = new_balance
    product.save(update_fields=["current_stock", "updated_at"])

    return StockMovement.objects.create(
        product=product,
        movement_type=movement_type,
        quantity_change=change,
        balance_after=new_balance,
        reason=reason or "",
        created_by=user,
        invoice=invoice,
    )
