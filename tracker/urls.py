from django.urls import path
from tracker.views import HabitListView, HabitDetailView, HabitCompletionView, MoodListCreateViews, AnalyticsView

urlpatterns = [
    path("habits/", HabitListView.as_view(), name="habit-list"),
    path("habits/<int:pk>/", HabitDetailView.as_view(), name="habit-detail"),
    path("completions/", HabitCompletionView.as_view(), name="habit-completion"),
    path("moods/", MoodListCreateViews.as_view(), name="mood-list"),
    path("analytics/", AnalyticsView.as_view(), name="analytics"),
]
