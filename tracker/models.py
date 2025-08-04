from django.contrib.auth.models import AbstractUser
from django.db import models


class User(AbstractUser):
    pass


class UserProfile(models.Model):
    user = models.OneToOneField(
        User, on_delete=models.CASCADE, related_name="profile")
    bio = models.TextField(blank=True)
    avatar = models.ImageField(
        upload_to="profile_pics/", null=True, blank=True)
    date_of_birth = models.DateField(null=True, blank=True)
    # Can store user preferences as JSON
    preference = models.TextField(blank=True)

    def __str__(self):
        return f"{self.user.username}'s Profile."


PERIODICITY_CHOICES = [
    ("daily", "Daily"),
    ("weekly", "Weekly"),
    ("monthly", "Monthly")
]


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
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    score = models.IntegerField(choices=[(i, str(i)) for i in range(1, 6)])
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
