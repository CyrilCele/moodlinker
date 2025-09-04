"""
Integration tests for key views and user flows in the `tracker` app.

This module verifies:
    - Public pages and auth flows (index, login, logout, register)
    - Dashboard behavior (auto-creating today's HabitCompletion, posting MoodEntry)
    - Habit CRUD (create, delete)
    - Analytics/chart data API
    - Preferences & notifications
    - Calendar ICS feed
"""

from typing import Any

import pytest
from django.contrib.auth import get_user_model
from django.urls import reverse
from django.utils import timezone

from tracker.models import Habit, HabitCompletion, MoodEntry, Notification

User = get_user_model()

# Mark the entire module as requiring DB acces by default.
pytestmark = pytest.mark.django_db


# --------------------
# Fixtures
# --------------------
@pytest.fixture
def user(django_user_model: Any) -> User:
    """
    Create a test user and ensure the related UserProfile exists.

    Returns
    -------
    User
        Auth-capable user instance with an attached profile.
    """
    user = django_user_model.objects.create_user(
        username="tester", email="test@example.com", password="pass1234"
    )

    # Ensure the associated profile exists (signals normally create this).
    from tracker.models import UserProfile

    UserProfile.objects.get_or_create(user=user)
    return user


@pytest.fixture
def auth_client(client, user):
    """
    Django test client authenticated as `user`.

    Uses `force_login` to avoid dependency on authentication backends or the user's password.
    """
    client.force_login(user)
    return client


# ---------- AUTH & BASIC VIEWS ----------


def test_index_view(client):
    """
    GET / (home) should return an HTML document (200 OK).
    """
    response = client.get(reverse("home"))

    assert response.status_code == 200, "Index page must return 200"
    # crude check that HTML-like content is returned
    assert b"html" in response.content.lower()


def test_login_view_valid(client, user):
    """
    POST /login with valid credentials should redirect to the home page.

    This posts to the real view (form-handling path), not using client.login().
    """
    response = client.post(
        reverse("login"),
        {"username": "tester", "password": "pass1234"}
    )

    assert response.status_code == 302, "Successful login should redirect"
    assert response.url == reverse("home"), "Login should redirect to home"


@pytest.mark.django_db
def test_login_view_invalid(client):
    """Invalid credentials should re-render the login page with an error message."""
    response = client.post(
        reverse("login"),
        {"username": "x", "password": "y"}
    )

    assert response.status_code == 200, "Invalid login shows the form again"
    assert b"Invalid" in response.content, "Response should include an \"Invalid\" message"


def test_logout_view(auth_client):
    """Visiting logout should redirect the user to home (logout side-effect)."""
    response = auth_client.get(reverse("logout"))

    assert response.status_code == 302
    assert response.url == reverse("home")


def test_register_view(client, db):
    """POST /register should create a new user and redirect on success."""
    response = client.post(reverse("register"), {
        "username": "newbie",
        "email": "new@example.com",
        "password": "pass123",
        "confirmation": "pass123"
    })

    assert response.status_code == 302, "Register should redirect after success"
    assert User.objects.filter(
        username="newbie").exists(), "New user should be persisted"


# ---------- DASHBOARD ----------


def test_dashboard_view_creates_completions(auth_client, user, db):
    """
    GET /dashboard should create HabitCompletion rows for the user's habits for today.
    This validates the daily-fill behavior.
    """
    habit = Habit.objects.create(
        user=user, habit="Drink water", periodicity="daily"
    )
    response = auth_client.get(reverse("dashboard"))

    assert response.status_code == 200
    assert HabitCompletion.objects.filter(
        user=user,
        habit=habit,
        date=timezone.localdate()
    ).exists(), "Dashboard should auto-create today's HabitCompletion"


def test_dashboard_post_creates_mood_and_completions(auth_client, user):
    """
    POSTing the dashboard form should:
        - create a MoodEntry for today
        - update HabitCompletion.completed for checkboxes (habit_<id> == "on")
    """
    habit = Habit.objects.create(user=user, habit="Run", periodicity="daily")
    payload = {
        "score": 4,
        "reflection": "Good day",
        f"habit_{habit.id}": "on"
    }
    response = auth_client.post(reverse("dashboard"), payload)

    assert response.status_code == 302, "Successful submission should redirect"
    assert MoodEntry.objects.filter(
        user=user, date=timezone.now().date()
    ).exists(), "Mood entry should be created"

    completion = HabitCompletion.objects.get(
        user=user, habit=habit, date=timezone.localdate()
    )
    assert completion.completed is True, "Checkbox submission should mark completion True"


# ---------- HABIT CRUD ----------


def test_create_habit_view(auth_client, user):
    """POST /create_habit should persist a new Habit for the authenticated user."""
    response = auth_client.post(reverse("create_habit"), {
        "habit": "Read",
        "description": "10 pages",
        "periodicity": "daily"
    })

    assert response.status_code == 302
    assert Habit.objects.filter(
        user=user, habit="Read").exists(), "Habit should be created"


def test_delete_habit_view(auth_client, user):
    """
    The delete endpoint in this codebase expects a HabitCompletion id to delete.
    This test ensures posting to delete_habit removes the completion record.
    """
    habit = Habit.objects.create(user=user, habit="Yoga", periodicity="daily")
    completion = HabitCompletion.objects.create(
        user=user, habit=habit, date=timezone.localdate()
    )

    response = auth_client.post(reverse("delete_habit", args=[completion.id]))

    assert response.status_code == 302
    assert not HabitCompletion.objects.filter(
        id=completion.id).exists(), "Completion record should be deleted"


# ---------- ANALYTICS & CHART API ----------


def test_analytics_view(auth_client):
    """GET /analytics should render successfully (200 OK)."""
    response = auth_client.get(reverse("analytics"))

    assert response.status_code == 200
    assert b"html" in response.content.lower()


def test_chart_data_api(auth_client, mocker, user):
    """
    The chart-data API returns JSON from AnalyticsService.summaries.
    Patch the service to isolate the endpoint's JSON shaping logic.
    """
    mocker.patch(
        "tracker.views.AnalyticsService.summaries",
        return_value=(["Monday"], [3], [75])
    )
    response = auth_client.get(reverse("chart_data_api") + "?view=weekly")

    assert response.status_code == 200
    data = response.json()
    assert data["labels"] == ["Monday"]
    assert data["datasets"][0]["data"] == [3]


# ---------- ABOUT, PREFS, NOTIFICATIONS ----------


def test_about_view(auth_client):
    """GET /about should respond 200 OK."""
    response = auth_client.get(reverse("about"))
    assert response.status_code == 200


def test_preferences_save(auth_client, mocker, user):
    """
    Saving preferences should queue reminder scheduling;
    patch the background task to avoid side-effects.
    """
    mocker.patch(
        "tracker.tasks.schedule_user_habit_reminders.delay", return_value=None
    )

    response = auth_client.post(reverse("preferences"), {
        "reminder_hour_local": 9,
        "timezone": "UTC",
        "notify_low_mood": "on",
        "low_mood_threshold": 3
    })

    assert response.status_code == 302


def test_notifications_list(auth_client, user):
    """Notifications list should render entries for the logged-in user."""
    Notification.objects.create(user=user, message="Test")
    response = auth_client.get(reverse("notifications"))

    assert response.status_code == 200
    assert b"Test" in response.content


def test_mark_notification_read(auth_client, user):
    """Visiting mark_notification_read should set `read=True` and redirect."""
    note = Notification.objects.create(user=user, message="New")
    response = auth_client.get(
        reverse("mark_notification_read", args=[note.id])
    )

    note.refresh_from_db()
    assert response.status_code == 302
    assert note.read is True


# ---------- CALENDAR FEED ----------


def test_calendar_feed_valid(auth_client, user, mocker):
    """
    A valid calendar token should return an ICS file payload.
    Patch generate_ics so test don't exercise the ICS generator itself.
    """
    user.calendar_token = "abc123"
    user.save()

    Habit.objects.create(user=user, habit="Hydrate", periodicity="daily")
    # Patch the function imported in the view module to return raw bytes.
    mocker.patch(
        "tracker.views.generate_ics",
        return_value="BEGIN:VCALENDAR\nEND:VCALENDAR"
    )

    url = reverse("calendar_feed", args=["abc123"])
    response = auth_client.get(url)

    assert response.status_code == 200
    assert b"VCALENDAR" in response.content


def test_calendar_feed_invalid(auth_client):
    """Invalid calendar token should return HTTP 404."""
    response = auth_client.get(reverse("calendar_feed", args=["wrongtoken"]))
    assert response.status_code == 404
