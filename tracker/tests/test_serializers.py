"""
Unit tests for serializers.

This module verifies key business rules and serialization behavior:
- HabitSerializer: attaches request.user on create, enforces a 5-habit-per-user
  limit on creation (but not on update).
- MoodEntrySerializer: attaches request.user and a default date on create,
  enforces one mood entry per user per server-level day (create only),
  and validates score bounds (1...5).
- HabitCompletionSerializer: basic serialization and readonly fields contract.

Notes:
- These tests use server local dates (timezone.localdate()). If you adopt user-local
  date semantics later, update serializers and tests accordingly.
- Serializer-level checks (like the 5-habit limit) are not atomic and can be raced
  by concurrent requests. A DB-level guard is required for strict enforcement.
"""

import pytest
from django.utils import timezone
from types import SimpleNamespace

from tracker.api.serializers import (
    HabitSerializer,
    MoodEntrySerializer,
    HabitCompletionSerializer
)
from tracker.models import Habit, MoodEntry, HabitCompletion


# ---------- Fixtures ----------
@pytest.fixture
def user(django_user_model):
    """Create a simple test user."""
    return django_user_model.objects.create_user(username="user", password="pass123")


@pytest.fixture
def other_user(django_user_model):
    """Create another user for tests that may need multiple users."""
    return django_user_model.objects.create_user(username="user2", password="pass123")


@pytest.fixture
def habit(user):
    """Create a simple habit for the primary test user."""
    return Habit.objects.create(
        user=user,
        habit="Read",
        description="Books",
        periodicity="daily"
    )


# ---------- Helper utilities ----------
def request_context_for(user_obj):
    """
    Return a minimal serializer context containing a request-like object.

    Many serializers only need `context['request'].user`. Using SimpleNamespace
    keeps tests lightweight and explicit.
    """
    return {"request": SimpleNamespace(user=user_obj)}


# ---------- HabitSerializer tests ----------
@pytest.mark.django_db
class TestHabitSerializer:
    """Tests for HabitSerializer: creation, limit validation, and updates."""

    def test_habit_create_assigns_user(self, user):
        """Creating a habit via the serializer must attach request.user to the model."""
        serializer = HabitSerializer(
            data={
                "habit": "Run",
                "description": "Morning Run",
                "periodicity": "daily"
            },
            context=request_context_for(user)
        )

        # Include serializer.errors on failure to speed debugging
        assert serializer.is_valid(
        ), f"Unexpected serializer errors: {serializer.errors}"

        created = serializer.save()

        assert created.user == user, "Created habit must be owned by the request user"

    def test_validate_rejects_more_than_five_habits(self, user):
        """
        If a user already has 5 habits, creating a 6th via the serializer should fail.
        This enforces the application-level habit limit.
        """
        # Send five existing habits for the user
        for i in range(5):
            Habit.objects.create(
                user=user, habit=f"Habit{i}", periodicity="daily"
            )

        serializer = HabitSerializer(
            data={
                "habit": "Extra",
                "description": "6th one",
                "periodicity": "daily"
            },
            context=request_context_for(user)
        )

        # Creation should be invalid due to business rule
        assert not serializer.is_valid(), "Serializer should reject when habit limit reached"

        # The error message is provided by the serializer; assert it mentions the limit.
        assert "Limit of 5 habits" in str(serializer.errors), \
            f"Unexpected errors: {serializer.errors}"

    def test_update_does_not_trigger_limit_validation(self, user, habit):
        """
        Updating an existing Habit instance should not be blocked by the 5-habit rule.
        The limit applies only on creation (self.instance is None).
        """
        # Make the total habits count 5 (the fixture `habit` + 4 new ones)
        for i in range(4):
            Habit.objects.create(
                user=user, habit=f"Habit{i}", periodicity="daily"
            )

        # Partial update of an existing instance should be allowed
        serializer = HabitSerializer(
            instance=habit,
            data={"habit": "Updated"},
            context=request_context_for(user),
            partial=True
        )

        assert serializer.is_valid(), \
            f"Update should be valid: {serializer.errors}"

        updated = serializer.save()
        assert updated.habit == "Updated", "Habit field should be updated on partial save"


# ---------- MoodEntrySerializer tests ----------
@pytest.mark.django_db
class TestMoodEntrySerializer:
    """Tests for MoodEntrySerializer: creation defaults, uniqueness, and bounds."""

    def test_mood_create_assigns_user_and_date(self, user):
        """
        Creating a mood entry without a date should set the entry's user and
        date (server-local today).
        """
        serializer = MoodEntrySerializer(
            data={"score": 3, "reflection": "Feeling okay"},
            context=request_context_for(user)
        )

        assert serializer.is_valid(
        ), f"Serializer invalid: {serializer.errors}"

        mood = serializer.save()

        assert mood.user == user
        assert mood.date == timezone.localdate(), "Date should default to server-local today"

    def test_validate_rejects_multiple_entries_per_day(self, user):
        """
        Creating a second mood entry on the same day for the same user should be rejected.
        """
        today = timezone.localdate()
        # Create an initial mood for today
        MoodEntry.objects.create(
            user=user, score=2, reflection="First", date=today
        )

        serializer = MoodEntrySerializer(
            data={"score": 4, "reflection": "Second try"},
            context=request_context_for(user)
        )

        assert not serializer.is_valid(), "Serializer should reject second mood for same day"
        assert "Mood already logged for today" in str(serializer.errors), \
            f"Errors: {serializer.errors}"

    def test_update_allows_existing_mood_even_if_today_already_logged(self, user):
        """
        Updating an existing MoodEntry should be allowed even when an entry exists for today.
        The uniqueness check applies only on create.
        """
        today = timezone.localdate()
        mood = MoodEntry.objects.create(
            user=user, score=2, reflection="First", date=today
        )

        serializer = MoodEntrySerializer(
            instance=mood,
            data={"reflection": "Updated reflection"},
            context=request_context_for(user),
            partial=True
        )

        assert serializer.is_valid(), f"Update invalid: {serializer.errors}"

        updated = serializer.save()
        assert updated.reflection == "Updated reflection"

    @pytest.mark.parametrize("score", [0, 6])
    def test_score_out_of_range_fails_validation(self, user, score):
        """
        Scores outside 1...5 should cause validation to fail (IntegerField validators).
        """
        serializer = MoodEntrySerializer(
            data={"score": score, "reflection": "meh"},
            context=request_context_for(user)
        )

        assert not serializer.is_valid(), "Out-of-range score should fail validation"
        # The DRF error message for min/max comes from IntegerField; check for that phrase.
        assert "Ensure this value" in str(serializer.errors), \
            f"Unexpected errors: {serializer.errors}"


# ---------- HabitCompletionSerializer tests ----------
@pytest.mark.django_db
class TestHabitCompletionSerializer:
    """Tests for HabitCompletionSerializer verifying serialization contract and readonly fields."""

    def test_completion_serialization_and_readonly_fields(self, user, habit):
        """
        Ensure HabitCompletion serializes correctly and that "id" and "date" are present
        and match the model (date serialized as ISO string).
        """
        completion = HabitCompletion.objects.create(
            user=user, habit=habit, date=timezone.localdate(), completed=True
        )

        serializer = HabitCompletionSerializer(completion)
        data = serializer.data

        # Validate returned serialized representation
        assert data["id"] == completion.id
        assert data["date"] == str(completion.date)
        assert data["completed"] is True
