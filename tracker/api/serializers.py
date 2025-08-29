from django.utils import timezone
from rest_framework import serializers
from tracker.models import Habit, MoodEntry, HabitCompletion


class HabitSerializer(serializers.ModelSerializer):
    class Meta:
        model = Habit
        fields = ["id", "habit", "description", "periodicity", "created_at"]
        read_only_fields = ["id", "created_at"]

    def validate(self, data):
        """
        Enforce at most 5 habits per user on create.
        For update, we allow changes to fields; uniqueness of (user, habit) enforced by DB.
        """
        user = self.context["request"].user
        if self.instance is None:
            # Create path: check count
            current_count = Habit.objects.filter(user=user).count()
            if current_count >= 5:
                raise serializers.ValidationError(
                    "Limit of 5 habits reached for this user.")
        return data

    def create(self, validated_data):
        validated_data["user"] = self.context["request"].user
        return super().create(validated_data)


class MoodEntrySerializer(serializers.ModelSerializer):
    score = serializers.IntegerField(min_value=1, max_value=5)
    date = serializers.DateField(read_only=True)

    class Meta:
        model = MoodEntry
        fields = ["id", "score", "reflection", "date"]
        read_only_fields = ["id", "date"]

    def validate(self, data):
        # Prevent multiple mood entries per user per day
        user = self.context["request"].user
        today = timezone.localdate()
        exists = MoodEntry.objects.filter(user=user, date=today).exists()
        # If we are updating existing instance, allow it (user can patch existing record)
        if self.instance is None and exists:
            raise serializers.ValidationError(
                "Mood already logged for today.")
        return data

    def create(self, validated_data):
        validated_data["user"] = self.context["request"].user
        validated_data.setdefault("date", timezone.now().date())
        return super().create(validated_data)


class HabitCompletionSerializer(serializers.ModelSerializer):
    class Meta:
        model = HabitCompletion
        fields = ["id", "habit", "date", "completed"]
        read_only_fields = ["id", "date"]
