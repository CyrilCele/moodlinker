import pytest
from django.utils import timezone

from tracker.api.serializers import (
    HabitSerializer,
    MoodEntrySerializer,
    HabitCompletionSerializer
)
from tracker.models import Habit, MoodEntry, HabitCompletion


@pytest.fixture
def user(django_user_model):
    return django_user_model.objects.create_user(username="user", password="pass123")


@pytest.fixture
def other_user(django_user_model):
    return django_user_model.objects.create_user(username="user2", password="pass123")


@pytest.fixture
def habit(user):
    return Habit.objects.create(user=user, habit="Read", description="Books", periodicity="daily")


@pytest.mark.django_db
class TestHabitSerializer:
    def test_habit_create_assigns_user(self, user):
        """
        Serializer should attach current user when creating.
        """
        serializer = HabitSerializer(
            data={"habit": "Run", "description": "Morning Run",
                  "periodicity": "daily"},
            context={"request": type("req", (), {"user": user})}
        )

        assert serializer.is_valid(), serializer.errors

        habit = serializer.save()

        assert habit.user == user

    def test_validate_rejects_more_than_five_habits(self, user):
        """
        Serializer should block creation if user already has 5 habits.
        """
        for i in range(5):
            Habit.objects.create(
                user=user, habit=f"Habit{i}", periodicity="daily")

        serializer = HabitSerializer(
            data={"habit": "Extra", "description": "6th one",
                  "periodicity": "daily"},
            context={"request": type("req", (), {"user": user})}
        )

        assert not serializer.is_valid()
        assert "Limit of 5 habits" in str(serializer.errors)

    def test_update_does_not_trigger_limit_validation(self, user, habit):
        """
        Updating an existing habit should not check the 5-habit limit.
        """
        # give the user 5 habits already
        for i in range(4):
            Habit.objects.create(
                user=user, habit=f"Habit{i}", periodicity="daily")

        serializer = HabitSerializer(
            instance=habit,
            data={"habit": "Updated"},
            context={"request": type("req", (), {"user": user})},
            partial=True
        )

        assert serializer.is_valid(), serializer.errors

        updated = serializer.save()

        assert updated.habit == "Updated"


@pytest.mark.django_db
class TestMoodEntrySerializer:
    def test_mood_create_assigns_user_and_date(self, user):
        serializer = MoodEntrySerializer(
            data={"score": 3, "reflection": "Feeling okay"},
            context={"request": type("req", (), {"user": user})}
        )

        assert serializer.is_valid(), serializer.errors

        mood = serializer.save()

        assert mood.user == user
        assert mood.date == timezone.localdate()

    def test_validate_rejects_multiple_entries_per_day(self, user):
        today = timezone.localdate()
        MoodEntry.objects.create(
            user=user, score=2, reflection="First", date=today
        )

        serializer = MoodEntrySerializer(
            data={"score": 4, "reflection": "Second try"},
            context={"request": type("req", (), {"user": user})}
        )

        assert not serializer.is_valid()
        assert "Mood already logged for today" in str(serializer.errors)

    def test_update_allows_existing_mood_even_if_today_already_logged(self, user):
        today = timezone.localdate()
        mood = MoodEntry.objects.create(
            user=user, score=2, reflection="First", date=today
        )

        serializer = MoodEntrySerializer(
            instance=mood,
            data={"reflection": "Updated reflection"},
            context={"request": type("req", (), {"user": user})},
            partial=True
        )

        assert serializer.is_valid(), serializer.errors

        updated = serializer.save()

        assert updated.reflection == "Updated reflection"

    @pytest.mark.parametrize("score", [0, 6])
    def test_score_out_of_range_fails_validation(self, user, score):
        serializer = MoodEntrySerializer(
            data={"score": score, "reflection": "meh"},
            context={"request": type("req", (), {"user": user})}
        )

        assert not serializer.is_valid()
        assert "Ensure this value" in str(serializer.errors)


@pytest.mark.django_db
class TestHabitCompletionSerializer:
    def test_completion_serialization_and_readonly_fields(self, user, habit):
        completion = HabitCompletion.objects.create(
            user=user, habit=habit, date=timezone.localdate, completed=True
        )
        serializer = HabitCompletionSerializer(completion)
        data = serializer.data

        # "id" and "date" should be present but readonly
        assert data["id"] == completion.id
        assert data["date"] == str(completion.date)
        assert data["completed"] is True
