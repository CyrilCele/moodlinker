"""
Signal handlers for user/profile, mood entry, and habit lifecycle events.

Responsibilities:
- Auto-create user profiles when a new User is created.
- Save the related profile when a User is saved.
- Trigger a low-mood alert (Celery task) when a MoodEntry for today is created.
- Rebuild/schedule habit reminders (Celery task) when a Habit is created , updated, or deleted.

Notes:
- These handlers are intentionally conservative: they avoid raising on missing
  records and rely on Celery tasks for background work (resilient to transient failures).
- Consider using dispatch_uid on @reciever registrations to avoid duplicate handlers
  when Django reloads modules in dev.
"""

from django.conf import settings
from django.db.models.signals import post_save, post_delete
from django.dispatch import receiver
from django.utils import timezone

from tracker.models import User, UserProfile, MoodEntry, Habit
from tracker.tasks import send_low_mood_alert, schedule_user_habit_reminders


@receiver(post_save, sender=settings.AUTH_USER_MODEL)
def create_user_profile(sender, instance, created, **kwargs):
    """
    Create a UserProfile automatically when a new User is created.

    Description:
        Called on the `post_save` signal for the configured auth user model.
        If `created` is True, creates a `UserProfile` instance tied to the new user.

    Parameters:
        sender (Model): The model class that sent the signal (AUTH_USER_MODEL).
        instance (User): The user model instance that was saved.
        created (bool): True if a new user was created (not just updated).
        **kwargs (dict): Additional signal kwargs (e.g., `raw`, `using`, `updated_fields`).

    Returns:
        None - side-effect function (creates a UserProfile row).

    Exceptions:
        - IntegrityError/DatabaseError: If a profile for that user already exists or
          DB write fails. This can happen in race conditions.
        - AttributeError: If the expected models/fields are missing (rare).

    Example usage (implicit):
        Creating a new user in Django admin or via `User.objects.create_user(...)`
        will automatically cause this receiver to run and create the profile.

    Important notes / edge-cases:
        - Race condition: If two processes create the same user concurrently or if
          another process also tries to create a profile, `.create()` may raise
          an IntegrityError. Using `get_or_create()` or wrapping this in a
          transaction is safer for high-concurrency environments.
        - The sender is `settings.AUTH_USER_MODEL` to support custom user models.
        - To prevent double-registration during module reloads, consider supplying
          `dispatch_uid` to the @receiver decorator.
    """
    if created:
        # Simple creation; may raise IntegrityError under race conditions.
        UserProfile.objects.create(user=instance)


@receiver(post_save, sender=User)
def save_user_profile(sender, instance, **kwargs):
    """
    Ensure the user's profile is saved when the User model is saved.

    Description:
        Called on `post_save` for the concrete `User` model (imported above).
        This saves the `instance.profile` to persist any derived/related profile changes
        that should follow a user save. This pattern is commonly used when profile
        fields are written via signals or when `user.save()` must propagate changes.

    Parameters:
        sender (Model): The `User` model class.
        instance (User): The user instance that was saved.
        **kwargs (dict): Additional signal kwargs.

    Returns:
        None

    Exceptions:
        - UserProfile.DoesNotExist: If the profile does not exist (rare if create_user_profile works).
        - Other DB exceptions from calling `profile.save()`.

    Example:
        When an admin edits a user in the Django admin, the profile save hook runs
        right after the user save.

    Important notes / edge-cases:
        - If a profile was not created (e.g., `create_user_profile` failed earlier),
          `instance.profile` will raise `UserProfile.DoesNotExist`. You can defensively
          guard this with `hasattr(instance, "profile")` or try/except.
        - Consider using `get_user_model()` consistently to avoid missing `User` imports
          and setting `settings.AUTH_USER_MODEL` as senders. Mixing can confuse signal registration
          if a custom user model is used.
    """
    # Defensive real-world alternative:
    # try:
    #     instance.profile.save()
    # except UserProfile.DoesNotExist:
    #     UserProfile.objects.create(user=instance)

    instance.profile.save()


@receiver(post_save, sender=MoodEntry)
def on_mood_saved(sender, instance: MoodEntry, created, **kwargs):
    """
    Trigger a low-mood alert task when a new MoodEntry is created for today.

    Description:
        Runs after a MoodEntry is saved. If the entry is newly created (`created=True`)
        and the entry's `date` matches the current date (server timezone), the handler
        enqueues `send_low_mood_alert` as a Celery background task.

    Parameters:
        sender (Model): The MoodEntry model class.
        instance (MoodEntry): The MoodEntry instance that was saved.
        created (bool): True if a new entry was created (not just updated).
        **kwargs (dict): Additional signal kwargs.

    Returns:
        None

    Exceptions:
        - AttributeError / FieldError: If `instance.date` does not exist or uses unexpected type.
        - Celery exceptions: If the broker is down, `.delay()` will raise at enqueue time
          (but usually Celery's client raises only when misconfigured).

    Example usage:
        >>> mood = MoodEntry.objects.create(user=user, date=date.today(), score=2)
        >>> # send_low_mood_alert will be scheduled automatically

    Important notes / edge-cases:
        - Timezone semantics: The comparison uses `timezone.now().date()` (server current date).
          If `MoodEntry.date` stores a user-local date or naive date, you may get mismatches.
          For robust behavior consider comparing using the user's timezone (profile.tz()).
        - Only checks `created` to avoid duplicate alerts on updates. If you want alerts on
          score changes after creation, you must compare prior vs new values (requires tracking).
        - If multiple entries for the same day exist, this will act only for the specific
          `instance.id` enqueued; business logic should ensure only one mood per day per user.
    """
    # Only alert on creation and only if the entry is for "today" (server date).
    if created and instance.date == timezone.now().date():
        send_low_mood_alert.delay(instance.user_id, instance.id)


@receiver([post_save, post_delete], sender=Habit)
def on_habit_changed(sender, instance: Habit, **kwargs):
    """
    Enqueue a job to (re)schedule habit reminders when a Habit changes.

    Description:
        Listens to both `post_save` and `post_delete` for the Habit model.
        When a Habit is created, updated, or deleted, we schedule a background
        job `schedule_user_habit_reminders` to (re)compute the user's habit reminders.

    Parameters:
        sender (Model): The Habit model class.
        instance (Habit): The Habit instance that was saved or deleted.
        **kwargs (dict): Additional signal kwargs, including `created` for post_save.

    Returns:
        None

    Exceptions:
        - AttributeError: If `instance.user_id` is not available (rare).
        - Celery enqueue errors if the broker is misconfigured.

    Example:
        >>> habit = Habit.objects.create(user=user, habit="30 pushups")
        >>> # schedule_user_habit_reminders will be enqueued automatically

    Important notes / edge-cases:
        - When a Habit is deleted, `instance.user_id` is usually still present on the instance;
          however, relying on many fields after delete can be brittle. Defensive code might use
          `getattr(instance, "user_id", None)` and bail if None.
        - This naively enqueues one task per habit change. Rapi updates (or bulk operations)
          can enqueue many tasks. Consider debouncing or batched schedulimg for high-volume operations.
        - The handler assumes `schedule_user_habot_reminders` is idempotent and safe to call multiple times.
    """
    # Defensive alternative:
    # user_id = getattr(instance, "user_id", None):
    # if user_id is not None:
    #       schedule_user_habit_reminders.delay(user_id)

    schedule_user_habit_reminders.delay(instance.user_id)
