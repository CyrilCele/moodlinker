from django.contrib import admin

from .models import User, UserProfile, Habit, MoodEntry, HabitCompletion, Address, Notification, HabitReminder


class AddressAdmin(admin.ModelAdmin):
    list_display = [
        "street_address", "city", "state_province", "postal_code", "country"
    ]


class UserProfileAdmin(admin.ModelAdmin):
    list_display = ["user", "date_of_birth"]


class HabitAdmin(admin.ModelAdmin):
    list_display = ["user", "habit", "periodicity"]


class MoodEntryAdmin(admin.ModelAdmin):
    list_display = ["user", "score", "date"]


class HabitCompletionAdmin(admin.ModelAdmin):
    list_display = ["user", "habit", "date", "completed"]


class NotificationAdmin(admin.ModelAdmin):
    list_display = ["user", "message", "created_at", "read"]


class HabitReminderAdmin(admin.ModelAdmin):
    list_display = ["user", "habit", "next_trigger_utc"]


# Register your models here.
admin.site.register(User)
admin.site.register(Address, AddressAdmin)
admin.site.register(UserProfile, UserProfileAdmin)
admin.site.register(Habit, HabitAdmin)
admin.site.register(MoodEntry, MoodEntryAdmin)
admin.site.register(HabitCompletion, HabitCompletionAdmin)
admin.site.register(Notification, NotificationAdmin)
admin.site.register(HabitReminder, HabitReminderAdmin)
