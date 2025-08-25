from django.db.models.signals import post_save, post_delete
from django.dispatch import receiver
from django.utils import timezone

from tracker.models import User, UserProfile, MoodEntry, Habit
from tracker.tasks import send_low_mood_alert, schedule_user_habit_reminders


@receiver(post_save, sender=User)
def create_user_profile(sender, instance, created, **kwargs):
    if created:
        UserProfile.objects.create(user=instance)


@receiver(post_save, sender=User)
def save_user_profile(sender, instance, **kwargs):
    instance.profile.save()


@receiver(post_save, sender=MoodEntry)
def on_mood_saved(sender, instance: MoodEntry, created, **kwargs):
    # Only alert on creation for "today"
    if created and instance.date == timezone.now().date():
        send_low_mood_alert.delay(instance.user_id, instance.id)


@receiver([post_save, post_delete], sender=Habit)
def on_habit_changed(sender, instance: Habit, **kwargs):
    schedule_user_habit_reminders.delay(instance.user_id)
