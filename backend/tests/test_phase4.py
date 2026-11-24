"""
Phase 4 tests — Products and inventory.

Test groups:
    1. Units
    2. Product creation and each item type
    3. Product codes
    4. Validation
    5. Search and filters
    6. Detail and PATCH
    7. Item-type change rules
    8. Stock-in
    9. Adjustment
    10. Concurrent stock changes
    11. Stock movement list
    12. check_stock_consistency
    13. Authentication and permissions
    14. Response formats and pagination
"""

import json
import threading
from decimal import Decimal

import pytest
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import Client
from django.utils import timezone
from rest_framework import status

from apps.accounts.models import User
from apps.common.constants import MovementType
from apps.inventory.models import StockMovement
from apps.products.models import Product, ProductCodeCounter, Unit

PRODUCTS_URL = "/api/products/"
UNITS_URL = "/api/units/"
MOVEMENTS_URL = "/api/stock-movements/"

SEEDED_UNITS = [
    "pcs",
    "bag",
    "kg",
    "litre",
    "box",
    "trip",
    "metre",
    "foot",
    "set",
    "pair",
    "roll",
]

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def reference_data(db):
    """Re-create migrated reference rows after a transaction=True flush."""
    for name in SEEDED_UNITS:
        Unit.objects.get_or_create(name=name)
    ProductCodeCounter.objects.get_or_create(
        pk=1,
        defaults={"next_value": 1},
    )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def detail_url(pk: int) -> str:
    return f"{PRODUCTS_URL}{pk}/"


def stock_in_url(pk: int) -> str:
    return f"{PRODUCTS_URL}{pk}/stock-in/"


def adjust_url(pk: int) -> str:
    return f"{PRODUCTS_URL}{pk}/adjust/"


def get_unit(name: str = "pcs") -> Unit:
    return Unit.objects.get(name=name)


def make_product(client, **overrides):
    payload = {
        "name": "Test Product",
        "item_type": "GOODS",
        "unit": get_unit().id,
        "selling_price": "100.00",
    }
    payload.update(overrides)
    resp = client.post(PRODUCTS_URL, payload, format="json")
    assert resp.status_code == status.HTTP_201_CREATED, resp.data
    return resp.data


# ===========================================================================
# 1. Units
# ===========================================================================

def test_units_are_seeded_and_listed(admin_client):
    resp = admin_client.get(UNITS_URL)
    assert resp.status_code == status.HTTP_200_OK
    assert resp.data["count"] == len(SEEDED_UNITS)
    names = {unit["name"] for unit in resp.data["results"]}
    assert names == set(SEEDED_UNITS)


def test_units_list_is_paginated(admin_client):
    resp = admin_client.get(UNITS_URL)
    assert set(resp.data) == {"count", "next", "previous", "results"}


def test_units_staff_can_read(staff_client):
    resp = staff_client.get(UNITS_URL)
    assert resp.status_code == status.HTTP_200_OK


# ===========================================================================
# 2. Product creation and each item type
# ===========================================================================

def test_create_goods_product_without_opening_stock(admin_client):
    data = make_product(admin_client, name="Plain Goods")
    assert data["item_type"] == "GOODS"
    assert data["tracks_stock"] is True
    assert data["current_stock"] == "0.000"
    assert data["is_low_stock"] is False
    assert data["code"].startswith("P")
    assert StockMovement.objects.filter(product_id=data["id"]).count() == 0


def test_create_goods_product_with_opening_stock(admin_client):
    data = make_product(
        admin_client,
        name="Opening Goods",
        opening_stock="10.500",
    )
    assert data["current_stock"] == "10.500"

    movement = StockMovement.objects.get(product_id=data["id"])
    assert movement.movement_type == MovementType.OPENING
    assert movement.quantity_change == Decimal("10.500")
    assert movement.balance_after == Decimal("10.500")
    assert movement.reason == "Opening stock"
    assert movement.created_by == User.objects.get(username="admin")


def test_create_goods_hardware_tracks_stock(admin_client):
    data = make_product(
        admin_client,
        name="Hardware",
        item_type="GOODS_HARDWARE",
        opening_stock="2.000",
    )
    assert data["item_type"] == "GOODS_HARDWARE"
    assert data["tracks_stock"] is True
    assert data["current_stock"] == "2.000"
    assert StockMovement.objects.filter(
        product_id=data["id"],
        movement_type=MovementType.OPENING,
    ).exists()


def test_create_service_does_not_track_stock(admin_client):
    data = make_product(
        admin_client,
        name="Consulting",
        item_type="SERVICE",
    )
    assert data["tracks_stock"] is False
    assert data["current_stock"] == "0.000"
    assert data["is_low_stock"] is False
    assert StockMovement.objects.filter(product_id=data["id"]).count() == 0


@pytest.mark.parametrize("opening_stock", ["0", "0.000", "5.000"])
def test_service_rejects_opening_stock(admin_client, opening_stock):
    resp = admin_client.post(
        PRODUCTS_URL,
        {
            "name": "Service With Stock",
            "item_type": "SERVICE",
            "unit": get_unit().id,
            "selling_price": "10.00",
            "opening_stock": opening_stock,
        },
        format="json",
    )
    assert resp.status_code == status.HTTP_400_BAD_REQUEST
    assert "opening_stock" in resp.data["fields"]


def test_service_rejects_reorder_level(admin_client):
    resp = admin_client.post(
        PRODUCTS_URL,
        {
            "name": "Service With Reorder",
            "item_type": "SERVICE",
            "unit": get_unit().id,
            "selling_price": "10.00",
            "reorder_level": "5.000",
        },
        format="json",
    )
    assert resp.status_code == status.HTTP_400_BAD_REQUEST
    assert "reorder_level" in resp.data["fields"]


def test_low_stock_flag_on_create(admin_client):
    at_level = make_product(
        admin_client,
        name="At Reorder",
        opening_stock="5.000",
        reorder_level="5.000",
    )
    above_level = make_product(
        admin_client,
        name="Above Reorder",
        opening_stock="6.000",
        reorder_level="5.000",
    )
    assert at_level["is_low_stock"] is True
    assert above_level["is_low_stock"] is False


# ===========================================================================
# 3. Product codes
# ===========================================================================

def test_codes_are_sequential(admin_client):
    ProductCodeCounter.objects.update_or_create(
        pk=1,
        defaults={"next_value": 1},
    )
    Product.objects.all().delete()

    first = make_product(admin_client, name="First")
    second = make_product(admin_client, name="Second")
    assert first["code"] == "P0001"
    assert second["code"] == "P0002"


def test_custom_code_is_accepted(admin_client):
    data = make_product(admin_client, name="Custom", code="SKU-ABC")
    assert data["code"] == "SKU-ABC"


def test_blank_code_is_generated(admin_client):
    data = make_product(admin_client, name="Blank Code", code="")
    assert data["code"].startswith("P")


def test_duplicate_code_rejected(admin_client):
    make_product(admin_client, name="First Code", code="DUPLICATE")
    resp = admin_client.post(
        PRODUCTS_URL,
        {
            "name": "Second Code",
            "item_type": "GOODS",
            "unit": get_unit().id,
            "selling_price": "10.00",
            "code": "DUPLICATE",
        },
        format="json",
    )
    assert resp.status_code == status.HTTP_400_BAD_REQUEST
    assert "code" in resp.data["fields"]


# ===========================================================================
# 4. Validation
# ===========================================================================

def test_missing_name(admin_client):
    resp = admin_client.post(
        PRODUCTS_URL,
        {
            "item_type": "GOODS",
            "unit": get_unit().id,
            "selling_price": "1.00",
        },
        format="json",
    )
    assert resp.status_code == status.HTTP_400_BAD_REQUEST
    assert "name" in resp.data["fields"]


def test_missing_unit(admin_client):
    resp = admin_client.post(
        PRODUCTS_URL,
        {
            "name": "No Unit",
            "item_type": "GOODS",
            "selling_price": "1.00",
        },
        format="json",
    )
    assert resp.status_code == status.HTTP_400_BAD_REQUEST
    assert "unit" in resp.data["fields"]


def test_missing_item_type(admin_client):
    resp = admin_client.post(
        PRODUCTS_URL,
        {
            "name": "No Type",
            "unit": get_unit().id,
            "selling_price": "1.00",
        },
        format="json",
    )
    assert resp.status_code == status.HTTP_400_BAD_REQUEST
    assert "item_type" in resp.data["fields"]


def test_invalid_item_type(admin_client):
    resp = admin_client.post(
        PRODUCTS_URL,
        {
            "name": "Bad Type",
            "item_type": "RAW_MATERIAL",
            "unit": get_unit().id,
            "selling_price": "1.00",
        },
        format="json",
    )
    assert resp.status_code == status.HTTP_400_BAD_REQUEST
    assert "item_type" in resp.data["fields"]


def test_negative_selling_price_rejected(admin_client):
    resp = admin_client.post(
        PRODUCTS_URL,
        {
            "name": "Negative Price",
            "item_type": "GOODS",
            "unit": get_unit().id,
            "selling_price": "-1.00",
        },
        format="json",
    )
    assert resp.status_code == status.HTTP_400_BAD_REQUEST
    assert "selling_price" in resp.data["fields"]


@pytest.mark.parametrize("gst_rate", ["-1.00", "100.01", "101.00"])
def test_invalid_gst_rate_rejected(admin_client, gst_rate):
    resp = admin_client.post(
        PRODUCTS_URL,
        {
            "name": "Bad GST",
            "item_type": "GOODS",
            "unit": get_unit().id,
            "selling_price": "1.00",
            "gst_rate": gst_rate,
        },
        format="json",
    )
    assert resp.status_code == status.HTTP_400_BAD_REQUEST
    assert "gst_rate" in resp.data["fields"]


def test_valid_gst_rate_accepted(admin_client):
    data = make_product(admin_client, name="GST Product", gst_rate="18.00")
    assert data["gst_rate"] == "18.00"


def test_negative_reorder_level_rejected(admin_client):
    resp = admin_client.post(
        PRODUCTS_URL,
        {
            "name": "Bad Reorder",
            "item_type": "GOODS",
            "unit": get_unit().id,
            "selling_price": "1.00",
            "reorder_level": "-0.001",
        },
        format="json",
    )
    assert resp.status_code == status.HTTP_400_BAD_REQUEST
    assert "reorder_level" in resp.data["fields"]


def test_negative_opening_stock_rejected(admin_client):
    resp = admin_client.post(
        PRODUCTS_URL,
        {
            "name": "Bad Opening",
            "item_type": "GOODS",
            "unit": get_unit().id,
            "selling_price": "1.00",
            "opening_stock": "-1.000",
        },
        format="json",
    )
    assert resp.status_code == status.HTTP_400_BAD_REQUEST
    assert "opening_stock" in resp.data["fields"]


# ===========================================================================
# 5. Search and filters
# ===========================================================================

def test_search_by_name_case_insensitive(admin_client):
    make_product(admin_client, name="Wonderful Widget")
    resp = admin_client.get(PRODUCTS_URL, {"search": "wonderful"})
    assert resp.status_code == status.HTTP_200_OK
    names = [p["name"] for p in resp.data["results"]]
    assert "Wonderful Widget" in names


def test_search_by_code(admin_client):
    data = make_product(admin_client, name="Code Search", code="SEARCH-1")
    resp = admin_client.get(PRODUCTS_URL, {"search": "search-1"})
    assert resp.status_code == status.HTTP_200_OK
    codes = [p["code"] for p in resp.data["results"]]
    assert data["code"] in codes


def test_item_type_filter(admin_client):
    make_product(admin_client, name="Goods One", item_type="GOODS")
    make_product(admin_client, name="Hardware One", item_type="GOODS_HARDWARE")
    make_product(admin_client, name="Service One", item_type="SERVICE")

    resp = admin_client.get(PRODUCTS_URL, {"item_type": "GOODS_HARDWARE"})
    assert resp.status_code == status.HTTP_200_OK
    assert [p["item_type"] for p in resp.data["results"]] == ["GOODS_HARDWARE"]


def test_search_and_item_type_filters_combine(admin_client):
    make_product(admin_client, name="Blue Widget", item_type="GOODS")
    make_product(admin_client, name="Blue Service", item_type="SERVICE")
    make_product(admin_client, name="Red Widget", item_type="GOODS")

    resp = admin_client.get(
        PRODUCTS_URL,
        {"search": "blue", "item_type": "GOODS"},
    )
    assert resp.status_code == status.HTTP_200_OK
    names = [p["name"] for p in resp.data["results"]]
    assert names == ["Blue Widget"]


def test_is_active_filter(admin_client):
    active = make_product(admin_client, name="Active Product")
    inactive = make_product(admin_client, name="Inactive Product")
    admin_client.patch(
        detail_url(inactive["id"]),
        {"is_active": False},
        format="json",
    )

    resp = admin_client.get(PRODUCTS_URL, {"is_active": "false"})
    assert resp.status_code == status.HTTP_200_OK
    ids = [p["id"] for p in resp.data["results"]]
    assert inactive["id"] in ids
    assert active["id"] not in ids


def test_low_stock_filter(admin_client):
    low = make_product(
        admin_client,
        name="Low Stock",
        opening_stock="2.000",
        reorder_level="5.000",
    )
    at_level = make_product(
        admin_client,
        name="At Level",
        opening_stock="5.000",
        reorder_level="5.000",
    )
    healthy = make_product(
        admin_client,
        name="Healthy",
        opening_stock="10.000",
        reorder_level="5.000",
    )
    no_reorder = make_product(admin_client, name="No Reorder")
    make_product(admin_client, name="Service Item", item_type="SERVICE")

    resp = admin_client.get(PRODUCTS_URL, {"low_stock": "true"})
    assert resp.status_code == status.HTTP_200_OK
    ids = {p["id"] for p in resp.data["results"]}
    assert low["id"] in ids
    assert at_level["id"] in ids
    assert healthy["id"] not in ids
    assert no_reorder["id"] not in ids
    assert all(p["tracks_stock"] for p in resp.data["results"])


def test_default_ordering_by_name(admin_client):
    make_product(admin_client, name="Zulu Product")
    make_product(admin_client, name="Alpha Product")
    make_product(admin_client, name="Mike Product")

    resp = admin_client.get(PRODUCTS_URL)
    names = [p["name"] for p in resp.data["results"]]
    assert names == sorted(names)


# ===========================================================================
# 6. Detail and PATCH
# ===========================================================================

def test_product_detail(admin_client):
    data = make_product(admin_client, name="Detail Product")
    resp = admin_client.get(detail_url(data["id"]))
    assert resp.status_code == status.HTTP_200_OK
    assert resp.data["id"] == data["id"]


def test_patch_does_not_change_stock(admin_client):
    data = make_product(admin_client, name="Patch Product", opening_stock="10.000")
    resp = admin_client.patch(
        detail_url(data["id"]),
        {
            "name": "Patched Product",
            "selling_price": "250.50",
            "current_stock": "999.000",
            "is_active": False,
        },
        format="json",
    )
    assert resp.status_code == status.HTTP_200_OK
    assert resp.data["name"] == "Patched Product"
    assert resp.data["selling_price"] == "250.50"
    assert resp.data["current_stock"] == "10.000"
    assert resp.data["is_active"] is False


def test_patch_opening_stock_rejected(admin_client):
    data = make_product(admin_client, name="No Opening Patch")
    resp = admin_client.patch(
        detail_url(data["id"]),
        {"opening_stock": "5.000"},
        format="json",
    )
    assert resp.status_code == status.HTTP_400_BAD_REQUEST
    assert "opening_stock" in resp.data["fields"]


def test_put_and_delete_not_allowed(admin_client):
    data = make_product(admin_client, name="No Put Delete")
    put_resp = admin_client.put(
        detail_url(data["id"]),
        {"name": "Changed"},
        format="json",
    )
    delete_resp = admin_client.delete(detail_url(data["id"]))
    assert put_resp.status_code == status.HTTP_405_METHOD_NOT_ALLOWED
    assert delete_resp.status_code == status.HTTP_405_METHOD_NOT_ALLOWED


def test_inactive_product_still_retrievable(admin_client):
    data = make_product(admin_client, name="Inactive Detail")
    admin_client.patch(
        detail_url(data["id"]),
        {"is_active": False},
        format="json",
    )
    resp = admin_client.get(detail_url(data["id"]))
    assert resp.status_code == status.HTTP_200_OK
    assert resp.data["is_active"] is False


# ===========================================================================
# 7. Item-type change rules
# ===========================================================================

def test_goods_to_hardware_allowed_after_movements(admin_client):
    data = make_product(admin_client, name="Switch Goods", opening_stock="4.000")
    resp = admin_client.patch(
        detail_url(data["id"]),
        {"item_type": "GOODS_HARDWARE"},
        format="json",
    )
    assert resp.status_code == status.HTTP_200_OK
    assert resp.data["item_type"] == "GOODS_HARDWARE"
    assert resp.data["current_stock"] == "4.000"


def test_goods_to_service_rejected_after_movements(admin_client):
    data = make_product(admin_client, name="Cannot Service", opening_stock="4.000")
    resp = admin_client.patch(
        detail_url(data["id"]),
        {"item_type": "SERVICE", "reorder_level": None},
        format="json",
    )
    assert resp.status_code == status.HTTP_400_BAD_REQUEST
    assert "item_type" in resp.data["fields"]


def test_service_to_goods_allowed_without_movements(admin_client):
    data = make_product(
        admin_client,
        name="Service To Goods",
        item_type="SERVICE",
    )
    resp = admin_client.patch(
        detail_url(data["id"]),
        {"item_type": "GOODS", "reorder_level": "5.000"},
        format="json",
    )
    assert resp.status_code == status.HTTP_200_OK
    assert resp.data["item_type"] == "GOODS"
    assert resp.data["tracks_stock"] is True
    assert resp.data["is_low_stock"] is True


def test_goods_to_service_allowed_without_movements(admin_client):
    data = make_product(admin_client, name="Goods To Service")
    resp = admin_client.patch(
        detail_url(data["id"]),
        {"item_type": "SERVICE"},
        format="json",
    )
    assert resp.status_code == status.HTTP_200_OK
    assert resp.data["item_type"] == "SERVICE"
    assert resp.data["tracks_stock"] is False


def test_service_rejects_reorder_level_on_patch(admin_client):
    data = make_product(
        admin_client,
        name="Service Patch Reorder",
        item_type="SERVICE",
    )
    resp = admin_client.patch(
        detail_url(data["id"]),
        {"reorder_level": "1.000"},
        format="json",
    )
    assert resp.status_code == status.HTTP_400_BAD_REQUEST
    assert "reorder_level" in resp.data["fields"]


# ===========================================================================
# 8. Stock-in
# ===========================================================================

def test_stock_in_increases_stock_and_creates_movement(admin_client):
    data = make_product(admin_client, name="Stock In", opening_stock="10.000")
    resp = admin_client.post(
        stock_in_url(data["id"]),
        {"quantity": "5.500", "reason": "Received"},
        format="json",
    )
    assert resp.status_code == status.HTTP_200_OK
    assert resp.data["current_stock"] == "15.500"

    movement = StockMovement.objects.filter(
        product_id=data["id"],
        movement_type=MovementType.STOCK_IN,
    ).get()
    assert movement.quantity_change == Decimal("5.500")
    assert movement.balance_after == Decimal("15.500")
    assert movement.reason == "Received"


def test_stock_in_reason_is_optional(admin_client):
    data = make_product(admin_client, name="Stock In No Reason")
    resp = admin_client.post(
        stock_in_url(data["id"]),
        {"quantity": "1.000"},
        format="json",
    )
    assert resp.status_code == status.HTTP_200_OK
    movement = StockMovement.objects.get(
        product_id=data["id"],
        movement_type=MovementType.STOCK_IN,
    )
    assert movement.reason == ""


@pytest.mark.parametrize("quantity", ["0", "0.000", "-1.000"])
def test_stock_in_rejects_zero_or_negative(admin_client, quantity):
    data = make_product(admin_client, name="Bad Stock In")
    resp = admin_client.post(
        stock_in_url(data["id"]),
        {"quantity": quantity},
        format="json",
    )
    assert resp.status_code == status.HTTP_400_BAD_REQUEST
    assert "quantity" in resp.data["fields"]


def test_stock_in_service_rejected(admin_client):
    data = make_product(
        admin_client,
        name="Service Stock In",
        item_type="SERVICE",
    )
    resp = admin_client.post(
        stock_in_url(data["id"]),
        {"quantity": "1.000"},
        format="json",
    )
    assert resp.status_code == status.HTTP_400_BAD_REQUEST
    assert resp.data["code"] == "VALIDATION_ERROR"
    assert StockMovement.objects.filter(product_id=data["id"]).count() == 0


def test_stock_in_unknown_product(admin_client):
    resp = admin_client.post(
        stock_in_url(999999),
        {"quantity": "1.000"},
        format="json",
    )
    assert resp.status_code == status.HTTP_404_NOT_FOUND


# ===========================================================================
# 9. Adjustment
# ===========================================================================

def test_adjustment_up_and_down(admin_client):
    data = make_product(admin_client, name="Adjust", opening_stock="10.000")

    up = admin_client.post(
        adjust_url(data["id"]),
        {"quantity_change": "5.250", "reason": "Found stock"},
        format="json",
    )
    assert up.status_code == status.HTTP_200_OK
    assert up.data["current_stock"] == "15.250"

    down = admin_client.post(
        adjust_url(data["id"]),
        {"quantity_change": "-3.250", "reason": "Damage"},
        format="json",
    )
    assert down.status_code == status.HTTP_200_OK
    assert down.data["current_stock"] == "12.000"

    movements = StockMovement.objects.filter(
        product_id=data["id"],
        movement_type=MovementType.ADJUSTMENT,
    ).order_by("id")
    assert [m.quantity_change for m in movements] == [
        Decimal("5.250"),
        Decimal("-3.250"),
    ]
    assert [m.balance_after for m in movements] == [
        Decimal("15.250"),
        Decimal("12.000"),
    ]


def test_adjustment_zero_rejected(admin_client):
    data = make_product(admin_client, name="Zero Adjust")
    resp = admin_client.post(
        adjust_url(data["id"]),
        {"quantity_change": "0.000", "reason": "Nothing"},
        format="json",
    )
    assert resp.status_code == status.HTTP_400_BAD_REQUEST
    assert "quantity_change" in resp.data["fields"]


@pytest.mark.parametrize("payload", [{}, {"quantity_change": "-1.000"}])
def test_adjustment_reason_required(admin_client, payload):
    data = make_product(admin_client, name="No Reason")
    resp = admin_client.post(
        adjust_url(data["id"]),
        payload,
        format="json",
    )
    assert resp.status_code == status.HTTP_400_BAD_REQUEST
    assert "reason" in resp.data["fields"]


def test_adjustment_blank_reason_rejected(admin_client):
    data = make_product(admin_client, name="Blank Reason")
    resp = admin_client.post(
        adjust_url(data["id"]),
        {"quantity_change": "-1.000", "reason": "   "},
        format="json",
    )
    assert resp.status_code == status.HTTP_400_BAD_REQUEST
    assert "reason" in resp.data["fields"]


def test_adjustment_below_zero_rejected(admin_client):
    data = make_product(admin_client, name="Too Much Down", opening_stock="10.000")
    resp = admin_client.post(
        adjust_url(data["id"]),
        {"quantity_change": "-11.000", "reason": "Too much"},
        format="json",
    )
    assert resp.status_code == status.HTTP_409_CONFLICT
    assert resp.data["code"] == "INSUFFICIENT_STOCK"
    assert resp.data["details"][0]["product"] == data["id"]
    assert resp.data["details"][0]["available"] == "10.000"
    assert resp.data["details"][0]["required"] == "11.000"

    product = Product.objects.get(pk=data["id"])
    assert product.current_stock == Decimal("10.000")
    assert not StockMovement.objects.filter(
        product_id=data["id"],
        movement_type=MovementType.ADJUSTMENT,
    ).exists()


def test_adjustment_service_rejected(admin_client):
    data = make_product(
        admin_client,
        name="Service Adjust",
        item_type="SERVICE",
    )
    resp = admin_client.post(
        adjust_url(data["id"]),
        {"quantity_change": "1.000", "reason": "Nope"},
        format="json",
    )
    assert resp.status_code == status.HTTP_400_BAD_REQUEST
    assert resp.data["code"] == "VALIDATION_ERROR"


# ===========================================================================
# 10. Concurrent stock changes
# ===========================================================================

@pytest.mark.django_db(transaction=True)
def test_concurrent_adjustments_cannot_oversell(admin_client, admin_user):
    data = make_product(admin_client, name="Concurrent", opening_stock="10.000")

    statuses = []
    errors = []
    lock = threading.Lock()
    barrier = threading.Barrier(2)

    def adjust_one():
        from django.db import connection

        try:
            user = User.objects.get(pk=admin_user.pk)
            client = Client()
            client.force_login(user)
            barrier.wait()
            resp = client.post(
                adjust_url(data["id"]),
                data=json.dumps(
                    {"quantity_change": "-8.000", "reason": "Concurrent"}
                ),
                content_type="application/json",
            )
            with lock:
                statuses.append(resp.status_code)
        except Exception as exc:  # pragma: no cover - surfaced via assertion
            with lock:
                errors.append(str(exc))
        finally:
            connection.close()

    threads = [threading.Thread(target=adjust_one) for _ in range(2)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert not errors, errors
    assert sorted(statuses) == [
        status.HTTP_200_OK,
        status.HTTP_409_CONFLICT,
    ]

    product = Product.objects.get(pk=data["id"])
    assert product.current_stock == Decimal("2.000")
    assert StockMovement.objects.filter(
        product_id=data["id"],
        movement_type=MovementType.ADJUSTMENT,
    ).count() == 1


# ===========================================================================
# 11. Stock movement list
# ===========================================================================

def _make_movement_scenario(admin_client):
    data = make_product(admin_client, name="Ledger", opening_stock="10.000")
    admin_client.post(
        stock_in_url(data["id"]),
        {"quantity": "5.000", "reason": "Restock"},
        format="json",
    )
    admin_client.post(
        adjust_url(data["id"]),
        {"quantity_change": "-3.000", "reason": "Damage"},
        format="json",
    )
    return data


def test_stock_movement_list_and_filters(admin_client):
    data = _make_movement_scenario(admin_client)

    resp = admin_client.get(MOVEMENTS_URL)
    assert resp.status_code == status.HTTP_200_OK
    assert resp.data["count"] == 3
    # Newest first.
    assert resp.data["results"][0]["movement_type"] == MovementType.ADJUSTMENT

    by_product = admin_client.get(MOVEMENTS_URL, {"product": data["id"]})
    assert by_product.data["count"] == 3

    by_type = admin_client.get(
        MOVEMENTS_URL,
        {"movement_type": MovementType.OPENING},
    )
    assert by_type.data["count"] == 1
    assert by_type.data["results"][0]["quantity_change"] == "10.000"

    by_item_type = admin_client.get(MOVEMENTS_URL, {"item_type": "GOODS"})
    assert by_item_type.data["count"] == 3

    service = make_product(
        admin_client,
        name="No Movements Service",
        item_type="SERVICE",
    )
    service_movements = admin_client.get(
        MOVEMENTS_URL,
        {"item_type": "SERVICE"},
    )
    assert service_movements.data["count"] == 0
    assert service["id"] not in {
        m["product"] for m in service_movements.data["results"]
    }


def test_stock_movement_date_filter(admin_client):
    _make_movement_scenario(admin_client)
    today = timezone.localdate().isoformat()

    resp = admin_client.get(MOVEMENTS_URL, {"from": today, "to": today})
    assert resp.status_code == status.HTTP_200_OK
    assert resp.data["count"] == 3


def test_stock_movement_invalid_date_range(admin_client):
    resp = admin_client.get(
        MOVEMENTS_URL,
        {"from": "2026-02-02", "to": "2026-02-01"},
    )
    assert resp.status_code == status.HTTP_400_BAD_REQUEST
    assert resp.data["code"] == "INVALID_DATE_RANGE"


def test_stock_movement_requires_both_dates(admin_client):
    resp = admin_client.get(MOVEMENTS_URL, {"from": "2026-02-01"})
    assert resp.status_code == status.HTTP_400_BAD_REQUEST
    assert resp.data["code"] == "INVALID_DATE_RANGE"


def test_stock_movement_invalid_product_filter(admin_client):
    resp = admin_client.get(MOVEMENTS_URL, {"product": "abc"})
    assert resp.status_code == status.HTTP_400_BAD_REQUEST
    assert "product" in resp.data["fields"]


def test_stock_movement_list_paginated(admin_client):
    _make_movement_scenario(admin_client)
    resp = admin_client.get(MOVEMENTS_URL)
    assert set(resp.data) == {"count", "next", "previous", "results"}


# ===========================================================================
# 12. check_stock_consistency
# ===========================================================================

def test_check_stock_consistency_passes(admin_client, capsys):
    _make_movement_scenario(admin_client)
    call_command("check_stock_consistency")
    output = capsys.readouterr().out
    assert "passed" in output.lower()


def test_check_stock_consistency_detects_corruption(admin_client, capsys):
    data = make_product(admin_client, name="Corrupt", opening_stock="10.000")
    Product.objects.filter(pk=data["id"]).update(
        current_stock=Decimal("99.000")
    )

    with pytest.raises(CommandError):
        call_command("check_stock_consistency")

    captured = capsys.readouterr()
    assert "MISMATCH" in captured.err


# ===========================================================================
# 13. Authentication and permissions
# ===========================================================================

@pytest.mark.parametrize(
    "method,url",
    [
        ("get", UNITS_URL),
        ("get", PRODUCTS_URL),
        ("post", PRODUCTS_URL),
        ("get", MOVEMENTS_URL),
    ],
)
def test_anonymous_rejected(anon_client, method, url):
    resp = getattr(anon_client, method)(url)
    assert resp.status_code == status.HTTP_401_UNAUTHORIZED
    assert resp.data["code"] == "NOT_AUTHENTICATED"


def test_staff_can_create_and_change_stock(staff_client):
    data = make_product(
        staff_client,
        name="Staff Product",
        opening_stock="3.000",
    )
    stock_in = staff_client.post(
        stock_in_url(data["id"]),
        {"quantity": "2.000"},
        format="json",
    )
    adjust = staff_client.post(
        adjust_url(data["id"]),
        {"quantity_change": "-1.000", "reason": "Staff"},
        format="json",
    )
    assert stock_in.status_code == status.HTTP_200_OK
    assert adjust.status_code == status.HTTP_200_OK
    assert adjust.data["current_stock"] == "4.000"


# ===========================================================================
# 14. Response formats and pagination
# ===========================================================================

def test_decimal_output_formats(admin_client):
    data = make_product(
        admin_client,
        name="Format Product",
        selling_price="1250",
        opening_stock="10.5",
        gst_rate="18",
    )
    assert data["selling_price"] == "1250.00"
    assert data["current_stock"] == "10.500"
    assert data["gst_rate"] == "18.00"


def test_product_list_pagination_shape(admin_client):
    make_product(admin_client, name="Paginated Product")
    resp = admin_client.get(PRODUCTS_URL)
    assert set(resp.data) == {"count", "next", "previous", "results"}
