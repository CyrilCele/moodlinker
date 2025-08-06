from datetime import date

from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required
from django.db import IntegrityError
from django.http import HttpResponseRedirect
from django.shortcuts import render
from django.urls import reverse

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
    if request.method == "POST":
        form = UserProfileForm(request.POST, request.FILES, instance=profile)
        if form.is_valid():
            form.save()
            return HttpResponseRedirect(reverse("home"))
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

    return render(request, "dashboard.html", {
        "mood_form": mood_form,
        "habits": habits,
        "completions": completions,
        "done": done,
        "total": total,
        "mood_logged": mood_logged
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
