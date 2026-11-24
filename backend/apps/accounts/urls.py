"""
accounts URL configuration — Phase 1.

Auth routes  (all under /api/auth/):
  GET  /api/auth/csrf/
  POST /api/auth/login/
  POST /api/auth/logout/
  GET  /api/auth/me/

Staff routes (all under /api/staff/):
  GET  /api/staff/
  POST /api/staff/
  GET  /api/staff/<id>/
  PATCH /api/staff/<id>/
  POST /api/staff/<id>/set-password/
"""

from django.urls import path

from apps.accounts.views import (
    CSRFView,
    LoginView,
    LogoutView,
    MeView,
    StaffDetailView,
    StaffListCreateView,
    StaffSetPasswordView,
)

urlpatterns = [
    # Auth
    path("auth/csrf/", CSRFView.as_view(), name="auth-csrf"),
    path("auth/login/", LoginView.as_view(), name="auth-login"),
    path("auth/logout/", LogoutView.as_view(), name="auth-logout"),
    path("auth/me/", MeView.as_view(), name="auth-me"),

    # Staff management (Admin only)
    path("staff/", StaffListCreateView.as_view(), name="staff-list-create"),
    path("staff/<int:pk>/", StaffDetailView.as_view(), name="staff-detail"),
    path("staff/<int:pk>/set-password/", StaffSetPasswordView.as_view(), name="staff-set-password"),
]
