"""
company URL configuration — Phase 2.

  GET   /api/company/ or /api/settings/company/   — any signed-in user
  PATCH /api/company/ or /api/settings/company/   — Admin only
"""

from django.urls import path

from apps.company.views import CompanySettingsView

urlpatterns = [
    path(
        "company/",
        CompanySettingsView.as_view(),
        name="company-settings-alias",
    ),
    path(
        "settings/company/",
        CompanySettingsView.as_view(),
        name="company-settings",
    ),
]
