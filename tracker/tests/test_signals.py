"""
Signal behavior tests for the tracker application.

Covered signals:
    - User profile creation/synchroniztion when a `User` is saved.
    - Low-mood alert task dispatch when a `MoodEntry` is created for "today".
    - Habit reminder (re)scheduling when a `Habit` is created/updated/deleted.
"""

from datetime import timedelta
from unittest.mock import patch

import pytest
from django.utils import timezone

from tracker.models import UserProfile, MoodEntry, Habit


@pytest.mark.django_db
class TestUserSignals:
    """
    Tests for user-related signals (profile creation and sync).
    """

    def test_create_user_profile_signal_creates_profile(self, django_user_model):
        """
        Creating a User should also create a related UserProfile via post_save.

        Steps:
            1) Create a user.
            2) Assert `user.profile` exists and is a `UserProfile`.
        """
        user = django_user_model.objects.create_user(
            username="tester", password="pass123"
        )

        assert hasattr(
            user, "profile"), "User should have a related `profile` attribute."
        assert isinstance(
            user.profile, UserProfile), "Related object must be a UserProfile instance."

    def test_save_user_profile_signal_is_called(self, django_user_model):
        """
        Saving a User should trigger a signal that also persists the related profile.

        We modify the profile before saving the user. If the signal's handler saves
        `instance.profile` (common pattern), the change persists.
        """
        user = django_user_model.objects.create_user(
            username="tester2", password="pass123"
        )

        # Update profile and save the user (post_save should touch profile).
        user.profile.bio = "Updated bio"
        user.save()  # Expected to trigger the `save_user_profile` signal.
        user.refresh_from_db()

        assert user.profile.bio == "Updated bio", "Profile bio should persist after User save()"


@pytest.mark.django_db
class TestMoodEntrySignals:
    """Tests for mood-entry signals (low-mood alert task dispatch)."""
    @patch("tracker.signals.send_low_mood_alert.delay")
    def test_on_mood_saved_triggers_task_for_today(self, mock_task, django_user_model):
        """
        Creating a MoodEntry for today should enqueue the low-mood alert task.

        We don't assert on "low" specifically here because that logic may live in the
        signal handler; we assert the task is dispatched with expected args.
        """
        user = django_user_model.objects.create_user(
            username="tester3", password="pass123"
        )
        today = timezone.localdate()

        entry = MoodEntry.objects.create(
            user=user, score=1, date=today
        )

        mock_task.assert_called_once_with(user.id, entry.id)

    @patch("tracker.signals.send_low_mood_alert.delay")
    def test_on_mood_saved_does_not_trigger_for_past_date(self, mock_task, django_user_model):
        """
        Creating a MoodEntry for a past date should NOT enqueue the task.

        Important: Create the entry WITH the past date initially. If you create today
        and then change to yesterday, the signal will have already fired on create.
        """
        user = django_user_model.objects.create_user(
            username="tester4", password="pass123"
        )
        yesterday = timezone.localdate() - timedelta(days=1)

        MoodEntry.objects.create(
            user=user, score=5, reflection="happy", date=yesterday
        )

        mock_task.assert_not_called()

    @patch("tracker.signals.send_low_mood_alert.delay")
    def test_on_mood_saved_does_not_trigger_on_update(self, mock_task, django_user_model):
        """
        Updating an existing MoodEntry for today should NOT enqueue the task again.

        Steps:
            1) Create today's entry (signal might have fired once here).
            2) Reset the mock.
            3) Save an update to the same entry.
            4) Assert no new calls were made.
        """
        user = django_user_model.objects.create_user(
            username="tester5", password="pass123"
        )
        entry = MoodEntry.objects.create(
            user=user, score=2, date=timezone.localdate()
        )

        # Ignore the call from the create above; we are testing updates only.
        mock_task.reset_mock()

        entry.score = 2  # No logical change, but still triggers save()
        entry.save()

        mock_task.assert_not_called()


@pytest.mark.django_db
class TestHabitSignals:
    """Tests for habit signals that (re)schedule reminders."""
    @patch("tracker.signals.schedule_user_habit_reminders.delay")
    def test_on_habit_created_triggers_task(self, mock_task, django_user_model):
        """
        Creating a Habit should enqueue reminder scheduling for that user.
        """
        user = django_user_model.objects.create_user(
            username="tester6", password="pass123"
        )

        Habit.objects.create(user=user, habit="Drink Water")

        mock_task.assert_called_once_with(user.id)

    @patch("tracker.signals.schedule_user_habit_reminders.delay")
    def test_on_habit_updated_triggers_task(self, mock_task, django_user_model):
        """
        Updating a Habit should also enqueue reminder (re)scheduling.
        """
        user = django_user_model.objects.create_user(
            username="tester7", password="pass123"
        )

        habit = Habit.objects.create(user=user, habit="Run 5km")

        # Ignore the call from create; focus on the update path.
        mock_task.reset_mock()

        habit.habit = "Run 10km"
        habit.save()

        mock_task.assert_called_once_with(user.id)

    @patch("tracker.signals.schedule_user_habit_reminders.delay")
    def test_on_habit_deleted_triggers_task(self, mock_task, django_user_model):
        """
        Deleting a Habit should enqueue reminder (re)scheduling
        (often to cancel or adjust pending reminders).
        """
        user = django_user_model.objects.create_user(
            username="tester8", password="pass123"
        )
        habit = Habit.objects.create(user=user, habit="Meditate")

        # Ignore the call from create; focus on the delete path.
        mock_task.reset_mock()

        habit.delete()

        mock_task.assert_called_once_with(user.id)
