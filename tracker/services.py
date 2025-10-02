from collections import defaultdict
from datetime import timedelta
from statistics import mean

from django.utils import timezone

from nltk.sentiment import SentimentIntensityAnalyzer

from tracker.models import Habit, MoodEntry, HabitCompletion


class AnalyticsService:
    """
    Analytics helpers for MoodLinker.

    Responsibilities:
        - Compute streaks for a habit.
        - Produce a label/mood/completion rate summaries suitable for Chart.js.

    Notes:
        - Methods are simple, ORM-based implementations suitable for small-to-medium
          datasets. For large datasets consider DB-side aggregation and caching.
    """

    @staticmethod
    def longest_streak(user, habit: Habit) -> int:
        """
        Compute the current consecutive-day completion streak for a specific habit.

        Description:
            Starting from today and moving backwards day-by-day, count how many
            consecutive calendar days the given `habit` has a `HabitCompletion`
            with `completed=True` for `user`.

        Args:
            user (User): The Django User instance owning the habit.
            habit (Habit): The Habit instance for which to compute the streak.

        Returns:
            int: Number of consecutive days (including today if completed).
                 Zero if no completion for today (or earlier days).

        Raises:
            >>> streak = AnayticsService.longest_streak(request.user, habit)
            >>> print(streak) # e.g., 3

        Important notes / edge cases:
            - The implementation issues one DB query per day in the streak loop.
              For long streaks or many users this can be inefficient.
            - If `HabitCompletion` rows have gaps or multiple completions per day,
              the function uses `exists()` semantics (true if any completed row exists).
        """
        today = timezone.now().date()
        streak = 0
        day = today

        while True:
            exists = HabitCompletion.objects.filter(
                user=user, habit=habit, date=day, completed=True
            ).exists()

            if not exists:
                break

            streak += 1
            day -= timedelta(days=1)

        return streak

    @staticmethod
    def summaries(user, view: str = "weekly"):
        """
        Produce labels, average mood scores, and habit completion rates for Chart.js.

        Description:
            Returns three parallel lists suitable for Chart.js:
                - labels: list[str] (day labels)
                - moods: list[float] (average mood score for each label)
                - rates: list[float] (habit completion % for each label)

            Supports three `view` modes:
                - "daily": last 7 calendar days, returns 7 points.
                - "monthly": days of current month up to today.
                - "weekly": default - last 7 days aggregated into weekday buckets
                            (Monday...Sunday), wih average mood/average completion per weekday.

        Args:
            user (User): The user to summarize data for.
            view (str, optional): One of "daily", "monthly", or "weekly". Defaults to "weekly".

        Returns:
            tuple[list(str), list(float), list(float)]:
                labels, moods, completion_rates

        Raises:
            django.db.Error: Any ORM query errors may bubble up.
            ValueError: If `view` is invalid (current code defaults to weekly for unknown views).

        Example:
            >>> labels, moods, rates = AnalyticsService.summaries(request.user, "daily")

        Implementation notes:
            - `completion_rate(d0, d1)` computes:
                (count of completed HabitCompletion rows in date range)
                / (number_of_user_habits * number_of_days)
                then multiplies by 100 and rounds to 1 decimal.
            - If user has zero habits, completion_rate returns 0.0.
            - For weekly view, mood averages are computed per weekday using Python mean.
            - If no mood entries exist for a day, mood value is 0 (so chart shows flat zero).
            - Uses `strftime` for human-friendly labels.

        Important edge cases:
            - When there are no habits, rates are 0.0 to avoid division by zero.
            - Aggregation is done in Python and can be inefficient for large datasets.
            - The monthly days calculation handles December specially; it works but is
              slighlty verbose and could be simplified with calendar.monthrange.
        """
        today = timezone.now().date()

        def completion_rate(d0, d1) -> float:
            """
            Compute normalized completion percentage for user between dates d0 and d1.

            Returns:
                float: Percentage (0...100) rounded to 1 decimal place.
            """
            # NOTE: `Habit.objects.filter(user=user).count()` is executed per call.
            # Consider caching habit_count outside the inner function for efficiency.
            habits = Habit.objects.filter(user=user).count()

            if habits == 0:
                return 0.0

            completions = HabitCompletion.objects.filter(
                user=user, date__range=(d0, d1), completed=True
            ).count()
            days = (d1 - d0).days + 1
            # normalize: average per day across all habits
            return round((completions / (habits * days)) * 100.0, 1)

        if view == "daily":
            # Last 7 days, by day
            start = today - timedelta(days=6)
            labels, moods, rates = [], [], []

            for i in range(7):
                day = start + timedelta(days=i)
                labels.append(day.strftime("%b %d"))
                day_moods = list(
                    MoodEntry.objects.filter(
                        user=user, date=day
                    ).values_list("score", flat=True)
                )

                moods.append(mean(day_moods) if day_moods else 0)
                rates.append(completion_rate(day, day))

            return labels, moods, rates

        if view == "monthly":
            # Current month, by day
            # Determine number of days in the month (handles non-December by computing next month's day 1 minus one day)
            days_in_month = (
                (today.replace(month=today.month %
                 12 + 1, day=1) - timedelta(days=1)).day
                if today.month != 12
                else 31
            )
            start = today.replace(day=1)

            labels, moods, rates = [], [], []

            for daynum in range(1, days_in_month + 1):
                day = start.replace(day=daynum)

                if day > today:  # don't include future days
                    break

                labels.append(day.strftime("%d %b"))
                day_moods = list(
                    MoodEntry.objects.filter(
                        user=user, date=day
                    ).values_list("score", flat=True)
                )

                moods.append(mean(day_moods) if day_moods else 0)
                rates.append(completion_rate(day, day))

            return labels, moods, rates

        # weekly (default): last 7 days bucketed by weekday
        start = today - timedelta(days=6)
        entries = MoodEntry.objects.filter(
            user=user, date__gte=start, date__lte=today
        )
        mood_map = defaultdict(list)

        for entry in entries:
            mood_map[entry.date.strftime("%A")].append(entry.score)

        week_days = [
            "Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"
        ]
        labels = week_days
        moods = [
            round(mean(mood_map[day]), 2) if mood_map[day] else 0 for day in week_days
        ]

        # completion rate per weekday (averaged across observed days)
        rate_map = defaultdict(list)

        for i in range(7):
            day = start + timedelta(days=i)
            rate_map[day.strftime("%A")].append(completion_rate(day, day))

        rates = [
            round(mean(rate_map[day]), 1) if rate_map[day] else 0 for day in week_days
        ]

        return labels, moods, rates


class AISuggestionService:
    """
    AI-powered suggestion service using VADER (NLTK SentimentIntensityAnalyzer).

    Responsibilities:
        - Lazily instantiate the sentiment analyzer.
        - Compute sentiment compounds for text reflections.
        - Produce human-readable suggestions based on recent mood history
          and today's reflection sentiment.

    Notes:
        - Uses NLTK VADER which outputs a `compound` score in [-1, 1].
        - The analyzer is cached as a class-level singleton (`_analyzer`) to avoid repeated
          heavy initialization.
    """
    _analyzer = None

    @classmethod
    def _get_analyzer(cls):
        """
        Lazily initialize and return a SentimentIntensityAnalyzer instance.

        Returns:
            SentimentIntensityAnalyzer: Ready-to-use analyzer.

        Raises:
            LookupError: If NLTK `vader_lexicon` isn't present; the implementation
                         attempts to download it, but in locked environments that
                         will raise. See notes.

        Example:
            >>> analyzer = AISuggestionService._get_analyzer()

        Important notes:
            - On the first call, if the `vader_lexicon` resource is missing, the
              code attempts `nltk.download("vader_lexicon")`, which requires network
              access and can block (or fail) in production. Pre-download the lexicon
              during deployment or in an init task.
            - The class field `_analyzer` acts as a simple in-process cache. If you
              run multiple worker processes (e.g., gunicorn + Celery), each process
              will have its own analyzer instance.
        """
        if cls._analyzer is None:
            try:
                cls._analyzer = SentimentIntensityAnalyzer()
            except LookupError:
                import nltk
                nltk.download("vader_lexicon")
                cls._analyzer = SentimentIntensityAnalyzer()

        return cls._analyzer

    @classmethod
    def analyze_reflection(cls, text: str) -> float:
        """
        Compute sentiment compound score for the provided text.

        Args:
            text (str): The reflection text to analyze.

        Returns:
            float: `compound` sentiment score in [-1.0, 1.0]. Returns 0.0 for empty or falsy text.

        Raises:
            LookupError: If the analyzer cannot be instantiated and download fails.
            Exception: Underlying SentimentIntensityAnalyzer errors may propagate.

        Example:
            >>> score = AISuggestionService.analyze_reflection("I feel great today!")
            >>> print(score) # e.g., 0.8

        Notes:
            - Compound score interpretation: > 0.05 positive, < -0.05 negative (per VADER docs).
            - This function returns 0.0 for empty strings to avoid misleading signals.
        """
        if not text:
            return 0.0

        analyzer = cls._get_analyzer()
        scores = analyzer.polarity_scores(text or "")
        # compund in [-1, 1]
        return scores.get("compound", 0.0)

    @classmethod
    def suggest(cls, user):
        """
        Produce 1-2 actionable suggestions based on recent mood history and today's reflection.

        Description:
            - Fetch up to the last 7 MoodEntry rows (most recent first, up to today).
            - Compute today's reflection sentiment (if any).
            - Compute average mood over the recent slice.
            - Detect the weakest weekday (very simple heuristic).
            - Compose 1-2 short, human-readable suggestions.

        Args:
            user (User): User instance for which to generate suggestions.

        Returns:
            str: Concatenated suggestion(s). If no recent mood entries exist returns a prompt to log mood.

        Raises:
            django.db.Error: ORM errors may bubble up.
            StatisticsError: `mean()` on empty list is protected by guarding logic, so should not occur.

        Example:
            >>> tip = AISuggestionService.suggest(request.user)

        Implementation details and edge cases:
            - If `recent` is empty, returns a generic instruction to log mood.
            - If a reflection exists for today's entry, `analyze_reflection()` is used
              to determine tone and produce stress-focused tips.
            - `low_day` uses weekday averages - if user entries are sparse this heuristic
              can be noisy.
            - Suggestions are heuristics - intended to be friendly nudges, not clinical advice.
        """
        today = timezone.now().date()
        recent = list(
            MoodEntry.objects.filter(
                user=user, date__lte=today
            ).order_by("-date")[:7]
        )

        if not recent:
            return "Log a mood today to unlock personalized tips."

        # sentiment on today's reflection if exists
        today_ref = next(
            (
                entry.reflection for entry in recent
                if entry.date == today and entry.reflection
            ), ""
        )

        mood_sent = cls.analyze_reflection(today_ref)

        # average mood over the recent entries
        avg_mood = mean([entry.score for entry in recent]) if recent else 0

        # simple weekday pattern detection: group recent scores by weekday
        by_weekday = defaultdict(list)
        for entry in recent:
            by_weekday[entry.date.strftime("%A")].append(entry.score)

        low_day = None
        if by_weekday:
            # find weekday with the lowest average score
            low_day = min(by_weekday, key=lambda day: mean(by_weekday[day]))

        suggestion = []

        if low_day:
            suggestion.append(
                f"Your motivation dips on {low_day}s. Consider a low-effort habit that day (e.g., 5-minute walk)."
            )

        if mood_sent < -0.2:
            suggestion.append(
                "Your reflection sounds stressed. Try box breathing for 2 minutes."
            )

        elif avg_mood <= 2:
            suggestion.append(
                "Mood's been low. Queue a tiny win: drink water and 10 deep breaths."
            )

        elif avg_mood >= 4:
            suggestion.append(
                "Riding high! Level up a habit today (add one more rep/minute)."
            )

        if not suggestion:
            suggestion.append(
                "Keep the streak alive. Aim for one simple habit before noon."
            )

        return " ".join(suggestion)
