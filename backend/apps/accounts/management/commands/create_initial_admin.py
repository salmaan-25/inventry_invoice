"""
Management command: create_initial_admin

Creates the first ADMIN user. Reads credentials from environment variables
INITIAL_ADMIN_USERNAME and INITIAL_ADMIN_PASSWORD, or prompts interactively
when those are not set.

Never uses a hard-coded password (Section 3.8 / Phase 1 requirement).

Usage:
    python manage.py create_initial_admin
    INITIAL_ADMIN_USERNAME=owner INITIAL_ADMIN_PASSWORD=... python manage.py create_initial_admin
"""

import os
import getpass

from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.core.management.base import BaseCommand, CommandError

from apps.accounts.models import User
from apps.common.constants import Role


class Command(BaseCommand):
    help = "Create the initial ADMIN user. Reads credentials from env vars or prompts."

    def handle(self, *args, **options):
        username = os.environ.get("INITIAL_ADMIN_USERNAME", "").strip()
        password = os.environ.get("INITIAL_ADMIN_PASSWORD", "").strip()

        # --- Username ---
        if not username:
            username = input("Admin username: ").strip()
        if not username:
            raise CommandError("Username cannot be empty.")

        if User.objects.filter(username=username).exists():
            self.stdout.write(
                self.style.WARNING(
                    f"A user with username '{username}' already exists. No changes made."
                )
            )
            return

        # --- Password ---
        if not password:
            password = getpass.getpass("Admin password: ")
            confirm = getpass.getpass("Confirm password: ")
            if password != confirm:
                raise CommandError("Passwords do not match.")

        if not password:
            raise CommandError("Password cannot be empty.")

        # Validate against Django's configured password validators.
        try:
            validate_password(password)
        except ValidationError as exc:
            raise CommandError("Password is not strong enough:\n" + "\n".join(exc.messages))

        # --- Full name and phone (optional interactive prompts) ---
        full_name = os.environ.get("INITIAL_ADMIN_FULL_NAME", "").strip()
        if not full_name:
            full_name = input("Full name (press Enter to use username): ").strip() or username

        phone = os.environ.get("INITIAL_ADMIN_PHONE", "").strip()
        if not phone:
            phone = input("Phone number (press Enter to skip): ").strip()

        # --- Create user ---
        user = User.objects.create_user(
            username=username,
            password=password,
            full_name=full_name,
            phone=phone,
            role=Role.ADMIN,
            is_staff=True,
            is_superuser=True,
        )
        self.stdout.write(
            self.style.SUCCESS(
                f"Admin user '{user.username}' created successfully."
            )
        )
