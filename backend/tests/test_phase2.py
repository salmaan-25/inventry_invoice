"""
Phase 2 tests — Settings (business details).

Covers the mandatory cases from the phase plan:
  - Exactly one record can exist.
  - Admin can update; Staff can read but gets PERMISSION_DENIED on update.
  - Logo: valid PNG/JPG accepted; wrong type, oversized and non-image content
    with an image extension rejected.
  - Replacing a logo keeps the old file on disk.
  - GSTIN format validation.
"""

from io import BytesIO
from pathlib import Path

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import IntegrityError, transaction
from PIL import Image
from rest_framework import status

from apps.company.models import CompanySettings

SETTINGS_URL = "/api/settings/company/"


# ===========================================================================
# Helpers and fixtures
# ===========================================================================


@pytest.fixture
def media_root(settings, tmp_path):
    """Store uploaded logos in an isolated directory for each test."""
    settings.MEDIA_ROOT = str(tmp_path)
    return tmp_path


def image_bytes(image_format: str = "PNG", size=(20, 20)) -> bytes:
    buffer = BytesIO()
    Image.new("RGB", size, (200, 210, 220)).save(buffer, format=image_format)
    return buffer.getvalue()


def upload_logo(
    client,
    content: bytes,
    name: str = "logo.png",
    content_type: str = "image/png",
):
    return client.patch(
        SETTINGS_URL,
        {"logo": SimpleUploadedFile(name, content, content_type=content_type)},
        format="multipart",
    )


def current_settings() -> CompanySettings:
    return CompanySettings.objects.get(pk=CompanySettings.SINGLETON_PK)


# ===========================================================================
# Read access
# ===========================================================================


@pytest.mark.django_db
def test_get_requires_authentication(anon_client):
    response = anon_client.get(SETTINGS_URL)
    assert response.status_code == status.HTTP_401_UNAUTHORIZED
    assert response.json()["code"] == "NOT_AUTHENTICATED"


@pytest.mark.django_db
def test_get_returns_the_single_empty_record(admin_client):
    response = admin_client.get(SETTINGS_URL)
    assert response.status_code == status.HTTP_200_OK

    data = response.json()
    assert data["business_name"] == ""
    assert data["logo"] is None
    assert data["address"] == ""
    assert data["phone"] == ""
    assert data["email"] == ""
    assert data["gstin"] == ""
    assert data["updated_by"] is None
    assert CompanySettings.objects.count() == 1


@pytest.mark.django_db
def test_get_creates_the_record_if_missing(admin_client):
    CompanySettings.objects.all().delete()
    assert CompanySettings.objects.count() == 0

    response = admin_client.get(SETTINGS_URL)
    assert response.status_code == status.HTTP_200_OK
    assert CompanySettings.objects.count() == 1
    assert current_settings().pk == CompanySettings.SINGLETON_PK


@pytest.mark.django_db
def test_staff_can_read_settings(staff_client):
    response = staff_client.get(SETTINGS_URL)
    assert response.status_code == status.HTTP_200_OK


# ===========================================================================
# Singleton rule
# ===========================================================================


@pytest.mark.django_db
def test_only_one_record_can_exist():
    assert CompanySettings.objects.count() == 1

    with pytest.raises(IntegrityError):
        with transaction.atomic():
            CompanySettings.objects.create(
                pk=2,
                business_name="Second business",
                address="Somewhere",
                phone="9000000000",
            )

    assert CompanySettings.objects.count() == 1


@pytest.mark.django_db
def test_no_create_or_delete_endpoint(admin_client):
    create_response = admin_client.post(
        SETTINGS_URL,
        {"business_name": "Other", "address": "X", "phone": "9000000000"},
        format="json",
    )
    assert create_response.status_code == status.HTTP_405_METHOD_NOT_ALLOWED

    delete_response = admin_client.delete(SETTINGS_URL)
    assert delete_response.status_code == status.HTTP_405_METHOD_NOT_ALLOWED

    assert CompanySettings.objects.count() == 1


# ===========================================================================
# Update access and fields
# ===========================================================================


@pytest.mark.django_db
def test_admin_can_update_settings(admin_client, admin_user):
    payload = {
        "business_name": "Kumar Traders",
        "address": "12 Market Road\nCoimbatore",
        "phone": "9876543210",
        "email": "accounts@kumartraders.test",
        "gstin": "27ABCDE1234F1Z5",
    }
    response = admin_client.patch(SETTINGS_URL, payload, format="json")
    assert response.status_code == status.HTTP_200_OK

    data = response.json()
    assert data["business_name"] == payload["business_name"]
    assert data["address"] == payload["address"]
    assert data["phone"] == payload["phone"]
    assert data["email"] == payload["email"]
    assert data["gstin"] == payload["gstin"]
    assert data["updated_by"] == admin_user.pk

    saved = current_settings()
    assert saved.business_name == payload["business_name"]
    assert saved.address == payload["address"]
    assert saved.phone == payload["phone"]
    assert saved.email == payload["email"]
    assert saved.gstin == payload["gstin"]
    assert saved.updated_by_id == admin_user.pk

    # A later GET returns the saved details.
    read_response = admin_client.get(SETTINGS_URL)
    assert read_response.status_code == status.HTTP_200_OK
    assert read_response.json()["business_name"] == payload["business_name"]


@pytest.mark.django_db
def test_staff_cannot_update_settings(staff_client):
    response = staff_client.patch(
        SETTINGS_URL,
        {"business_name": "Changed by staff"},
        format="json",
    )
    assert response.status_code == status.HTTP_403_FORBIDDEN
    assert response.json()["code"] == "PERMISSION_DENIED"
    assert current_settings().business_name == ""


@pytest.mark.django_db
def test_anonymous_cannot_update_settings(anon_client):
    response = anon_client.patch(
        SETTINGS_URL,
        {"business_name": "Changed anonymously"},
        format="json",
    )
    assert response.status_code == status.HTTP_401_UNAUTHORIZED
    assert response.json()["code"] == "NOT_AUTHENTICATED"


@pytest.mark.django_db
def test_required_fields_are_validated(admin_client):
    response = admin_client.patch(
        SETTINGS_URL,
        {"business_name": "   ", "phone": ""},
        format="json",
    )
    assert response.status_code == status.HTTP_400_BAD_REQUEST
    body = response.json()
    assert body["code"] == "VALIDATION_ERROR"
    assert "business_name" in body["fields"]
    assert "phone" in body["fields"]


@pytest.mark.django_db
def test_invalid_email_rejected(admin_client):
    response = admin_client.patch(
        SETTINGS_URL,
        {"email": "not-an-email"},
        format="json",
    )
    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert "email" in response.json()["fields"]


# ===========================================================================
# GSTIN validation
# ===========================================================================


@pytest.mark.django_db
@pytest.mark.parametrize(
    "gstin",
    [
        "",                 # optional
        "27ABCDE1234F1Z5",  # Maharashtra
        "07AAAAA0000A1Z5",  # Delhi
    ],
)
def test_valid_gstin_accepted(admin_client, gstin):
    response = admin_client.patch(SETTINGS_URL, {"gstin": gstin}, format="json")
    assert response.status_code == status.HTTP_200_OK
    assert response.json()["gstin"] == gstin
    assert current_settings().gstin == gstin


@pytest.mark.django_db
@pytest.mark.parametrize(
    "gstin",
    [
        "27ABCDE1234F1Z",    # too short
        "27ABCDE1234F1Z55",  # too long
        "27abcde1234f1z5",   # lower case does not match the pattern
        "27ABCDE1234F0Z5",   # 13th character must be 1-9 or A-Z
        "ABCDE1234F1Z5",     # missing state code
    ],
)
def test_invalid_gstin_rejected(admin_client, gstin):
    response = admin_client.patch(SETTINGS_URL, {"gstin": gstin}, format="json")
    assert response.status_code == status.HTTP_400_BAD_REQUEST
    body = response.json()
    assert body["code"] == "VALIDATION_ERROR"
    assert "gstin" in body["fields"]
    assert current_settings().gstin == ""


# ===========================================================================
# Logo validation and storage
# ===========================================================================


@pytest.mark.django_db
def test_valid_png_logo_accepted(admin_client, media_root):
    response = upload_logo(admin_client, image_bytes("PNG"), "logo.png", "image/png")
    assert response.status_code == status.HTTP_200_OK

    data = response.json()
    assert data["logo"] is not None
    assert data["logo"].startswith("http://testserver/media/company/logos/")
    assert data["logo"].endswith(".png")

    saved = current_settings()
    assert saved.logo.name.startswith("company/logos/")
    assert saved.logo.name.endswith(".png")
    assert Path(saved.logo.path).exists()


@pytest.mark.django_db
def test_valid_jpg_logo_accepted(admin_client, media_root):
    response = upload_logo(admin_client, image_bytes("JPEG"), "logo.jpg", "image/jpeg")
    assert response.status_code == status.HTTP_200_OK
    assert response.json()["logo"].endswith(".jpg")
    assert current_settings().logo.name.endswith(".jpg")


@pytest.mark.django_db
def test_gif_logo_rejected(admin_client, media_root):
    response = upload_logo(admin_client, image_bytes("GIF"), "logo.gif", "image/gif")
    assert response.status_code == status.HTTP_400_BAD_REQUEST
    body = response.json()
    assert body["code"] == "VALIDATION_ERROR"
    assert "logo" in body["fields"]
    assert not current_settings().logo


@pytest.mark.django_db
def test_non_image_with_image_extension_rejected(admin_client, media_root):
    response = upload_logo(
        admin_client,
        b"this is not an image",
        "logo.png",
        "image/png",
    )
    assert response.status_code == status.HTTP_400_BAD_REQUEST
    body = response.json()
    assert body["code"] == "VALIDATION_ERROR"
    assert "logo" in body["fields"]
    assert not current_settings().logo


@pytest.mark.django_db
def test_oversized_logo_rejected(admin_client, media_root):
    oversized = image_bytes("PNG") + b"\x00" * (2 * 1024 * 1024)
    response = upload_logo(admin_client, oversized, "logo.png", "image/png")
    assert response.status_code == status.HTTP_400_BAD_REQUEST
    body = response.json()
    assert body["code"] == "VALIDATION_ERROR"
    assert "logo" in body["fields"]
    assert not current_settings().logo


@pytest.mark.django_db
def test_replacing_logo_keeps_old_file(admin_client, media_root):
    first_response = upload_logo(
        admin_client,
        image_bytes("PNG"),
        "first.png",
        "image/png",
    )
    assert first_response.status_code == status.HTTP_200_OK
    first_name = current_settings().logo.name
    first_path = Path(media_root, first_name)
    assert first_path.exists()

    second_response = upload_logo(
        admin_client,
        image_bytes("PNG"),
        "second.png",
        "image/png",
    )
    assert second_response.status_code == status.HTTP_200_OK
    second_name = current_settings().logo.name

    assert second_name != first_name
    assert Path(media_root, second_name).exists()
    # The replaced file is intentionally kept for documents that reference it.
    assert first_path.exists()
