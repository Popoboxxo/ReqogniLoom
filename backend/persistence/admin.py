"""
Django admin registration for persistence.User (REQ-L1-010).

Registers the custom User model with Django admin using a tailored ModelAdmin
(not django.contrib.auth.admin.UserAdmin) because persistence.User has a
different field set than AbstractUser (UUID pk, tenant FK, no groups/permissions
tables, no last_login/date_joined).

The admin site authenticates against AUTH_USER_MODEL = "persistence.User", so
staff users with is_staff=True can log in at /admin/ with their ReqFlow credentials.
"""
from __future__ import annotations

from django.contrib import admin
from django.contrib.auth import get_user_model

User = get_user_model()


@admin.register(User)
class ReqFlowUserAdmin(admin.ModelAdmin):
    """Admin view for the ReqFlow User model."""

    list_display = (
        "username",
        "email",
        "is_active",
        "is_staff",
        "is_superuser",
        "tenant",
    )
    list_filter = ("is_active", "is_staff", "is_superuser", "tenant")
    search_fields = ("username", "email")
    ordering = ("username",)

    fieldsets = (
        (None, {"fields": ("username", "email", "password")}),
        (
            "Permissions",
            {"fields": ("is_active", "is_staff", "is_superuser")},
        ),
        (
            "Tenant",
            {"fields": ("tenant",)},
        ),
    )
    add_fieldsets = (
        (
            None,
            {
                "classes": ("wide",),
                "fields": (
                    "username",
                    "email",
                    "password",
                    "is_active",
                    "is_staff",
                    "is_superuser",
                    "tenant",
                ),
            },
        ),
    )

    def save_model(self, request, obj, form, change):
        """Hash the password via set_password when it changes in admin."""
        if "password" in form.changed_data and form.cleaned_data.get("password"):
            obj.set_password(form.cleaned_data["password"])
        super().save_model(request, obj, form, change)
