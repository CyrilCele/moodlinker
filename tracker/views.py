from django.http import (
    HttpResponseRedirect, JsonResponse, HttpResponse, Http404
)
from django.shortcuts import render, redirect, get_object_or_404
from django.urls import reverse
from django.contrib.auth import authenticate, login, logout
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db import IntegrityError, transaction
from django.utils import timezone

# Project-specific modules
from .models import User, Habit, HabitCompletion, MoodEntry, Notification
from .forms import (
    UserProfileForm, MoodEntryForm, HabitForm, NotificationPreferencesForm
)
from .services import AnalyticsService, AISuggestionService
from .tasks import send_mood_reminder
from .utils.ics import generate_ics


def index(request):
    """
    Render the home (index) page.

    Args:
        request (HttpRequest): Incoming HTTP request object.

    Returns:
        HttpResponse: Rendered `index.html` page.

    Example:
        >>> response = index(request)
        >>> response.status_code
        200
    """
    return render(request, "index.html", {})


def login_view(request):
    """
    Handle user login via username and password.

    Supports GET (render login form) and POST (authenticate user).

    Args:
        request (HttpRequest): Incoming request. Should include `username` and
            `password` in `POST` when logging in.

    Returns:
        HttpResponse:
            - GET: Render `login.html` with an empty form.
            - POST: Redirect to 'home' if successful,
              otherwise re-render with error message.

    Raises:
        None directly, but authentication failures are handled gracefully.

    Example:
        POST payload:
            {
                "username": "cyril",
                "password": "secret"
            }
    """
    if request.method == "POST":
        username = request.POST.get("username")
        password = request.POST.get("password")
        user = authenticate(request, username=username, password=password)

        if user is not None:
            login(request, user)
            return HttpResponseRedirect(reverse("home"))
        return render(request, "login.html", {
            "message": "Invalid username and/or password!"
        })
    return render(request, "login.html")


def logout_view(request):
    """
    Log out the currently authenticated user.

    Args:
        request (HttpRequest): Incoming request.

    Returns:
        HttpResponseRedirect: Redirect to 'home' after logout.

    Example:
        >>> response = logout_view(request)
        >>> response.status_code
        302
    """
    logout(request)
    return HttpResponseRedirect(reverse("home"))


def register(request):
    """
    Handle new user registration.

    Args:
        request (HttpRequest): Incoming request. POST should include:
            - username (str)
            - email (str)
            - password (str)
            - confirmation (str)

    Returns:
        HttpResponse:
            - GET: Render `register.html`.
            - POST:
                * Redirect to 'home' if registration succeeds.
                * Render with error message otherwise.

    Raises:
        IntegrityError: If username already exists.

    Example:
        POST payload:
            {
                "username": "cyril",
                "email": "cyril@example.com",
                "password": "secret",
                "confirmation": "secret"
            }
    """
    if request.method == "POST":
        username = request.POST.get("username")
        email = request.POST.get("email")
        password = request.POST.get("password")
        confirmation = request.POST.get("confirmation")

        if not (username and email and password):
            return render(request, "register.html", {
                "message": "All fields are required."
            })

        if password != confirmation:
            return render(request, "register.html", {
                "message": "Password must match!"
            })

        try:
            user = User.objects.create_user(username, email, password)
            user.save()
        except IntegrityError:
            return render(request, "register.html", {
                "message": "Username exists!"
            })

        login(request, user)
        return HttpResponseRedirect(reverse("home"))
    return render(request, "register.html")


@login_required
def user_profile(request):
    """
    Display and update user profile.

    Args:
        request (HttpRequest): Incoming request.

    Returns:
        HttpResponse: Rendered `profile.html` with user profile form.

    Example:
        GET -> profile form populated
        POST -> saves changes if valid, redirects to 'profile'
    """
    profile = request.user.profile
    form = UserProfileForm(
        request.POST, request.FILES or None, instance=profile, user=request.user
    )

    if request.method == "POST":
        if form.is_valid():
            form.save()
            return HttpResponseRedirect(reverse("profile"))
    else:
        form = UserProfileForm()

    return render(request, "profile.html", {"form": form, "profile": profile})


@login_required
def dashboard(request):
    """
    User dashboard showing habits, mood, completions, and AI suggestions.

    Args:
        request (HttpRequest): Incoming request.

    Returns:
        HttpResponse: Rendered `dashboard.html` with:
            - mmod form
            - habits
            - completions (done vs total)
            - AI suggestion
            - flag if mood already logged
    """
    user = request.user
    today = timezone.now().date()

    if hasattr(user, "latest_mood") and user.latest_mood < 3:
        send_mood_reminder.delay(user.email, user.latest_mood)

    habits = Habit.objects.filter(user=user)
    for habit in habits:
        HabitCompletion.objects.get_or_create(
            user=user, habit=habit, date=today
        )

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

                completions = HabitCompletion.objects.filter(
                    user=user, date=today
                )
                for complete in completions:
                    complete.completed = (
                        request.POST.get(f"habit_{complete.habit.id}") == "on"
                    )
                    complete.save()
            return HttpResponseRedirect(reverse("dashboard"))
    else:
        form = MoodEntryForm()

    completions = HabitCompletion.objects\
        .filter(user=user, date=today)\
        .select_related("habit")
    done = completions.filter(completed=True).count()
    total = completions.count()
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
    Provide analytics data for Chart.js visualizations.

    Args:
        request (HttpRequest): Incoming request. Optional GET param `view`
            (str): one of {"weekly", "monthly"}.

    Returns:
        JsonResponse: Payload with mood data and habit completion rates.

    Example:
        GET /chart-data-api?view=weekly
        Response:
            {
                "labels": [...],
                "datasets": [
                    {
                        {"label": "Mood (weekly)", "data": [...], "yAxisID": "y"},
                        {"label": "Habit Completion % (Weekly)", "data": [...], "yAxisID": "y1"}
                    }
                ]
            }
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
    """
    Create a new habit for the user (up to 5).

    Args:
        request (HttpRequest): Incoming request.

    Returns:
        HttpResponse: Render `create_habit.html` with form or redirect to dashboard.

    Raises:
        ValidationError: If habit limit exceeded.
    """
    if request.method == "POST":
        form = HabitForm(request.POST)
        if form.is_valid():
            habit = form.save(commit=False)
            habit.user = request.user
            if Habit.user_habits_limit(request.user):
                habit.save()
                return HttpResponseRedirect(reverse("dashboard"))
            form.add_error(None, "Limit of 5 habits reached.")
    else:
        form = HabitForm()
    return render(request, "create_habit.html", {"form": form})


@login_required
def user_habit(request, habit_id):
    """
    View a specific habit by ID.

    Args:
        request (HttpRequest): Incoming request.
        habit_id (int): ID of the habit.

    Returns:
        HttpResponse: Rendered `habits.html` with habit details.

    Raises:
        Habit.DoesNotExist: If habit not found.
    """
    habit = Habit.objects.get(id=habit_id)
    return render(request, "habits.html", {"habit": habit})


@login_required
def delete_habit(request, habit_id):
    """
    Delete a habit completion record (NOT the habit itself).

    Args:
        request (HttpRequest): Incoming request.
        habit_id (int): ID of HabitCompletion object.

    Returns:
        HttpResponse: Redirect to dashboard if successful, or confirmation page.
    """

    if request.method == "POST":
        habit = HabitCompletion.objects.get(id=habit_id)
        habit.delete()
        messages.success(
            request, f"Habit '{habit.habit}' deleted successfully."
        )
        return HttpResponseRedirect(reverse("dashboard"))

    return render(request, "confirm_delete.html", {"habit": habit})


@login_required
def analytics(request):
    """Render analytics page."""
    return render(request, "analytics.html", {})


@login_required
def about(request):
    """Render about page."""
    return render(request, "about.html", {})


@login_required
def preferences(request):
    """
    Manage user notification preferences.

    Args:
        request (HttpRequest): Incoming request.

    Returns:
        HttpResponse: Render preferences form or redirect after save.
    """
    profile = request.user.profile
    if request.method == "POST":
        form = NotificationPreferencesForm(request.POST, instance=profile)
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
    """
    List latest notifications for the user.

    Args:
        request (HttpRequest): Incoming request.

    Returns:
        HttpResponse: Rendered `notifications.html` with up to 50 items.
    """
    items = Notification.objects\
        .filter(user=request.user)\
        .order_by("-created_at")[:50]
    return render(request, "notifications.html", {"items": items})


@login_required
def mark_notification_read(request, pk):
    """
    Mark a single notification as read

    Args:
        request (HttpRequest): Incoming request.
        pk (int): Primary key of the notification.

    Returns:
        HttpResponseRedirect: Redirect to notifications list.

    Raises:
        Http404: If notification not found or not owned by user.
    """
    note = get_object_or_404(Notification, pk=pk, user=request.user)
    note.read = True
    note.save(update_fields=["read"])
    return redirect("notifications")


@login_required
def calendar_feed(request, token):
    """
    Generate ICS calendar feed for user habits.

    Args:
        request (HttpRequest): Incoming request.
        token (str): User's calendar token for authentication.

    Returns:
        HttpResponse: ICS file download containing habits.

    Raises:
        Http404: If token invalid.
    """
    try:
        user = User.objects.get(calendar_token=token)
    except User.DoesNotExist:
        raise Http404("Invalid calendar token.")

    habits = Habit.objects.filter(user=user)
    ics_data = generate_ics(user, habits)
    response = HttpResponse(ics_data, content_type="text/calendar")
    response["Content-Disposition"] = "attachment; filename='habits.ics'"
    return response
