"""
accounts.models — Phase 1 (no schema changes from Phase 0).

The User model schema was declared in full during Phase 0.
Phase 1 replaces the minimal manager stub with the full UserManager
and adds the admin.py registration for the Django admin.
"""

from django.contrib.auth.models import AbstractBaseUser, BaseUserManager, PermissionsMixin
from django.core.exceptions import ValidationError
from django.db import models

from apps.common.constants import Role


class UserManager(BaseUserManager):
    """
    Full manager for the custom User model.

    create_user  — used by application code and tests.
    create_superuser — used by manage.py createsuperuser / create_initial_admin.
    """

    def create_user(
        self,
        username: str,
        password: str | None = None,
        full_name: str = "",
        phone: str = "",
        email: str = "",
        role: str = Role.STAFF,
        **extra_fields,
    ) -> "User":
        if not username:
            raise ValueError("Username is required.")
        user = self.model(
            username=username,
            full_name=full_name,
            phone=phone,
            email=email,
            role=role,
            **extra_fields,
        )
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_superuser(
        self,
        username: str,
        password: str,
        **extra_fields,
    ) -> "User":
        extra_fields.setdefault("role", Role.ADMIN)
        extra_fields.setdefault("full_name", username)
        extra_fields.setdefault("phone", "")
        extra_fields.setdefault("is_staff", True)
        extra_fields.setdefault("is_superuser", True)
        return self.create_user(username, password, **extra_fields)


class User(AbstractBaseUser, PermissionsMixin):
    """
    Custom user model for the Billing & Inventory Management System V1.

    Two roles: ADMIN (owner) and STAFF. No self-registration.
    Fields match Phase 1 / D2 defaults.
    """

    username = models.CharField(max_length=150, unique=True)
    full_name = models.CharField(max_length=255)
    phone = models.CharField(max_length=20)
    email = models.EmailField(blank=True, default="")
    role = models.CharField(
        max_length=10,
        choices=Role.choices,
        default=Role.STAFF,
    )
    is_active = models.BooleanField(default=True)
    # is_staff gives access to the Django admin. ADMIN role users get this.
    is_staff = models.BooleanField(default=False)
    date_joined = models.DateTimeField(auto_now_add=True)
    # last_login is provided by AbstractBaseUser.

    objects = UserManager()

    USERNAME_FIELD = "username"
    REQUIRED_FIELDS = []

    class Meta:
        ordering = ["username"]

    def __str__(self) -> str:
        return f"{self.full_name} ({self.username})"


class Employee(models.Model):
    """
    Business employee / staff member working in the business.
    """

    employee_id = models.CharField(max_length=50, unique=True)
    name = models.CharField(max_length=255)
    contact = models.CharField(max_length=50, blank=True, default="")
    notes = models.TextField(blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    objects = models.Manager()

    class Meta:
        ordering = ["employee_id", "name"]
        verbose_name = "Employee"
        verbose_name_plural = "Employees"

    def __str__(self) -> str:
        return f"{self.name} ({self.employee_id})"

