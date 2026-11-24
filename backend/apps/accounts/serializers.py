"""
accounts.serializers — Phase 1.

Serializers:
  UserReadSerializer       — read-only user representation (id, username, full_name, phone, email, role)
  StaffCreateSerializer    — Admin registers a new staff member (includes password + confirm)
  StaffUpdateSerializer    — Admin edits details, role, is_active (no password here)
  SetPasswordSerializer    — Admin sets a staff member's password
  LoginSerializer          — Validates username + password credentials
"""

from django.contrib.auth import authenticate
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError as DjangoValidationError
from rest_framework import serializers

from apps.accounts.models import User, Employee
from apps.common.constants import Role


# ---------------------------------------------------------------------------
# Read serializer — used by /auth/me/, staff list and detail endpoints
# ---------------------------------------------------------------------------


class UserReadSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ("id", "username", "full_name", "phone", "email", "role", "is_active", "date_joined")
        read_only_fields = fields


# ---------------------------------------------------------------------------
# Login serializer — validates credentials, returns nothing (view handles session)
# ---------------------------------------------------------------------------


class LoginSerializer(serializers.Serializer):
    username = serializers.CharField()
    password = serializers.CharField(write_only=True, style={"input_type": "password"})

    def validate(self, attrs):
        username = attrs.get("username", "").strip()
        password = attrs.get("password", "")

        # authenticate() uses USERNAME_FIELD which is "username".
        # Return the same generic message whether the user does not exist or
        # the password is wrong (do not reveal whether the username exists).
        user = authenticate(
            request=self.context.get("request"),
            username=username,
            password=password,
        )
        if not user:
            raise serializers.ValidationError(
                {"non_field_errors": ["Invalid credentials. Please try again."]}
            )
        if not user.is_active:
            raise serializers.ValidationError(
                {"non_field_errors": ["This account has been deactivated."]}
            )
        attrs["user"] = user
        return attrs


# ---------------------------------------------------------------------------
# Staff create serializer — Admin only
# ---------------------------------------------------------------------------


class StaffCreateSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True, style={"input_type": "password"})
    confirm_password = serializers.CharField(write_only=True, style={"input_type": "password"})

    class Meta:
        model = User
        fields = (
            "username",
            "full_name",
            "phone",
            "email",
            "role",
            "is_active",
            "password",
            "confirm_password",
        )
        extra_kwargs = {
            "role": {"default": Role.STAFF},
            "is_active": {"default": True},
        }

    def validate_username(self, value):
        if User.objects.filter(username=value).exists():
            raise serializers.ValidationError("A user with this username already exists.")
        return value


# ---------------------------------------------------------------------------
# Employee serializer — Business staff management
# ---------------------------------------------------------------------------


class EmployeeSerializer(serializers.ModelSerializer):
    class Meta:
        model = Employee
        fields = [
            "id",
            "employee_id",
            "name",
            "contact",
            "notes",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "created_at", "updated_at"]


    def validate(self, attrs):
        password = attrs.get("password", "")
        confirm = attrs.pop("confirm_password", "")
        if password != confirm:
            raise serializers.ValidationError({"confirm_password": ["Passwords do not match."]})
        # Run Django's built-in password validators.
        try:
            validate_password(password)
        except DjangoValidationError as exc:
            raise serializers.ValidationError({"password": list(exc.messages)})
        return attrs

    def create(self, validated_data):
        password = validated_data.pop("password")
        user = User(**validated_data)
        user.set_password(password)
        # Sync is_staff with role so the Django admin reflects ADMIN status.
        user.is_staff = validated_data.get("role") == Role.ADMIN
        user.save()
        return user


# ---------------------------------------------------------------------------
# Staff update serializer — Admin only, no password field here
# ---------------------------------------------------------------------------


class StaffUpdateSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ("full_name", "phone", "email", "role", "is_active")

    def validate(self, attrs):
        request = self.context["request"]
        instance = self.instance

        # An Admin cannot deactivate or demote themselves.
        if instance.pk == request.user.pk:
            if "is_active" in attrs and not attrs["is_active"]:
                raise serializers.ValidationError(
                    {"is_active": ["You cannot deactivate your own account."]}
                )
            if "role" in attrs and attrs["role"] != Role.ADMIN:
                raise serializers.ValidationError(
                    {"role": ["You cannot change your own role."]}
                )

        # The last active Admin cannot be deactivated or demoted.
        if instance.role == Role.ADMIN:
            new_active = attrs.get("is_active", instance.is_active)
            new_role = attrs.get("role", instance.role)
            if new_active is False or new_role != Role.ADMIN:
                active_admin_count = (
                    User.objects.filter(role=Role.ADMIN, is_active=True)
                    .exclude(pk=instance.pk)
                    .count()
                )
                if active_admin_count == 0:
                    raise serializers.ValidationError(
                        "Cannot deactivate or demote the last active admin."
                    )

        return attrs

    def update(self, instance, validated_data):
        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        # Keep Django admin access in sync with role.
        instance.is_staff = instance.role == Role.ADMIN
        instance.save()
        return instance


# ---------------------------------------------------------------------------
# Set-password serializer — Admin only
# ---------------------------------------------------------------------------


class SetPasswordSerializer(serializers.Serializer):
    new_password = serializers.CharField(write_only=True, style={"input_type": "password"})

    def validate_new_password(self, value):
        try:
            validate_password(value)
        except DjangoValidationError as exc:
            raise serializers.ValidationError(list(exc.messages))
        return value


# ---------------------------------------------------------------------------
# Employee serializer — Business staff management
# ---------------------------------------------------------------------------


class EmployeeSerializer(serializers.ModelSerializer):
    class Meta:
        model = Employee
        fields = [
            "id",
            "employee_id",
            "name",
            "contact",
            "notes",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "created_at", "updated_at"]

