"""
accounts.views — Phase 1.

Auth endpoints  (public or any authenticated user):
  GET  /api/auth/csrf/           — sets CSRF cookie
  POST /api/auth/login/          — login; returns user object
  POST /api/auth/logout/         — ends session
  GET  /api/auth/me/             — current user info

Staff endpoints (Admin only):
  GET  /api/staff/               — list staff (search, filter)
  POST /api/staff/               — create staff
  GET  /api/staff/{id}/          — detail
  PATCH /api/staff/{id}/         — update
  POST /api/staff/{id}/set-password/ — set password

Login is throttled: 5 attempts per minute per username+IP combined.
Inactive users are rejected on every authenticated request.
"""

import logging

from django.contrib.auth import SESSION_KEY
from django.db.models import Q
from django.middleware.csrf import get_token
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import ensure_csrf_cookie
from rest_framework import status
from rest_framework.authentication import SessionAuthentication
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.generics import get_object_or_404
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.throttling import AnonRateThrottle
from rest_framework.views import APIView

class CsrfExemptSessionAuthentication(SessionAuthentication):
    def enforce_csrf(self, request):
        return  # CSRF check not enforced on logout

from apps.accounts.models import User, Employee
from apps.accounts.serializers import (
    EmployeeSerializer,
    LoginSerializer,
    SetPasswordSerializer,
    StaffCreateSerializer,
    StaffUpdateSerializer,
    UserReadSerializer,
)
from apps.accounts.services import deactivate_user_sessions, login_user, logout_user, set_user_password
from apps.common.pagination import StandardPagination
from apps.common.permissions import IsAdmin, IsAdminOrStaff

logger = logging.getLogger(__name__)


from apps.accounts.throttles import LoginRateThrottle


# ---------------------------------------------------------------------------
# Auth — CSRF cookie
# ---------------------------------------------------------------------------


class CSRFView(APIView):
    """
    GET /api/auth/csrf/

    Sets the CSRF cookie so the frontend can read the token and include it
    in subsequent mutation requests (POST/PATCH/DELETE) as X-CSRFToken.
    Public — no authentication required.
    """

    permission_classes = [AllowAny]
    authentication_classes = []

    @method_decorator(ensure_csrf_cookie)
    def get(self, request, *args, **kwargs):
        return Response({"detail": "CSRF cookie set."})


# ---------------------------------------------------------------------------
# Auth — Login
# ---------------------------------------------------------------------------


class LoginView(APIView):
    """
    POST /api/auth/login/

    Body: { "username": "...", "password": "..." }
    Returns: the authenticated user object (Section 3 response shape).
    Sets session cookie.

    Rate-limited: 5 attempts per minute per IP.
    Generic error message on failure — does not reveal whether username exists.
    """

    permission_classes = [AllowAny]
    authentication_classes = []
    throttle_classes = [LoginRateThrottle]

    def post(self, request, *args, **kwargs):
        serializer = LoginSerializer(data=request.data, context={"request": request})
        serializer.is_valid(raise_exception=True)
        user = serializer.validated_data["user"]
        login_user(request, user)
        return Response(UserReadSerializer(user).data, status=status.HTTP_200_OK)


# ---------------------------------------------------------------------------
# Auth — Logout
# ---------------------------------------------------------------------------


class LogoutView(APIView):
    """
    POST /api/auth/logout/

    Ends the session. Requires authentication (any active user).
    """

    permission_classes = [IsAuthenticated]
    authentication_classes = [CsrfExemptSessionAuthentication]

    def post(self, request, *args, **kwargs):
        logout_user(request)
        return Response({"detail": "Logged out successfully."}, status=status.HTTP_200_OK)


# ---------------------------------------------------------------------------
# Auth — Current user
# ---------------------------------------------------------------------------


class MeView(APIView):
    """
    GET /api/auth/me/

    Returns the authenticated user's details. Any active, authenticated user.
    """

    permission_classes = [IsAuthenticated]

    def get(self, request, *args, **kwargs):
        serializer = UserReadSerializer(request.user)
        return Response(serializer.data)


# ---------------------------------------------------------------------------
# Business Staff (Employees) — List and Create
# ---------------------------------------------------------------------------


class StaffListCreateView(APIView):
    """
    GET  /api/staff/  — list business employees (search, pagination, or all=true)
    POST /api/staff/  — create a new business employee
    """

    permission_classes = [IsAdminOrStaff]

    def get(self, request, *args, **kwargs):
        qs = Employee.objects.all()

        search = request.query_params.get("search", "").strip()
        if search:
            qs = qs.filter(
                Q(name__icontains=search)
                | Q(employee_id__icontains=search)
                | Q(contact__icontains=search)
            )

        if request.query_params.get("all") in ("true", "1"):
            serializer = EmployeeSerializer(qs, many=True)
            return Response({"count": qs.count(), "results": serializer.data})

        paginator = StandardPagination()
        page = paginator.paginate_queryset(qs, request)
        serializer = EmployeeSerializer(page, many=True)
        return paginator.get_paginated_response(serializer.data)

    def post(self, request, *args, **kwargs):
        serializer = EmployeeSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        employee = serializer.save()
        return Response(EmployeeSerializer(employee).data, status=status.HTTP_201_CREATED)


# ---------------------------------------------------------------------------
# Business Staff (Employees) — Detail, Update, Delete
# ---------------------------------------------------------------------------


class StaffDetailView(APIView):
    """
    GET    /api/staff/{id}/  — employee detail
    PATCH  /api/staff/{id}/  — update details
    DELETE /api/staff/{id}/  — delete employee
    """

    permission_classes = [IsAdminOrStaff]

    def _get_employee(self, pk):
        return get_object_or_404(Employee, pk=pk)

    def get(self, request, pk, *args, **kwargs):
        employee = self._get_employee(pk)
        return Response(EmployeeSerializer(employee).data)

    def patch(self, request, pk, *args, **kwargs):
        employee = self._get_employee(pk)
        serializer = EmployeeSerializer(employee, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        updated_emp = serializer.save()
        return Response(EmployeeSerializer(updated_emp).data)

    def delete(self, request, pk, *args, **kwargs):
        employee = self._get_employee(pk)
        name = employee.name
        emp_id = employee.employee_id
        employee.delete()
        return Response(
            {"detail": f"Employee {name} ({emp_id}) deleted successfully."},
            status=status.HTTP_200_OK,
        )


# ---------------------------------------------------------------------------
# Staff — Set password
# ---------------------------------------------------------------------------


class StaffSetPasswordView(APIView):
    """
    POST /api/staff/{id}/set-password/

    Admin sets a staff member's password.
    Admin only.
    """

    permission_classes = [IsAdmin]

    def post(self, request, pk, *args, **kwargs):
        user = get_object_or_404(User, pk=pk)
        serializer = SetPasswordSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        set_user_password(user, serializer.validated_data["new_password"])
        return Response({"detail": "Password updated successfully."}, status=status.HTTP_200_OK)
