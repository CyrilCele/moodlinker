from rest_framework.routers import DefaultRouter
from tracker.api.views import HabitViewSet, MoodEntryViewSet

router = DefaultRouter()
router.register(r"habits", HabitViewSet, basename="habits")
router.register(r"moods", MoodEntryViewSet, basename="moods")

urlpatterns = router.urls