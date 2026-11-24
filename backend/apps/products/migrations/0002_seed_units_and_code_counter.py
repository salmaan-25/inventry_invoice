"""
Data migration — seed the approved unit list (D6) and the product code counter.

The unit list is the client-approved default from the Phase 4 plan:
pcs, bag, kg, litre, box, trip, metre, foot, set, pair, roll.

The ProductCodeCounter singleton must exist before any product is created so
the select_for_update() lock in services.create_product() always finds a row.
The service also calls get_or_create as a safety net.
"""

from django.db import migrations

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


def seed_units_and_counter(apps, schema_editor):
    Unit = apps.get_model("products", "Unit")
    ProductCodeCounter = apps.get_model("products", "ProductCodeCounter")

    for name in SEEDED_UNITS:
        Unit.objects.get_or_create(name=name)

    ProductCodeCounter.objects.get_or_create(
        pk=1,
        defaults={"next_value": 1},
    )


def unseed_units_and_counter(apps, schema_editor):
    Unit = apps.get_model("products", "Unit")
    ProductCodeCounter = apps.get_model("products", "ProductCodeCounter")

    Unit.objects.filter(name__in=SEEDED_UNITS).delete()
    ProductCodeCounter.objects.filter(pk=1).delete()


class Migration(migrations.Migration):

    dependencies = [
        ("products", "0001_initial"),
    ]

    operations = [
        migrations.RunPython(
            seed_units_and_counter,
            reverse_code=unseed_units_and_counter,
        ),
    ]
