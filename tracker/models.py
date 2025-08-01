from django.db import models
from django.contrib.auth.models import User


class Habit(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    name = models.CharField(max_length=100)
    PERIODICITY = [
        ("daily", "Daily"),
        ("weekly", "Weekly"),
        ("monthly", "Monthly"),
        ("yearly", "Yearly")
    ]
    frequency = models.CharField(max_length=10, choices=PERIODICITY)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name_plural = "Habit"

    def __str__(self):
        return f"{self.habit_name} ({self.frequency})"


class HabitCompletion(models.Model):
    habit = models.ForeignKey(
        Habit, on_delete=models.CASCADE, related_name="completions")
    date = models.DateField()
    completed = models.BooleanField(default=True)  # True = done on this day

    class Meta:
        # One record per habit per day, etc.
        unique_together = ("habit", "date")
        verbose_name_plural = "Habit Completion"


class MoodEntry(models.Model):
    user = models.ForeignKey(
        User, on_delete=models.CASCADE, related_name="moods")
    date = models.DateField(auto_now_add=True)
    score = models.IntegerField()  # 1...5 mood rating
    emoji = models.CharField(max_length=1)
    reflection = models.TextField(blank=True)
    # These fields will be auto-filled from reflection
    sentiment_compound = models.FloatField(
        null=True, blank=True)  # VADER compound score

    class Meta:
        verbose_name_plural = "Mood Entry"

    def __str__(self):
        return f"Mood {self.score} on {self.date}"
