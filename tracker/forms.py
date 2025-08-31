from django import forms
from django.db import transaction
from django.core.exceptions import ValidationError
from .models import UserProfile, MoodEntry, Habit, Address


class UserProfileForm(forms.ModelForm):
    """
    Form used to edit a user's profile and related address.

    This ModeForm edits `UserProfile` fields (avatar, bio, date_of_birth, phone_number)
    while exposing separate free-form fields for address components:
        - street_address, city, state_province, postal_code, country

    Important behavior:
        - On initialization, if the instance has an Address, address fields are populated
          into `initial`.
        - On save():
            * Preserves existing `bio`, `date_of_birth`, and `phone_number` if the form submits
              an empty value (prevents accidental clearing).
            * Updates an existing Address in-place, or creates a new Address only if at least
              one address field is non-empty.
            * Returns the saved `UserProfile` instance.
    """

    # Address sub-fields (not part of the UserProfile model directly)
    street_address = forms.CharField(
        required=False,
        widget=forms.TextInput(
            attrs={"class": "form-control text-white bg-dark p-2"})
    )

    city = forms.CharField(
        required=False,
        widget=forms.TextInput(
            attrs={"class": "form-control text-white bg-dark p-2"})
    )

    state_province = forms.CharField(
        required=False,
        widget=forms.TextInput(
            attrs={"class": "form-control text-white bg-dark p-2"})
    )

    postal_code = forms.CharField(
        required=False,
        widget=forms.TextInput(
            attrs={"class": "form-control text-white bg-dark p-2"})
    )

    country = forms.CharField(
        required=False,
        widget=forms.TextInput(
            attrs={"class": "form-control text-white bg-dark p-2"})
    )

    class Meta:
        model = UserProfile
        fields = ["avatar", "bio", "date_of_birth", "phone_number"]
        widgets = {
            "date_of_birth": forms.DateInput(
                attrs={
                    "type": "date",
                    "class": "form-control text-white bg-dark p-2",
                }
            ),
            "phone_number": forms.TextInput(attrs={"class": "form-control text-white bg-dark p-2", "placeholder": "+27 82 123 4567"}),
            "bio": forms.Textarea(attrs={"class": "form-control text-white bg-dark p-2"}),
            "avatar": forms.ClearableFileInput(attrs={"class": "form-control text-white bg-dark p-2"}),
        }

    def __init__(self, *args, **kwargs):
        """
        Initialize the form.

        Args:
            *args: positional args forwarded to ModelForm.
            **kwargs: keyword args forwarded to ModelForm; accepts optional:
                - user (User|None): optional current user; stored on the form instance.
                - instance (UserProfile|None): optional profile instance being edited.

        Behavior:
            - Populates `self.user` if a "user" kwarg is provided.
            - Marks `bio` and `date_of_birth` as not required so they can be left blank.
            - If the bound/instance profile has a linked Address, populate address fields
              into `initial` so they render in the form.
        """
        # Pull out user argument for potential use in save/validation later
        self.user = kwargs.pop("user", None)
        super().__init__(*args, **kwargs)

        # Explicitly make these optional so empty submissions do not fail validation.
        self.fields["bio"].required = False
        self.fields["date_of_birth"].required = False

        # If editing an existing profile that has an address, populate the initial data
        if self.instance and getattr(self.instance, "address", None):
            address = self.instance.address
            # Use update so other initial keys are preserved
            self.initial.update({
                "street_address": address.street_address,
                "city": address.city,
                "state_province": address.state_province,
                "postal_code": address.postal_code,
                "country": address.country
            })

    def clean(self):
        """
        Perform cross-field validation as necessary.

        Notes:
            - This method is hook - you can add extra validation here (e.g. validate
              postal_code format for a given country, require phone number when notify_low_mood,
              or sanitize whitespace).
        """
        cleaned = super().clean()

        # Example: trim whitespace from postal code if present
        postal = cleaned.get("postal_code")
        if postal and isinstance(postal, str):
            cleaned["postal_code"] = postal.strip()

        return cleaned

    def save(self, commit: bool = True) -> UserProfile:
        """
        Persist the UserProfile and optional Address.

        Args:
            commit (bool): If True, save to DB. If False, return unsaved instance(s).
                Note: address will be created/updated in-memory but not saved if commit=False.

        Returns:
            UserProfile: The saved (or prepared, if commit=False) profile instance.

        Raises:
            django.core.exceptions.ValidationError: If the form is not valid (should be called
                only after form.is_valid()).
            django.db.Error: Database errors propagated from save/create (e.g., IntegrityError).
        """
        if not self.is_valid():
            raise ValidationError(
                "Cannot save an invalid form. Call is_valid() first."
            )

        # Get the profile instance without committing yet
        profile: UserProfile = super().save(commit=False)

        # Fields to preserve from the DB when submitted as empty
        fields_to_preserve = [
            "bio", "date_of_birth", "phone_number"
        ]

        # Load the original row from DB to read preserved values (if it exists).
        # This may raise UserProfile.DoesNotExist if the instance was deleted externally;
        # we let that bubble up as it's an unsual race condition.
        original = None
        if profile.pk:
            try:
                original = UserProfile.objects.get(pk=profile.pk)
            except UserProfile.DoesNotExist:
                original = None  # defensive: continue, treat as new

        # Preserve fields that were intentionally left blank in the form
        for field in fields_to_preserve:
            form_value = self.cleaned_data.get(field)
            # If the submitted value is empty and there was an original value, keep it
            if form_value in [None, ""] and original:
                setattr(profile, field, getattr(original, field))

        # Address handling: prepare the address data from cleaned_data
        address_data = {
            "street_address": self.cleaned_data.get("street_address"),
            "city": self.cleaned_data.get("city"),
            "state_province": self.cleaned_data.get("state_province"),
            "postal_code": self.cleaned_data.get("postal_code"),
            "country": self.cleaned_data.get("country")
        }

        # Use an atomic block to avoid partial saves between address and profile
        # (commit=True case). If commit=False, we still prepare objects but don't save.
        if commit:
            with transaction.atomic():
                # Update existing address if present on profile
                if profile.address:
                    for field, value in address_data.items():
                        # Preserve old value if the submitted input is empty
                        if value in [None, ""]:
                            value = getattr(profile.address, field)
                        setattr(profile.address, field, value)
                    profile.address.save()

                else:
                    # Only create address if at least one field is non-empty
                    if any(value not in (None, "") for value in address_data.values()):
                        address = Address.objects.create(**address_data)
                        profile.address = address

                # Finally save profile (and its FK to address)
                profile.save()

        else:
            # commit=False: only mutate in-memory objects; do not persist to DB.
            # Update or prepare address object in-memory
            if profile.address:
                for field, value in address_data.items():
                    if value in [None, ""]:
                        value = getattr(profile.address, field)
                    setattr(profile.address, field, value)
            else:
                if any(value not in (None, "") for value in address_data.values()):
                    # Prepare an Address instance but do not save it
                    profile.address = Address(**address_data)

            # Do not call save() on profile or address here.
        return profile


class MoodEntryForm(forms.ModelForm):
    """
    Form for creating a MoodEntry.

    Fields:
        - store (int): selected via RadioSelect; choices defined by MoodEntry.MOOD_CHOICES.
        - reflection (str): optional text area (2 rows by default).

    Usage:
        form = MoodEntryForm(data=request.POST)
        if form.is_valid():
            mood = form.save(commit=False)
            mood.user = request.user
            mood.save()

    Notes:
        - Unique constraint (user, date) exists on the model; saving for the same date twice
          will raise an IntegrityError at DB level - handle gracefully in views.
    """
    class Meta:
        model = MoodEntry
        fields = ["score", "reflection"]
        widgets = {
            "score": forms.RadioSelect(),
            "reflection": forms.Textarea(
                attrs={"rows": 2, "placeholder": "How are you feeling today?"}
            )
        }


class HabitForm(forms.ModelForm):
    """
    Form for creating or updating a Habit.

    Fields:
        - habit (str): Name/label of the habit (textarea widget).
        - description (str): Short description of the habit.
        - periodicity (str): Choice of 'daily', 'weekly', 'monthly'.

    Usage:
        form = HabitForm(data=request.POST)
        if form.is_valid():
            habit = form.save(commit=False)
            habit.user = request.user
            if Habit.user_habits_limit(request.user):
                habit.save()
            else:
                form.add_error(None, "Limit of 5 habits reached.")

    Notes:
        - Business logic (limit of 5 habits) should be enforced outside the form
          (views or service layer) because the model does not enforce it.
    """
    class Meta:
        model = Habit
        fields = ["habit", "description", "periodicity"]
        widgets = {
            "habit": forms.Textarea(attrs={"class": "form-control text-white bg-dark p-2"}),
            "description": forms.Textarea(attrs={"class": "form-control text-white bg-dark p-2", "rows": 2}),
            "periodicity": forms.Select(attrs={"class": "form-control text-white bg-dark p-2"})
        }


class NotificationPreferencesForm(forms.ModelForm):
    """
    Form to edit notification preferences on the UserProfile.

    Fields:
        - notify_low_mood (bool): checkbox to enable/disable low mood alerts.
        - low_mood_threshold (int): numeric input 1...5 for the alert threshold.
        - timezone (str): IANA timezone string, e.g. "Europe/Paris".
        - reminder_hour_local (int): local hour 0...23 for habit reminders.

    Usage:
        form = NotificationPreferencesForm(instance=request.user.profile, data=request.POST)
        if form.is_valid():
            form.save()
            # schedule reminders as appropriate in view/task layer

    Notes:
        - Consider validating timezone strings and hour bounds either here or on the model.
        - Changing reminder_hour_local should typically trigger rescheduling of reminders.
    """
    class Meta:
        model = UserProfile
        fields = [
            "notify_low_mood", "low_mood_threshold", "timezone", "reminder_hour_local"
        ]
        widgets = {
            "notify_low_mood": forms.CheckboxInput(attrs={"class": "form-check-input"}),
            "low_mood_threshold": forms.NumberInput(attrs={"class": "form-control text-white bg-dark p-2", "min": 1, "max": 5}),
            "timezone": forms.TextInput(attrs={"class": "form-control text-white bg-dark p-2", "placeholder": "e.g. Europe/Paris"}),
            "reminder_hour_local": forms.NumberInput(attrs={"class": "form-control text-white bg-dark p-2", "min": 0, "max": 23}),
        }
