import pytest
import pytz

from datetime import datetime, timedelta
from icalendar import Calendar
from unittest.mock import patch

from django.utils import timezone

from tracker.models import User, Habit, HabitReminder
from tracker.utils.ics import generate_ics


@pytest.mark.django_db
@patch("django.utils.timezone.now")
def test_generate_ics_returns_bytes(mock_now):
    # Fix the current time
    fixed_now = datetime(2025, 8, 29, 12, 0, tzinfo=pytz.UTC)
    mock_now.return_value = fixed_now

    user = User.objects.create(
        username="testuser", timezone="Africa/Johannesburg")
    habit = Habit.objects.create(
        user=user, habit="Meditate", periodicity="daily")
    reminder_time = timezone.now() + timedelta(minutes=10)
    HabitReminder.objects.create(
        user=user, habit=habit, next_trigger_utc=reminder_time)

    ical_bytes = generate_ics(user)

    assert isinstance(ical_bytes, bytes), "ICS output should be bytes"


@pytest.mark.django_db
@patch("django.utils.timezone.now")
def test_generate_ics_creates_correct_number_of_events(mock_now):
    fixed_now = datetime(2025, 8, 29, 12, 0, tzinfo=pytz.UTC)
    mock_now.return_value = fixed_now

    user = User.objects.create(
        username="habituser", timezone="Africa/Johannesburg"
    )

    habits = []
    reminders = []

    for i in range(3):
        habit = Habit.objects.create(
            user=user, habit=f"Habit {i}", periodicity="daily"
        )
        habits.append(habit)
        reminder = HabitReminder.objects.create(
            user=user, habit=habit, next_trigger_utc=timezone.now() + timedelta(minutes=i*10)
        )
        reminders.append(reminder)

    ical_bytes = generate_ics(user)
    cal = Calendar.from_ical(ical_bytes)

    events = [comp for comp in cal.walk() if comp.name == "VEVENT"]

    assert len(events) == len(habits), \
        "ICS should contain one event per active reminder"


@pytest.mark.django_db
@patch("django.utils.timezone.now")
def test_generate_ics_event_summary_and_description(mock_now):
    fixed_now = datetime(2025, 8, 29, 12, 0, tzinfo=pytz.UTC)
    mock_now.return_value = fixed_now

    user = User.objects.create(
        username="summaryuser", timezone="Africa/Johannesburg"
    )
    habit = Habit.objects.create(
        user=user, habit="Exercise", periodicity="daily"
    )
    reminder_time = timezone.now() + timedelta(minutes=5)

    HabitReminder.objects.create(
        user=user, habit=habit, next_trigger_utc=reminder_time
    )

    ical_bytes = generate_ics(user)
    cal = Calendar.from_ical(ical_bytes)

    event = [comp for comp in cal.walk() if comp.name == "VEVENT"][0]

    assert event.get("summary") == f"Reminder: {habit.habit}"
    assert event.get("description") == \
        f"Don't forget to complete your habit: {habit.habit}"


@pytest.mark.django_db
@patch("django.utils.timezone.now")
def test_generate_ics_event_times_match_reminder(mock_now):
    fixed_now = datetime(2025, 8, 29, 12, 0, tzinfo=pytz.UTC)
    mock_now.return_value = fixed_now

    user = User.objects.create(
        username="timeuser", timezone="Africa/Johannesburg"
    )
    habit = Habit.objects.create(user=user, habit="Read", periodicity="daily")
    reminder_time = timezone.now() + timedelta(hours=1)

    HabitReminder.objects.create(
        user=user, habit=habit, next_trigger_utc=reminder_time
    )

    ical_bytes = generate_ics(user)
    cal = Calendar.from_ical(ical_bytes)

    event = [comp for comp in cal.walk() if comp.name == "VEVENT"][0]

    dtstart = event.get("dtstart").dt
    dtend = event.get("dtend").dt

    # Allow small delta for datetime conversion differences
    delta = timedelta(seconds=1)

    assert abs(dtstart - reminder_time) < delta, \
        "Event start should match next_trigger_utc"
    assert abs(dtend - (reminder_time + timedelta(minutes=30))) < delta, \
        "Event end should be 30 mins after start"
