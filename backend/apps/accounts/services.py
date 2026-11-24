"""
accounts.services — Phase 1.

Business-logic functions for authentication and staff management.
Views stay thin; all workflows go here.
"""

import logging

from django.contrib.auth import login as django_login, logout as django_logout
from django.db import transaction

from apps.accounts.models import User

logger = logging.getLogger(__name__)


def login_user(request, user: User) -> None:
    """
    Establish a session for the authenticated user.

    Uses Django's login() which rotates the CSRF token and sets the
    session cookie. Must be called after credentials are verified.
    """
    django_login(request, user)


def logout_user(request) -> None:
    """Flush the session."""
    django_logout(request)


def set_user_password(user: User, new_password: str) -> None:
    """
    Set a new password for a user and invalidate all existing sessions.

    Wrapping in a transaction is not strictly required here (single write),
    but it keeps the pattern consistent with other service functions.
    """
    with transaction.atomic():
        user.set_password(new_password)
        user.save(update_fields=["password"])
        # Clear all sessions for this user so they must log in again with
        # the new password (security best practice).
        _clear_user_sessions(user)


def deactivate_user_sessions(user: User) -> None:
    """
    Delete all database sessions belonging to a user so that an inactive
    user is immediately rejected on their next request.
    """
    _clear_user_sessions(user)


def _clear_user_sessions(user: User) -> None:
    """Remove all Django database sessions owned by this user."""
    from django.contrib.sessions.backends.db import SessionStore
    from django.contrib.sessions.models import Session
    from django.utils import timezone

    # Walk active sessions and delete those that belong to this user.
    # This is O(n) on active sessions — acceptable for a small-team app.
    active_sessions = Session.objects.filter(expire_date__gte=timezone.now())
    for session in active_sessions:
        try:
            data = session.get_decoded()
        except Exception:
            continue
        if str(data.get("_auth_user_id")) == str(user.pk):
            session.delete()
