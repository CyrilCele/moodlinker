"""
Management command to load JSON test fixtures for users, habits, mood entries,
and habit completions.

Expected JSON shape (example):
{
    "users": [
        {
            "username": "cyril",
            "email": "email@example.com",
            "password": "password",
            "habits": [
                {"habit": "Drink water", "description": "2L / day", "periodicity": "daily"}
            ],
            "mood-entries": [
                {"date": "2025-08-01", "score": 4, "reflection": "Feeling okay."}
            ],
            "completions": [
                {"date": "2025-08-01", "habit": "Drink water", "completed": true}
            ]
        }
    ]
}

Notes:
- This command is idempotent-ish: it uses get_or_create / update_or_create
  so running it multiple times updates existing rows, minimizing duplicates.
- All writes are wrapped in a single atomic transaction for consistency.
"""

import json
from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils.dateparse import parse_date

from tracker.models import Habit, MoodEntry, HabitCompletion

User = get_user_model()


class Command(BaseCommand):
    """
    Load JSON test fixtures for Habit, MoodEntry, and HabitCompletion.

    This command ingests a JSON file and:
        1) Creates or updates users.
        2) Creates or updates their habits.
        3) Creates or updates mood entries per date.
        4) Creates or updates habit completions per date.

    All operations execute inside a single database transaction so either
    everything succeeds or no changes are committed.

    Command-line usage:
        python manage.py load_data /path/to/user_mocks_4weeks.json

    Attributes:
        help (str): Short description shown in `manage.py help`.

    Caveats / Edge Cases:
        - JSON schema must match expectations (see module docstring).
        - `parse_date` returns `None` for invalid date strings; current code
          does not guard against this - bad input will cause database errors.
        - A concurrency spike during get_or_create / update_or_create can still
          raise IntegrityError (rare in local fixtures, but possible).
        - INDENTATION WARNING: As written, the loops for mood entries and
          completions are outside the per-user loop. That means only the *last*
          user's mood/completion data will be processed. See inline comment for
          recommended fix.
    """
    help = "Load JSON test fixtures for habits, mood entries, and completions"

    def add_arguments(self, parser):
        """
        Register command-line arguments.

        Args:
            parser (argparse.ArgumentParser): The argument parser provided by Django.

        Adds:
            filepath (str): Path to the JSON fixture file to load.

        Example:
            python manage.py load_data ./fixtures/user_mocks_4weeks.json
        """
        parser.add_argument(
            "filepath",
            type=str,
            help="Path to JSON fixture file"
        )

    def handle(self, *args, **options):
        """
        Entry point for the management command.

        Steps:
            1) Read and parse the JSON file at `filepath`.
            2) Within a transaction:
                a) For each user: get_or_create the user; set password if provided.
                b) Build a map of user's habits by name (get_or_create).
                c) (BUG) After the user loop ends, process mood entries and completions
                  for the last `user_data` only (see inline note).
            3) Print success message.

        Args:
            *args: Unused positional arguments passed by Django.
            **options: Dict containing parsed CLI options (expects "filepath").

        Returns:
            None

        Raises:
            FileNotFoundError: If the provided JSON file path does not exist.
            PermissionError: If the file cannot be read.
            json.JSONDecodeError: If the file is not valid JSON.
            KeyError: If required keys (e.g., "username" or "habit") are missing.
            ValueError: If date parsing fails and is used without validation.
            django.db.IntegrityError: If database constraints are violated.
        """
        path = options["filepath"]

        # Open and parse the JSON fixture file. Use UTF-8 for cross-platform consistency.
        with open(path, "r", encoding="utf-8") as fh:
            data = json.load(fh)

        # Use a single atomic transaction so the dataset is consistent if any error occurs.
        with transaction.atomic():
            for user_data in data.get("users", []):
                username = user_data["username"]

                # Create or fetch the user; provide a default email if missing.
                user, created = User.objects.get_or_create(
                    username=username,
                    defaults={
                        "email": user_data.get("email", f"{username}@example.com")
                    }
                )

                # If we created a new user and have a password, set it properly (hashing it).
                if created and "password" in user_data:
                    user.set_password(user_data["password"])
                    user.save()

                # Create and get all habits for this user and build a lookup map by habit name.
                habits_map = {}
                for habit in user_data.get("habits", []):
                    habit_obj, _ = Habit.objects.get_or_create(
                        user=user,
                        habit=habit["habit"],
                        defaults={
                            "description": habit.get("description", ""),
                            "periodicity": habit.get("periodicity", "daily")
                        }
                    )
                    habits_map[habit["habit"]] = habit_obj

            # -------------------- IMPORTANT INDENTATION NOTE --------------------
            # The following two loops (mood entries and completions) are outisde
            # the `for user_data in data.get("users", [])` loop.
            # As a result, they only process `user_data` and `user` from the LAST
            # iteration of that loop. If your JSON contains multiple users,
            # only the last user's moods/completions will be handled.
            # Consider moving these loops inside the user loop for correct behavior.
            # ---------------------------------------------------------------------

            # Create or update mood entries for the (last) user in the loop above.
            for mood in user_data.get("mood_entries", []):
                date = parse_date(mood["date"]) # May return None if invalid; consider validation.
                MoodEntry.objects.update_or_create(
                    user=user,
                    date=date,
                    defaults={
                        "score": mood["score"], # expected 1...5; model-level choices enforce bounds
                        "reflection": mood.get("reflection", "")
                    }
                )

            # Create or update habit completions for the (last) user.
            for comp in user_data.get("completions", []):
                date = parse_date(comp["date"])
                habit_obj = habits_map.get(comp["habit"])

                # If a completion references an unknown habit, skip it silently.
                # (You might prefer to warn or raise to catch data issues.)
                if not habit_obj:
                    continue

                HabitCompletion.objects.update_or_create(
                    user=user,
                    habit=habit_obj,
                    date=date,
                    defaults={"completed": comp.get("completed", False)}
                )

        self.stdout.write(self.style.SUCCESS("Fixture loaded seccessfully."))
