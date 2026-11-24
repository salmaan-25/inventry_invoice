"""
company.models — Phase 2 (Settings).

``CompanySettings`` stores the business identity exactly once.  A database
check constraint restricts the table to the single row with id 1, and a data
migration creates that row.  There is no create or delete API.
"""

import uuid
from pathlib import Path

from django.conf import settings
from django.db import models

from apps.common.constants import INDIAN_STATE_CHOICES


def company_logo_upload_path(instance, filename: str) -> str:
    """
    Return a unique storage path for a logo upload.

    A random name is used so an uploaded logo never overwrites an earlier file.
    Old logo files are intentionally left on disk: issued documents keep
    referencing the logo that was current when they were issued.
    """
    extension = Path(filename).suffix.lower()
    return f"company/logos/{uuid.uuid4().hex}{extension}"


class CompanySettings(models.Model):
    """The business details used on documents. Exactly one row (id=1)."""

    objects = models.Manager()
    SINGLETON_PK = 1

    business_name = models.CharField(max_length=255)
    logo = models.ImageField(
        upload_to=company_logo_upload_path,
        blank=True,
        null=True,
    )
    address = models.TextField()
    state = models.CharField(
        max_length=100,
        choices=INDIAN_STATE_CHOICES,
        blank=True,
        default="Tamil Nadu",
    )
    phone = models.CharField(max_length=20)
    email = models.EmailField(blank=True, default="")
    gstin = models.CharField(max_length=15, blank=True, default="")

    # -- Bank details printed on documents (Phase 5B) --
    bank_holder_name = models.CharField(max_length=255, blank=True, default="")
    bank_name = models.CharField(max_length=255, blank=True, default="")
    bank_account_no = models.CharField(max_length=50, blank=True, default="")
    bank_ifsc = models.CharField(max_length=20, blank=True, default="")

    updated_at = models.DateTimeField(auto_now=True)
    updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="company_settings_updates",
    )

    class Meta:
        verbose_name = "Company settings"
        verbose_name_plural = "Company settings"
        constraints = [
            models.CheckConstraint(
                check=models.Q(pk=1),
                name="company_settings_single_row",
            ),
        ]

    def __str__(self) -> str:
        return self.business_name or "Company settings"
