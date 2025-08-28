import pytest
from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APIClient

from tracker.models import Habit, HabitCompletion, MoodEntry


@pytest.fixture
def api_client():
    return APIClient()


@pytest.fixture
def user(django_user_model):
    return django_user_model.objects.create_user(username="user1", password="pass123")


@pytest.fixture
def other_user(django_user_model):
    return django_user_model.objects.create_user(username="user2", password="pass123")


@pytest.fixture
def auth_client(api_client, user):
    api_client.force_authenticate(user=user)
    return api_client


@pytest.fixture
def habit(user):
    return Habit.objects.create(user=user, name="Read", periodicity="daily")


@pytest.fixture
def other_habit(other_user):
    return Habit.objects.create(user=other_user, name="Run", periodicity="daily")


@pytest.fixture
def mood_entry(user):
    return MoodEntry.objects.create(
        user=user,
        mood="😊",
        reflection="Good day",
        date=timezone.now().date()
    )


@pytest.fixture
def other_mood(other_user):
    return MoodEntry.objects.create(
        user=other_user,
        mood="😡",
        reflection="Bad day",
        date=timezone.now().date()
    )


@pytest.mark.django_db
class TestHabitViewSet:
    def test_user_only_sees_own_habits(self, auth_client, habit, other_habit):
        url = reverse("habit-list")
        response = auth_client.get(url)

        names = [habit["name"] for habit in response.data]
        assert habit.name in names
        assert other_habit.name not in names

    def test_user_can_create_habit(self, auth_client):
        url = reverse("habit-list")
        payload = {"name": "Exercise", "periodicity": "daily"}
        response = auth_client.post(url, payload)

        assert response.status_code == 201
        assert Habit.objects.filter(name="Exercise").exists()

    def test_user_can_update_own_habit(self, auth_client, habit):
        url = reverse("habit-detail", args=[habit.id])
        response = auth_client.patch(url, {"name": "Read 1 hour"})
        habit.refresh_from_db()

        assert response.status_code == 200
        assert habit.name == "Read 1 hour"

    def test_user_cannot_access_other_users_habit(self, auth_client, other_habit):
        url = reverse("habit-detail", args=[other_habit.id])
        response = auth_client.get(url)
        assert response.status_code == 404

    def test_habit_completions_endpoint_returns_only_own_data(
            self, auth_client, habit, other_habit, other_user
    ):
        # Create completions
        own_completion = HabitCompletion.objects.create(
            user=user, habit=habit, date=timezone.now().date()
        )
        HabitCompletion.objects.create(
            user=other_user, habit=other_habit, date=timezone.now().date()
        )

        # completions for own habit
        url = reverse("habit-completions", args=[habit.id])
        response = auth_client.get(url)

        assert response.status_code == 200
        assert len(response.data) == 1
        assert response.data[0]["id"] == own_completion.id

        # completions for other user habit -> 404
        url = reverse("habit-completions", args=[other_habit.id])
        response = auth_client.get(url)
        assert response.status_code == 404


@pytest.mark.django_db
class TestMoodEntryViewSet:
    def test_user_only_sees_own_moods(self, auth_client, mood_entry, other_mood):
        url = reverse("moodentry-list")
        response = auth_client.get(url)

        moods = [mood["mood"] for mood in response.data]
        assert mood_entry.mood in moods
        assert other_mood.mood not in moods

    def test_user_can_create_mood(self, auth_client):
        url = reverse("moodentry-list")
        payload = {"mood": "😔", "reflection": "Tough day",
                   "date": timezone.now().date()}
        response = auth_client.post(url, payload)

        assert response.status_code == 201
        assert MoodEntry.objects.filter(reflection="Tough day").exists()

    def test_user_can_update_own_mood(self, auth_client, mood_entry):
        url = reverse("moodentry-detail", args=[mood_entry.id])
        response = auth_client.patch(url, {"reflection": "Actually amazing"})
        mood_entry.refresh_from_db()

        assert response.status_code == 200
        assert mood_entry.reflection == "Actually amazing"

    def test_user_cannot_access_other_users_mood(self, auth_client, other_mood):
        url = reverse("moodentry-detail", args=[other_mood.id])
        response = auth_client.get(url)
        assert response.status_code == 404
