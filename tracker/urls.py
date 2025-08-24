from django.urls import path
from . import views

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

    # JSON for Chart.js (no mock data)
    path("api/chart-data/", views.chart_data_api, name="chart_data_api"),
]
