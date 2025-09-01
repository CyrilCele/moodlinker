from django.shortcuts import get_object_or_404

from rest_framework import viewsets, permissions
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.request import Request
from rest_framework.serializers import Serializer

from tracker.models import Habit, MoodEntry, HabitCompletion
from .serializers import (
    HabitSerializer,
    MoodEntrySerializer,
    HabitCompletionSerializer
)


class HabitViewSet(viewsets.ModelViewSet):
    """
    ViewSet for CRUD operations on a user's Habit objects.

    - Only authenticated users may access these endpoints (permission_classes).
    - get_queryset restricts results to the authenticated user (multi-tenant safety).
    - An extra `completions` action returns the HabitCompletion history for a habit.

    Routes exposed by DRF router (typical):
        - GET    /habits/                    -> list
        - POST   /habits/                    -> create
        - GET    /habits/{pk}/               -> retrieve
        - PUT    /habits/{pk}/               -> update
        - PATCH  /habits/{pk}/               -> partial_update
        - DELETE /habits/{pk}/               -> destroy
        - GET    /habits/{pk}/completions/   -> custom action

    Notes:
        - The serializer is responsible for attaching the request.user on create (or
          you may prefer to override perform_create here for a single source of truth).
        - All queries are scoped to request.user to avoid leaking other users' data.
    """
    serializer_class = HabitSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        """
        Return a QuerySet containing only habits owned by the current authenticated user.

        Args:
            self: HabitViewSet instance. Expects `self.request` to be present and
                  `self.request.user` to be an authenticated user.

        Returns:
            QuerySet[Habit]: Ordered queryset of the user's Habit objects.

        Raises:
            AttributeError: If `self.request` is not available (unexpected in DFR routing).
        """
        # Filter habits to the current user to enforce ownership at DB query time.
        # Order by newest first so list view shows most recent habits topmost.
        return Habit.objects.filter(user=self.request.user).order_by("-created_at")

    def perform_destroy(self, instance: Habit):
        """
        Destroy a habit instance.

        This method is called by the default `destroy` action. We keep the simple
        `instance.delete()` call here so that Django will cascade deletes according
        to model FK `on_delete` rules (e.g., HabitCompletion cascade).

        Args:
            instance (Habit): The Habit instance to delete.

        Returns:
            None

        Notes / Edge Cases:
            - If you want soft-deletes, override this to set as `is_active=False`
              flag instead of hard deleting.
            - Consider wrapping deletion in a transaction if you perform multiple DB writes.
        """
        # Direct deletion; rely on DB cascade for dependent rows (HabitCompletion etc.).
        instance.delete()

    @action(detail=True, methods=["get"])
    def completions(self, request: Request, pk: int = None):
        """
        Custom action: return completion history for a specific habit.

        URL: GET /habits/{pk}/completions

        Args:
            request (Request): DRF request instance.
            pk (int | str | None): Primary key of the Habit to inspect.

        Returns:
            Response: DRF Response containing serialized HabitCompletion objects.

        Raises:
            Http404: If habit with pk does not exist or does not belong to request.user.
        """
        # Use get_object_or_404 with explicit user filter to ensure the habit belongs to the user.
        habit = get_object_or_404(Habit, pk=pk, user=request.user)

        # Query completions for this habit and user, most recent first.
        # select_related can be added if you want to eager-load `habit` or `user` to avoid N+1 later.
        qs = HabitCompletion.objects.filter(
            user=request.user, habit=habit
        ).order_by("-date")

        # Provide serializer context so serializers that depend on request (hyperlinks, permissions)
        # have access to it. Many real-world serializers assume context exists.
        serializer: Serializer = HabitCompletionSerializer(qs, many=True, context={
            "request": request
        })

        # Return serialized list
        return Response(serializer.data)


class MoodEntryViewSet(viewsets.ModelViewSet):
    """
    ViewSet for CRUD operations on a user's MoodEntry objects.

    - Only authenticated users may access these endpoints.
    - Queryset is restricted to the authenticated user.
    - The serializer enforces one mood-per-day on creation.

    Routes:
        - GET    /moods/          -> list
        - POST   /moods/          -> create
        - GET    /moods/{pk}/     -> retrieve
        - PUT    /moods/{pk}/     -> update
        - PATCH  /moods/{pk}/     -> partial_update
        - DELETE /moods/{pk}/     -> destroy
    """
    serializer_class = MoodEntrySerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        """
        Return MoodEntry queryset for the current authenticated user, ordered by date desc.

        Returns:
            QuerySet[MoodEntry]: User's mood entries.

        Notes:
            - If you want to eager-load relations, add select_related/prefetch_related here.
        """
        return MoodEntry.objects.filter(user=self.request.user).order_by("-date")
