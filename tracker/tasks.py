from celery import shared_task

from django.contrib.auth.models import User
from django.core.mail import send_mail  # Assuming email reminders

from tracker.models import MoodEntry


@shared_task
def send_daily_reminder():
    """
    This task runs daily (via celery beat) to check each user's recent mood/habit
    and send a reminder or motivational message.
    """
    from datetime import date, timedelta
    today = date.today()
    yesterday = today - timedelta(days=1)
    users = User.objects.all()
    for user in users:
        # If yesterday's mood was low (score <=2), send a motivational mail
        mood = MoodEntry.objects.filter(user=user, date=yesterday).first()
        if mood and mood.score <= 2:
            send_mail(
                subject="Keep Going! 🌟",
                message=f"Hi {user.username}, we noticed you had a rough day yesterday. Keep up with your habits! You've got this!",
                from_email="noreply@moodlinker.com",
                recipient_list="[user.email]",
            )
