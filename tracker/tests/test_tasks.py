"""
Behavioral tests for Celery tasks and scheduling utilities in tasks.

Covered units:
    - `_build_next_local_dt(profile, hour)`: compute the next local datetime for a reminder.
    - `send_low_mood_alert(user_id, mood_entry_id)`: notify users when mood is below threshold.
    - `schedule_user_habit_reminders(user_id)`: (re)build user habit reminders.
    - `process_due_reminders()`: dispatch pending reminders and reschedule the next run.
    - `send_mood_reminder(email, score)`: send a templated mood reminder email.

Key testing notes:
    - We patch the import location used inside `tracker.tasks` (e.g. `tracker.tasks._notify`)
      so that real external effects (emails, integrations) are not triggered during tests.
    - Date/time checks use Django's timezone utilities and profile time zones to avoid
      DST/UTC pitfalls. Where necessary, we assert on local dates.
"""

from datetime import datetime, timedelta
from unittest.mock import patch

import pytest
from django.utils import timezone

from tracker.models import UserProfile, MoodEntry, Habit, HabitReminder
from tracker.tasks import (
    send_low_mood_alert,
    schedule_user_habit_reminders,
    process_due_reminders,
    send_mood_reminder,
    _build_next_local_dt
)


# ---------- FIXTURES ----------


@pytest.fixture
def user(db, django_user_model):
    """
    Create a user with a fully initialized profile suitable for reminder tests.

    The profile fields (timezone, notify settings, and reminder hour) are
    set explicitly to ensure deterministic behavior across test runs.
    """
    user = django_user_model.objects.create_user(
        username="tester", email="user@email.com", password="Pass123"
    )
    # Ensure the profile exists with desired defaults. `get_or_create` helps
    # when signals already created one.
    profile, _ = UserProfile.objects.get_or_create(
        user=user,
        defaults={
            "timezone": "UTC",
            "notify_low_mood": True,
            "low_mood_threshold": 2,
            "reminder_hour_local": 9
        }
    )
    # Normalize critical fields even if an existing profile was found.
    profile.timezone = "UTC"
    profile.notify_low_mood = True
    profile.low_mood_threshold = 2
    profile.reminder_hour_local = 9
    profile.save()
    return user


@pytest.fixture
def habit(user):
    """A simple daily habit for the authenticated user."""
    return Habit.objects.create(user=user, habit="Drink Water", periodicity="daily")


@pytest.fixture
def today():
    """Today's date in the current timezone (date-only, no time)."""
    return timezone.localdate()


# ---------- UTILITY TESTS ----------


def test_build_next_local_dt_future_today(user):
    """
    When the requested hour is in the future relative to the user's local time,
    `_build_next_local_dt` should return a datetime later today.
    """
    profile = user.profile
    # Compute current local time for the user profile's timezone.
    local_now = timezone.now().astimezone(profile.tz())
    # Pick an hour one hour ahead to ensure its later today.
    hour = (local_now.hour + 1) % 24

    next_dt = _build_next_local_dt(profile, hour)

    # Returned value should be in the future relative to "now" (UTC-aware).
    assert next_dt > timezone.now(), "Next datetime should be in the future today."


def test_build_next_local_dt_passed_hour_tomorrow(user):
    """
    When the requestd hour has already passed in the user's local time,
    `_build_next_local_dt` should return tomorrow at the specified hour.
    """
    profile = user.profile
    local_now = timezone.now().astimezone(profile.tz())
    # Pick an hour that already passed to force "tomorrow".
    hour = (local_now.hour - 1) % 24

    next_dt = _build_next_local_dt(profile, hour)
    local_next = next_dt.astimezone(profile.tz())

    # Expect the scheduled date to be "tomorrow" in the user's local timezone.
    assert local_next.date() == (local_now + timedelta(days=1)).date(), \
        "Past-hour scheduling should fail on tomorrow (local date)."


# ---------- SEND LOW MOOD ALERT ----------


@pytest.mark.django_db
@patch("tracker.tasks._notify")
def test_send_low_mood_alert_triggers_notification(mock_notify, user, today):
    """
    Low mood (score below threshold) should trigger a notification via `_notify`.
    """
    mood = MoodEntry.objects.create(user=user, date=today, score=1)

    send_low_mood_alert(user.id, mood.id)

    mock_notify.assert_called_once()
    args, kwargs = mock_notify.call_args
    # args[1] is the message content (implementation detail of `_notify` in tasks).
    assert "Be kind to yourself" in args[1]
    # Email channel should be enabled for alerts.
    assert kwargs.get("email") is True


@pytest.mark.django_db
@patch("tracker.tasks._notify")
def test_send_low_mood_alert_no_trigger_above_threshold(mock_notify, user, today):
    """
    High mood (>= threshold) should NOT trigger a notification.
    """
    mood = MoodEntry.objects.create(user=user, date=today, score=5)

    send_low_mood_alert(user.id, mood.id)

    mock_notify.assert_not_called()


@pytest.mark.django_db
def test_send_low_mood_alert_invalid_entry(user):
    """
    Passing a non-existent mood_entry_id should not raise an exception.
    The task should fail fast and exit quietly.
    """
    # Non-existent primary key should be handled gracefully.
    send_low_mood_alert(user.id, 9999)


# ---------- SCHEDULE USER HABIT REMINDERS ----------


@pytest.mark.django_db
def test_schedule_user_habit_reminders_creates_entries(user, habit):
    """
    When a user has a habit but no reminders, scheduling should create one,
    set it to active, and compute an initial next_trigger_utc.
    """
    schedule_user_habit_reminders(user.id)
    reminder = HabitReminder.objects.get(user=user, habit=habit)

    assert reminder.active is True
    assert reminder.next_trigger_utc is not None


@pytest.mark.django_db
def test_schedule_user_habit_reminders_updates_existing(user, habit):
    """
    If a reminder already exists (even inactive or stale), the scheduler
    should update it to active with a next run in the future.
    """
    # Create a stale/inactive reminder.
    old_reminder = HabitReminder.objects.create(
        user=user,
        habit=habit,
        next_trigger_utc=timezone.now() - timedelta(days=1),
        active=False
    )

    schedule_user_habit_reminders(user.id)
    old_reminder.refresh_from_db()

    assert old_reminder.active is True
    assert old_reminder.next_trigger_utc > timezone.now()


# ---------- PROCESS DUE REMINDERS ----------


@pytest.mark.django_db
@patch("tracker.tasks._notify")
def test_process_due_reminders_sends_and_reschedules(mock_notify, user, habit):
    """
    A due reminder should be delivered via `_notify` and rescheduled into the future.
    """
    next_trigger = timezone.now() - timedelta(minutes=1)  # already due
    reminder = HabitReminder.objects.create(
        user=user,
        habit=habit,
        next_trigger_utc=next_trigger,
        active=True
    )

    process_due_reminders()

    reminder.refresh_from_db()
    mock_notify.assert_called_once()
    assert reminder.next_trigger_utc > timezone.now(), \
        "Next trigger must be pushed into the future after sending."


@pytest.mark.django_db
@patch("tracker.tasks._notify")
def test_processes_due_reminders_handles_no_profile(mock_notify, user, habit):
    """
    If a user profile is missing, the task should still send the reminder
    and choose a safe fallback (usually UTC, next day) for scheduling.
    """
    # Remove the profile to simulate a data edge case.
    user.profile.delete()

    reminder = HabitReminder.objects.create(
        user=user,
        habit=habit,
        next_trigger_utc=timezone.now() - timedelta(minutes=1),
        active=True
    )

    process_due_reminders()

    reminder.refresh_from_db()
    mock_notify.assert_called_once()
    assert reminder.next_trigger_utc.date() == \
        (timezone.now() + timedelta(days=1)).date(), \
        "Fallback reschedule should land on the next day when profile data is missing."


# ---------- SEND MOOD REMINDER ----------


@pytest.mark.django_db
@patch("tracker.tasks.send_reminder_email")
def test_send_mood_reminder_calls_service(mock_send, user):
    """
    `send_mood_reminder` should call the email service with message content appropriate
    to the mood "score" (e.g., supportive for low, reinforcing for high).
    """
    # Low mood path
    send_mood_reminder(user.email, 1)
    mock_send.assert_called_once()
    args, kwargs = mock_send.call_args
    # args[2] is the email body in the current implementation.
    assert "low" in args[2].lower() or "lift your spirits" in args[2]

    # High mood path
    mock_send.reset_mock()
    send_mood_reminder(user.email, 4)
    mock_send.assert_called_once()
    args, kwargs = mock_send.call_args
    assert "keep up" in args[2].lower() or "good work" in args[2]
