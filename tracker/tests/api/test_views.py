"""
End-to-end API tests for the Habit and MoodEntry viewsets.

What this file covers (high level):
- AuthZ scoping: a user should only see and mutate their own resources.
- CRUD basics on /habits/ and /moods/ endpoints (list, create, update, detail).
- Custom "completions" action on HabitViewSet is correctly user-scoped.

Why this matters:
These tests lock down security/ownership rules and core UX flows so future
refactors (serializers/viewsets/permissions) won't silently regress them.

Notes / assumptions:
- DRF defaults are used (IsAuthenticated on both viewsets).
- Router names are "habits" and "moods". If you rename the routes, update
  `reverse()` names here.
- Dates are treated as server-local days via `timezone.localdate()`.
- Status code constants from DRF are used for clarity.
"""

from typing import Generator

import pytest
from django.urls import reverse
from django.utils import timezone

from rest_framework import status
from rest_framework.test import APIClient

from tracker.models import Habit, HabitCompletion, MoodEntry


# ----------------------------
# Fixtures
# ----------------------------

@pytest.fixture
def api_client() -> APIClient:
    """
    Return a DRF APIClient for issuing HTTP requests.

    Returns
    -------
    APIClient
        Authless test client (use `auth_client` for an authenticated one).
    """
    return APIClient()


@pytest.fixture
def user(django_user_model):
    """
    Create the primary test user.

    Returns
    -------
    User
        Django user instance persisted to the test DB.
    """
    return django_user_model.objects.create_user(username="user1", password="pass123")


@pytest.fixture
def other_user(django_user_model):
    """
    Create a secondary test user to verift authorization boundaries.

    Returns
    --------
    User
        Another Django user instance.
    """
    return django_user_model.objects.create_user(username="user2", password="pass123")


@pytest.fixture
def auth_client(api_client: APIClient, user) -> APIClient:
    """
    An APIClient authenticated as `user`.

    Parameters
    ----------
    api_client : APIClient
        The base client.
    user : User
        The user to authenticate as.

    Returns
    --------
    APIClient
        Client with authentication credentials applied.
    """
    # Force-auth so we don't need to call the login endpoint in every test
    api_client.force_authenticate(user=user)
    return api_client


@pytest.fixture
def habit(user) -> Habit:
    """
    Persist a sample Habit for `user`.
    """
    return Habit.objects.create(user=user, habit="Read", periodicity="daily")


@pytest.fixture
def other_habit(other_user) -> Habit:
    """
    Persist a sample Habit for `other_user`.
    """
    return Habit.objects.create(user=other_user, habit="Run", periodicity="daily")


@pytest.fixture
def mood_entry(user) -> MoodEntry:
    """
    Persist a sample MoodEntry today for `user`.
    """
    return MoodEntry.objects.create(
        user=user,
        score="5",
        reflection="Good day",
        date=timezone.localdate()
    )


@pytest.fixture
def other_mood(other_user) -> MoodEntry:
    """
    Persist a sample MoodEntry today for `other_user`.
    """
    return MoodEntry.objects.create(
        user=other_user,
        score="1",
        reflection="Bad day",
        date=timezone.localdate()
    )


# ----------------------------
# Fixtures
# ----------------------------

@pytest.mark.django_db
class TestHabitViewSet:
    """
    Behavioral tests for the HabitViewSet (list/create/update/detail + completions).
    """

    def test_user_only_sees_own_habits(
            self,
            auth_client: APIClient,
            habit: Habit,
            other_habit: Habit
    ) -> None:
        """
        GET /habits/ returns only the authenticated user's habits.

        Steps
        -----
        1) List habits.
        2) Extract the "habit" names from the response.
        3) Assert own habit is present and other's habit is absent.
        """
        url = reverse("habits-list")
        resp = auth_client.get(url)

        assert resp.status_code == status.HTTP_200_OK, resp.data
        names = [h["habit"] for h in resp.data]

        assert habit.habit in names
        assert other_habit.habit not in names

    def test_user_can_create_habit(self, auth_client: APIClient) -> None:
        """
        POST /habits/ creates a habit owned by the current user.
        """
        url = reverse("habits-list")
        payload = {"habit": "Exercise", "periodicity": "daily"}
        resp = auth_client.post(url, payload, format="json")

        assert resp.status_code == status.HTTP_201_CREATED, resp.data
        assert Habit.objects.filter(habit="Exercise").exists()

    def test_user_can_update_own_habit(self, auth_client: APIClient, habit: Habit) -> None:
        """
        PATCH /habits/{id}/ allows updating the user's own habit.
        """
        url = reverse("habits-detail", args=[habit.id])
        resp = auth_client.patch(url, {"habit": "Read 1 hour"}, format="json")
        habit.refresh_from_db()

        assert resp.status_code == status.HTTP_200_OK, resp.data
        assert habit.habit == "Read 1 hour"

    def test_user_cannot_access_other_users_habit(
            self, auth_client: APIClient, other_habit: Habit
    ) -> None:
        """
        Accessing another user's habit should return 404 (scoped queryset).
        """
        url = reverse("habits-detail", args=[other_habit.id])
        resp = auth_client.get(url)

        assert resp.status_code == status.HTTP_404_NOT_FOUND

    def test_habit_completions_endpoint_returns_only_own_data(
            self,
            auth_client: APIClient,
            habit: Habit,
            other_habit: Habit,
            other_user,
            user
    ) -> None:
        """
        GET /habits/{id}/completions should return only completions belonging
        to the authenticated user and to the referenced habit.

        Also verifies that hitting the completions endpoint for someone else's habit is 404.
        """
        today = timezone.localdate()

        # Create one completion for the authenticated user and habit
        own_completion = HabitCompletion.objects.create(
            user=user, habit=habit, date=today
        )
        HabitCompletion.objects.create(
            user=other_user, habit=other_habit, date=today
        )

        # Request completions for the user's own habit
        url = reverse("habits-completions", args=[habit.id])
        resp = auth_client.get(url)

        assert resp.status_code == status.HTTP_200_OK, resp.data
        assert len(resp.data) == 1
        assert resp.data[0]["id"] == own_completion.id

        # Request completions for another user's habit - should be hidden as 404
        url = reverse("habits-completions", args=[other_habit.id])
        resp = auth_client.get(url)

        assert resp.status_code == status.HTTP_404_NOT_FOUND


# ----------------------------
# MoodEntryViewSet tests
# ----------------------------

@pytest.mark.django_db
class TestMoodEntryViewSet:
    """
    Behavioral tests for the MoodEntryViewSet (list/create/update/detail).
    """

    def test_user_only_sees_own_moods(
            self,
            auth_client: APIClient,
            mood_entry: MoodEntry,
            other_mood: MoodEntry
    ) -> None:
        """
        GET /moods/ returns only the authenticated user's mood entries.
        """
        url = reverse("moods-list")
        resp = auth_client.get(url)

        assert resp.status_code == status.HTTP_200_OK, resp.data
        scores = [row["score"] for row in resp.data]

        assert mood_entry.score in scores
        assert other_mood.score not in scores

    def test_user_can_create_mood(self, auth_client: APIClient) -> None:
        """
        POST /moods/ creates a mood entry for the current user.

        Note: date is optional in the serializer and will default to today; we
        include it here to show the accepted ISO-8601 format.
        """
        url = reverse("moods-list")
        payload = {
            "score": 3,
            "reflection": "Tough day",
            "date": timezone.localdate().isoformat()
        }
        resp = auth_client.post(url, payload, format="json")

        assert resp.status_code == status.HTTP_201_CREATED, resp.data
        assert MoodEntry.objects.filter(reflection="Tough day").exists()

    def test_user_can_update_own_mood(self, auth_client: APIClient, mood_entry: MoodEntry) -> None:
        """
        PATCH /moods/{id}/ allows updating the user's own mood entry.
        """
        url = reverse("moods-detail", args=[mood_entry.id])
        resp = auth_client.patch(
            url, {"reflection": "Actually amazing"}, format="json")
        mood_entry.refresh_from_db()

        assert resp.status_code == status.HTTP_200_OK, resp.data
        assert mood_entry.reflection == "Actually amazing"

    def test_user_cannot_access_other_users_mood(self, auth_client: APIClient, other_mood: MoodEntry) -> None:
        """
        Accessing another user's mood entry should return 404 (scoped queryset).
        """
        url = reverse("moods-detail", args=[other_mood.id])
        resp = auth_client.get(url)

        assert resp.status_code == status.HTTP_404_NOT_FOUND
