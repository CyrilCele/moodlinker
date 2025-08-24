from collections import defaultdict
from datetime import date, timedelta
from statistics import mean

from django.db.models import Q
from django.utils import timezone

from nltk.sentiment import SentimentIntensityAnalyzer

from tracker.models import Habit, MoodEntry, HabitCompletion


class AnalyticsService:
    @staticmethod
    def longest_streak(user, habit: Habit) -> int:
        """
        Compute the current streak of consecutive days the habit has been completed.
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
        Return labels + aggregated mood & completetion rate for Chart.js
        """
        today = timezone.now().date()

        def completion_rate(d0, d1) -> float:
            # completed count / total habits for the given day range
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
                        user=user, date=day).values_list("score", flat=True)
                )
                moods.append(mean(day_moods) if day_moods else 0)
                rates.append(completion_rate(day, day))
            return labels, moods, rates

        if view == "monthly":
            # Current month, by day
            start = today.replace(day=1)
            days_in_month = (today.replace(month=today.month % 12 + 1, day=1) - timedelta(days=1)).day \
                if today.month != 12 else 31
            labels, moods, rates = [], [], []
            for daynum in range(1, days_in_month + 1):
                day = start.replace(day=daynum)
                if day > today:  # future days
                    break
                labels.append(day.strftime("%d %b"))
                day_moods = list(
                    MoodEntry.objects.filter(
                        user=user, date=day).values_list("score", flat=True)
                )
                moods.append(mean(day_moods) if day_moods else 0)
                rates.append(completion_rate(day, day))
            return labels, moods, rates

        # weekly (default): last 7 days, bucketed by weekday
        start = today - timedelta(days=6)
        entries = MoodEntry.objects.filter(
            user=user, date__gte=start, date__lte=today)
        mood_map = defaultdict(list)
        for entry in entries:
            mood_map[entry.date.strftime("%A")].append(entry.score)

        week_days = ["Monday", "Tuesday", "Wednesday",
                     "Thursday", "Friday", "Saturday", "Sunday"]
        labels = week_days
        moods = [round(mean(mood_map[day]), 2) if mood_map[day]
                 else 0 for day in week_days]

        # completion rate per weekday (averaged across observed days)
        rate_map = defaultdict(list)
        for i in range(7):
            day = start + timedelta(days=i)
            rate_map[day.strftime("%A")].append(completion_rate(day, day))
        rates = [round(mean(rate_map[day]), 1) if rate_map[day]
                 else 0 for day in week_days]

        return labels, moods, rates


class AISuggestionService:
    """
    Uses VADER to analyze reflection sentiment and gives a recommendation.
    """
    _analyzer = None

    @classmethod
    def _get_analyzer(cls):
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
        if not text:
            return 0.0
        analyzer = cls._get_analyzer()
        scores = analyzer.polarity_scores(text or "")
        # compund in [-1, 1]
        return scores.get("compound", 0.0)

    @classmethod
    def suggest(cls, user):
        """
        Look at last few days of mood + today's reflection sentiment,
        then offer 1-2 actionable suggestions.
        """
        today = timezone.now().date()
        recent = list(MoodEntry.objects.filter(
            user=user, date__lte=today).order_by("-date")[:7])
        if not recent:
            return "Log a mood today to unlock personalized tips."

        # sentiment on today's reflection if exists
        today_ref = next(
            (entry.reflection for entry in recent if entry.date == today and entry.reflection), "")
        mood_sent = cls.analyze_reflection(today_ref)

        # average mood
        avg_mood = mean([entry.score for entry in recent]) if recent else 0

        # find a weak weekday pattern (very simple heuristic)
        by_weekday = defaultdict(list)
        for entry in recent:
            by_weekday[entry.date.strftime("%A")].append(entry.score)
        low_day = min(by_weekday, key=lambda day: mean(
            by_weekday[day])) if by_weekday else None

        suggestion = []
        if low_day:
            suggestion.append(
                f"Your motivation dips on {low_day}s. Consider a low-effort habit that day (e.g., 5-minute walk)."
            )

        if mood_sent < -0.2:
            suggestion.append(
                "Your reflection sounds stressed. Try box breathing for 2 minutes.")
        elif avg_mood <= 2:
            suggestion.append(
                "Mood's been low. Queue a tiny win: drink water and 10 deep breaths.")
        elif avg_mood >= 4:
            suggestion.append(
                "Riding high! Level up a habit today (add one more rep/minute).")

        if not suggestion:
            suggestion.append(
                "Keep the streak alive. Aim for one simple habit before noon.")

        return " ".join(suggestion)
