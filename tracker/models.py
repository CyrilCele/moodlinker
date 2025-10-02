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
    """
    Custom User model.

    Fields:
        timezone (str): IANA timezone name (e.g., "Africa/Johannesburg"). Defaults to "UTC".
        calendar_token (str|None): Unique hex token for ICS calendar access. Auto-generated
            on first save if blank.

    Notes:
        - `calendar_token` is used as a bearer token in URLs; keep it secret.
        - For SSO/custom auth, ensure this model remains the `AUTH_USER_MODEL`.
    """
    timezone = models.CharField(max_length=50, default="UTC")
    calendar_token = models.CharField(
        max_length=64, unique=True, blank=True, null=True
    )

    def save(self, *args, **kwargs):
        """
        Persisit the user, ensuring a unique `calendar_token` exists.

        Behavior:
            - If `calendar_token` is falsy, generates a 64-char hex token via
              `secrets.token_hex(32)` before calling the parent `save()`.

        Args:
            *args: Positional args passed to Django's `Model.save`.
            **kwargs: Keyword args passed to Django's `Model.save`.

        Returns
            None

        Raises:
            IntegrityError: If the generated token collides (extremely unlikely) and violates
                the unique constraint on `calendar_token`.
            Exception: Any other database/backend error from `super().save`.

        Example:
            >>> user = User(username="cyril")
            >>> user.save() # calendar_token auto-populates
            >>> assert user.calendar_token is not None

        Important:
            - Token is only generated if empty; it remains stable across edits.
            - If you ever need to rotate the token, explicitly set `calendar_token=None`
              and call `save()`.
        """
        if not self.calendar_token:
            self.calendar_token = secrets.token_hex(32)
        super().save(*args, **kwargs)


class Address(models.Model):
    """
    Postal address (optional for UserProfile).

    Fields:
        street_address (str)
        city (str)
        state_province (str|None)
        postal_code (str)
        country (str)

    Notes:
        - Keep as a separate entity so multiple profiles in future could reference
          shared addresses, and to allow nullability independently of the profile.
    """
    street_address = models.CharField(max_length=255)
    city = models.CharField(max_length=100)
    state_province = models.CharField(max_length=100, blank=True, null=True)
    postal_code = models.CharField(max_length=20)
    country = models.CharField(max_length=100)

    def __str__(self):
        """
        Human-friendly one-line address.

        Returns:
            str: "<street>, <city>, <country>"

        Example:
            "123 Main St, Durban, South Africa"
        """
        return f"{self.street_address}, {self.city}, {self.country}"


class UserProfile(models.Model):
    """
    Extended profile data and notification settings for a user.

    Fields:
        user (OneToOne[user]): Owner of this profile.
        address (ForeignKey[Address]|None): Optional address.
        bio (str): Freeform text.
        avatar (ImageField|None): Upload profile image.
        date_of_birth (date|None)
        phone_number (PhoneNumberField|None): ZA region validation.

        notify_low_mood (bool): If True, send low mood alerts.
        low_mood_threshold (int): Inclusive threshold on 1-5 scale to trigger alerts.
        timezone (str): IANA timezone (e.g., "Africa/Johannesburg").
        reminder_hour_local (int): Hour of day (0-23) for habit reminders in local time.

    Notes:
        - `tz()` helper converts the stored timezone string into a `ZoneInfo`.
        - Keep profile creation in sync via signals to guarantee existence.
    """
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
    # e.g "Africa/Johannesburg"
    timezone = models.CharField(max_length=64, default="UTC")
    reminder_hour_local = models.PositiveSmallIntegerField(
        default=9
    )   # 0-23 local time

    def tz(self) -> ZoneInfo:
        """
        Resolve the profile's timezone string to a `ZoneInfo` object.

        Returns:
            ZoneInfo: The user's timezone object. Falls back to UTC on error.

        Raises:
            None (errors are swallowed and UTC is returned).

        Example:
            >>> profile.tz()
            ZoneInfo(key="Africa/Johannesburg")

        Important:
            - If `self.timezone` is invalid or unknown, this returns UTC to prevent crashes.
            - Prefer valid IANA TZ names; consider enforcing choices or validation.
        """
        try:
            return ZoneInfo(self.timezone)
        except Exception:
            return ZoneInfo("UTC")

    def __str__(self):
        """
        Human-readable representation.

        Returns:
            str: "<username>'s Profile."
        """
        return f"{self.user.username}'s Profile."


class Notification(models.Model):
    """
    In-app notification record (optionally mirrored via email).

    Fields:
        user (ForeignKey[User]): Recipient.
        message (str): Notification content.
        created_at (datetime): Auto-set when created.
        read (bool): Has the user read it?
        category (str): e.g., "info", "warning", "alert".

    Meta:
        ordering: newest first (`-created_at`).

    Usage:
        - Created via services/tasks (e.g., reminder sends, low mood alerts).
    """
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
        """
        Short preview string.

        Returns:
            str: "Notification({self.user}): <first 32 chars>..."
        """
        return f"Notification({self.user}): {self.message[:32]}..."


class HabitReminder(models.Model):
    """
    Next scheduled time to remind a user about a habit (stored in UTC).

    Fields:
        user (ForeignKey[User]): Owner of the reminder.
        habit (ForeignKey[Habit]): The habit to nudge.
        next_trigger_utc (datetime): UTC instant when next reminder should fire.
        active (bool): If False, ignore this reminder.

    Meta:
        unique_together: (user, habit) - at most one reminder per habit per user.
        ordering: by `next_trigger_utc` ascending.
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
        """
        Readable summary.

        Returns:
            str: "Reminder(<user>, <habit>) at <iso-utc>"
        """
        return f"Reminder({self.user}, {self.habit.habit}) at {self.next_trigger_utc.isoformat()}"


class Habit(models.Model):
    """
    A tracked habit for a user.

    Fields:
        user (ForeignKey[User]): Owner.
        habit (str): Short display name (<=100 chars).
        description (str): Optional details.
        periodicity (str): One of PERIODICITY_CHOICES ("daily", "weekly", "monthly").
        created_at (datetime): Auto-set timestamp.

    Meta:
        constraints:
            - unique_user_habit: (user, habit) must be unique to avoid duplicates.

    Notes:
        - Business rule: app-level limit of 5 habits per user (see `user_habits_limit`).
          This is intentionally enforced in code, not in the DB.
    """
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
        """
        Human-friendly label.

        Returns:
            str: "Habit: <habit> for <username>"
        """
        return f"Habit: {self.habit} for {self.user.username}"

    @staticmethod
    def user_habits_limit(user):
        """
        Check whether the user can create another habit (max 5).

        Args:
            user (User): Target user.

        Returns:
            bool: True if the user currently tracks fewer than 5 habits; otherwise False.

        Example:
            >>> if Habit.user_habits_limit(request.user):
            ...     Habit.objects.create(user=request.user, habit="Read 5 pages", periodicity="daily")
            ... else:
            ...     raise ValidationError("Limit of 5 habits reached.")

        Notes:
            - This is not a hard databese constraint; it should be checked in forms/views/services
              to enforce the rule.
            - For absolute enforcement, consider soft blocks in business logic plus monitoring.
        """
        return Habit.objects.filter(user=user).count() < 5


class MoodEntry(models.Model):
    """
    A user's mood for a given day.

    Fields:
        user (ForeignKey[User])
        score (int): One of MOOD_CHOICES (1...5).
        reflection (str): Optional text.
        date (date): Logical day of the mood entry. Defaults to `timezone.now` (date portion).

    Meta:
        unique_together: (user, date) - at most one mood per user per day.
        ordering: newest date first.

    Notes:
        - `date` uses the server's current date by default; if you need user-local dates,
          normalize on save (e.g., using the user's timezone).
    """
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
        """
        Concise description.

        Returns:
            str: "<username> - Mood: <score> on <YYYY-MM-DD>"
        """
        return f"{self.user.username} - Mood: {self.score} on {self.date}"


class HabitCompletion(models.Model):
    """
    Daily completition status for a user's habit.

    Fields:
        user (ForeignKey[User])
        habit (ForeignKey[Habit])
        date (date): Auto-set on creation (server date).
        completed (bool): Whether the habit was completed for that day.

    Meta:
        unique_together: (user, habit, date) - prevents duplicate daily rows.
        ordering: newest date first.

    Usage:
        - Used to compute streaks, completion rates, and drive analytics.
    """
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    habit = models.ForeignKey(Habit, on_delete=models.CASCADE)
    date = models.DateField(default=timezone.now)
    completed = models.BooleanField(default=False)

    class Meta:
        unique_together = ("user", "habit", "date")
        ordering = ["-date"]

    def __str__(self):
        return f"{self.user.username} - {self.habit.habit} on {self.date}: {'Done' if self.completed else 'Not Done'}"
