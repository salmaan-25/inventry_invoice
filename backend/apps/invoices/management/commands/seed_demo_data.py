"""Management command: seed_demo_data

Create sample staff, customers, products, invoices, payments, challans,
expenses and income for frontend development and demos.

Refuses to run when DEBUG is False (development only).
"""

import datetime
import random
import uuid

from decimal import Decimal

from django.conf import settings
from django.core.management.base import BaseCommand

from apps.accounts.models import User
from apps.common.constants import Role
from apps.customers.models import Customer
from apps.products.models import Product, Unit
from apps.invoices.models import Invoice, InvoiceItem
from apps.payments.models import Payment, PaymentAllocation
from apps.expenses.models import Expense, ExpenseCategory
from apps.other_income.models import OtherIncome, IncomeCategory


class Command(BaseCommand):
    help = (
        "Seed demo data for development and demos. "
        "Refuses to run when DEBUG is False."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--force",
            action="store_true",
            help="Force seeding even if DEBUG is False",
        )

    def handle(self, *args, **options):
        # --- Check DEBUG ---
        if not settings.DEBUG and not options["force"]:
            self.stderr.write(
                self.style.ERROR(
                    "seed_demo_data is development-only. "
                    "Run with --force to override."
                )
            )
            return

        self.stdout.write(self.style.NOTICE("Seeding demo data..."))

        # --- Create staff users ---
        self._create_staff_users()

        # --- Create customers ---
        self._create_customers()

        # --- Create products ---
        self._create_products()

        # --- Create invoices ---
        self._create_invoices()

        # --- Create payments ---
        self._create_payments()

        # --- Create expenses ---
        self._create_expenses()

        # --- Create other income ---
        self._create_other_income()

        self.stdout.write(self.style.SUCCESS("Demo data seeded successfully."))

    # ---- Staff users ----
    def _create_staff_users(self):
        users_data = [
            {"username": "admin_user", "full_name": "Admin User", "role": Role.ADMIN},
            {"username": "staff_user", "full_name": "Staff User", "role": Role.STAFF},
        ]
        for u in users_data:
            if not User.objects.filter(username=u["username"]).exists():
                user = User.objects.create_user(
                    username=u["username"],
                    password="password123",
                    full_name=u["full_name"],
                    role=u["role"],
                    is_staff=u["role"] == Role.STAFF,
                    is_superuser=u["role"] == Role.ADMIN,
                )
                self.stdout.write(f"Created user: {u['username']}")

    # ---- Customers ----
    def _create_customers(self):
        customers_data = [
            {"name": "Kumar Hardware", "gstin": "AAAAA0000A", "state": "Maharashtra"},
            {"name": "Sri Textiles", "gstin": "BBBBB1111B", "state": "Tamil Nadu"},
            {"name": "Patel Enterprises", "gstin": "CCCCC2222C", "state": "Gujarat"},
            {"name": "Roy Electronics", "gstin": "DDDDD3333D", "state": "Karnataka"},
        ]
        for c in customers_data:
            if not Customer.objects.filter(name=c["name"]).exists():
                customer = Customer.objects.create(
                    name=c["name"],
                    gstin=c.get("gstin", ""),
                    state=c.get("state", ""),
                    is_active=True,
                )
                self.stdout.write(f"Created customer: {c['name']}")

    # ---- Products ----
    def _create_products(self):
        # Create units first
        units_data = [
            {"name": "pcs", "abbreviation": "pcs"},
            {"name": "kg", "abbreviation": "kg"},
            {"name": "bag", "abbreviation": "bag"},
            {"name": "bundle", "abbreviation": "bundle"},
        ]
        for u in units_data:
            Unit.objects.get_or_create(name=u["name"], defaults={"abbreviation": u["abbreviation"]})

        # Create products
        item_types = ["GOODS", "GOODS_HARDWARE", "SERVICE"]
        product_names = [
            ("Wall putty 20 kg", "PWT20"),
            ("Paint emulsion 1L", "PEM1L"),
            ("Cement 50 kg", "CMT50"),
            ("Steel pipe 10mm", "STP10"),
            ("Hardware kit", "HK001"),
            ("Service consultation", "CONSULT"),
        ]

        for i, (name, code) in enumerate(product_names):
            item_type = item_types[i % len(item_types)]
            unit = Unit.objects.get(name="pcs" if item_type != "SERVICE" else "bag")
            product, created = Product.objects.get_or_create(
                code=code,
                defaults={
                    "name": name,
                    "description": f"{name} description",
                    "item_type": item_type,
                    "unit": unit,
                    "selling_price": Decimal("100.00" if item_type != "SERVICE" else "0.00"),
                    "gst_rate": Decimal("18.00" if item_type != "SERVICE" else None),
                    "reorder_level": Decimal("10.00" if item_type in ["GOODS", "GOODS_HARDWARE"] else None),
                    "current_stock": Decimal("100.00" if item_type in ["GOODS", "GOODS_HARDWARE"] else "0.000"),
                    "is_active": True,
                },
            )
            if created:
                self.stdout.write(f"Created product: {name} ({item_type})")

    # ---- Invoices ----
    def _create_invoices(self):
        customers = list(Customer.objects.all())
        if not customers:
            self.stdout.write("No customers found. Create customers first.")
            return

        # Create some draft invoices
        for i in range(3):
            customer = random.choice(customers)
            invoice = Invoice.objects.create(
                customer=customer,
                invoice_date=datetime.date.today() - datetime.timedelta(days=random.randint(0, 30)),
                notes=f"Demo invoice {i+1}",
                status="DRAFT",
            )
            # Add 2-3 invoice items
            item_types = ["GOODS", "GOODS_HARDWARE", "SERVICE"]
            for j in range(random.randint(2, 3)):
                item_type = random.choice(item_types)
                product_name = random.choice(["Wall putty 20 kg", "Paint emulsion 1L", "Cement 50 kg", "Steel pipe 10mm", "Hardware kit", "Service consultation"])
                product, _ = Product.objects.get_or_create(name=product_name)
                quantity = Decimal(str(random.randint(1, 10)))
                rate = Decimal(str(random.randint(50, 500)))
                line_total = quantity * rate
                InvoiceItem.objects.create(
                    invoice=invoice,
                    product=product,
                    line_no=j + 1,
                    quantity=quantity,
                    rate=rate,
                    line_total=line_total,
                    gst_rate=product.gst_rate,
                )
            self.stdout.write(f"Created draft invoice {invoice.id} for {customer.name}")

        # Create some ISSUED invoices
        for i in range(2):
            customer = random.choice(customers)
            invoice_date = datetime.date.today() - datetime.timedelta(days=random.randint(0, 10))
            invoice = Invoice.objects.create(
                customer=customer,
                invoice_date=invoice_date,
                notes=f"Issued demo invoice {i+1}",
                status="ISSUED",
                issued_by=User.objects.get(username="admin_user"),
                issued_at=datetime.datetime.now(),
            )
            # Add invoice items
            for j in range(random.randint(2, 4)):
                item_type = random.choice(["GOODS", "GOODS_HARDWARE"])
                product_name = random.choice(["Wall putty 20 kg", "Paint emulsion 1L", "Cement 50 kg", "Steel pipe 10mm", "Hardware kit"])
                product, _ = Product.objects.get_or_create(name=product_name)
                quantity = Decimal(str(random.randint(1, 5)))
                rate = Decimal(str(random.randint(50, 300)))
                line_total = quantity * rate
                InvoiceItem.objects.create(
                    invoice=invoice,
                    product=product,
                    line_no=j + 1,
                    quantity=quantity,
                    rate=rate,
                    line_total=line_total,
                    gst_rate=product.gst_rate,
                )
            self.stdout.write(f"Created ISSUED invoice {invoice.id} for {customer.name} (date: {invoice_date})")

    # ---- Payments ----
    def _create_payments(self):
        customers = list(Customer.objects.all())
        if not customers:
            return

        # Create some payments allocated to invoices
        issued_invoices = list(Invoice.objects.filter(status="ISSUED"))
        if not issued_invoices:
            return

        for i in range(3):
            customer = random.choice(customers)
            payment_date = datetime.date.today() - datetime.timedelta(days=random.randint(0, 20))
            amount = Decimal(str(random.randint(200, 1500)))
            method = random.choice(["CASH", "UPI", "BANK_TRANSFER", "CHEQUE"])
            reference = f"REF{uuid.uuid4().hex[:8].upper()}"

            payment = Payment.objects.create(
                customer=customer,
                payment_date=payment_date,
                amount=amount,
                method=method,
                reference=reference,
                note=f"Demo payment {i+1}",
            )

            # Allocate payment to 1-3 invoices
            allocated = random.sample(issued_invoices, k=min(random.randint(1, 3), len(issued_invoices)))
            remaining_amount = amount
            for inv in allocated:
                # Allocate a portion of the payment to this invoice
                alloc_amount = min(Decimal(str(random.randint(50, 200))), remaining_amount)
                remaining_amount -= alloc_amount
                PaymentAllocation.objects.create(
                    payment=payment,
                    invoice=inv,
                    amount=alloc_amount,
                )
            self.stdout.write(f"Created payment {payment.id} for {customer.name} (amount: {amount})")

    # ---- Expenses ----
    def _create_expenses(self):
        categories = ["Rent", "Electricity", "Transport", "Salary", "Repairs", "Other"]
        for cat_name in categories:
            ExpenseCategory.objects.get_or_create(name=cat_name)

        today = datetime.date.today()
        expense_data = [
            {"date": today - datetime.timedelta(days=1), "category": "Rent", "amount": Decimal("5000.00")},
            {"date": today - datetime.timedelta(days=2), "category": "Electricity", "amount": Decimal("1200.50")},
            {"date": today - datetime.timedelta(days=3), "category": "Transport", "amount": Decimal("300.00")},
            {"date": today - datetime.timedelta(days=4), "category": "Salary", "amount": Decimal("8000.00")},
            {"date": today - datetime.timedelta(days=5), "category": "Repairs", "amount": Decimal("450.75")},
        ]

        for ed in expense_data:
            category = ExpenseCategory.objects.get(name=ed["category"])
            Expense.objects.create(
                date=ed["date"],
                category=category,
                description=f"Demo expense on {ed['date']}",
                amount=ed["amount"],
                payment_method="CASH",
                paid_to="",
                notes=f"Demo expense note",
                recorded_by=User.objects.get(username="admin_user"),
            )
        self.stdout.write("Created demo expenses")

    # ---- Other income ----
    def _create_other_income(self):
        categories = ["Scrap sale", "Commission", "Interest", "Other"]
        for cat_name in categories:
            IncomeCategory.objects.get_or_create(name=cat_name)

        today = datetime.date.today()
        income_data = [
            {"date": today - datetime.timedelta(days=1), "category": "Commission", "amount": Decimal("2000.00")},
            {"date": today - datetime.timedelta(days=2), "category": "Interest", "amount": Decimal("500.50")},
            {"date": today - datetime.timedelta(days=3), "category": "Scrap sale", "amount": Decimal("800.00")},
        ]

        for id in income_data:
            category = IncomeCategory.objects.get(name=id["category"])
            OtherIncome.objects.create(
                date=id["date"],
                category=category,
                description=f"Demo other income on {id['date']}",
                amount=id["amount"],
                payment_method="CASH",
                received_from="",
                recorded_by=User.objects.get(username="admin_user"),
            )
        self.stdout.write("Created demo other income")