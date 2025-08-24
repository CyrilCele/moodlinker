import json
from collections import defaultdict
from datetime import date, timedelta

from django.contrib import messages
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required
from django.db import IntegrityError
from django.http import HttpResponseRedirect
from django.shortcuts import render, get_object_or_404
from django.urls import reverse
from django.utils import timezone

from .forms import UserProfileForm, MoodEntryForm, HabitForm
from .models import User, MoodEntry, Habit, HabitCompletion


def index(request):
    return render(request, "index.html", {})


def login_view(request):
    if request.method == "POST":

        # Attempt to sign user in
        username = request.POST.get("username")
        password = request.POST.get("password")
        user = authenticate(request, username=username, password=password)

        # Check if authentication successful
        if user is not None:
            login(request, user)
            return HttpResponseRedirect(reverse("home"))
        else:
            return render(request, "login.html", {"message": "Invalid username and/or password!"})
    else:
        return render(request, "login.html")


def logout_view(request):
    logout(request)
    return HttpResponseRedirect(reverse("home"))


def register(request):
    if request.method == "POST":
        username = request.POST.get("username")
        email = request.POST.get("email")
        password = request.POST.get("password")
        confirmation = request.POST.get("confirmation")

        # Check for empty required fields
        if not (username and email and password):
            return render(request, "register.html", {"message": "All fields are required."})

        # Ensure password matches confirmation
        if password != confirmation:
            return render(request, "register.html", {"message": "Password must match!"})

        # Attempt to create new user
        try:
            user = User.objects.create_user(username, email, password)
            user.save()
        except IntegrityError:
            return render(request, "register.html", {"message": "Username exists!"})
        login(request, user)
        return HttpResponseRedirect(reverse("home"))
    else:
        return render(request, "register.html")


@login_required
def user_profile(request):
    profile = request.user.profile
    form = UserProfileForm(request.POST, request.FILES or None,
                           instance=profile, user=request.user)

    if request.method == "POST":
        if form.is_valid():
            form.save()
            return HttpResponseRedirect(reverse("profile"))
    else:
        form = UserProfileForm()
    return render(request, "profile.html", {"form": form, "profile": profile})


@login_required
def dashboard(request):
    user = request.user
    today = date.today()

    # Check or create today's mood entry
    mood_entry = MoodEntry.objects.filter(user=user, date=today).first()
    mood_logged = mood_entry is not None

    # Ensure all habits have completions today
    habits = Habit.objects.filter(user=user)
    for habit in habits:
        HabitCompletion.objects.get_or_create(
            user=user, habit=habit, date=today)
    completions = HabitCompletion.objects.filter(user=user, date=today)

    if request.method == "POST" and not mood_logged:
        mood_form = MoodEntryForm(request.POST)
        if mood_form.is_valid():
            mood = mood_form.save(commit=False)
            mood.user = user
            mood.date = today
            # mood_form.instance.user = user
            mood_form.save()

        # Habit checkboxes
        for completion in completions:
            checkbox = request.POST.get(f"habit_{completion.habit.id}")
            # completion.completed = True if checkbox == "on" else False
            completion.completed = checkbox == "on"
            completion.save()
        return HttpResponseRedirect(reverse("dashboard"))

    # Fresh form after POST or GET
    mood_form = MoodEntryForm()

    # Stats
    total = completions.count()
    done = completions.filter(completed=True).count()
    # view_mode = request.GET.get("view", "weekly")
    # chart_data = get_chart_data(user, view_mode)

    return render(request, "dashboard.html", {
        "mood_form": mood_form,
        "habits": habits,
        "completions": completions,
        "done": done,
        "total": total,
        "mood_logged": mood_logged,
        # "chart_data": chart_data,
        # "view_mode": view_mode
    })


@login_required
def create_habit(request):
    if request.method == "POST":
        form = HabitForm(request.POST)
        if form.is_valid():
            habit = form.save(commit=False)
            habit.user = request.user
            if Habit.user_habits_limit(request.user):
                habit.save()
                return HttpResponseRedirect(reverse("dashboard"))
            else:
                form.add_error(None, "Limit of 5 habits reached.")
    else:
        form = HabitForm()
    return render(request, "create_habit.html", {"form": form})


@login_required
def user_habit(request, habit_id):
    habit = Habit.objects.get(id=habit_id)
    return render(request, "habits.html", {"habit": habit})


@login_required
def delete_habit(request, habit_id):
    habit = HabitCompletion.objects.get(id=habit_id)

    if request.method == "POST":
        habit.delete()
        messages.success(
            request, f"Habit '{habit.habit}' deleted successfully.")
        return HttpResponseRedirect(reverse("dashboard"))
    return render(request, "confirm_delete.html", {"habit": habit})


# @login_required
# def get_chart_data(user, view_mode="weekly"):
#     today = timezone.now().date()
#     mood_entries = MoodEntry.objects.filter(user=user)

#     if view_mode == "daily":
#         entries = mood_entries.order_by("-date")[:7]
#         entries = list(reversed(entries))
#         labels = [entry.date.strftime("%b %d") for entry in entries]
#         scores = [entry.score for entry in entries]

#     elif view_mode == "monthly":
#         start = today.replace(day=1)
#         entries = mood_entries.filter(date__gte=start)
#         data = defaultdict(list)

#         for entry in entries:
#             key = entry.date.strftime("%d %b")
#             data[key].append(entry.score)
#         labels = list(data.keys())
#         scores = [round(sum(value) / len(value), 2) for value in data.values()]

#     else:  # weekly (default)
#         start = today - timedelta(days=6)
#         entries = mood_entries.filter(date__gte=start)
#         data = defaultdict(list)

#         for entry in entries:
#             key = entry.date.strftime("%A")
#             data[key].append(entry.score)

#         week_days = ["Monday", "Tuesday", "Wednesday",
#                      "Thursday", "Friday", "Saturday", "Sunday"]
#         labels = week_days
#         scores = [round(sum(data[day]) / len(data[day]), 2)
#                   if data[day] else 0 for day in week_days]

#     # chart_data = {
#     #     "labels": labels,
#     #     "datasets": [{
#     #         "label": f"Mood ({view_mode.title()})",
#     #         "data": scores,
#     #         "borderColor": "#0dcaf0",
#     #         "backgroundColor": "rgba(13, 202, 240, 0.2)",
#     #         "fill": True,
#     #         "tension": 0.4
#     #     }]
#     # }
#     # return chart_data
#     return {
#         "labels": labels,
#         "values": scores,
#     }
