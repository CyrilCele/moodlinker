from django.urls import path
from tracker.views import (HabitListView, HabitDetailView, HabitCompletionView, MoodListCreateViews, AnalyticsView,
                           register_page, login_page, dashboard_page, habit_entry_page,
                           mood_entry_page, analytics_page, profile_page
                           )

urlpatterns = [
    # API endpoints
    path("api/habits/", HabitListView.as_view(), name="habit-list"),
    path("api/habits/<int:pk>/", HabitDetailView.as_view(), name="habit-detail"),
    path("api/completions/", HabitCompletionView.as_view(), name="habit-completion"),
    path("api/mood/", MoodListCreateViews.as_view(), name="mood-list"),
    path("api/analytics/", AnalyticsView.as_view(), name="analytics"),

    # Template-rendered views
    path('register/', register_page, name='register-page'),
    path('login/', login_page, name='login-page'),
    path('dashboard/', dashboard_page, name='dashboard-page'),
    path('habits/', habit_entry_page, name='habit-entry-page'),
    path('mood/', mood_entry_page, name='mood-entry-page'),
    path('analytics/', analytics_page, name='analytics-page'),
    path('profile/', profile_page, name='profile-page'),
]
