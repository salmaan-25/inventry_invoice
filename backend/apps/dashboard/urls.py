"""Dashboard URL patterns — Phase 10."""

from django.urls import path

from apps.dashboard.views import DashboardAPIView

urlpatterns = [
    path("dashboard/", DashboardAPIView.as_view(), name="dashboard"),
    path("", DashboardAPIView.as_view(), name="dashboard-root"),
]
