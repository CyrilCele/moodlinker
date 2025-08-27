import io
import pytest

from django.contrib.auth import get_user_model
from django.urls import reverse
from django.utils import timezone

from tracker.models import Habit, HabitCompletion, MoodEntry, Notification

User = get_user_model


@pytest.fixture
def user(db, django_user_model):
    return django_user_model.objects.create_user(
        username="tester", email="test@example.com", password="pass1234"
    )


@pytest.fixture
def auth_client(client, user):
    client.login(username="tester", password="password1234")
    return client


# ---------- AUTH & BASIC VIEWS ----------


def test_index_view(client):
    response = client.get(reverse("home"))
    assert response.status_code == 200
    assert b"html" in response.content.lower()


def test_login_view_valid(client, user):
    response = client.post(reverse("login"), {
        "username": "tester",
        "password": "pass1234"
    })
    assert response.status_code == 302
    assert response.url == reverse("home")


def test_login_view_invalid(client):
    response = client.post(reverse("login"), {
        "username": "x",
        "password": "y"
    })
    assert response.status_code == 200
    assert b"Invalid" in response.content


def test_logout_view(auth_client):
    response = auth_client.get(reverse("logout"))
    assert response.status_code == 302
    assert response.url == reverse("home")


def test_register_view(client, db):
    response = client.post(reverse("register"), {
        "username": "newbie",
        "email": "new@example.com",
        "password": "pass123",
        "confirmation": "pass123"
    })
    assert response.status_code == 302
    assert User.objects.filter(username="newbie").exists()


# ---------- DASHBOARD ----------


def test_dashboard_view_creates_completions(auth_client, user, db):
    habit = Habit.objects.create(
        user=user, name="Drink water", periodicity="daily")
    response = auth_client.get(reverse("dashboard"))
    assert response.status_code == 200
    assert HabitCompletion.objects.filter(user=user, habit=habit).exists()


def test_dashboard_post_creates_mood_and_completions(auth_client, user, db):
    habit = Habit.objects.create(user=user, name="Run", periodicity="daily")
    data = {
        "mood": 4,
        "reflection": "Good day",
        f"habit_{habit.id}": "on"
    }
    response = auth_client.post(reverse("dashboard"), data)
    assert response.status_code == 302
    assert MoodEntry.objects.filter(
        user=user, date=timezone.now().date()).exists()
    completion = HabitCompletion.objects.get(
        user=user, habit=habit, date=timezone.now().date())
    assert completion.completed is True


# ---------- HABIT CRUD ----------


def test_create_habit_view(auth_client, user):
    response = auth_client.post(reverse("create_habit"), {
        "name": "Read",
        "description": "10 pages",
        "periodicity": "daily"
    })
    assert response.status_code == 302
    assert Habit.objects.filter(user=user, name="Read").exists()


def test_delete_habit_view(auth_client, user):
    habit = Habit.objects.create(user=user, name="Yoga", periodicity="daily")
    completion = HabitCompletion.objects.create(
        user=user, habit=habit, date=timezone.now().date())
    response = auth_client.post(reverse("delete_habit", args=[completion.id]))
    assert response.status_code == 302
    assert not HabitCompletion.objects.filter(id=completion.id).exists()


# ---------- ANALYTICS & CHART API ----------


def test_analytics_view(auth_client):
    response = auth_client.get(reverse("analytics"))
    assert response.status_code == 200
    assert b"html" in response.content.lower()


def test_chart_data_api(auth_client, mocker, user):
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
    response = auth_client.get(reverse("about"))
    assert response.status_code == 200


def test_preferences_save(auth_client, mocker, user):
    mocker.patch(
        "tracker.views.schedule_user_habit_reminder.delay", return_value=None)
    response = auth_client.post(reverse("preferences"), {
                                "reminder_time": "09:00"})
    assert response.status_code == 302


def test_notifications_list(auth_client, user):
    Notification.objects.create(user=user, message="Test")
    response = auth_client.get(reverse("notifications"))
    assert response.status_code == 200
    assert b"Test" in response.content


def test_mark_notification_read(auth_client, user):
    note = Notification.objects.create(user=user, message="New")
    response = auth_client.get(
        reverse("mark_notification_read", args=[note.id]))
    note.refresh_from_db()
    assert response.status_code == 302
    assert note.read is True


# ---------- CALENDAR FEED ----------


def test_calendar_feed_valid(auth_client, user, mocker):
    user.calendar_token = "abc123"
    user.save()
    Habit.objects.create(user=user, name="Hydrate", periodicity="daily")
    mocker.patch("tracker.views.generate_ics",
                 return_value="BEGIN:VCALENDAR\nEND:VCALENDAR")
    url = reverse("calendar_feed", args=["abc123"])
    response = auth_client.get(user)
    assert response.status_code == 200
    assert b"VCALENDAR" in response.content


def test_calendar_feed_invalid(client):
    response = client.get(reverse("calendar_feed", args=["wrongtoken"]))
    assert response.status_code == 404
