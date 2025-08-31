"""
Django admin registrations and ModelAdmin customizations for the `tracker` app.

This module:
    - Declares ModelAdmin subclasses that control how models appear in the Django admin list view.
    - Registers the models with the admin site so staff users can inspect and manage them.

Guidelines:
    - Keep admin list_dispaly short and meaningful to avoid UI clutter
    - Add `search_fields`, `list_filter`, `ordering`, and `readonly_fields` as needed for better UX.
    - If you register a custom User model, prefer integrating with Django's `UserAdmin` to
      preserve authentication-related admin functionality.
"""

from django.contrib import admin
from django.contrib.admin.sites import AlreadyRegistered

from .models import (
    User,
    UserProfile,
    Habit,
    MoodEntry,
    HabitCompletion,
    Address,
    Notification,
    HabitReminder
)


class AddressAdmin(admin.ModelAdmin):
    """
    Admin presentation for Address model.

    Controls:
        list_display (list[str]): Columns shown in change-list for Address.

    Usage:
        - Registered below with admin.site.register(Address, AddressAdmin).
        - Consider adding search_fields=["city", "postal_code"] or list_filter for country.
    """
    # Columns to show in the admin list view (keep to short, searchable fields)
    list_display = [
        "street_address",
        "city",
        "state_province",
        "postal_code",
        "country"
    ]


class UserProfileAdmin(admin.ModelAdmin):
    """
    Admin presentation for UserProfile model.

    Controls:
        list_display (list[str]): Columns shown in change-list for Profile.
    """
    list_display = ["user", "date_of_birth"]
    search_fields = ["user__username", "user__email"]


class HabitAdmin(admin.ModelAdmin):
    """
    Admin presentation for Habit model.

    Controls:
        list_display (list[str]): Columns shown in change-list for Habit.
    """
    list_display = ["user", "habit", "periodicity"]
    list_filter = ["periodicity"]
    search_fields = ["habit"]


class MoodEntryAdmin(admin.ModelAdmin):
    """
    Admin presentation for MoodEntry model.

    Controls:
        list_display (list[str]): Columns shown in change-list for MoodEntry.
    """
    list_display = ["user", "score", "date"]
    list_filter = ["date", "score"]
    date_hierarchy = "date"


class HabitCompletionAdmin(admin.ModelAdmin):
    """
    Admin presentation for HabitCompletion model.

    Controls:
        list_dispay (list[str]): Columns shown in change-list for HabitCompletion.
    """
    list_display = ["user", "habit", "date", "completed"]
    list_filter = ["completed"]


class NotificationAdmin(admin.ModelAdmin):
    """
    Admin presentation for Notification model.

    Controls:
        list_display (list[str]): Columns shown in change-list for Notification.
    """
    list_display = ["user", "message", "created_at", "read"]
    readonly_fields = ["created_at"]


class HabitReminderAdmin(admin.ModelAdmin):
    """
    Admin presentation for HabitReminder model.

    Controls:
        list_display (list[str]): Columns shown in change-list for HabitReminder
    """
    list_display = ["user", "habit", "next_trigger_utc"]
    ordering = ["next_trigger_utc"]


# Registering a model twice raises admin.sites.AlreadyRegistered.
try:
    admin.site.register(User)
except AlreadyRegistered:
    # We silently ignore to avoid startup errors, but log or handle as needed.
    pass

# Register your models with the customized ModelAdmin classes above.
admin.site.register(Address, AddressAdmin)
admin.site.register(UserProfile, UserProfileAdmin)
admin.site.register(Habit, HabitAdmin)
admin.site.register(MoodEntry, MoodEntryAdmin)
admin.site.register(HabitCompletion, HabitCompletionAdmin)
admin.site.register(Notification, NotificationAdmin)
admin.site.register(HabitReminder, HabitReminderAdmin)
