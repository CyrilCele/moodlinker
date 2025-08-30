import pytest

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
            username="tester3", password="pass123"
        )

        score = MoodEntry.objects.create(
            user=user, score=1, date=timezone.now().date()
        )

        mock_task.assert_called_once_with(user.id, score.id)

    @patch("tracker.signals.send_low_mood_alert.delay")
    def test_on_mood_saved_does_not_trigger_for_past_date(self, mock_task, django_user_model):
        user = django_user_model.objects.create_user(
            username="tester4", password="pass123"
        )

        yesterday = timezone.now().date() - timezone.timedelta(days=1)
        mood = MoodEntry.objects.create(user=user, score=5, reflection="happy")
        mood.date = yesterday
        mood.save(update_fields=["date"])

        mock_task.assert_not_called()

    @patch("tracker.signals.send_low_mood_alert.delay")
    def test_on_mood_saved_does_not_trigger_on_update(self, mock_task, django_user_model):
        user = django_user_model.objects.create_user(
            username="tester5", password="pass123"
        )

        score = MoodEntry.objects.create(
            user=user, score=2, date=timezone.now().date()
        )

        mock_task.reset_mock()

        # Update existing entry (signal should NOT call)
        score.score = 2
        score.save()

        mock_task.assert_not_called()


@pytest.mark.django_db
class TestHabitSignals:
    @patch("tracker.signals.schedule_user_habit_reminders.delay")
    def test_on_habit_created_triggers_task(self, mock_task, django_user_model):
        user = django_user_model.objects.create_user(
            username="tester6", password="pass123"
        )

        habit = Habit.objects.create(user=user, habit="Drink Water")

        mock_task.assert_called_once_with(user.id)

    @patch("tracker.signals.schedule_user_habit_reminders.delay")
    def test_on_habit_updated_triggers_task(self, mock_task, django_user_model):
        user = django_user_model.objects.create_user(
            username="tester7", password="pass123"
        )

        habit = Habit.objects.create(user=user, habit="Run 5km")

        mock_task.reset_mock()

        habit.habit = "Run 10km"
        habit.save()

        mock_task.assert_called_once_with(user.id)

    @patch("tracker.signals.schedule_user_habit_reminders.delay")
    def test_on_habit_deleted_triggers_task(self, mock_task, django_user_model):
        user = django_user_model.objects.create_user(
            username="tester8", password="pass123"
        )

        habit = Habit.objects.create(user=user, habit="Meditate")

        mock_task.reset_mock()
        habit.delete()

        mock_task.assert_called_once_with(user.id)
