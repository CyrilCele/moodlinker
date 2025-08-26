from django.urls import path, include
from tracker import views

urlpatterns = [
    path("", views.index, name="home"),
    path("login/", views.login_view, name="login"),
    path("logout/", views.logout_view, name="logout"),
    path("register/", views.register, name="register"),
    path("profile/", views.user_profile, name="profile"),
    path("dashboard/", views.dashboard, name="dashboard"),
    path("create-habit/", views.create_habit, name="create_habit"),
    path("habit/<int:habit_id>/", views.user_habit, name="user_habit"),
    path("habit/<int:habit_id>/delete/",
         views.delete_habit, name="delete_habit"),
    path("analytics/", views.analytics, name="analytics"),
    path("about/", views.about, name="about"),
    path("preferences/", views.preferences, name="preferences"),
    path("notifications/", views.notifications, name="notifications"),
    path("notifications/<int:pk>/read/",
         views.mark_notification_read, name="mark_notification_read"),
    path("calendar/<str:token>.ics/", views.calendar_feed, name="calendar_feed"),
    path("api/chart-data/", views.chart_data_api, name="chart_data_api"),
    path("api/", include("tracker.api.urls")),
]
