from django.contrib.auth.models import User

from rest_framework import generics, permissions
from rest_framework.response import Response
from rest_framework_simplejwt.views import TokenObtainPairView

from tracker.models import Habit, HabitCompletion, MoodEntry
from tracker.serializers import HabitSerializer, HabitCompletionSerializer, MoodEntrySerializer, UserSerializer

from django.shortcuts import render
from django.contrib.auth.decorators import login_required


def register_page(request):
    return render(request, "register.html")


def login_page(request):
    return render(request, "login.html")


@login_required
def dashboard_page(request):
    from datetime import date
    from .models import Habit, MoodEntry
    today = date.today()
    habits = Habit.objects.filter(user=request.user)
    mood = MoodEntry.objects.filter(user=request.user, date=today).first()
    return render(request, "dashboard.html", {
        "habits": habits,
        "mood": mood
    })


@login_required
def habit_entry_page(request):
    return render(request, "habit_entry.html")


@login_required
def mood_entry_page(request):
    return render(request, "mood_entry.html")


@login_required
def analytics_page(request):
    return render(request, "analytics.html")


@login_required
def profile_page(request):
    return render(request, "profile.html")


# Registration view
class RegisterView(generics.CreateAPIView):
    serializer_class = UserSerializer
    permission_classes = [permissions.AllowAny]

    def post(self, request, *args, **kwargs):
        # Create a new user
        username = request.data.get("username")
        password = request.data.get("password")
        if username and password:
            user = User.objects.create_user(
                username=username, password=password)
            return Response({"status": "user created"})
        return Response({
            "error": "Username and password required"
        }, status=400)


# Habit views
class HabitListView(generics.ListCreateAPIView):
    serializer_class = HabitSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        return Habit.objects.filter(user=self.request.user)


class HabitDetailView(generics.RetrieveUpdateDestroyAPIView):
    serializer_class = HabitSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        return Habit.objects.filter(user=self.request.user)


# HabitCompletion view
class HabitCompletionView(generics.CreateAPIView):
    serializer_class = HabitCompletionSerializer
    permission_classes = [permissions.IsAuthenticated]


# Mood entry views
class MoodListCreateViews(generics.ListCreateAPIView):
    serializer_class = MoodEntrySerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        return MoodEntry.objects.filter(user=self.request.user).order_by("-date")


# Analytics view: return aggregated data for charts
class AnalyticsView(generics.GenericAPIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        user = request.user
        # Return last 7 days of (date, mood score, habits done)
        from django.utils import timezone
        import datetime
        today = timezone.now().date()
        week_ago = today - datetime.timedelta(days=6)
        data = []
        for i in range(7):
            day = week_ago + datetime.timedelta(days=1)
            mood = MoodEntry.objects.filter(user=user, date=day).first()
            # Count habits completed on that day
            completed = HabitCompletion.objects.filter(
                habit__user=user, date=day, completed=True).count()
            data.append({
                "date": str(day),
                "mood": mood.score if mood else None,
                "habits_done": completed
            })
        return Response(data)
