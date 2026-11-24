"""
Seed the single CompanySettings row.

The settings record is created empty so the application always has exactly
one row to read and update. The Admin fills it in through the API.
"""

from django.db import migrations


def create_company_settings(apps, schema_editor):
    CompanySettings = apps.get_model("company", "CompanySettings")
    CompanySettings.objects.get_or_create(
        pk=1,
        defaults={
            "business_name": "",
            "address": "",
            "phone": "",
        },
    )


def remove_company_settings(apps, schema_editor):
    CompanySettings = apps.get_model("company", "CompanySettings")
    CompanySettings.objects.filter(pk=1).delete()


class Migration(migrations.Migration):

    dependencies = [
        ("company", "0001_initial"),
    ]

    operations = [
        migrations.RunPython(
            create_company_settings,
            reverse_code=remove_company_settings,
        ),
    ]
