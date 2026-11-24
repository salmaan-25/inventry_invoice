"""
company.serializers — Phase 2.

Read serializer exposes the business details with the logo as an absolute URL
(or null). The update serializer validates the optional logo and GSTIN; it is
only used for input, so the response always uses the read serializer.
"""

from drf_spectacular.utils import extend_schema_field
from rest_framework import serializers

from apps.common.validators import validate_gstin as validate_gstin_format
from apps.company.models import CompanySettings
from apps.company.validators import validate_logo_file


class CompanySettingsReadSerializer(serializers.ModelSerializer):
    logo = serializers.SerializerMethodField()
    updated_by = serializers.IntegerField(
        source="updated_by_id",
        read_only=True,
        allow_null=True,
    )

    class Meta:
        model = CompanySettings
        fields = (
            "id",
            "business_name",
            "logo",
            "address",
            "state",
            "phone",
            "email",
            "gstin",
            "bank_holder_name",
            "bank_name",
            "bank_account_no",
            "bank_ifsc",
            "updated_at",
            "updated_by",
        )
        read_only_fields = fields

    @extend_schema_field(serializers.URLField(allow_null=True))
    def get_logo(self, obj: CompanySettings) -> str | None:
        if not obj.logo:
            return None
        url = obj.logo.url
        request = self.context.get("request")
        if request is not None:
            return request.build_absolute_uri(url)
        return url


class CompanySettingsUpdateSerializer(serializers.ModelSerializer):
    logo = serializers.ImageField(required=False)

    class Meta:
        model = CompanySettings
        fields = (
            "business_name",
            "logo",
            "address",
            "state",
            "phone",
            "email",
            "gstin",
            "bank_holder_name",
            "bank_name",
            "bank_account_no",
            "bank_ifsc",
        )

    def validate_gstin(self, value):
        return validate_gstin_format(value)

    def validate_logo(self, value):
        validate_logo_file(value)
        return value
