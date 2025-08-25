from django.contrib import messages
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required
from django.db import IntegrityError, transaction
from django.http import HttpResponseRedirect, JsonResponse, HttpResponse, Http404
from django.shortcuts import render, get_object_or_404, redirect
from django.urls import reverse
from django.utils import timezone

from tracker.forms import UserProfileForm, MoodEntryForm, HabitForm, NotificationPreferencesForm
from tracker.models import User, MoodEntry, Habit, HabitCompletion, Notification
from tracker.services import AnalyticsService, AISuggestionService
from tracker.tasks import send_mood_reminder
from tracker.utils.ics import generate_ics


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
    today = timezone.now().date()

    # Demo mood reminder
    if hasattr(user, "latest_mood") and user.latest_mood < 3:
        send_mood_reminder.delay(user.email, user.latest_mood)

    # Ensure completions exist for today
    habits = Habit.objects.filter(user=user)
    for habit in habits:
        HabitCompletion.objects.get_or_create(
            user=user, habit=habit, date=today
        )

    # One mood per day
    mood_entry = MoodEntry.objects.filter(user=user, date=today).first()
    mood_logged = mood_entry is not None

    if request.method == "POST" and not mood_logged:
        form = MoodEntryForm(request.POST)
        if form.is_valid():
            with transaction.atomic():
                mood = form.save(commit=False)
                mood.user = user
                mood.date = today
                mood.save()

                # update today's habit completions
                completions = HabitCompletion.objects.filter(
                    user=user, date=today)
                for complete in completions:
                    complete.completed = request.POST.get(
                        f"habit_{complete.habit.id}") == "on"
                    complete.save()

            return HttpResponseRedirect(reverse("dashboard"))
    else:
        form = MoodEntryForm()

    completions = HabitCompletion.objects.filter(
        user=user, date=today).select_related("habit")
    done = completions.filter(completed=True).count()
    total = completions.count()

    # AI Suggestion
    ai_suggestion = AISuggestionService.suggest(user)

    return render(request, "dashboard.html", {
        "mood_form": form,
        "habits": habits,
        "completions": completions,
        "done": done,
        "total": total,
        "mood_logged": mood_logged,
        "ai_suggestion": ai_suggestion,
    })


@login_required
def chart_data_api(request):
    """
    Return JSON payload for Chart.js; no mock data.
    """
    user = request.user
    view = request.GET.get("view", "weekly")
    labels, moods, rates = AnalyticsService.summaries(user, view)
    payload = {
        "labels": labels,
        "datasets": [
            {
                "label": f"Mood ({view.title()})",
                "data": moods,
                "yAxisID": "y",
            },
            {
                "label": f"Habit Completion % ({view.title()})",
                "data": rates,
                "yAxisID": "y1",
            }
        ]
    }
    return JsonResponse(payload)


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

    if request.method == "POST":
        habit = HabitCompletion.objects.get(id=habit_id)
        habit.delete()
        messages.success(
            request, f"Habit '{habit.habit}' deleted successfully.")
        return HttpResponseRedirect(reverse("dashboard"))
    return render(request, "confirm_delete.html", {"habit": habit})


@login_required
def analytics(request):
    return render(request, "analytics.html", {})


@login_required
def about(request):
    return render(request, "about.html", {})


@login_required
def preferences(request):
    profile = request.user.profile
    if request.method == "POST":
        form = NotificationPreferencesForm(request.POST, isinstance=profile)
        if form.is_valid():
            form.save()
            messages.success(request, "Preferences saved.")
            from tracker.tasks import schedule_user_habit_reminders
            schedule_user_habit_reminders.delay(request.user.id)
            return redirect("preferences")
    else:
        form = NotificationPreferencesForm()
    return render(request, "preferences.html", {"form": form})


@login_required
def notifications(request):
    items = Notification.objects.filter(
        user=request.user).order_by("-created_at")[:50]
    return render(request, "notifications.html", {"items": items})


@login_required
def mark_notification_read(request, pk):
    note = get_object_or_404(Notification, pk=pk, user=request.user)
    note.read = True
    note.save(update_fields=["read"])
    return redirect("notifications")


@login_required
def calendar_feed(request, token):
    try:
        user = User.objects.get(calendar_token=token)
    except User.DoesNotExist:
        raise Http404("Invalid calendar token.")

    habits = Habit.objects.filter(user=user)
    ics_data = generate_ics(user, habits)

    response = HttpResponse(ics_data, content_type="text/calendar")
    response["Content-Disposition"] = "attachment; filename='habits.ics'"
    return response
