import json
from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils.dateparse import parse_date

from tracker.models import Habit, MoodEntry, HabitCompletion

User = get_user_model()


class Command(BaseCommand):
    help = "Load JSON test fixtures for habits, mood entries, and completions"

    def add_arguments(self, parser):
        parser.add_argument(
            "filepath", type=str, help="Path to JSON fixture file"
        )

    def handle(self, *args, **options):
        path = options["filepath"]
        with open(path, "r", encoding="utf-8") as fh:
            data = json.load(fh)

        with transaction.atomic():
            for user_data in data.get("users", []):
                username = user_data["username"]
                user, created = User.objects.get_or_create(username=username, defaults={
                    "email": user_data.get("email", f"{username}@example.com")
                })

                if created and "password" in user_data:
                    user.set_password(user_data["password"])
                    user.save()

                # create habits
                habits_map = {}

                for habit in user_data.get("habits", []):
                    habit_obj, _ = Habit.objects.get_or_create(user=user, habit=habit["habit"], defaults={
                        "description": habit.get("description", ""),
                        "periodicity": habit.get("periodicity", "daily"),
                    })
                    habits_map[habit["habit"]] = habit_obj

            # create moods
            for mood in user_data.get("mood_entries", []):
                date = parse_date(mood["date"])
                MoodEntry.objects.update_or_create(user=user, date=date, defaults={
                    "score": mood["score"],
                    "reflection": mood.get("reflection", "")
                })

            # create completitions
            for comp in user_data.get("completions", []):
                date = parse_date(comp["date"])
                habit_obj = habits_map.get(comp["habit"])

                if not habit_obj:
                    continue

                HabitCompletion.objects.update_or_create(
                    user=user, habit=habit_obj, date=date,
                    defaults={"completed": comp.get("completed", False)}
                )

        self.stdout.write(self.style.SUCCESS("Fixture loaded seccessfully."))
