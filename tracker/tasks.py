from celery import shared_task
from datetime import datetime, timedelta, time as dtime

from django.conf import settings
from django.core.mail import send_mail
from django.utils import timezone

from tracker.models import Notification, HabitReminder, Habit, MoodEntry, UserProfile
# from tracker.services import send_reminder_email

from zoneinfo import ZoneInfo


def _now_utc():
    return timezone.now()


def _user_local_now(profile: UserProfile):
    return _now_utc().astimezone((profile.tz()))


def _build_next_local_dt(profile: UserProfile, hour: int) -> datetime:
    """
    Next occurrence of HH:00 in user's local timezone (today or tomorrow),
    returned as *UTC* datetime.
    """
    local_now = _user_local_now(profile)
    candidate = datetime.combine(
        local_now.date(), dtime(hour=hour), tzinfo=profile.tz()
    )

    if candidate <= local_now:
        candidate += timedelta(days=1)

    return candidate.astimezone(ZoneInfo("UTC"))


def send_reminder_email(to_email: str, subject: str, message: str):
    """
    Centralized email sender using Gmail SMTP.
    """
    send_mail(
        subject=subject,
        message=message,
        from_email=settings.DEFAULT_FROM_EMAIL,
        recipient_list=[to_email],
        fail_silently=False
    )


def _notify(
        user, message: str, category="info", email=False, subject="MoodLinker Notification"
):
    """
    Create in-app notification and optionally send email.
    """
    Notification.objects.create(user=user, message=message, category=category)
    if email and user.email:
        send_reminder_email(user.email, subject, message)


@shared_task
def send_low_mood_alert(user_id: int, entry_id: int):
    try:
        entry = MoodEntry.objects.get(id=entry_id, user_id=user_id)
        profile = entry.user.profile
    except (MoodEntry.DoesNotExist, UserProfile.DoesNotExist):
        return

    if not profile.notify_low_mood:
        return

    # Only alert if it truly violates the threshold
    if entry.score <= profile.low_mood_threshold:
        _notify(
            entry.user,
            f"Your mood today was {entry.score}. Be kind to yourself - try a small, gentle habit.",
            category="warning",
            email=True,
            subject="Low Mood Alert"
        )


@shared_task
def schedule_user_habit_reminders(user_id: int):
    """
    Create or update HabitReminder rows for all of a user's habits to the next local reminder time.
    """
    from django.contrib.auth import get_user_model

    try:
        User = get_user_model()
        user = User.objects.get(id=user_id)
        profile = user.profile
    except Exception:
        return

    habits = Habit.objects.filter(user=user)
    for habit in habits:
        next_utc = _build_next_local_dt(profile, profile.reminder_hour_local)
        HabitReminder.objects.update_or_create(
            user=user,
            habit=habit,
            defaults={"next_trigger_utc": next_utc, "active": True}
        )


@shared_task
def process_due_reminders():
    """
    Runs every minute (Celery Beat). Sends reminders that are due and bumps their next_trigger_utc.
    """
    now = _now_utc()
    due = HabitReminder.objects \
        .select_related("user", "habit", "user__profile") \
        .filter(active=True, next_trigger_utc__lte=now)

    for reminder in due:
        # send reminder
        _notify(
            reminder.user,
            f"Reminder: '{reminder.habit.habit}' - a tiny step today goes a long way.",
            category="info",
            email=True,
            subject="Habit Reminder"
        )

        # reschedule next occurrence for tomorrow at user's local reminder hour
        try:
            profile = reminder.user.profile
        except UserProfile.DoesNotExist:
            profile = None

        if profile:
            reminder.next_trigger_utc = _build_next_local_dt(
                profile, profile.reminder_hour_local
            )
        else:
            # fallback: +24h
            reminder.next_trigger_utc = now + timedelta(days=1)

        reminder.save(update_fields=["next_trigger_utc"])


@shared_task
def rebuild_all_user_reminders():
    """
    Nightly maintenance to ensure every active habit has a reminder row.
    """
    from django.contrib.auth import get_user_model
    User = get_user_model()

    for user in User.objects.all():
        schedule_user_habit_reminders.delay(user.id)


# This is for demo purposes: goes with the Gmail SMTP
@shared_task
def send_mood_reminder(user_email, mood_level):
    """
    Demo / simple reminder email.
    """

    subject = "MoodLinker Reminder"
    if mood_level < 3:
        message = (
            "We noticed your mood has been low."
            "Try completing a habit today - it may lift your spirits! 💙"
        )
    else:
        message = "Keep up the good work! Stay consistent with your habits 🙌"

    send_reminder_email(user_email, subject, message)
