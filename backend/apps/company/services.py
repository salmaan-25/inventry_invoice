"""
company.services — Phase 2.

All business operations for the single CompanySettings record live here.
Views stay thin and delegate to these functions.
"""

from typing import Any

from django.db import transaction

from apps.accounts.models import User
from apps.company.models import CompanySettings

SINGLETON_DEFAULTS = {
    "business_name": "",
    "address": "",
    "state": "Tamil Nadu",
    "phone": "",
}


def get_company_settings() -> CompanySettings:
    """
    Return the one CompanySettings row, creating an empty one if it is
    missing (for example after a manual database reset in development).
    """
    company_settings, _ = CompanySettings.objects.get_or_create(
        pk=CompanySettings.SINGLETON_PK,
        defaults=SINGLETON_DEFAULTS,
    )
    return company_settings


def update_company_settings(
    *,
    data: dict[str, Any],
    user: User,
) -> CompanySettings:
    """
    Update the company settings and record who made the change.

    The row is locked for the duration of the update so two simultaneous
    updates cannot interleave. Uploaded files are stored under a unique name
    by the model, so previous logo files are never overwritten.
    """
    with transaction.atomic():
        company_settings = get_company_settings()
        company_settings = CompanySettings.objects.select_for_update().get(
            pk=company_settings.pk
        )

        for field, value in data.items():
            setattr(company_settings, field, value)

        company_settings.updated_by = user
        company_settings.save()

    return company_settings
