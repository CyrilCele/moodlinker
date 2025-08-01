from django.contrib import admin
from tracker.models import Habit, HabitCompletion, MoodEntry


@admin.register(Habit)
class HabitAdmin(admin.ModelAdmin):
    list_display = ("user", "name", "frequency", "created_at")
    list_filter = ("user",)
    search_fields = ("frequency",)


@admin.register(HabitCompletion)
class HabitCompletionAdmin(admin.ModelAdmin):
    list_display = ("habit", "date", "completed")
    list_filter = ("habit", "completed")
    search_fields = ("habit",)


@admin.register(MoodEntry)
class MoodEntryAdmin(admin.ModelAdmin):
    list_display = ("user", "date", "score")
    list_filter = ("user", "score")
    search_fields = ("user",)
