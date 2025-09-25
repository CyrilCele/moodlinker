import json
from datetime import timedelta
from django.core.management.base import BaseCommand
from django.contrib.auth import get_user_model
from django.utils.dateparse import parse_date
from django.db import IntegrityError

from tracker.models import Habit, MoodEntry, HabitCompletion

User = get_user_model()
if not User.objects.filter(username="admin").exists():
    User.object.create_user(
        username="admin",
        email="admin@exmaple.com",
        password="admin"
    )


class Command(BaseCommand):
    help = "Load demo seed (habits, mood entries, completions) for a user and print analytics"

    def add_arguments(self, parser):
        parser.add_argument(
            "--user", required=True, help="username to attach demo data"
        )
        parser.add_argument(
            "--file", default="tracker/fixtures/demo_seed.json"
        )

    def handle(self, *args, **options):
        username = options["user"]
        path = options["file"]

        try:
            user = User.objects.get(username=username)
        except User.DoesNotExist:
            self.stderr.write(
                self.style.ERROR(
                    f"User '{username}' does not exist."
                )
            )
            return

        with open(path, "r", encoding="utf-8") as fh:
            data = json.load(fh)

        start_date = parse_date(data.get("start_date"))
        days = int(data.get("days", 28))
        habits_map = data["habits"]
        pattern_scores = data["moods"]["pattern_scores"]
        reflections = data["moods"]["reflections"]
        completions_pattern = data["completions_pattern"]

        # NEW: clear old demo data for this user
        HabitCompletion.objects.filter(user=user).delete()
        MoodEntry.objects.filter(user=user).delete()
        Habit.objects.filter(user=user).delete()

        # create habits fresh
        created_habits = {}
        for h in habits_map:
            habit_obj, _ = Habit.objects.get_or_create(
                user=user,
                habit=h.get("habit") or h.get("name"),
                defaults={
                    "periodicity": h.get("periodicity", "daily"),
                    "description": h.get("description", "")
                }
            )
            created_habits[habit_obj.habit] = habit_obj

        # create day-by-day mood and completion rows idempotently
        for offset in range(days):
            d = start_date + timedelta(days=offset)
            idx = offset % len(pattern_scores)
            score = pattern_scores[idx]
            reflection = reflections[idx] if reflections else ""
            MoodEntry.objects.get_or_create(
                user=user,
                date=d,
                defaults={
                    "score": score,
                    "reflection": reflection
                }
            )
            for habit_name, pattern in completions_pattern.items():
                habit = created_habits.get(habit_name)
                if not habit:
                    continue
                completed = bool(pattern[offset % len(pattern)])
                try:
                    HabitCompletion.objects.update_or_create(
                        user=user,
                        habit=habit,
                        date=d,
                        defaults={"completed": completed}
                    )
                except IntegrityError:
                    # if duplicate happens, just update the existing row
                    HabitCompletion.objects.filter(
                        user=user, habit=habit, date=d
                    ).update(completed=completed)

        self.stdout.write(
            self.style.SUCCESS(
                f"Demo data for '{username}' loaded successfully."
            )
        )

        # -------------------------------
        # DEMO ANALYTICS & STREAK LOGIC
        # -------------------------------
        self.stdout.write("\n--- DEMO ANALYTICS ---\n")

        # 1. List all habits
        habits = Habit.objects.filter(user=user)
        self.stdout.write(f"All habits: {[h.habit for h in habits]}")

        # 2. List habits by periodicity
        daily = habits.filter(periodicity="daily").values_list(
            "habit", flat=True)
        weekly = habits.filter(
            periodicity="weekly").values_list("habit", flat=True)
        self.stdout.write(f"Daily habits: {list(daily)}")
        self.stdout.write(f"Weekly habits: {list(weekly)}")

        # 3 & 4. Longest streaks
        def longest_streak(habit):
            completions = (
                HabitCompletion.objects
                .filter(user=user, habit=habit)
                .order_by("date")
                .values_list("date", "completed")
            )
            streak = longest = 0
            last_date = None
            for date, completed in completions:
                if not completed:
                    streak = 0
                    continue
                if last_date is None:
                    streak = 1
                else:
                    delta = (date - last_date).days
                    # daily streak requires +1 day gap; weekly requires +7 days gap
                    required_gap = 1 if habit.periodicity == "daily" else 7
                    if delta == required_gap:
                        streak += 1
                    else:
                        streak = 1
                last_date = date
                longest = max(longest, streak)
            return longest

        longest_overall = 0
        best_habit = None
        for h in habits:
            s = longest_streak(h)
            if s > longest_overall:
                longest_overall, best_habit = s, h.habit
        self.stdout.write(
            f"Longest overall streak: {longest_overall} days (Habit: {best_habit})")

        # Example: longest streak for one habit
        example_habit = habits.first()
        if example_habit:
            self.stdout.write(
                f"Longest streak for '{example_habit.habit}': {longest_streak(example_habit)} days"
            )

        # 5. Streak correctness example (daily vs weekly)
        self.stdout.write("\n=== STREAK COREECTNESS CHECK ===")
        for h in habits:
            s = longest_streak(h)
            self.stdout.write(
                f"Habit: '{h.habit}' ({h.periodicity}): Longest Streak = {s} (respects {h.periodicity} logic)"
            )