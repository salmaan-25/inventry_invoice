"""
Customer serializers — Phase 3.

CustomerSerializer handles both read and write.  The `code` field is always
read-only.  `outstanding_amount` is a read-only derived value (Phase 6).
"""

from rest_framework import serializers

from apps.common.constants import INDIAN_STATES_AND_UTS
from apps.common.decimals import format_money
from apps.common.validators import validate_gstin
from apps.customers.models import Customer
from apps.customers.validators import validate_phone


class CustomerSerializer(serializers.ModelSerializer):
    """
    Serializer for Customer — used for list, detail, create, and partial update.

    Read-only fields: id, code, outstanding_amount, created_at, updated_at.
    All other fields are writable on create; partial=True is passed on PATCH.
    """

    outstanding_amount = serializers.SerializerMethodField()

    class Meta:
        model = Customer
        fields = [
            "id",
            "code",
            "name",
            "phone",
            "gstin",
            "state",
            "billing_address",
            "is_active",
            "outstanding_amount",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "code", "created_at", "updated_at"]

    def get_outstanding_amount(self, customer: Customer) -> str:
        """
        Use the list/detail annotation when present; otherwise calculate it
        for the single customer being written or returned.
        """
        annotated = getattr(customer, "outstanding_amount", None)
        if annotated is not None:
            return format_money(annotated)

        from apps.payments.selectors import customer_outstanding_amount
        return format_money(customer_outstanding_amount(customer.id))

    # ------------------------------------------------------------------
    # Field-level validation
    # ------------------------------------------------------------------

    def validate_phone(self, value: str) -> str:
        return validate_phone(value)

    def validate_gstin(self, value: str) -> str:
        return validate_gstin(value)

    def validate_state(self, value: str) -> str:
        if value and value not in INDIAN_STATES_AND_UTS:
            raise serializers.ValidationError(
                f"'{value}' is not a valid Indian state or union territory."
            )
        return value
