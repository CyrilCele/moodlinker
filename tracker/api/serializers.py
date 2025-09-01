"""
REST Framework serializers for the tracker app.

This module defines:
    - HabitSerializer: validates habit creation limits and assigns the request user.
    - MoodEntrySerializer: prevents duplicate mood entries per user per day and
      assigns the request user and date on creation.
    - HabitCompletionSerializer: simple serializer for habit completion rows.

Important:
    - These serializers expect `self.context["request"]` to be provided (DRF ViewSetsdo this automatically).
    - Some validations rely on server-local dates (timezone.localdate). If you prefer user-local dates,
      adapt validations to use the user's timezone from their profile.
"""

from django.db import IntegrityError
from django.utils import timezone
from rest_framework import serializers

from tracker.models import Habit, MoodEntry, HabitCompletion


class HabitSerializer(serializers.ModelSerializer):
    """
    Serializer for Habit model.

    Responsibilities:
        - Validate at most 5 habits per user during creation.
        - On create, attach the authenticated user from the request context.

    Meta:
        model: Habit
        fields: id, habit, description, periodicity, created_at
        read_only_fields: id, created_at

    Notes:
        - The 5-habit limit is enforced here at the serializer level for UX
          (clean error messages). It is advisory only; concurrent creates may
          bypass it briefly - DB-level enforcement would be required for absolute guarantees.
    """
    class Meta:
        model = Habit
        fields = ["id", "habit", "description", "periodicity", "created_at"]
        read_only_fields = ["id", "created_at"]

    def validate(self, data):
        """
        Object-level validation for Habit.

        Ensures that a user may not create more than 5 habits.

        Args:
            data (dict): the partially validated data (field-level validators already applied).

        Returns:
            dict: the validated data unchanged.

        Raises:
            serializers.ValidationError: if the user already has 5 or more habits.

        Important notes:
            - This check runs only on create (self.instance is None).
            - The check relies on self.context["request"] existing and having .user.
            - Race conditions (two concurrent creates) can still lead to more than 5 habits;
              DB-level checks or a transaction with locking are necessary to prevent that.

        Example:
            >>> serializer = HabitSerializer(data={"habit": "Run", "periodicity": "daily"}, context={"request": request})
            >>> serializer.is_valid(raise_exception=True)
            >>> serializer.save()
        """
        # Ensure request user is available in the serializer context
        request = self.context.get("request")
        if request is None:
            # Defensive: if request not provided, raise meaningful error rather than KeyError later
            raise serializers.ValidationError(
                "Request context is required for Habit validation.")

        user = request.user

        # Only enforce limit on creation, not on updates
        if self.instance is None:
            current_count = Habit.objects.filter(user=user).count()
            if current_count >= 5:
                raise serializers.ValidationError(
                    "Limit of 5 habits reached for this user."
                )

        return data

    def create(self, validated_data):
        """
        Create a Habit instance and attach the request user.

        Args:
            validated_data (dict): validated fields from the serializer.

        Returns:
            Habit: the created Habit instance.

        Raises:
            Exception: underlying model save exceptions may propagate (e.g., IntegrityError).

        Example:
            >>> serializer.save() # assuming validated and context["request"] present
        """
        # Attach the authenticated user from context; DRF provides request in context automatically
        validated_data["user"] = self.context["request"].user
        return super().create(validated_data)


class MoodEntrySerializer(serializers.ModelSerializer):
    """
    Serializer for MoodEntry model.

    Responsibilities:
        - Prevent more than one MoodEntry per user per day on create.
        - Validate score is in 1...5 (via IntegerField with min/max)
        - On create, attach request.user and set the date (defaults to server date).

    Notes:
        - The uniqueness of (user, date) is enforced by the model DB constraint; this serializer
          provides a friendlier validation message before the DB throws as IntegrityError.
        - Date comparisons use `timezone.localdate()` (server-local date). If you need user-local
          date behavior, change to use the user's timezone.
    """

    # Explicitly declare field-level constraints and read-only date
    score = serializers.IntegerField(min_value=1, max_value=5)
    date = serializers.DateField(read_only=True)

    class Meta:
        model = MoodEntry
        fields = ["id", "score", "reflection", "date"]
        read_only_fields = ["id", "date"]

    def validate(self, data):
        """
        Object-level validation to prevent duplicate mood entries for today.

        Args:
            data (dict): validated field-level data.

        Returns:
            dict: the validated data unchanged.

        Raises:
            serializers.ValidationError: if a mood entry for today already exists for this user
                                         and tnis is a create operation.

        Edge cases & notes:
            - We use timezone.localdate() for 'today' (server-local date). If a user's timezone is
              different and you want to prevent duplicate entries by the user's day, adjust logic.
            - If two requests race (both pass this check), the DB unique constraint will cause the
              second create to raise IntegrityError. Views should handle that gracefully.

        Example:
            >>> serializer = MoodEntrySerializer(data={"score": 4, "reflection": "ok"}, context={"request": request})
            >>> serializer.is_valid(raise_exception=True)
            >>> serializer.save()
        """
        request = self.context.get("request")
        if request is None:
            raise serializers.ValidationError(
                "Request context is required for MoodEntry validation."
            )

        user = request.user
        # Server-local "today"; can change to timezone.localdate() or user-specific date as needed
        today = timezone.localdate()

        # If we're creating (self.instance is None) and an entry exists for today, reject
        exists = MoodEntry.objects.filter(user=user, date=today).exists()
        if self.instance is None and exists:
            raise serializers.ValidationError(
                "Mood already logged for today."
            )

        return data

    def create(self, validated_data):
        """
        Create a MoodEntry instance with user and date defaults.

        Args:
            validated_data (dict): validated fields.

        Returns:
            MoodEntry: the created instance.

        Raises:
            IntegrityError: if the model-level unique constraint on (user, date) is violated
                            due to a race condition. Calling view should catch and handle DB errors.

        Notes:
            - This method sets 'user' from the request and a default 'date' if one is not provided.
            - We set date to timezone.now().date() to be explicit; if you want the server local date,
              prefer timezone.localdate() for consistency with validate().

        Example:
            >>> serializer.save()
        """
        # Attach authenticated user
        validated_data["user"] = self.context["request"].user
        # Ensure date is set; prefer timezone.localdate() if you used that in validate()
        validated_data.setdefault("date", timezone.localdate())

        try:
            return super().create(validated_data)
        except IntegrityError:
            # Defensive: if a race caused duplicate insertion, convert DB error into serializer error
            raise serializers.ValidationError(
                "Mood entry for today already exists."
            )


class HabitCompletionSerializer(serializers.ModelSerializer):
    """
    Serializer for HabitCompletion model.

    Responsibilities:
        - Simple serialization of habit completion rows (id, habit, date, completed).
        - `date` is read-only and will be set by the model (auto_now_add).

    Notes:
        - This serializer does not validate that the referenced `habit` belongs to the request.user.
          In endpoints that allow creating/updating HabitCompletion, enforce that the habit belongs to
          the user (either in view-level permission checks or add a `validate_habit` method here).
    """
    class Meta:
        model = HabitCompletion
        fields = ["id", "habit", "date", "completed"]
        read_only_fields = ["id", "date"]
