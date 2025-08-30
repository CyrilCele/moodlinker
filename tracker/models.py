import secrets

from django.conf import settings
from django.contrib.auth.models import AbstractUser
from django.db import models
from django.utils import timezone

from phonenumber_field.modelfields import PhoneNumberField
from zoneinfo import ZoneInfo


PERIODICITY_CHOICES = [
    ("daily", "Daily"),
    ("weekly", "Weekly"),
    ("monthly", "Monthly")
]


class User(AbstractUser):
    timezone = models.CharField(max_length=50, default="UTC")
    calendar_token = models.CharField(
        max_length=64, unique=True, blank=True, null=True
    )

    def save(self, *args, **kwargs):
        if not self.calendar_token:
            self.calendar_token = secrets.token_hex(32)
        super().save(*args, **kwargs)


class Address(models.Model):
    street_address = models.CharField(max_length=255)
    city = models.CharField(max_length=100)
    state_province = models.CharField(max_length=100, blank=True, null=True)
    postal_code = models.CharField(max_length=20)
    country = models.CharField(max_length=100)

    def __str__(self):
        return f"{self.street_address}, {self.city}, {self.country}"


class UserProfile(models.Model):
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="profile"
    )

    address = models.ForeignKey(
        Address, blank=True, null=True, on_delete=models.SET_NULL, related_name="profiles"
    )

    bio = models.TextField(blank=True)

    avatar = models.ImageField(
        upload_to="profile_pics/", null=True, blank=True
    )

    date_of_birth = models.DateField(null=True, blank=True)
    phone_number = PhoneNumberField(region="ZA", blank=True, null=True)

    # Notifications & timezone
    notify_low_mood = models.BooleanField(default=True)
    low_mood_threshold = models.PositiveSmallIntegerField(
        default=2
    )    # 1-5 scale; alert if mood <= threshold
    # e.g "America/New_York"
    timezone = models.CharField(max_length=64, default="UTC")
    reminder_hour_local = models.PositiveSmallIntegerField(
        default=9
    )   # 0-23 local time

    def tz(self) -> ZoneInfo:
        try:
            return ZoneInfo(self.timezone)
        except Exception:
            return ZoneInfo("UTC")

    def __str__(self):
        return f"{self.user.username}'s Profile."


class Notification(models.Model):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="notifications"
    )

    message = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)
    read = models.BooleanField(default=False)
    # e.g., info, warning, alert
    category = models.CharField(max_length=32, default="info")

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"Notification({self.user}): {self.message[:32]}..."


class HabitReminder(models.Model):
    """
    Tracks the next time we should remind a user for a habit (local-time aware).
    """
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="reminders"
    )

    habit = models.ForeignKey(
        "Habit", on_delete=models.CASCADE, related_name="reminders"
    )

    next_trigger_utc = models.DateTimeField()
    active = models.BooleanField(default=True)

    class Meta:
        unique_together = ("user", "habit")
        ordering = ["next_trigger_utc"]

    def __str__(self):
        return f"Reminder({self.user}, {self.habit.habit}) at {self.next_trigger_utc.isoformat()}"


class Habit(models.Model):
    user = models.ForeignKey(
        User, on_delete=models.CASCADE, related_name="habits"
    )

    habit = models.CharField(max_length=100)
    description = models.TextField(blank=True)
    periodicity = models.CharField(max_length=10, choices=PERIODICITY_CHOICES)
    created_at = models.DateTimeField(auto_now_add=True)
    # Custom constraint to ensure only 5 habits are tracked per user

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["user", "habit"], name="unique_user_habit"
            )
        ]

    def __str__(self):
        return f"Habit: {self.habit} for {self.user.username}"

    @staticmethod
    def user_habits_limit(user):
        return Habit.objects.filter(user=user).count() < 5


class MoodEntry(models.Model):
    MOOD_CHOICES = [
        (1, "1 😡 Angry"),
        (2, "2 😴 Tired"),
        (3, "3 😢 Sad"),
        (4, "4 😐 Meh"),
        (5, "5 😊 Happy")
    ]

    user = models.ForeignKey(User, on_delete=models.CASCADE)
    score = models.IntegerField(choices=MOOD_CHOICES)
    reflection = models.TextField(blank=True)
    date = models.DateField(default=timezone.now)

    class Meta:
        unique_together = ("user", "date")
        ordering = ["-date"]

    def __str__(self):
        return f"{self.user.username} - Mood: {self.score} on {self.date}"


class HabitCompletion(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    habit = models.ForeignKey(Habit, on_delete=models.CASCADE)
    date = models.DateField(auto_now_add=True)
    completed = models.BooleanField(default=False)

    class Meta:
        unique_together = ("user", "habit", "date")
        ordering = ["-date"]
