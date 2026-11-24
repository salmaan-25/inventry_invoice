"""
Permission classes — Section 4.

Two roles: ADMIN and STAFF.

IsAdmin         — only ADMIN users (for Staff management, Settings update, etc.)
IsAdminOrStaff  — any authenticated active user (alias for IsAuthenticated
                  with an active check; kept here for explicit clarity in views)
"""

from rest_framework.permissions import BasePermission

from apps.common.constants import Role


class IsAdmin(BasePermission):
    """Allow access only to users with role == ADMIN."""

    message = "You must be an admin to perform this action."

    def has_permission(self, request, view):
        return bool(
            request.user
            and request.user.is_authenticated
            and request.user.is_active
            and getattr(request.user, "role", None) == Role.ADMIN
        )


class IsAdminOrStaff(BasePermission):
    """
    Allow access to any authenticated active user (ADMIN or STAFF).

    This is effectively the same as IsAuthenticated combined with an is_active
    check.  Used explicitly in views so intent is clear at a glance.
    """

    message = "Authentication required."

    def has_permission(self, request, view):
        return bool(
            request.user
            and request.user.is_authenticated
            and request.user.is_active
        )
