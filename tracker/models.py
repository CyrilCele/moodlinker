from django.contrib.auth.models import AbstractUser
from django.db import models

from phonenumber_field.modelfields import PhoneNumberField


PERIODICITY_CHOICES = [
    ("daily", "Daily"),
    ("weekly", "Weekly"),
    ("monthly", "Monthly")
]


class User(AbstractUser):
    pass


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
        User, on_delete=models.CASCADE, related_name="profile")
    address = models.OneToOneField(
        Address, blank=True, null=True, on_delete=models.CASCADE, related_name="address")
    bio = models.TextField(blank=True)
    avatar = models.ImageField(
        upload_to="profile_pics/", null=True, blank=True)
    date_of_birth = models.DateField(null=True, blank=True)
    phone_number = PhoneNumberField(region="ZA", blank=True, null=True)
    # Can store user preferences as JSON
    preference = models.TextField(blank=True)

    def __str__(self):
        return f"{self.user.username}'s Profile."


class Habit(models.Model):
    user = models.ForeignKey(
        User, on_delete=models.CASCADE, related_name="habits")
    habit = models.CharField(max_length=100)
    description = models.TextField(blank=True)
    periodicity = models.CharField(max_length=10, choices=PERIODICITY_CHOICES)
    created_at = models.DateTimeField(auto_now_add=True)
    # Custom constraint to ensure only 5 habits are tracked per user

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["user", "habit"], name="unique_user_habit")
        ]

    def __str__(self):
        return f"Habit: {self.habit} for {self.user.username}"

    @staticmethod
    def user_habits_limit(user):
        return Habit.objects.filter(user=user).count() < 5


class MoodEntry(models.Model):
    MOOD_CHOICES = [
        (1, "😢 Sad"),
        (2, "😐 Meh"),
        (3, "😊 Happy"),
        (4, "😡 Angry"),
        (5, "😴 Tired")
    ]

    user = models.ForeignKey(User, on_delete=models.CASCADE)
    score = models.IntegerField(choices=MOOD_CHOICES)
    reflection = models.TextField(blank=True)
    date = models.DateField(auto_now_add=True)

    def __str__(self):
        return f"{self.user.username} - Mood: {self.score} on {self.date}"


class HabitCompletion(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    habit = models.ForeignKey(Habit, on_delete=models.CASCADE)
    date = models.DateField(auto_now_add=True)
    completed = models.BooleanField(default=False)

    class Meta:
        unique_together = ("user", "habit", "date")
