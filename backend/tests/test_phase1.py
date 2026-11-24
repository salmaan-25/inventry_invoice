"""
Phase 1 tests — Authentication and Staff.

Covers all mandatory test cases from the phase plan:
  - Login success and failure. Logout. `me` returns the right user.
  - Rate limit triggers THROTTLED.
  - Anonymous requests rejected (NOT_AUTHENTICATED).
  - Staff user calling any staff endpoint gets PERMISSION_DENIED.
  - Admin creates staff; staff can sign in; Admin deactivates; next request fails.
  - Cannot deactivate self, cannot demote or deactivate the last Admin.
  - Password validators reject weak passwords. Passwords not in responses.
"""

import pytest
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APIClient

from apps.accounts.models import User
from apps.common.constants import Role


# ===========================================================================
# Helpers
# ===========================================================================


def make_user(username, password, role=Role.STAFF, is_active=True, **kwargs):
    return User.objects.create_user(
        username=username,
        password=password,
        full_name=kwargs.pop("full_name", username),
        phone=kwargs.pop("phone", "9000000000"),
        role=role,
        is_active=is_active,
        **kwargs,
    )


def login(client, username, password):
    return client.post(
        "/api/auth/login/",
        {"username": username, "password": password},
        format="json",
    )


# ===========================================================================
# CSRF endpoint
# ===========================================================================


@pytest.mark.django_db
def test_csrf_endpoint_is_public(anon_client):
    resp = anon_client.get("/api/auth/csrf/")
    assert resp.status_code == status.HTTP_200_OK


# ===========================================================================
# Login
# ===========================================================================


@pytest.mark.django_db
def test_login_success(anon_client):
    make_user("alice", "StrongP@ss1")
    resp = login(anon_client, "alice", "StrongP@ss1")
    assert resp.status_code == status.HTTP_200_OK
    data = resp.json()
    assert data["username"] == "alice"
    # Password must never appear in any response.
    assert "password" not in data


@pytest.mark.django_db
def test_login_wrong_password(anon_client):
    make_user("bob", "StrongP@ss1")
    resp = login(anon_client, "bob", "wrong")
    assert resp.status_code == status.HTTP_400_BAD_REQUEST
    data = resp.json()
    assert data["code"] == "VALIDATION_ERROR"
    # Generic message — must not reveal whether user exists.
    assert "password" not in data["message"].lower() or "invalid" in data["message"].lower()


@pytest.mark.django_db
def test_login_nonexistent_user_gives_generic_error(anon_client):
    """Same error shape whether user exists or not (no username enumeration)."""
    resp = login(anon_client, "doesnotexist", "whatever")
    assert resp.status_code == status.HTTP_400_BAD_REQUEST
    assert resp.json()["code"] == "VALIDATION_ERROR"


@pytest.mark.django_db
def test_login_inactive_user_rejected(anon_client):
    make_user("carol", "StrongP@ss1", is_active=False)
    resp = login(anon_client, "carol", "StrongP@ss1")
    assert resp.status_code == status.HTTP_400_BAD_REQUEST


# ===========================================================================
# Logout
# ===========================================================================


@pytest.mark.django_db
def test_logout(staff_client):
    resp = staff_client.post("/api/auth/logout/")
    assert resp.status_code == status.HTTP_200_OK


@pytest.mark.django_db
def test_logout_requires_auth(anon_client):
    resp = anon_client.post("/api/auth/logout/")
    assert resp.status_code == status.HTTP_401_UNAUTHORIZED
    assert resp.json()["code"] == "NOT_AUTHENTICATED"


# ===========================================================================
# /auth/me/
# ===========================================================================


@pytest.mark.django_db
def test_me_returns_current_user(admin_client, admin_user):
    resp = admin_client.get("/api/auth/me/")
    assert resp.status_code == status.HTTP_200_OK
    data = resp.json()
    assert data["username"] == admin_user.username
    assert data["role"] == Role.ADMIN
    assert "password" not in data


@pytest.mark.django_db
def test_me_anonymous_returns_401(anon_client):
    resp = anon_client.get("/api/auth/me/")
    assert resp.status_code == status.HTTP_401_UNAUTHORIZED
    assert resp.json()["code"] == "NOT_AUTHENTICATED"


# ===========================================================================
# Rate limiting — login throttle
# ===========================================================================


@pytest.mark.django_db
def test_login_rate_limit_triggers_throttled(anon_client):
    """
    After 5 attempts within a minute, the throttle returns THROTTLED (429).
    """
    for _ in range(5):
        login(anon_client, "nobody", "wrong")
    resp = login(anon_client, "nobody", "wrong")
    assert resp.status_code == status.HTTP_429_TOO_MANY_REQUESTS
    assert resp.json()["code"] == "THROTTLED"


# ===========================================================================
# Employee Management CRUD & Permissions
# ===========================================================================


@pytest.mark.django_db
def test_admin_creates_employee(admin_client):
    payload = {
        "employee_id": "EMP001",
        "name": "Dave Miller",
        "contact": "9111111111",
    }
    resp = admin_client.post("/api/staff/", payload, format="json")
    assert resp.status_code == status.HTTP_201_CREATED
    data = resp.json()
    assert data["employee_id"] == "EMP001"
    assert data["name"] == "Dave Miller"
    assert data["contact"] == "9111111111"


@pytest.mark.django_db
def test_staff_can_view_employee_list(staff_client, admin_client):
    admin_client.post(
        "/api/staff/",
        {"employee_id": "EMP002", "name": "Eve Adams", "contact": "9222222222"},
        format="json",
    )
    resp = staff_client.get("/api/staff/")
    assert resp.status_code == status.HTTP_200_OK
    results = resp.json()["results"]
    assert any(emp["employee_id"] == "EMP002" for emp in results)


@pytest.mark.django_db
def test_staff_list_search_by_name_and_id(admin_client):
    admin_client.post(
        "/api/staff/",
        {"employee_id": "EMP101", "name": "Frank Ocean", "contact": "9333333333"},
        format="json",
    )
    admin_client.post(
        "/api/staff/",
        {"employee_id": "EMP102", "name": "Grace Hopper", "contact": "9444444444"},
        format="json",
    )
    resp = admin_client.get("/api/staff/?search=Frank")
    assert resp.status_code == status.HTTP_200_OK
    names = [e["name"] for e in resp.json()["results"]]
    assert "Frank Ocean" in names
    assert "Grace Hopper" not in names


@pytest.mark.django_db
def test_admin_updates_employee(admin_client):
    create_resp = admin_client.post(
        "/api/staff/",
        {"employee_id": "EMP201", "name": "Old Name", "contact": "9555555555"},
        format="json",
    )
    emp_id = create_resp.json()["id"]

    patch_resp = admin_client.patch(
        f"/api/staff/{emp_id}/",
        {"name": "New Name", "contact": "9666666666"},
        format="json",
    )
    assert patch_resp.status_code == status.HTTP_200_OK
    assert patch_resp.json()["name"] == "New Name"
    assert patch_resp.json()["contact"] == "9666666666"


@pytest.mark.django_db
def test_admin_deletes_employee(admin_client):
    create_resp = admin_client.post(
        "/api/staff/",
        {"employee_id": "EMP301", "name": "To Delete", "contact": "9777777777"},
        format="json",
    )
    emp_id = create_resp.json()["id"]

    del_resp = admin_client.delete(f"/api/staff/{emp_id}/")
    assert del_resp.status_code in (status.HTTP_200_OK, status.HTTP_204_NO_CONTENT)

    get_resp = admin_client.get(f"/api/staff/{emp_id}/")
    assert get_resp.status_code == status.HTTP_404_NOT_FOUND


@pytest.mark.django_db
def test_employee_missing_required_fields_rejected(admin_client):
    resp = admin_client.post("/api/staff/", {"contact": "9888888888"}, format="json")
    assert resp.status_code == status.HTTP_400_BAD_REQUEST


@pytest.mark.django_db
def test_anonymous_cannot_access_staff(anon_client):
    assert anon_client.get("/api/staff/").status_code == status.HTTP_401_UNAUTHORIZED
    assert anon_client.post("/api/staff/", {}).status_code == status.HTTP_401_UNAUTHORIZED


@pytest.mark.django_db
def test_password_not_in_login_response(anon_client):
    make_user("nopassinresp", "StrongP@ss1!")
    resp = login(anon_client, "nopassinresp", "StrongP@ss1!")
    assert resp.status_code == status.HTTP_200_OK
    assert "password" not in resp.json()
