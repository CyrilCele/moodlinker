import pytest
from rest_framework.test import APIClient
from tracker.models import User, Habit


@pytest.mark.django_db
def test_habit_create_limit():
    user = User.objects.create_user(username="apiuser", password="pw")
    client = APIClient()
    client.force_authenticate(user=user)
    for i in range(5):
        response = client.post(
            "/api/habits/", {"habit": f"habit{i}", "periodicity": "daily"})
        assert response.status_code == 201
    # sixth should fail
    response = client.post(
        "/api/habits/", {"habit": "h6", "periodicity": "daily"})
    assert response.status_code == 400
