"""
Unit tests for generate_ics

These tests verify that:
    - generate_ics returns a bytes payload (iCalendar binary)
    - the calendar contains one VEVENT per active HabitReminder
    - VEVENT SUMMARY and DESCRIPTION fields are correct
    - VEVENT DTSTART/DTEND correspond to the HabitReminder.next_trigger_utc
        (with tolerance for small conversion differences)
"""

from datetime import datetime, timedelta
from unittest.mock import patch

import pytz
import pytest
from icalendar import Calendar

from django.utils import timezone

from tracker.models import User, Habit, HabitReminder
from tracker.utils.ics import generate_ics


@pytest.mark.django_db
@patch("django.utils.timezone.now")
def test_generate_ics_returns_bytes(mock_now):
    """
    The ICS generator should return a bytes object suitable for HTTP responses.

    This sanity-check ensures the function produces a serializable iCalendar payload.
    """
    # Freeze "now" to a reproducible UTC instant to make the test deterministic.
    fixed_now = datetime(2025, 8, 29, 12, 0, tzinfo=pytz.UTC)
    mock_now.return_value = fixed_now

    # Create a user and a habit, then schedule a reminder shortly after `now`.
    user = User.objects.create(
        username="testuser", timezone="Africa/Johannesburg"
    )
    habit = Habit.objects.create(
        user=user, habit="Meditate", periodicity="daily"
    )
    reminder_time = timezone.now() + timedelta(minutes=10)
    HabitReminder.objects.create(
        user=user, habit=habit, next_trigger_utc=reminder_time
    )

    ical_bytes = generate_ics(user)

    # Basic sanity-checks: must be bytes and non-empty
    assert isinstance(
        ical_bytes, bytes), "generate_ics should return bytes (iCalendar)"
    assert len(ical_bytes) > 0, "Returned ICS payload should not be empty"

    # Also ensure it parses as a Calendar (raises on invalid iCal)
    cal = Calendar.from_ical(ical_bytes)
    assert cal.name == "VCALENDAR" or hasattr(cal, "walk"), \
        "Parsed object should be an iCalendar Calendar"


@pytest.mark.django_db
@patch("django.utils.timezone.now")
def test_generate_ics_creates_correct_number_of_events(mock_now):
    """
    One VEVENT should be created per active HabitReminder for the user.
    """
    fixed_now = datetime(2025, 8, 29, 12, 0, tzinfo=pytz.UTC)
    mock_now.return_value = fixed_now

    user = User.objects.create(
        username="habituser", timezone="Africa/Johannesburg"
    )

    # Create several habits and reminders, staggered by 10 minutes
    habits = []
    for i in range(3):
        habit = Habit.objects.create(
            user=user, habit=f"Habit {i}", periodicity="daily"
        )
        habits.append(habit)
        HabitReminder.objects.create(
            user=user,
            habit=habit,
            next_trigger_utc=timezone.now() + timedelta(minutes=i*10)
        )

    ical_bytes = generate_ics(user)
    cal = Calendar.from_ical(ical_bytes)

    # Walk VEVENT components from the calendar
    events = [comp for comp in cal.walk() if comp.name == "VEVENT"]

    assert len(events) == len(habits), (
        f"Expected {len(habits)} VEVENTs in the ICS, got {len(events)}."
        "Each active HabitReminder should become one VEVENT."
    )


@pytest.mark.django_db
@patch("django.utils.timezone.now")
def test_generate_ics_event_summary_and_description(mock_now):
    """
    Verify SUMMARY and DESCRIPTION fields are set to helpful, human-readable strings.
    """
    fixed_now = datetime(2025, 8, 29, 12, 0, tzinfo=pytz.UTC)
    mock_now.return_value = fixed_now

    user = User.objects.create(
        username="summaryuser", timezone="Africa/Johannesburg"
    )
    habit = Habit.objects.create(
        user=user, habit="Exercise", periodicity="daily"
    )

    # schedule shortly after mocked "now"
    reminder_time = timezone.now() + timedelta(minutes=5)
    HabitReminder.objects.create(
        user=user, habit=habit, next_trigger_utc=reminder_time
    )

    ical_bytes = generate_ics(user)
    cal = Calendar.from_ical(ical_bytes)

    # Pick the first VEVENT
    events = [comp for comp in cal.walk() if comp.name == "VEVENT"]
    assert events, "No VEVENTs found in generated ICS"
    event = events[0]

    # The iCalendar properties are bytes/strings depending on icalendar version; use str() for robust comparison
    summary = str(event.get("summary"))
    description = str(event.get("description"))

    assert summary == f"Reminder: {habit.habit}", f"Unexpected SUMMARY: {summary}"
    expected_description = f"Don't forget to complete your habit: {habit.habit}"
    assert description == expected_description, f"Unexpected DESCRIPTION: {description}"


@pytest.mark.django_db
@patch("django.utils.timezone.now")
def test_generate_ics_event_times_match_reminder(mock_now):
    """
    Ensure the VEVENT's DTSTART & DTEND correspond to the HabitReminder.next_trigger_utc
    and a default duration (30 minutes).

    The generator converts times between UTC and the user's local timezone; here we
    compare instants (which is timezone-aware arithmetic) with a small tolerance.
    """
    fixed_now = datetime(2025, 8, 29, 12, 0, tzinfo=pytz.UTC)
    mock_now.return_value = fixed_now

    user = User.objects.create(
        username="timeuser", timezone="Africa/Johannesburg"
    )
    habit = Habit.objects.create(user=user, habit="Read", periodicity="daily")

    # Next trigger one hour after mocked now (UTC-aware)
    reminder_time = timezone.now() + timedelta(hours=1)
    HabitReminder.objects.create(
        user=user, habit=habit, next_trigger_utc=reminder_time
    )

    ical_bytes = generate_ics(user)
    cal = Calendar.from_ical(ical_bytes)

    events = [comp for comp in cal.walk() if comp.name == "VEVENT"]
    assert events, "No VEVENTs produced for user's reminders"
    event = events[0]

    # icalendar returns vDatetime objects; `.dt` gives a datetime (possibly timezone-aware)
    dtstart = event.get("dtstart").dt
    dtend = event.get("dtend").dt

    # Defensive: ensure both are timezone-aware datetimes
    assert dtstart.tzinfo is not None, \
        "VEVENT DTSTART should be timezone-aware"
    assert dtend.tzinfo is not None, \
        "VEVENT DTEND should be timezone-aware"

    # Compare instants - convert to UTC for clarity (works even if dtstart is in user's TZ)
    dtstart_utc = dtstart.astimezone(pytz.UTC)
    dtend_utc = dtend.astimezone(pytz.UTC)

    # Allow a very small delta to account for serialization round-trips
    allowed_delta = timedelta(seconds=1)

    assert abs(dtstart_utc - reminder_time) < allowed_delta, (
        f"VEVENT dtstart {dtstart_utc!r} does not match reminder {reminder_time!r}"
    )
    assert abs(dtend_utc - (reminder_time + timedelta(minutes=30))) < allowed_delta, (
        f"VEVENT dtend {dtend_utc!r} does not equal reminder +30min {(reminder_time + timedelta(minutes=30))!r}"
    )
