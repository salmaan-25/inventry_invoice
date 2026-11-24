"""
Shared test fixtures for the whole test suite.

Provides:
  - admin_user   : an ADMIN-role User instance
  - staff_user   : a STAFF-role User instance
  - admin_client : APIClient authenticated as admin_user
  - staff_client : APIClient authenticated as staff_user
  - anon_client  : un-authenticated APIClient

Each fixture is function-scoped (default) so test state never leaks.
"""

import pytest
from django.core.cache import cache
from django.test import Client
from rest_framework.test import APIClient

from apps.accounts.models import User
from apps.common.constants import Role


# ---------------------------------------------------------------------------
# Test isolation
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def clear_cache_between_tests():
    """
    Clear the cache around every test.

    Login throttling stores counters in the cache. Without this, one test's
    failed logins can throttle another test that happens to run within the
    same minute, making the suite order-dependent.
    """
    cache.clear()
    yield
    cache.clear()


# ---------------------------------------------------------------------------
# User fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def admin_user(db):
    """An active ADMIN user."""
    return User.objects.create_user(
        username="admin",
        password="AdminPass123!",
        full_name="Test Admin",
        phone="9876543210",
        role=Role.ADMIN,
        is_staff=True,
    )


@pytest.fixture
def staff_user(db):
    """An active STAFF user."""
    return User.objects.create_user(
        username="staff",
        password="StaffPass123!",
        full_name="Test Staff",
        phone="9876543211",
        role=Role.STAFF,
    )


# ---------------------------------------------------------------------------
# API client fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def admin_client(admin_user):
    """APIClient authenticated as the admin user (session-based)."""
    client = APIClient()
    client.force_login(admin_user)
    return client


@pytest.fixture
def staff_client(staff_user):
    """APIClient authenticated as the staff user (session-based)."""
    client = APIClient()
    client.force_login(staff_user)
    return client


@pytest.fixture
def anon_client():
    """Un-authenticated APIClient."""
    return APIClient()
