from django.shortcuts import get_object_or_404
from django.utils import timezone

from rest_framework import viewsets, permissions, status
from rest_framework.decorators import action
from rest_framework.response import Response

from tracker.models import Habit, MoodEntry, HabitCompletion
from tracker.api.serializers import HabitSerializer, MoodEntrySerializer, HabitCompletionSerializer


class HabitViewSet(viewsets.ModelViewSet):
    serializer_class = HabitSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        return Habit.objects.filter(user=self.request.user).order_by("-created_at")

    def perform_destroy(self, instance):
        instance.delete()

    # extra endpoint to quickly get completions for habit
    @action(detail=True, methods=["get"])
    def completions(self, request, pk=None):
        habit = get_object_or_404(Habit, pk=pk, user=request.user)
        qs = HabitCompletion.objects.filter(
            user=request.user, habit=habit).order_by("-date")
        serializer = HabitCompletionSerializer(qs, many=True)
        return Response(serializer.data)


class MoodEntryViewSet(viewsets.ModelViewSet):
    serializer_class = MoodEntrySerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        return MoodEntry.objects.filter(user=self.request.user).order_by("-date")
