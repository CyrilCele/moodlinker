import spacy

from django.contrib.auth.models import User
from nltk.sentiment import SentimentIntensityAnalyzer
from rest_framework import serializers
from tracker.models import Habit, HabitCompletion, MoodEntry


# Serializer for User
class UserSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ["id", "username"]


# Serializer for Habit
class HabitSerializer(serializers.ModelSerializer):
    class Meta:
        model = Habit
        fields = ["id", "name", "frequency"]

    def create(self, validated_data):
        user = self.context["request"].user
        # Enforce exactly 5 habits per user
        if Habit.objects.filter(user=user).count() >= 5:
            raise serializers.ValidationError("Maximum 5 habits allowed!")
        return Habit.objects.create(user=user, **validated_data)


# Serializer for HabitCompletion
class HabitCompletionSerializer(serializers.ModelSerializer):
    class Meta:
        model = HabitCompletion
        fields = ["id", "habit", "date", "completed"]


# Serializer for MoodEntry (handles sentiment analysis)
class MoodEntrySerializer(serializers.ModelSerializer):
    class Meta:
        model = MoodEntry
        fields = ["id", "date", "score", "emoji", "reflection"]
        read_only_fields = ["score", "emoji", "date"]

    def create(self, validated_data):
        user = self.context["request"].user
        reflection = validated_data.get("reflection", "")
        # Use spaCy (for tokenization) and VADER for sentiment
        # (spaCy model load could be done once globally)
        nlp = spacy.load("en_core_web_sm")
        # Preprocess text (could use further for analysis)
        doc = nlp(reflection)
        sid = SentimentIntensityAnalyzer()
        comp = sid.polarity_scores(reflection)["compound"]
        # Map compound (-1...1) to score 1..5
        if comp >= 0.5:
            score = 5
            emoji = "😄"
        elif comp >= 0.05:
            score = 4
            emoji = "🙂"
        elif comp > -0.05:
            score = 3
            emoji = "😐"
        elif comp > -0.5:
            score = 2
            emoji = "🙁"
        else:
            score = 1
            emoji = "😞"
        # Create the mood entry with computed score/emoji
        mood = MoodEntry.objects.create(
            user=user,
            reflection=reflection,
            score=score,
            emoji=emoji,
            sentiment_compound=comp
        )
        return mood
