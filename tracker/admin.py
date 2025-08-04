from django.contrib import admin

from .models import User, UserProfile, Habit, MoodEntry, HabitCompletion


class UserProfileAdmin(admin.ModelAdmin):
    list_display = ["user", "date_of_birth"]


class HabitAdmin(admin.ModelAdmin):
    list_display = ["user", "habit", "periodicity"]


class MoodEntryAdmin(admin.ModelAdmin):
    list_display = ["user", "score", "date"]


class HabitCompletionAdmin(admin.ModelAdmin):
    list_display = ["user", "habit", "date", "completed"]


# Register your models here.
admin.site.register(User)
admin.site.register(UserProfile, UserProfileAdmin)
admin.site.register(Habit, HabitAdmin)
admin.site.register(MoodEntry, MoodEntryAdmin)
admin.site.register(HabitCompletion, HabitCompletionAdmin)
