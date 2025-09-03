"""
Unit tests for tracker form classes:
    - UserProfileForm
    - MoodEntryForm
    - HabitForm
    - NotificationPreferencesForm

Each test focuses on a single behavior of the corresponding Form:
    - Initial population of fields,
    - preservation of existing values when inputs are blank,
    - address creation/update logic,
    - basic valid form flows for mood and habit forms,
    - saving notification preferences.

Notes:
    - Tests run against the Django test database (pytest-django).
    - The app uses a OneToOne user->profile relationship; tests ensure a profile exists
      for each created user (defensive: create it if the signals didn't run).
"""

import pytest
from django.utils import timezone

from tracker.forms import (
    UserProfileForm,
    MoodEntryForm,
    HabitForm,
    NotificationPreferencesForm
)
from tracker.models import User, UserProfile, Address, MoodEntry, Habit


# ----------------------
# Helpers / fixtures
# ----------------------
def ensure_profile(user: User) -> UserProfile:
    """
    Ensure a UserProfile exists for `user`. Returns the profile instance.

    Defensive helper: in some test setups (or if signals are disabled) the
    OneToOne profile may not be auto-created; this helper guarantees it exists.
    """
    profile, _ = UserProfile.objects.get_or_create(user=user)
    return profile


# ----------------------
# UserProfileForm tests
# ----------------------
@pytest.mark.django_db
class TestUserProfileForm:
    """Tests validating UserProfileForm initialization and save behavior."""

    def test_init_populates_address_fields_when_address_exists(self):
        """
        If a profile has an Address, the form.initial should be populated with
        the address fields (street_address, city, state_province, postal_code, country).
        """
        # Create user and ensure profile exists
        user = User.objects.create_user(username="John", password="test123")
        profile = ensure_profile(user)

        # Create an address and attach to the profile
        address = Address.objects.create(
            street_address="123 Test St",
            city="Cape Town",
            state_province="WC",
            postal_code="8000",
            country="ZA"
        )

        profile.address = address
        profile.save()
        profile.refresh_from_db()

        # Initialize form from existing profile - init should copy address values into .initial
        form = UserProfileForm(instance=profile)

        assert form.initial["street_address"] == "123 Test St", "street_address initial not populated"
        assert form.initial["city"] == "Cape Town", "city initial not populated"
        assert form.initial["state_province"] == "WC", "state_province initial not populated"
        assert form.initial["postal_code"] == "8000", "postal_code initial not populated"
        assert form.initial["country"] == "ZA", "country initial not populated"

    def test_save_preserves_existing_fields_if_blank(self):
        """
        If the form is submitted with empty values for certain fields, the save()
        implementation should preserve existing values on the profile for those fields.
        """
        user = User.objects.create_user(username="Sizwe", password="test123")
        profile = ensure_profile(user)

        # Seed existing values that should be preserved when the form is submitted empty
        profile.bio = "existing bio"
        profile.phone_number = "+27727210629"
        profile.save()
        profile.refresh_from_db()

        # Simulate user submitting blank values for bio and phone_number
        form = UserProfileForm(
            instance=profile, data={"bio": "", "phone_number": ""}
        )

        assert form.is_valid(), f"Form should be valid: {form.errors}"
        updated = form.save()

        # Confirm that blank fields did not wipe existing values
        assert updated.bio == "existing bio", "Existing bio should be preserved when blank in form"
        assert (
            updated.phone_number == "+27727210629"
        ), "Existing phone_number should be preserved when blank in form"

    def test_save_updates_existing_address(self):
        """
        If a profile already has an Address, saving the form should update only the
        supplied address fields and preserve address fields left blank in the form.
        """
        user = User.objects.create_user(username="Mona", password="test123")
        profile = ensure_profile(user)

        # Create initial address and attach to profile
        address = Address.objects.create(
            street_address="Jules St",
            city="Johannesburg",
            state_province="Gauteng",
            postal_code="2094",
            country="South Africa"
        )
        profile.address = address
        profile.save()
        profile.refresh_from_db()

        # Submit a form that blanks some address fields and changes others
        form = UserProfileForm(
            instance=profile,
            data={
                "street_address": "Pandora St",  # updated
                "city": "",  # blank -> should preserve existing "Johannesburg"
                "state_province": "Kwa-Zulu Natal",  # updated
                "postal_code": "",  # blank -> preserve "2094"
                "country": "ZA"  # updated
            }
        )

        assert form.is_valid(), f"Form invalid: {form.errors}"
        updated = form.save()

        # Reload address from DB and perform assertions
        updated.address.refresh_from_db()
        assert updated.address.street_address == "Pandora St", "street_address should be updated"
        assert updated.address.city == "Johannesburg", "blank city should preserve old value"
        assert (
            updated.address.state_province == "Kwa-Zulu Natal"
        ), "state_province should be updated"
        assert updated.address.postal_code == "2094", "blank postal_code should preserve old value"
        assert updated.address.country == "ZA", "country should be updated"

    def test_save_creates_new_address_if_any_field_given(self):
        """
        If the profile has no Address and the form contains at least one address field,
        saving the form should create and attach a new Address to the profile.
        """
        user = User.objects.create_user(username="Alex", password="test123")
        profile = ensure_profile(user)

        # Ensure the profile starts without an address
        if profile.address:
            profile.address == None
            profile.save()
            profile.refresh_from_db()

        form = UserProfileForm(
            instance=profile,
            data={
                "street_address": "1 Main Rd",
                "city": "Durban"
                # other fields omitted - creation should still occur
            }
        )

        assert form.is_valid(), f"Form invalid: {form.errors}"
        updated = form.save()

        assert updated.address is not None, "Address should be created when any address field is provided"
        assert updated.address.street_address == "1 Main Rd"
        assert updated.address.city == "Durban"


# ----------------------
# MoodEntryForm tests
# ----------------------
@pytest.mark.django_db
class TestMoodEntryForm:
    """Tests for MoodEntryForm ensuring valid input is accepted and saved properly."""

    def test_form_accepts_valid_data(self):
        """
        Providing valid score and reflection should produce a saved MoodEntry
        with the provided values.
        """
        user = User.objects.create_user(username="Sam", password="test123")

        # Build a new unsaved MoodEntry instance tied to the user for the form instance
        form = MoodEntryForm(
            data={
                "score": 3,
                "reflection": "feeling okay"
            },
            instance=MoodEntry(user=user)
        )

        assert form.is_valid(), f"ModdEntryForm invalid: {form.errors}"
        mood = form.save()

        assert mood.score == 3
        assert mood.reflection == "feeling okay"
        # date default behavior is handled by model; we don't assert date here to keep test focused


# ----------------------
# HabitForm tests
# ----------------------
@pytest.mark.django_db
class TestHabitForm:
    """Tests for HabitForm acceptance of basic valid input."""

    def test_form_accepts_valid_data(self):
        user = User.objects.create_user(username="Lily", password="test123")

        form = HabitForm(
            data={
                "habit": "Meditation",
                "description": "Daily 10 min",
                "periodicity": "daily"
            },
            instance=Habit(user=user)
        )

        assert form.is_valid(), f"HabitForm invalid: {form.errors}"
        habit = form.save()

        assert habit.habit == "Meditation"
        assert habit.periodicity == "daily"
        assert habit.user == user  # ensure ownership was preserved from the instance


# ----------------------------------
# NotificationPreferencesForm tests
# ----------------------------------
@pytest.mark.django_db
class TestNotificationPreferencesForm:
    """Tests that notification preference fields save correctly to the UserProfile model."""

    def test_from_saves_notification_prefs(self):
        user = User.objects.create_user(username="Tom", password="test123")
        profile = ensure_profile(user)

        form = NotificationPreferencesForm(
            instance=profile,
            data={
                "notify_low_mood": True,
                "low_mood_threshold": 2,
                "timezone": "Europe/Paris",
                "reminder_hour_local": 8
            }
        )

        assert form.is_valid(
        ), f"NotificationPreferencesForm invalid: {form.errors}"
        updated = form.save()

        assert updated.notify_low_mood is True
        assert updated.low_mood_threshold == 2
        assert updated.timezone == "Europe/Paris"
        assert updated.reminder_hour_local == 8
