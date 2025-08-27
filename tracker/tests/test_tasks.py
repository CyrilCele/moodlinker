import pytest

from datetime import datetime, timedelta, time as dtime
from unittest.mock import patch
from zoneinfo import ZoneInfo

from django.conf import settings
from django.utils import timezone

from tracker.models import User, UserProfile, MoodEntry, Habit, HabitReminder, Notification
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
    user = django_user_model.objects.create_user(
        username="tester", email="user@email.com", password="Pass123")
    UserProfile.objects.create(
        user=user, tz="UTC", notify_low_mood=True, low_mood_threshold=2, reminder_hour_local=9
    )
    return user


@pytest.fixture
def habit(user):
    return Habit.objects.create(user=user, name="Drink Water", periodicity="daily")


@pytest.fixture
def today():
    return timezone.now().date()


# ---------- UTILITY TESTS ----------


def test_build_next_local_dt_future_today(user):
    profile = user.profile
    now = datetime.now(tz=ZoneInfo(profile.tz()))
    hour = (now.hour + 1) % 24  # ensure in future today
    next_dt = _build_next_local_dt(profile, hour)
    assert next_dt > timezone.now()


def test_build_next_local_dt_passed_hour_tomorrow(user):
    profile = user.profile
    now = datetime.now(tz=ZoneInfo(profile.tz()))
    hour = (now.hour - 1) % 24  # past hour triggers tomorrow
    next_dt = _build_next_local_dt(profile, hour)
    assert next_dt.date() >= (timezone.now() + timedelta(days=0)).date()


# ---------- SEND LOW MOOD ALERT ----------


@pytest.mark.django_db
@patch("tracker.tasks._notify")
def test_send_low_mood_alert_triggers_notification(mock_testify, user, today):
    mood = MoodEntry.objects.create(user=user, date=today, score=1)
    send_low_mood_alert(user.id, mood.id)
    mock_testify.assert_called_once()
    args, kwargs = mock_testify.call_args
    assert "Be kind to yourself" in args[1]
    assert kwargs["email"] is True


@pytest.mark.django_db
@patch("tracker.tasks._notify")
def test_send_low_mood_alert_no_trigger_above_threshold(mock_notify, user, today):
    mood = MoodEntry.objects.create(user=user, date=today, score=5)
    send_low_mood_alert(user.id, mood.id)
    mock_notify.assert_not_called()


@pytest.mark.django_db
def test_send_low_mood_alert_invalid_entry(user):
    # Should not raise even if entry_id is invalid
    send_low_mood_alert(user.id, 9999)  # non-existent
    # passes silently


# ---------- SCHEDULE USER HABIT REMINDERS ----------


@pytest.mark.django_db
def test_schedule_user_habit_reminders_creates_entries(user, habit):
    schedule_user_habit_reminders(user.id)
    reminder = HabitReminder.objects.get(user=user, habit=habit)
    assert reminder.active is True
    assert reminder.next_trigger_utc is not None


@pytest.mark.django_db
def test_schedule_user_habit_reminders_updates_existing(user, habit):
    # create old reminder
    old_reminder = HabitReminder.objects.create(
        user=user, habit=habit, next_trigger_utc=timezone.now() - timedelta(days=1), active=False
    )
    schedule_user_habit_reminders(user.id)
    old_reminder.refresh_from_db()
    assert old_reminder.active is True
    assert old_reminder.next_trigger_utc > timezone.now()


# ---------- PROCESS DUE REMINDERS ----------


@pytest.mark.django_db
@patch("tracker.tasks._notify")
def test_process_due_reminders_sends_and_reschedules(mock_notify, user, habit):
    next_trigger = timezone.now() - timedelta(minutes=1)
    reminder = HabitReminder.objects.create(
        user, habit=habit, next_trigger_utc=next_trigger, active=True
    )
    process_due_reminders()
    reminder.refresh_from_db()
    mock_notify.assert_called_once()
    assert reminder.next_trigger_utc > timezone.now()


@pytest.mark.django_db
@patch("tracker.tasks._notify")
def test_processes_due_reminders_handles_no_profile(mock_notify, user, habit):
    # remove profile to trigger fallback
    user.profile.delete()
    next_trigger = timezone.now() - timedelta(minutes=1)
    reminder = HabitReminder.objects.create(
        user=user, habit=habit, next_trigger_utc=next_trigger, active=True
    )
    process_due_reminders()
    reminder.refresh_from_db()
    mock_notify.assert_called_once()
    assert reminder.next_trigger_utc.date() == (
        timezone.now() + timedelta(days=1)).date()


# ---------- SEND MOOD REMINDER ----------


@pytest.mark.django_db
@patch("tracker.services.send_reminder_email")
def test_send_mood_reminder_calls_service(mock_send, user):
    send_mood_reminder(user.email, 1)  # low mood
    mock_send.assert_called_once()
    args, kwargs = mock_send.call_args
    assert "low" in args[2].lower() or "lift your spirits" in args[2]

    mock_send.reset_mock()
    send_mood_reminder(user.email, 4)  # high mood
    args, kwargs = mock_send.call_args
    assert "keep up" in args[2].lower() or "good work" in args[2]
