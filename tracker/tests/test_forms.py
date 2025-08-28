import pytest
from tracker.forms import (
    UserProfileForm,
    MoodEntryForm,
    HabitForm,
    NotificationPreferencesForm
)
from tracker.models import User, UserProfile, Address, MoodEntry, Habit


@pytest.mark.django_db
class TestUserProfileForm:
    def test_init_populates_address_fields_when_address_exists(self):
        user = User.objects.create_user(username="John", password="test123")
        address = Address.objects.create(
            street_address="123 Test St",
            city="Cape Town",
            state_province="WC",
            postal_code="8000",
            country="ZA"
        )
        profile = UserProfile.objects.create(user=user, address=address)

        form = UserProfileForm(instance=profile)
        assert form.initial["street_address"] == "123 Test St"
        assert form.initial["city"] == "Cape Town"
        assert form.initial["state_province"] == "WC"

    def test_save_preserves_existing_fields_if_blank(self):
        user = User.objects.create_user(username="Sizwe", password="test123")
        profile = UserProfile.objects.create(
            user=user, bio="existing bio", phone_number="+27727210629")
        form = UserProfileForm(instance=profile, data={
                               "bio": "", "phone_number": ""})

        assert form.is_valid()
        updated = form.save()

        assert updated.bio == "existing bio"
        assert updated.phone_number == "+27727210629"

    def test_save_updates_existing_address(self):
        user = User.objects.create_user(username="Mona", password="test123")
        address = Address.objects.create(street_address="Jules St", city="Johannesburg",
                                         state_province="Gauteng", postal_code="2094", country="South Africa")
        profile = UserProfile.objects.create(user=user, address=address)
        form = UserProfileForm(
            instance=profile,
            data={
                "street_address": "Pandora St",
                "city": "",
                "state_province": "Kwa-Zulu Natal",
                "postal_code": "",
                "country": "ZA"
            }
        )
        assert form.is_valid()

        updated = form.save()
        updated.address.refresh_from_db()

        # New values applied, blanks preserved as old values
        assert updated.address.street_address == "Pandora St"
        assert updated.address.city == "Johannesburg"  # preserved
        assert updated.address.state_province == "Kwa-Zulu Natal"
        assert updated.address.postal_code == "2094"  # preserved
        assert updated.address.country == "ZA"

    def test_save_creates_new_address_if_any_field_given(self):
        user = User.objects.create_user(username="Alex", password="test123")
        profile = UserProfile.objects.create(user=user)
        form = UserProfileForm(
            instance=profile,
            data={
                "street_address": "1 Main Rd",
                "city": "Durban"
            }
        )
        assert form.is_valid()
        updated = form.save()

        assert updated.address is not None
        assert updated.address.street_address == "1 Main Rd"
        assert updated.address.city == "Durban"


@pytest.mark.django_db
class TestMoodEntryForm:
    def test_form_accepts_valid_data(self):
        user = User.objects.create_user(username="Sam", password="test123")
        form = MoodEntryForm(
            data={
                "score": 3,
                "reflection": "feeling okay"
            },
            instance=MoodEntry(user=user)
        )
        assert form.is_valid()
        mood = form.save()
        assert mood.score == 3
        assert mood.reflection == "Feeling okay"


@pytest.mark.django_db
class TestHabitForm:
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
        assert form.is_valid()
        habit = form.save()
        assert habit.habit == "Meditation"
        assert habit.periodicity == "daily"


@pytest.mark.django_db
class TestNotificationPreferencesForm:
    def test_from_saves_notification_prefs(self):
        user = User.objects.create_user(username="Tom", password="test123")
        profile = UserProfile.objects.create(user=user)
        form = NotificationPreferencesForm(
            instance=profile,
            data={
                "notify_low_mood": True,
                "low_mood_threshold": 2,
                "timezone": "Europe/Paris",
                "reminder_hour_local": 8
            }
        )
        assert form.is_valid()
        updated = form.save()

        assert updated.notify_low_mood is True
        assert updated.low_mood_threshold == 2
        assert updated.timezone == "Europe/Paris"
        assert updated.reminder_hour_local == 8
