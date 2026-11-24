"""
company.views — Phase 2.

  GET   /api/settings/company/   — Any signed-in user
  PATCH /api/settings/company/   — Admin only

There is deliberately no POST (create) or DELETE endpoint: the business
settings record exists exactly once.
"""

from drf_spectacular.utils import extend_schema
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.common.permissions import IsAdmin, IsAdminOrStaff
from apps.company.serializers import (
    CompanySettingsReadSerializer,
    CompanySettingsUpdateSerializer,
)
from apps.company.services import get_company_settings, update_company_settings


class CompanySettingsView(APIView):
    """Read or update the single business settings record."""

    parser_classes = [MultiPartParser, FormParser, JSONParser]

    def get_permissions(self):
        # Reading is allowed to every signed-in user (documents need the
        # details); changing the settings is Admin only.
        if self.request.method == "PATCH":
            return [IsAdmin()]
        return [IsAdminOrStaff()]

    @extend_schema(
        tags=["Settings"],
        responses=CompanySettingsReadSerializer,
    )
    def get(self, request, *args, **kwargs):
        company_settings = get_company_settings()
        serializer = CompanySettingsReadSerializer(
            company_settings,
            context={"request": request},
        )
        return Response(serializer.data)

    @extend_schema(
        tags=["Settings"],
        request={
            "multipart/form-data": CompanySettingsUpdateSerializer,
            "application/json": CompanySettingsUpdateSerializer,
        },
        responses=CompanySettingsReadSerializer,
    )
    def patch(self, request, *args, **kwargs):
        company_settings = get_company_settings()
        serializer = CompanySettingsUpdateSerializer(
            company_settings,
            data=request.data,
            partial=True,
        )
        serializer.is_valid(raise_exception=True)

        updated = update_company_settings(
            data=serializer.validated_data,
            user=request.user,
        )
        return Response(
            CompanySettingsReadSerializer(
                updated,
                context={"request": request},
            ).data
        )
