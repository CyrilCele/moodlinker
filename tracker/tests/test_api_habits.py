import pytest
from django.urls import reverse

from rest_framework import status
from rest_framework.test import APIClient

from tracker.models import User


@pytest.mark.django_db
def test_habit_create_limit():
    """
    API-level test: verify a single user cannot create more than 5 habits.

    Behavior verified:
        - The API accepts up to 5 habit creations for an authenticated user (HTTP 201).
        - A sixth attempt returns HTTP 400 (validation failure).

    Implementation notes:
        - Uses DRF APIClient.force_authenticate to avoid calling the auth endpoints
        - Uses `reverse("habits-list")` to resolve the list or create route registered by the router.
        - Posts JSON payloads and checks both status codes and, on failure, includes response data in assertion messages.
    """
    # Create the test user and authenticate the client as that user
    user = User.objects.create_user(username="apiuser", password="pw")
    client = APIClient()
    client.force_authenticate(user=user)

    # Resolve the viewset route name rather than hard-coding the URL
    url = reverse("habits-list")

    # Create up to the allowed limit (5). Each should return 201 CREATED.
    for i in range(5):
        payload = {"habit": f"habit{i}", "periodicity": "daily"}
        response = client.post(url, payload, format="json")

        # Provide the response body in the failure message to speed debugging
        assert response.status_code == status.HTTP_201_CREATED, (
            f"Expected 201 for creation #{i}, got {response.status_code}: {response.data}"
        )

    # A sixth creation should be rejected (400 BAD REQUEST)
    response = client.post(
        url, {"habit": "h6", "periodicity": "daily"}, format="json")
    assert response.status_code == status.HTTP_400_BAD_REQUEST, (
        f"Expected 400 for the sixt habit, got {response.status_code}: {response.data}"
    )

    # Optional sanity: ensure DB still has only 5 habits for the user
    assert user.habits.count() == 5, \
        "User should have exactly 5 habits after the failed sixth attempt"
