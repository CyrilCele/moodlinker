import pytest

from datetime import timedelta

from django.db import transaction
from django.utils import timezone

from tracker.models import Habit, HabitCompletion, MoodEntry
from tracker.services import AnalyticsService, AISuggestionService


@pytest.fixture
def user(db, django_user_model):
    return django_user_model.objects.create_user(
        username="tester",
        email="test@example.com",
        password="pass123"
    )


@pytest.fixture
def habit(user):
    return Habit.objects.create(user=user, habit="Drink Water", periodicity="daily")


@pytest.fixture
def today():
    return timezone.now().date()


# ---------- ANALYTICS SERVICE ----------


def test_longest_streak_counts_correctly(user, habit, today):
    yesterday = today - timedelta(days=1)

    # Delete any pre-existing completions for this user/habit/dates
    HabitCompletion.objects.filter(
        user=user,
        habit=habit,
        date__in=[yesterday, today]
    ).delete()

    with transaction.atomic():
        HabitCompletion.objects.bulk_create([
            HabitCompletion(user=user, habit=habit,
                            date=yesterday, completed=False)
        ])
        HabitCompletion.objects.update_or_create(
            user=user,
            habit=habit,
            date=today,
            defaults={"completed": True}
        )

    streak = AnalyticsService.longest_streak(user, habit)
    assert streak == 1


def test_longest_streak_breaks_on_incomplete_day(user, habit, today):
    HabitCompletion.objects.create(
        user=user, habit=habit, date=today - timedelta(days=1), completed=False)
    streak = AnalyticsService.longest_streak(user, habit)
    assert streak == 0


@pytest.mark.django_db
def test_summaries_daily(user, habit, today):
    # Prepare mood entries
    MoodEntry.objects.create(user=user, date=today, score=3)
    labels, moods, rates = AnalyticsService.summaries(user, view="daily")
    assert len(labels) == 7
    assert labels[-1] == today.strftime("%b %d")
    assert moods[-1] == 3
    assert all(isinstance(rate, float) for rate in rates)


@pytest.mark.django_db
def test_summaries_monthly(user, habit, today):
    MoodEntry.objects.create(user=user, date=today, score=4)
    labels, moods, rates = AnalyticsService.summaries(user, view="monthly")
    assert labels[-1] == today.strftime("%d %b")
    assert moods[-1] == 4
    assert all(isinstance(rate, float) for rate in rates)


@pytest.mark.django_db
def test_summaries_weekly_no_entries(user):
    labels, moods, rates = AnalyticsService.summaries(user, view="weekly")
    assert all(mood == 0 for mood in moods)
    assert all(rate == 0 for rate in rates)


# ---------- AI SUGGESTION SERVICE ----------


@pytest.mark.django_db
def test_analyze_reflection_empty_returns_zero():
    score = AISuggestionService.analyze_reflection("")
    assert score == 0.0


@pytest.mark.django_db
def test_analyze_reflection_positive_text():
    score = AISuggestionService.analyze_reflection(
        "I am feeling amazing and happy")
    assert score > 0


@pytest.mark.django_db
def test_analyze_reflection_negative_text():
    score = AISuggestionService.analyze_reflection("I feel terrible and sad.")
    assert score < 0


@pytest.mark.django_db
def test_suggest_no_moods(user):
    suggestion = AISuggestionService.suggest(user)
    assert "Log a mood today" in suggestion


@pytest.mark.django_db
def test_suggest_low_mood(user, today):
    MoodEntry.objects.create(user=user, date=today,
                             score=1, reflection="Feeling sad.")
    suggestion = AISuggestionService.suggest(user)
    assert "low" in suggestion.lower() or "stressed" in suggestion.lower()


@pytest.mark.django_db
def test_suggest_high_mood(user, today):
    MoodEntry.objects.create(user=user, date=today,
                             score=5, reflection="Feeling great.")
    suggestion = AISuggestionService.suggest(user)
    assert "riding high" in suggestion.lower()


@pytest.mark.django_db(transaction=True)
def test_suggest_weekday_pattern(user, today):
    # Clear old entries to avoid unique constraint errors
    MoodEntry.objects.filter(user=user).delete()

    for i in range(7):
        day = today - timedelta(days=i)
        score = 1 if day.weekday() == 0 else 5
        MoodEntry.objects.update_or_create(
            user=user,
            date=day,
            defaults={"score": score, "reflection": "ok"}
        )
    suggestion = AISuggestionService.suggest(user)
    assert suggestion is not None


# ---------- EDGE CASES ----------
def test_analyze_reflection_handles_none(monkeypatch):
    # should treat None as empty string
    score = AISuggestionService.analyze_reflection(None)
    assert score == 0.0


@pytest.mark.django_db
def test_longest_streak_no_completions(user, habit):
    streak = AnalyticsService.longest_streak(user, habit)
    assert streak == 0
