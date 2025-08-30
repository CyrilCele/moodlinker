"""
Celery tasks and helpers for MoodLinker notifications and habit reminders.

This module centralizes:
- Timezone-aware scheduling of habit reminders.
- In-app + email notifications (low mood alerts, habit nudges).
- Periodic processing of due reminders and nightly rebuilds.

Key concepts:
- All scheduling uses the **user's local time** to compute the next HH:00,
  then converts that instant to UTC to store in `HabitReminder.next_trigger_utc`.
- Celery tasks are idempotent(ish) and defensive: if required rows or profiles
  are missing, they no-op rather than crash.
- Email sending is funneled through `send_reminder_email` to keep a single SMTP path.
"""

from celery import shared_task
from datetime import datetime, timedelta, time as dtime

from django.conf import settings
from django.core.mail import send_mail
from django.utils import timezone

from tracker.models import (
    Notification, HabitReminder, Habit, MoodEntry, UserProfile
)

from zoneinfo import ZoneInfo


def _now_utc():
    """
    Get the current timezone-aware UTC datetime.

    Returns:
        datetime: The current UTC time (`timezone.now()`), timezone-aware.

    Notes:
        - Wrapper for testability/mocking in unit tests.
        - All scheduling comparisons are performed against UTC.
    """
    return timezone.now()


def _user_local_now(profile: UserProfile):
    """
    Get the current time in the user's local timezone.

    Args:
        profile (UserProfile): The user's profile that exposes `tz()` returning
            a `tzinfo` (e.g., `zoneinfo.ZoneInfo`) for the user's timezone.

    Returns:
        datetime: Current time localized to the user's timezone, timezone-aware.

    Raises:
        AttributeError: If `profile.tz()` is missing or returns `None`.

    Example:
        >>> local_now = _user_local_now(request.user.profile)
        >>> local_now.tzinfo.key
        'Africa/Johannesburg'

    Notes:
        - Assumes `profile.tz()` returns a valid tzinfo instance.
        - Prefer `zoneinfo.ZoneInfo` over `pytz` for Python 3.9+.
    """
    return _now_utc().astimezone((profile.tz()))


def _build_next_local_dt(profile: UserProfile, hour: int) -> datetime:
    """
    Compute the next occurrence of HH:00 in the user's local timezone and return it as UTC.

    The function picks either **today at HH:00** (if still in the future) or
    **tomorrow at HH:00** (if today HH:00 has already passed), then converts the
    resulting local time to a UTC-aware datetime.

    Args:
        profile (UserProfile): User profile providing `tz()` -> tzinfo (local TZ).
        hour (int): Local hour (0-23) for the reminder.

    Returns:
        datetime: The next trigger time as a timezone-aware UTC datetime.

    Raises:
        ValueError: If `hour` is not in the range 0..23.
        AttributeError: If `profile.tz()` is missing/invalid.

    Example:
        >>> _build_next_local_dt(profile, 20) # 8 PM local, as UTC
        datetime(2025, 8, 30, 18, 0, tzinfo=zoneinfo.ZoneInfo('UTC'))

    Edge Cases:
        - **DST transitions.** Using `ZoneInfo`, constructing a wall clock
          datetime may be ambiguous/nonexisting around DST changes. The direct
          `tzinfo=` attach uses `fold=0` by default. If you need stricter handling,
          consider computing by date + hour and letting the conversion resolve.
        - If the user's TZ changes between calls, the next computed UTC instant
          will reflect the new TZ.

    Implementation:
        1) Get the user's local "now".
        2) Build a local datetime at HH:00 for today.
        3) If that instant has passed, add one day.
        4) Convert to UTC and return.
    """
    if not (0 <= hour <= 23):
        raise ValueError("Hour must be in 0..23")

    local_now = _user_local_now(profile)

    # Construct the *local* target at HH:00 (no minutes/seconds).
    candidate = datetime.combine(
        local_now.date(), dtime(hour=hour), tzinfo=profile.tz()
    )

    # If already passed for today, move to tomorrow.
    if candidate <= local_now:
        candidate += timedelta(days=1)

    # Convert the local wall time to a UTC instant for storage/comparison.
    return candidate.astimezone(ZoneInfo("UTC"))


def send_reminder_email(to_email: str, subject: str, message: str):
    """
    Send a plain-text email using the project's configured email backend.

    Centralizes outbound email so templates/backends can be changed in one place.

    Args:
        to_email (str): Recipient email address.
        subject (str): Email subject line.
        message (str): Plain-text email body.

    Returns:
        int: Number of successfully delivered messages (Django's `send_mail` return).

    Raises:
        django.core.mail.BadHeaderError: If headers are invalid.
        smtplib.SMTPException: For SMTP transport-level features.
        django.core.exceptions.ImproperlyConfigured: If email backend/settings are invalid.

    Example:
        >>> send_reminder_email("user@example.com", "Hello", "Keep going!")

    Notes:
        - `fail_silently=False` is used to surface issues in logs/monitoring.
        - For HTML emails or templates, extend this function accordingly.
    """
    send_mail(
        subject=subject,
        message=message,
        from_email=settings.DEFAULT_FROM_EMAIL,
        recipient_list=[to_email],
        fail_silently=False
    )


def _notify(
        user,
        message: str,
        category="info",
        email=False,
        subject="MoodLinker Notification"
):
    """
    Create in-app notification and optionally send email.

    Args:
        user (User): The recipient user model instance.
        message (str): Notification body text.
        category (str, optional): Category/severity label (e.g., 'info', 'warning').
            Defaults to "info".
        email (bool, optional): If True and `user.email` exists, send an email copy.
            Defaults to False.
        subject (str, optional): Email subject if `email=True`. Defaults to
            "MoodLinker Notification".

    Returns:
        None

    Raises:
        Exception: Any DB/SMTP exceptions propagate if underlying calls fail.

    Example:
        >>> _notify(request.user, "Great job today!", category="info", email=True)

    Notes:
        - In-app and email notifications are intentionally decoupled: the in-app
          record is created regardless of email state, unless an exception occurs.
        - Consider wrapping in a transaction if you require atomicity across DB + SMTP.
    """
    Notification.objects.create(user=user, message=message, category=category)

    # Only send email if requested and we have a recipient address.
    if email and user.email:
        send_reminder_email(user.email, subject, message)


@shared_task
def send_low_mood_alert(user_id: int, entry_id: int):
    """
    Task: Send a low mood alert if today's mood breaches the user's threshold.

    Args:
        user_id (int): ID of the mood author's User.
        entry_id (int): ID of the `MoodEntry` row for today.

    Returns:
        None

    Raises:
        None (task is defensive and returns on missing data).

    Example:
        >>> send_low_mood_alert.delay(user.id, mood_entry.id)

    Logic:
        1) Load the mood entry and the user's profile; silently return missing.
        2) Check `profile.notify_low_mood`; if disabled, return.
        3) If `entry.score <= profile.low_mood_threshold`, create a warning
           notification and send an email.

    Edge Cases:
        - If multiple mood entries exist for the same day (shouldn't), this task
          assumes the given `entry_id` is authoritative.
        - If the user's email is missing, only the in-app notification is recorded.
    """
    try:
        entry = MoodEntry.objects.get(id=entry_id, user_id=user_id)
        profile = entry.user.profile
    except (MoodEntry.DoesNotExist, UserProfile.DoesNotExist):
        return

    if not profile.notify_low_mood:
        return

    # Only alert if it truly violates the threshold
    if entry.score <= profile.low_mood_threshold:
        _notify(
            entry.user,
            f"Your mood today was {entry.score}. Be kind to yourself - try a small, gentle habit.",
            category="warning",
            email=True,
            subject="Low Mood Alert"
        )


@shared_task
def schedule_user_habit_reminders(user_id: int):
    """
    Task: For each of the user's habits, create/update a HabitReminder to the next local reminder time.

    Args:
        user_id (int): ID of the target user.

    Returns:
        None

    Raises:
        None (broad ecxceptions are swallowed to keep the task resilient).
        Prefer narrowing to `User.DoesNotExist`/`UserProfile.DoesNotExist` in future.

    Example:
        >>> schedule_user_habit_reminders.delay(request.user.id)

    Logic:
        1) Fetch the user + profile.
        2) Iterate the user's habits.
        3) Compute the next local HH:00 (using `profile.reminder_hour_local`), convert to UTC.
        4) `update_or_create` the `HabitReminder` with the next UTC trigger and set active=True.

    Edge Cases:
        - If `profile.reminder_hour_local` is out of range or missing, this may raise.
        - If the user has no habits, nothing is created.
        - TZ changes will affect the next scheduled UTC instant.
    """
    from django.contrib.auth import get_user_model

    try:
        User = get_user_model()
        user = User.objects.get(id=user_id)
        profile = user.profile
    except Exception:
        # Intentionally quiet: user/profile may have been deleted between scheduling and run.
        return

    habits = Habit.objects.filter(user=user)
    for habit in habits:
        next_utc = _build_next_local_dt(profile, profile.reminder_hour_local)
        HabitReminder.objects.update_or_create(
            user=user,
            habit=habit,
            defaults={"next_trigger_utc": next_utc, "active": True}
        )


@shared_task
def process_due_reminders():
    """
    Task (Celery Beat, every minute): Send due habit reminders and reschedule for the next day.

    Returns:
        None

    Example (Celery Beat schedule):
        # run every minute
        app.conf.beat_schedule = {
            "process-due-reminders": {
                "task": "tracker.tasks.process_due_reminders",
                "schedule": crontab(), # or schedule(60.0)
            }
        }

    Logic:
        1) Get current UTC time (`now`)
        2) Select all active `HabitReminder` rows with `next_trigger_utc <= now`.
        3) For each:
            a. Send an in-app + email reminder via `_notify`.
            b. Reschedule `next_trigger_utc` to tomorrow at the user's local reminder hour,
               converted back to UTC. If the user profile is missing, fallback to +24h.
            c. Save only the field that changed (`update_fields=["next_trigger_utc"]`).

    Edge Cases:
        - **Double sends** can occur if multiple workers pick up the same row at the
            same time. See improvements section for locking/atomic update suggestions.
        - If the user's timezone or reminder hour changes between cycles, the next
            trigger will reflect the *new* settings upon rescheduling.

    """
    now = _now_utc()

    # Select only due reminders, and pull related objects to avoid N+1 queries.
    due = (HabitReminder.objects
           .select_related("user", "habit", "user__profile")
           .filter(active=True, next_trigger_utc__lte=now))

    for reminder in due:
        # 1) Send reminder (in-app + email).
        _notify(
            reminder.user,
            f"Reminder: '{reminder.habit.habit}' - a tiny step today goes a long way.",
            category="info",
            email=True,
            subject="Habit Reminder"
        )

        # 2) Reschedule to next local occurrence. If user/profile missing, fallback.
        try:
            profile = reminder.user.profile
        except UserProfile.DoesNotExist:
            profile = None

        if profile:
            reminder.next_trigger_utc = _build_next_local_dt(
                profile, profile.reminder_hour_local
            )
        else:
            # Fallback keeps cadence but ignores TZ nuance.
            reminder.next_trigger_utc = now + timedelta(days=1)

        reminder.save(update_fields=["next_trigger_utc"])


@shared_task
def rebuild_all_user_reminders():
    """
    Task (nightly): Ensure every user's habits have up-to-date reminder rows.

    Returns:
        None

    Example (Celery Beat schedule):
        app.conf.beat_schedule = {
            "rebuild-reminders-nightly": {
                "task": "tracker.tasks.rebuild_all_user_reminders",
                "schedule": crontab(minute=0, hour=2) # nightly at 02:00
            }
        }

    Logic:
        - Iterate all users and enqueue `schedule_user_habit_reminders` for each.

    Notes:
        - This fans out N tasks for N users (scales better than doing all work in a single task).
        - If you have many users, consider batching/chunking to smooth queue load.
    """
    from django.contrib.auth import get_user_model
    User = get_user_model()

    for user in User.objects.all():
        schedule_user_habit_reminders.delay(user.id)


# This is for demo purposes: goes with the Gmail SMTP
@shared_task
def send_mood_reminder(user_email, mood_level):
    """
    Task (demo): Send a simple mood reminder email based on the mood level.

    Args:
        user_email (str): Recipient email address.
        mood_level (int|float): Mood score; lower values trigger supportive message.

    Returns:
        None

    Example:
        >>> send_mood_reminder.delay("user@example.com", 2)

    Behavior:
        - If `mood_level < 3`, sends an encouraging, supportive nudge.
        - Otherwise, sends a positive reinforcement message.

    Notes:
        - Intended for demo/testing. For production, consider templated, localized emails.
        - Emojis require UTF-8; ensure your email backend is configured accordingly.
    """
    subject = "MoodLinker Reminder"
    if mood_level < 3:
        message = (
            "We noticed your mood has been low."
            "Try completing a habit today - it may lift your spirits! 💙"
        )
    else:
        message = "Keep up the good work! Stay consistent with your habits 🙌"

    send_reminder_email(user_email, subject, message)
