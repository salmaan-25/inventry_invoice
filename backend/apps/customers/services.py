"""
Customer business logic — Phase 3.

All database writes happen inside atomic transactions so that concurrent
customer creations cannot produce duplicate codes.
"""

from django.db import transaction

from apps.customers.models import Customer, CustomerCodeCounter


# ---------------------------------------------------------------------------
# Code generation
# ---------------------------------------------------------------------------

def _generate_code(counter_value: int) -> str:
    """Format an integer as a customer code: 1 → 'C0001'."""
    return f"C{counter_value:04d}"


# ---------------------------------------------------------------------------
# Create
# ---------------------------------------------------------------------------

@transaction.atomic
def create_customer(validated_data: dict) -> Customer:
    """
    Create a Customer with an auto-generated, collision-safe code.

    The CustomerCodeCounter singleton row is locked with SELECT FOR UPDATE
    for the duration of the transaction, preventing any other concurrent
    transaction from reading the same counter value.
    """
    # Ensure the singleton counter row exists (idempotent).
    CustomerCodeCounter.objects.get_or_create(pk=1, defaults={"next_value": 1})

    counter = CustomerCodeCounter.objects.select_for_update().get(pk=1)
    code = _generate_code(counter.next_value)
    counter.next_value += 1
    counter.save(update_fields=["next_value"])

    customer = Customer.objects.create(code=code, **validated_data)
    return customer


# ---------------------------------------------------------------------------
# Update
# ---------------------------------------------------------------------------

def update_customer(instance: Customer, validated_data: dict) -> Customer:
    """Apply a partial update to an existing customer and save."""
    for attr, value in validated_data.items():
        setattr(instance, attr, value)
    instance.save()
    return instance
