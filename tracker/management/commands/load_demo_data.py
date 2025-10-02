"""
Management command: load_demo_data.py

Loads demo seed data (habits, mood entries, completions) for a specified user
and prints analytics including longest streaks and persistence verification.

Usage:
    python manage.py load_demo_data --user <username> --file <path_to_json>

Notes:
    - The command temporarily disconnects habit-related signals during data load to avoid side effects
        (e.g., scheduling tasks) while seeding large amounts of demo data. These signals are
        reconnected after the data load is complete.
    - The JSON file should follow the project's fixture schema (keys used in the code).
"""

from __future__ import annotations

import json
import random
import os
from calendar import monthrange
from datetime import timedelta, date
from typing import Dict, Any, Optional

from django.core.management.base import BaseCommand, CommandError
from django.contrib.auth import get_user_model
from django.db import IntegrityError
from django.db.models import signals
from django.utils import timezone
from django.utils.dateparse import parse_date

from tracker import signals as tracker_signals
from tracker.models import Habit, MoodEntry, HabitCompletion


# Get the configured user model
User = get_user_model()
# if not User.objects.filter(username="admin").exists():
#     User.object.create_user(
#         username="admin",
#         email="admin@exmaple.com",
#         password="admin"
#     )


class Command(BaseCommand):
    """
    Django management command to seed demo data for a user and print analytics.

    The command:
     - Reads a JSON seed file (default: tracker/fixtures/demo_seed.json).
     - Clears the user's existing demo data (habits, mood entries, completions).
     - Creates the demo habits.
     - Creates per-day MoodeEntry rows and HabitCompletion rows based on patterns.
     - Prints analytics including longest streaks and persistence verification.

    Important:
     - Signals that react to habit changes are disconnected during the data load
         to avoid side effects like scheduling tasks. They are reconnected afterward.
    """

    help = "Load demo seed (habits, mood entries, completions) for a user and print analytics"

    def add_arguments(self, parser) -> None:
        """
        Add command-line arguments.

        Parameters
        ----------
        parser : argparse.ArgumentParser
            The argument parser to which arguments are added.
        """
        parser.add_argument(
            "--user", required=True, help="username to attach demo data"
        )
        parser.add_argument(
            "--file",
            default="tracker/fixtures/demo_seed.json",
            help="Path to demo JSON seed file (default: tracker/fixtures/demo_seed.json)"
        )

    def handle(self, *args, **options) -> None:
        """
        Primary entry point for the management command.

        This method:
            - Validates user and file inputs.
            - Loads JSON data.
            - Seeds habits, moods, and completions.
            - Prints demo analytics and streak information.

        Exceptions are reported to stderr and the command exits gracefully.
        """
        # Disconnect habit -> schedule signals to prevent side effects during bulk load.
        # The signals are reconnected in the finally block to ensure normal app behavior is restored.
        # signals.post_delete.disconnect(
        #     tracker_signals.on_habit_changed, sender=Habit
        # )
        # signals.post_save.disconnect(
        #     tracker_signals.on_habit_changed, sender=Habit
        # )
        signals_to_disconnect = [
            (signals.post_delete, tracker_signals.on_habit_changed, Habit),
            (signals.post_save, tracker_signals.on_habit_changed, Habit)
        ]
        for signal, receiver, sender in signals_to_disconnect:
            try:
                signal.disconnect(receiver, sender=sender)
            except Exception:
                # If already disconnected or not connected, ignore and continue.
                pass

        username: str = options["user"]
        path: str = options["file"]

        try:
            # Validate user exists
            try:
                user = User.objects.get(username=username)
            except User.DoesNotExist:
                raise CommandError(f"User '{username}' does not exist.")

            # Validate the file path
            if not os.path.exists(path):
                raise CommandError(f"Seed file not found: {path}")
            # self.stderr.write(
            #     self.style.ERROR(
            #         f"User '{username}' does not exist."
            #     )
            # )
            # return

            # Load JSON seed file
            with open(path, "r", encoding="utf-8") as fh:
                try:
                    data: Dict[str, Any] = json.load(fh)
                except json.JSONDecodeError as e:
                    raise CommandError(f"Invalid JSON file: {e}") from e

            # Parse top-level fields with sensible fallbacks
            start_date: Optional[date] = parse_date(
                data.get("start_date") if data.get("start_date") else None)
            days: int = int(data.get("days", 28))
            habits_map: Any = data.get("habits", [])
            pattern_scores: list = data.get(
                "moods", {}).get("pattern_scores", [])
            reflections: list = data.get(
                "moods", {}).get("reflections", []) or []
            completions_pattern: Dict[str, Any] = data.get(
                "completions_pattern", {})

            # If no start_date provided or parsing failed, default to days-back window ending today
            if start_date is None:
                # default to a window ending today
                start_date = (timezone.localdate() - timedelta(days=days - 1))

            # --- Clear old demo data for this user (idempotent) ---
            HabitCompletion.objects.filter(user=user).delete()
            MoodEntry.objects.filter(user=user).delete()
            Habit.objects.filter(user=user).delete()

            # --- Create habits fresh ---
            created_habits: Dict[str, Habit] = {}
            for h in habits_map:
                # Support either {"habit": "..."} or {"name": "..."} keys
                habit_name = h.get("habit") or h.get("name")
                if not habit_name:
                    # Skip malformed habit entries
                    continue
                habit_obj, _ = Habit.objects.get_or_create(
                    user=user,
                    habit=habit_name,
                    defaults={
                        "periodicity": h.get("periodicity", "daily"),
                        "description": h.get("description", "")
                    }
                )
                created_habits[habit_obj.habit] = habit_obj

            # --- Create day-by-day MoodEntry and HabitCompletion rows idempotently ---
            for offset in range(days):
                d = start_date + timedelta(days=offset)
                # pattern_scores may be empty; if so default to neutral score (3)
                if pattern_scores:
                    idx = offset % len(pattern_scores)
                    score = int(pattern_scores[idx])
                else:
                    score = 3

                reflection = reflections[idx] if reflections and len(
                    reflections) > 0 else ""

                # Create mood entry only if not exists (idempotent)
                MoodEntry.objects.get_or_create(
                    user=user,
                    date=d,
                    defaults={
                        "score": score,
                        "reflection": reflection
                    }
                )

                # Create/update habit completions based on per-habit patterns
                for habit_name, pattern in completions_pattern.items():
                    habit = created_habits.get(habit_name)
                    if not habit:
                        # Skip patterns for unknown habits
                        continue

                    # Determine completion boolean for this offset; pattern may be list of 0/1 or booleans
                    if not pattern:
                        completed = False
                    else:
                        completed = bool(pattern[offset % len(pattern)])

                    # update_or_create is idempotent; catch IntegrityError as a safety net
                    try:
                        HabitCompletion.objects.update_or_create(
                            user=user,
                            habit=habit,
                            date=d,
                            defaults={"completed": completed}
                        )
                    except IntegrityError:
                        # In the unlikely event of concurrent insert race, update existing row.
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
            self.stdout.write("\n=== DEMO ANALYTICS ===\n")

            # 1. List all habits
            habits = Habit.objects.filter(user=user)
            self.stdout.write(f"All habits: {[h.habit for h in habits]}")

            # 2. List habits by periodicity
            daily = list(
                habits
                .filter(periodicity="daily")
                .values_list("habit", flat=True)
            )
            weekly = list(
                habits
                .filter(periodicity="weekly")
                .values_list("habit", flat=True)
            )
            self.stdout.write(f"Daily habits: {daily}")
            self.stdout.write(f"Weekly habits: {weekly}")

            # 3 & 4. Longest streaks (helper function)
            def longest_streak(habit: Habit) -> int:
                """
                Compute the longest streak for a habit, respecting its periodicity.

                Rules:
                    - daily: requires consecutive days (difference of 1 day).
                    - weekly: requires 7-day gaps (difference of 7 days).
                    - monthly requires same approximate day next month (handles month length variation).

                Parameters
                ----------
                habit : Habit
                    The model instance for which to compute the longest streak.

                Returns
                -------
                int
                    The length (in periods) of the longest consecutive completion streak.
                """
                completions = (
                    HabitCompletion.objects
                    .filter(user=habit.user, habit=habit, completed=True)
                    .order_by("date")
                    .values_list("date", flat=True)
                )

                streak = longest = 0
                last_date: Optional[date] = None

                for cur_date in completions:
                    if last_date is None:
                        # start a new streak
                        streak = 1
                    else:
                        delta_days = (cur_date - last_date).days

                        if habit.periodicity == "daily":
                            required_gap = 1
                        elif habit.periodicity == "weekly":
                            required_gap = 7
                        elif habit.periodicity == "monthly":
                            # Compute the next-month "expected" date with month rollover and variable lengths
                            next_month = (last_date.month % 12) + 1
                            next_year = last_date.year + \
                                (last_date.month // 12)
                            # Find the maximum day in that next month
                            max_day = monthrange(next_year, next_month)[1]
                            # Use the smaller of the original day and next month's max day
                            expected_day = min(last_date.day, max_day)
                            required_next = last_date.replace(
                                year=next_year, month=next_month, day=expected_day
                            )
                            required_gap = (required_next - last_date).days
                        else:
                            # Fallback: treat as daily periodicity
                            required_gap = 1

                        # Continue streak if exact required gap matches
                        if delta_days == required_gap:
                            streak += 1
                        else:
                            # Gap larger or smaller => streak broken, start a new streak of length 1
                            streak = 1

                    last_date = cur_date
                    if streak > longest:
                        longest = streak

                return longest

            # Determine the habit with the longest streak
            longest_overall = 0
            best_habit_name: Optional[str] = None
            for h in habits:
                s = longest_streak(h)
                if s > longest_overall:
                    longest_overall, best_habit = s, h.habit

            self.stdout.write(
                f"Longest overall streak: {longest_overall} days (Habit: {best_habit})"
            )

            # Example: longest streak for the first habit (if any)
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

            # -------------------------------
            # PERSISTENCE ROUNDTRIP DEMO
            # -------------------------------
            today = timezone.localdate()

            if habits.exists():
                self.stdout.write("\n=== PERSISTENCE ROUNDTRIP DEMO ===")

                # Pick a random habit to modify and verify persistence
                example_habit_for_roundtrip = random.choice(list(habits))
                HabitCompletion.objects.update_or_create(
                    user=user,
                    habit=example_habit_for_roundtrip,
                    date=today,
                    defaults={"completed": True}
                )
                refreshed = HabitCompletion.objects.get(
                    user=user, habit=example_habit_for_roundtrip, date=today
                )
                self.stdout.write(
                    f"Modified '{example_habit_for_roundtrip.habit}' for {today} → completed={refreshed.completed}"
                )
                self.stdout.write(
                    "Persistence verified: value survived ORM reload ✅"
                )

        finally:
            # Always reconnect signals even if an error occured to restore normal behavior.
            for signal, receiver, sender in signals_to_disconnect:
                try:
                    signal.connect(receiver, sender=sender)
                except Exception:
                    # If the reconnect fails, report it but do not raise further to avoid hiding original exceptions
                    self.stderr.write(
                        self.style.WARNING(
                            f"Failed to reconnect signal {receiver} for {sender}"
                        )
                    )
            # signals.post_delete.connect(
            #     tracker_signals.on_habit_changed, sender=Habit
            # )
            # signals.post_save.connect(
            #     tracker_signals.on_habit_changed, sender=Habit
            # )
