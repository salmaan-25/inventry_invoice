"""
Data migration — seed the CustomerCodeCounter singleton (pk=1, next_value=1).

This row must exist before any customer is created so that the
select_for_update() lock in services.create_customer() always finds a row.
The services layer also calls get_or_create as a safety net, but seeding here
keeps the happy-path fast.
"""

from django.db import migrations


def seed_counter(apps, schema_editor):
    CustomerCodeCounter = apps.get_model("customers", "CustomerCodeCounter")
    CustomerCodeCounter.objects.get_or_create(pk=1, defaults={"next_value": 1})


def unseed_counter(apps, schema_editor):
    CustomerCodeCounter = apps.get_model("customers", "CustomerCodeCounter")
    CustomerCodeCounter.objects.filter(pk=1).delete()


class Migration(migrations.Migration):

    dependencies = [
        ("customers", "0001_initial"),
    ]

    operations = [
        migrations.RunPython(seed_counter, reverse_code=unseed_counter),
    ]
