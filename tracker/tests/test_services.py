"""
Unit tests for AnalyticsService and AISuggestionService.

This file covers:
    - AnalyticsService.longest_streak and summaries (daily, monthly, weekly)
    - AISuggestionService.analyze_reflection and suggest
"""


import pytest
from datetime import timedelta

from django.db import transaction
from django.utils import timezone

from tracker.models import Habit, HabitCompletion, MoodEntry
from tracker.services import AnalyticsService, AISuggestionService


# ---------------------
# Fixtures
# ---------------------
@pytest.fixture
def user(db, django_user_model):
    """
    Create a test user.

    Parameters
    ----------
    db : pytest fixture
        Ensures the test database is available.
    django_user_model : Django user model factory provided by pytest-django.

    Returns
    -------
    User
    """
    return django_user_model.objects.create_user(
        username="tester",
        email="test@example.com",
        password="pass123"
    )


@pytest.fixture
def habit(user):
    """
    Create a Habit for the provided user.

    Returns
    -------
    Habit
    """
    return Habit.objects.create(user=user, habit="Drink Water", periodicity="daily")


@pytest.fixture
def today():
    """
    Return the server-local "today" date. Use timezone.localdate() to respect
    Django's timezone handling.
    """
    return timezone.now().date()


# ---------- ANALYTICS SERVICE ----------

@pytest.mark.django_db
def test_longest_streak_counts_correctly(user, habit, today):
    """
    When today's HabitCompletion is completed and yesterday is not completed,
    the current streak should be 1.

    Steps:
        1. Ensure no conflicting completions exist for the two dates.
        2. Create yesterday completion (not completed).
        3. Create or update today's completion to completed=True.
        4. Assert longest_streak returns 1.
    """
    yesterday = today - timedelta(days=1)

    # Delete any pre-existing completions to ensure deterministic start state
    HabitCompletion.objects.filter(
        user=user,
        habit=habit,
        date__in=[yesterday, today]
    ).delete()

    # Use a transaction for a deterministic bulk/batched writes
    with transaction.atomic():
        # Create yesterday completion (not completed)
        HabitCompletion.objects.bulk_create([
            HabitCompletion(
                user=user, habit=habit, date=yesterday, completed=False
            )
        ])

        # Ensure there's a completion for today that is marked completed=True
        HabitCompletion.objects.update_or_create(
            user=user,
            habit=habit,
            date=today,
            defaults={"completed": True}
        )

    streak = AnalyticsService.longest_streak(user, habit)
    assert streak == 1, f"Expected streak 1, got {streak}"


@pytest.mark.django_db
def test_longest_streak_breaks_on_incomplete_day(user, habit, today):
    """
    If the most recent day is incomplete (or missing), longest_streak should be 0.
    """
    # Create an incomplete completion for yesterday
    HabitCompletion.objects.create(
        user=user, habit=habit, date=today - timedelta(days=1), completed=False
    )

    streak = AnalyticsService.longest_streak(user, habit)
    assert streak == 0, f"Expected strak 0 when last day incomplete, got {streak}"


@pytest.mark.django_db
def test_longest_streak_no_completions(user, habit):
    """
    When there are no completions at all, streak should be 0.
    """
    # Ensure no completions exist for this user/habit
    HabitCompletion.objects.filter(user=user, habit=habit).delete()

    streak = AnalyticsService.longest_streak(user, habit)
    assert streak == 0, f"Expected streak 0 with no completions, got {streak}"


@pytest.mark.django_db
def test_summaries_daily(user, habit, today):
    """
    summaries(view="daily") should return 7 labels (last 7 days),
    the last label should be today's date formatted "%b %d",
    and mood for today should reflect the created entry.
    """
    # Create a mood entry for today
    MoodEntry.objects.create(user=user, date=today, score=3)

    labels, moods, rates = AnalyticsService.summaries(user, view="daily")

    assert len(labels) == 7, "Daily view should return 7 labels (last 7 days)"
    assert labels[-1] == today.strftime(
        "%b %d"), f"Last label should be today ({labels[-1]})"
    # moods may be floats; compare numerically
    assert float(
        moods[-1]) == 3.0, f"Expected today's mood average 3.0, got {moods[-1]}"
    assert all(isinstance(rate, float)
               for rate in rates), "Completion rates should be floats"


@pytest.mark.django_db
def test_summaries_monthly(user, habit, today):
    """
    summaries(view="monthly") should include all days up to today in the current month.
    The last label should match today's day/month and its mood should include the created entry.
    """
    MoodEntry.objects.create(user=user, date=today, score=4)

    labels, moods, rates = AnalyticsService.summaries(user, view="monthly")

    assert labels, "Monthly labels should not be empty"
    assert labels[-1] == today.strftime("%d %b"), \
        f"Expected last label to be today ({labels[-1]})"
    assert float(moods[-1]) == 4.0, \
        f"Expected today's mood avg 4.0, got {moods[-1]}"
    assert all(isinstance(rate, float) for rate in rates), \
        "Completion rates should be floats"


@pytest.mark.django_db
def test_summaries_weekly_no_entries(user):
    """
    When the user has no mood or completion entries, summaries (weekly) should return zeros.
    """
    labels, moods, rates = AnalyticsService.summaries(user, view="weekly")

    assert all(
        mood == 0 for mood in moods), "Expected all mood buckets to be 0 when no entries exist"
    assert all(
        rate == 0 for rate in rates), "Expected all completion rates to be 0 when no entries exist"


# ---------- AI SUGGESTION SERVICE ----------


def test_analyze_reflection_empty_returns_zero():
    """
    analyze_reflection("") should return 0.0 (no sentiment).
    This test does not require DB access.
    """
    score = AISuggestionService.analyze_reflection("")
    assert score == 0.0, f"Expected 0.0 for empty text, got {score}"


def test_analyze_reflection_handles_none():
    """
    analyze_reflection(None) should be treated the same as empty string and return 0.0.
    """
    score = AISuggestionService.analyze_reflection(None)
    assert score == 0.0, f"Expected 0.0 for None input, got {score}"


def test_analyze_reflection_positive_text():
    """
    Positive text should produce a positive compound sentiment score.
    Note: this relies on VADER; ensure NLTK resources are available in CI.
    """
    score = AISuggestionService.analyze_reflection(
        "I am feeling amazing and happy"
    )
    assert score > 0.0, f"Expected positive sentiment > 0, got {score}"


def test_analyze_reflection_negative_text():
    """
    Negative text should produce a negative compound sentiment score.
    """
    score = AISuggestionService.analyze_reflection("I feel terrible and sad.")
    assert score < 0.0, f"Expected negative sentiment < 0, got {score}"


@pytest.mark.django_db
def test_suggest_no_moods(user):
    """
    When there are no recent moods, suggest() should invite the user to log a mood.
    """
    suggestion = AISuggestionService.suggest(user)
    assert "Log a mood today" in suggestion, f"Expected prompt to log a mood, got {suggestion}"


@pytest.mark.django_db
def test_suggest_low_mood(user, today):
    """
    If today's mood is low and reflection indicates stress, suggestion should mention low/stress.
    """
    MoodEntry.objects.create(
        user=user, date=today, score=1, reflection="Feeling sad."
    )

    suggestion = AISuggestionService.suggest(user)

    assert ("low" in suggestion.lower()) or ("stressed" in suggestion.lower()), (
        f"Expected low/stress suggestion, got: {suggestion}"
    )


@pytest.mark.django_db
def test_suggest_high_mood(user, today):
    """
    If recent mood is high, suggestion should encourage leveling up (phraise "riding high" expected).
    """
    MoodEntry.objects.create(
        user=user, date=today, score=5, reflection="Feeling great."
    )

    suggestion = AISuggestionService.suggest(user)
    assert "riding high" in suggestion.lower() or "level up" in suggestion.lower(), (
        f"Expected encouragement for high mood, got: {suggestion}"
    )


@pytest.mark.django_db(transaction=True)
def test_suggest_weekday_pattern(user, today):
    """
    Create a week's worth of data with a weekday pattern (e.g., low on Monday).
    The suggestion should return a non-empty string and may mention weak weekday patterns.
    transaction=True is used here to make the test's DB activity explicit and isolated.
    """
    # Remove old entries to avoid unique_together errors for the same day
    MoodEntry.objects.filter(user=user).delete()

    for i in range(7):
        day = today - timedelta(days=i)
        # Heuristic: make Mondays (weekday==0) low, others high
        score = 1 if day.weekday() == 0 else 5
        MoodEntry.objects.update_or_create(
            user=user,
            date=day,
            defaults={"score": score, "reflection": "ok"}
        )

    suggestion = AISuggestionService.suggest(user)

    assert suggestion, "AISuggestionService.suggest should return a non-empty suggestion for patterned data"
