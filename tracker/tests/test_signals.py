import pytest

from django.db.models.signals import post_save, post_delete
from django.utils import timezone

from unittest.mock import patch

from tracker.models import User, UserProfile, MoodEntry, Habit


@pytest.mark.django_db
class TestUserSignals:
    def test_create_user_profile_signal_creates_profile(self):
        user = User.objects.create_user(username="tester", password="pass123")
        assert hasattr(user, "profile")
        assert isinstance(user.profile, UserProfile)

    def test_save_user_profile_signal_is_called(self):
        user = User.objects.create_user(username="tester2", password="pass123")
        # Modify something on profile
        user.profile.bio = "Updated bio"
        user.save()  # triggers save_user_profile signal
        user.refresh_from_db()
        assert user.profile.bio == "Updated bio"


@pytest.mark.django_db
class TestMoodEntrySignals:
    @patch("tracker.signals.send_low_mood_alert.delay")
    def test_on_mood_saved_triggers_task_for_today(self, mock_task, django_user_model):
        user = django_user_model.objects.create_user(
            username="tester3", password="pass123")
        mood = MoodEntry.objects.create(
            user=user, mood="sad", date=timezone.now().date())

        mock_task.assert_called_once_with(user.id, mood.id)

    @patch("tracker.signals.send_low_mood_alert.delay")
    def test_on_mood_saved_does_not_trigger_for_past_date(self, mock_task, django_user_model):
        user = django_user_model.objects.create_user(
            username="tester4", password="pass123")
        yesterday = timezone.now().date() - timezone.timedelta(days=1)
        MoodEntry.objects.create(user=user, mood="happy", date=yesterday)

        mock_task.assert_not_called()

    @patch("tracker.signals,send_low_mood_alert.delay")
    def test_on_mood_saved_does_not_trigger_on_update(self, mock_task, django_user_model):
        user = django_user_model.objects.create_user(
            username="tester5", password="pass123")
        mood = MoodEntry.objects.create(
            user=user, mood="neutral", date=timezone.now().date())
        mock_task.reset_mock()

        # Update existing entry (signal should NOT call)
        mood.mood = "sad"
        mood.save()

        mock_task.assert_not_called()


@pytest.mark.django_db
class TestHabitSignals:
    @patch("tracker.signals.schedule_user_habit_reminders.delay")
    def test_on_habit_created_triggers_task(self, mock_task, django_user_model):
        user = django_user_model.objects.create_user(
            username="tester6", password="pass123")
        habit = Habit.objects.create(user=user, name="Drink Water")

        mock_task.assert_called_once_with(user.id)

    @patch("tracker.signals.schedule_user_habit_reminders.delay")
    def test_on_habit_updated_triggers_task(self, mock_task, django_user_model):
        user = django_user_model.objects.create_user(
            username="tester7", password="pass123")
        habit = Habit.objects.create(user=user, name="Run 5km")
        mock_task.reset_mock()

        habit.name = "Run 10km"
        habit.save()

        mock_task.assert_called_once_with(user.id)

    @patch("tracker.signals.schedule_user_habit_reminders.delay")
    def test_on_habit_deleted_triggers_task(self, mock_task, django_user_model):
        user = django_user_model.objects.create_user(
            username="tester8", password="pass123")
        habit = Habit.objects.create(user=user, name="Meditate")
        mock_task.reset_mock()

        habit.delete()

        mock_task.assert_called_once_with(user.id)
