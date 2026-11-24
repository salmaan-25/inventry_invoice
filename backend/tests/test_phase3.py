"""
Phase 3 tests — Customers.

All tests run against the real PostgreSQL database (pytest-django with
DJANGO_SETTINGS_MODULE=config.settings.development, as configured in
pytest.ini).

Test groups:
    1. Create
    2. Code generation (uniqueness + sequential)
    3. Concurrent code generation
    4. Validation (name, phone, GSTIN, state)
    5. List / search / filter
    6. Detail / PATCH
    7. Ordering
    8. Pagination shape
    9. No DELETE endpoint
    10. Auth
"""

import threading

import pytest
from django.urls import reverse
from rest_framework import status

from apps.customers.models import Customer, CustomerCodeCounter

LIST_URL = "/api/customers/"


def detail_url(pk: int) -> str:
    return f"/api/customers/{pk}/"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_customer(admin_client, **kwargs):
    payload = {"name": "Test Customer", **kwargs}
    resp = admin_client.post(LIST_URL, payload, format="json")
    assert resp.status_code == status.HTTP_201_CREATED, resp.data
    return resp.data


# ===========================================================================
# 1. Create
# ===========================================================================

@pytest.mark.django_db(transaction=True)
def test_create_customer_minimal(admin_client):
    """Create with only the required `name` field."""
    resp = admin_client.post(LIST_URL, {"name": "Alpha Corp"}, format="json")
    assert resp.status_code == status.HTTP_201_CREATED
    data = resp.data
    assert data["name"] == "Alpha Corp"
    assert data["code"].startswith("C")
    assert len(data["code"]) == 5  # C + 4 digits
    assert data["is_active"] is True
    assert data["phone"] == ""
    assert data["gstin"] == ""
    assert data["state"] == ""
    assert data["billing_address"] == ""


@pytest.mark.django_db(transaction=True)
def test_create_customer_full(admin_client):
    """Create with all optional fields."""
    payload = {
        "name": "Beta Ltd",
        "phone": "+91 98765-43210",
        "gstin": "29ABCDE1234F1Z5",
        "state": "Karnataka",
        "billing_address": "123 MG Road, Bengaluru",
    }
    resp = admin_client.post(LIST_URL, payload, format="json")
    assert resp.status_code == status.HTTP_201_CREATED
    data = resp.data
    assert data["name"] == "Beta Ltd"
    # phone is stored cleaned (spaces/hyphens stripped)
    assert data["phone"] == "+919876543210"
    assert data["gstin"] == "29ABCDE1234F1Z5"
    assert data["state"] == "Karnataka"
    assert data["billing_address"] == "123 MG Road, Bengaluru"


@pytest.mark.django_db(transaction=True)
def test_create_customer_staff_allowed(staff_client):
    """Staff users can also create customers."""
    resp = staff_client.post(LIST_URL, {"name": "Gamma Inc"}, format="json")
    assert resp.status_code == status.HTTP_201_CREATED


@pytest.mark.django_db(transaction=True)
def test_create_customer_code_is_read_only(admin_client):
    """Supplying a code in the request body must be ignored."""
    resp = admin_client.post(LIST_URL, {"name": "Delta Co", "code": "C9999"}, format="json")
    assert resp.status_code == status.HTTP_201_CREATED
    assert resp.data["code"] != "C9999"


# ===========================================================================
# 2. Code generation
# ===========================================================================

@pytest.mark.django_db(transaction=True)
def test_codes_are_sequential(admin_client):
    """First customer gets C0001, second gets C0002."""
    # Reset counter to 1 (clean slate for this test)
    CustomerCodeCounter.objects.filter(pk=1).delete()
    CustomerCodeCounter.objects.create(pk=1, next_value=1)
    Customer.objects.all().delete()

    r1 = admin_client.post(LIST_URL, {"name": "First"}, format="json")
    r2 = admin_client.post(LIST_URL, {"name": "Second"}, format="json")
    assert r1.data["code"] == "C0001"
    assert r2.data["code"] == "C0002"


@pytest.mark.django_db(transaction=True)
def test_codes_are_unique(admin_client):
    """All created codes are unique."""
    codes = [make_customer(admin_client, name=f"Customer {i}")["code"] for i in range(5)]
    assert len(codes) == len(set(codes))


# ===========================================================================
# 3. Concurrent code generation
# ===========================================================================

@pytest.mark.django_db(transaction=True)
def test_concurrent_code_generation(admin_client):
    """
    Ten threads each create a customer concurrently.
    All resulting codes must be unique.
    """
    # Ensure the counter singleton exists
    CustomerCodeCounter.objects.get_or_create(pk=1, defaults={"next_value": 1})

    errors = []
    codes = []
    lock = threading.Lock()

    def create_one(index):
        from django.test import Client
        from apps.accounts.models import User

        # Each thread needs its own authenticated client
        try:
            user = User.objects.filter(role="ADMIN").first()
            c = Client()
            c.force_login(user)
            resp = c.post(
                LIST_URL,
                data=f'{{"name": "Concurrent {index}"}}',
                content_type="application/json",
            )
            if resp.status_code == 201:
                import json
                data = json.loads(resp.content)
                with lock:
                    codes.append(data["code"])
            else:
                with lock:
                    errors.append(f"Thread {index}: {resp.status_code}")
        except Exception as exc:
            with lock:
                errors.append(str(exc))

    threads = [threading.Thread(target=create_one, args=(i,)) for i in range(10)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert not errors, f"Errors during concurrent creation: {errors}"
    assert len(codes) == 10
    assert len(set(codes)) == 10, f"Duplicate codes found: {codes}"


# ===========================================================================
# 4. Validation
# ===========================================================================

@pytest.mark.django_db(transaction=True)
def test_create_missing_name(admin_client):
    resp = admin_client.post(LIST_URL, {}, format="json")
    assert resp.status_code == status.HTTP_400_BAD_REQUEST
    # Custom exception handler wraps field errors under resp.data["fields"]
    assert "name" in resp.data.get("fields", resp.data)


@pytest.mark.django_db(transaction=True)
@pytest.mark.parametrize("bad_phone", [
    "123",           # too short
    "abcdefghij",    # letters
    "12345678901234567",  # too long (>15 digits)
])
def test_create_bad_phone(admin_client, bad_phone):
    resp = admin_client.post(
        LIST_URL, {"name": "X", "phone": bad_phone}, format="json"
    )
    assert resp.status_code == status.HTTP_400_BAD_REQUEST
    # Custom exception handler wraps field errors under resp.data["fields"]
    assert "phone" in resp.data.get("fields", resp.data)


@pytest.mark.django_db(transaction=True)
@pytest.mark.parametrize("good_phone", [
    "9876543210",          # 10 digits
    "+919876543210",       # with country code
    "+91 98765-43210",     # with spaces and hyphens
    "123456789012345",     # 15 digits
])
def test_create_valid_phone(admin_client, good_phone):
    resp = admin_client.post(
        LIST_URL, {"name": "PhoneTest", "phone": good_phone}, format="json"
    )
    assert resp.status_code == status.HTTP_201_CREATED


@pytest.mark.django_db(transaction=True)
def test_create_bad_gstin(admin_client):
    resp = admin_client.post(
        LIST_URL, {"name": "X", "gstin": "INVALID"}, format="json"
    )
    assert resp.status_code == status.HTTP_400_BAD_REQUEST
    assert "gstin" in resp.data.get("fields", resp.data)


@pytest.mark.django_db(transaction=True)
def test_create_valid_gstin(admin_client):
    resp = admin_client.post(
        LIST_URL, {"name": "X", "gstin": "29ABCDE1234F1Z5"}, format="json"
    )
    assert resp.status_code == status.HTTP_201_CREATED


@pytest.mark.django_db(transaction=True)
def test_create_bad_state(admin_client):
    resp = admin_client.post(
        LIST_URL, {"name": "X", "state": "Neverland"}, format="json"
    )
    assert resp.status_code == status.HTTP_400_BAD_REQUEST
    assert "state" in resp.data.get("fields", resp.data)


@pytest.mark.django_db(transaction=True)
@pytest.mark.parametrize("state", ["Karnataka", "Tamil Nadu", "Delhi", "Puducherry"])
def test_create_valid_state(admin_client, state):
    resp = admin_client.post(
        LIST_URL, {"name": "StateTest", "state": state}, format="json"
    )
    assert resp.status_code == status.HTTP_201_CREATED


# ===========================================================================
# 5. List / search / filter
# ===========================================================================

@pytest.mark.django_db(transaction=True)
def test_list_all(admin_client):
    make_customer(admin_client, name="Zeta")
    make_customer(admin_client, name="Alpha")
    resp = admin_client.get(LIST_URL)
    assert resp.status_code == status.HTTP_200_OK
    assert resp.data["count"] >= 2


@pytest.mark.django_db(transaction=True)
def test_search_by_name_case_insensitive(admin_client):
    make_customer(admin_client, name="Wonderful Widgets")
    resp = admin_client.get(LIST_URL, {"search": "wonderful"})
    assert resp.status_code == status.HTTP_200_OK
    names = [c["name"] for c in resp.data["results"]]
    assert "Wonderful Widgets" in names


@pytest.mark.django_db(transaction=True)
def test_search_by_phone(admin_client):
    make_customer(admin_client, name="Phone Co", phone="9000011111")
    resp = admin_client.get(LIST_URL, {"search": "9000011111"})
    assert resp.status_code == status.HTTP_200_OK
    assert any(c["phone"] == "9000011111" for c in resp.data["results"])


@pytest.mark.django_db(transaction=True)
def test_search_by_code(admin_client):
    data = make_customer(admin_client, name="Code Searcher")
    code = data["code"]
    resp = admin_client.get(LIST_URL, {"search": code})
    assert resp.status_code == status.HTTP_200_OK
    codes = [c["code"] for c in resp.data["results"]]
    assert code in codes


@pytest.mark.django_db(transaction=True)
def test_filter_is_active_true(admin_client):
    make_customer(admin_client, name="Active One")
    inactive_data = make_customer(admin_client, name="Inactive One")
    admin_client.patch(
        detail_url(inactive_data["id"]),
        {"is_active": False},
        format="json",
    )
    resp = admin_client.get(LIST_URL, {"is_active": "true"})
    assert resp.status_code == status.HTTP_200_OK
    statuses = [c["is_active"] for c in resp.data["results"]]
    assert all(statuses)
    assert False not in statuses


@pytest.mark.django_db(transaction=True)
def test_filter_is_active_false(admin_client):
    make_customer(admin_client, name="Active Two")
    inactive_data = make_customer(admin_client, name="Inactive Two")
    admin_client.patch(
        detail_url(inactive_data["id"]),
        {"is_active": False},
        format="json",
    )
    resp = admin_client.get(LIST_URL, {"is_active": "false"})
    assert resp.status_code == status.HTTP_200_OK
    statuses = [c["is_active"] for c in resp.data["results"]]
    assert all(s is False for s in statuses)


# ===========================================================================
# 6. Detail / PATCH
# ===========================================================================

@pytest.mark.django_db(transaction=True)
def test_detail_retrieve(admin_client):
    data = make_customer(admin_client, name="Detail Test")
    resp = admin_client.get(detail_url(data["id"]))
    assert resp.status_code == status.HTTP_200_OK
    assert resp.data["id"] == data["id"]


@pytest.mark.django_db(transaction=True)
def test_patch_name(admin_client):
    data = make_customer(admin_client, name="Old Name")
    resp = admin_client.patch(
        detail_url(data["id"]), {"name": "New Name"}, format="json"
    )
    assert resp.status_code == status.HTTP_200_OK
    assert resp.data["name"] == "New Name"


@pytest.mark.django_db(transaction=True)
def test_deactivate_customer(admin_client):
    data = make_customer(admin_client, name="To Deactivate")
    resp = admin_client.patch(
        detail_url(data["id"]), {"is_active": False}, format="json"
    )
    assert resp.status_code == status.HTTP_200_OK
    assert resp.data["is_active"] is False


@pytest.mark.django_db(transaction=True)
def test_inactive_customer_still_retrievable(admin_client):
    data = make_customer(admin_client, name="Inactive But Retrievable")
    admin_client.patch(detail_url(data["id"]), {"is_active": False}, format="json")
    resp = admin_client.get(detail_url(data["id"]))
    assert resp.status_code == status.HTTP_200_OK
    assert resp.data["is_active"] is False


@pytest.mark.django_db(transaction=True)
def test_patch_code_is_ignored(admin_client):
    """PATCH must not allow changing the code."""
    data = make_customer(admin_client, name="Code Guard")
    original_code = data["code"]
    resp = admin_client.patch(
        detail_url(data["id"]), {"code": "C9999"}, format="json"
    )
    assert resp.status_code == status.HTTP_200_OK
    assert resp.data["code"] == original_code


@pytest.mark.django_db(transaction=True)
def test_patch_put_not_allowed(admin_client):
    data = make_customer(admin_client, name="No Put")
    resp = admin_client.put(detail_url(data["id"]), {"name": "X"}, format="json")
    assert resp.status_code == status.HTTP_405_METHOD_NOT_ALLOWED


# ===========================================================================
# 7. Ordering
# ===========================================================================

@pytest.mark.django_db(transaction=True)
def test_default_ordering_by_name(admin_client):
    """Results must arrive sorted by name ascending."""
    Customer.objects.all().delete()
    for name in ["Zorro", "Alpha", "Mike"]:
        make_customer(admin_client, name=name)
    resp = admin_client.get(LIST_URL)
    assert resp.status_code == status.HTTP_200_OK
    names = [c["name"] for c in resp.data["results"]]
    assert names == sorted(names)


# ===========================================================================
# 8. Pagination shape
# ===========================================================================

@pytest.mark.django_db(transaction=True)
def test_pagination_shape(admin_client):
    resp = admin_client.get(LIST_URL)
    assert resp.status_code == status.HTTP_200_OK
    assert "count" in resp.data
    assert "results" in resp.data


# ===========================================================================
# 9. No DELETE
# ===========================================================================

@pytest.mark.django_db(transaction=True)
def test_delete_not_allowed(admin_client):
    data = make_customer(admin_client, name="No Delete")
    resp = admin_client.delete(detail_url(data["id"]))
    assert resp.status_code == status.HTTP_405_METHOD_NOT_ALLOWED


@pytest.mark.django_db(transaction=True)
def test_delete_list_not_allowed(admin_client):
    resp = admin_client.delete(LIST_URL)
    assert resp.status_code == status.HTTP_405_METHOD_NOT_ALLOWED


# ===========================================================================
# 10. Auth
# ===========================================================================

@pytest.mark.django_db(transaction=True)
def test_anonymous_list_returns_401(anon_client):
    resp = anon_client.get(LIST_URL)
    assert resp.status_code == status.HTTP_401_UNAUTHORIZED


@pytest.mark.django_db(transaction=True)
def test_anonymous_create_returns_401(anon_client):
    resp = anon_client.post(LIST_URL, {"name": "Anon"}, format="json")
    assert resp.status_code == status.HTTP_401_UNAUTHORIZED


@pytest.mark.django_db(transaction=True)
def test_anonymous_detail_returns_401(admin_client, anon_client):
    data = make_customer(admin_client, name="Auth Test")
    resp = anon_client.get(detail_url(data["id"]))
    assert resp.status_code == status.HTTP_401_UNAUTHORIZED
