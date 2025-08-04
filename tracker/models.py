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
    preference = models.TextField(max_length=250, blank=True)

    def __str__(self):
        return f"{self.user.username}'s Profile."
