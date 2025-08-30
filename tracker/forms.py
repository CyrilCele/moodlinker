from django import forms
from .models import UserProfile, MoodEntry, Habit, Address


class UserProfileForm(forms.ModelForm):
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
        self.user = kwargs.pop("user", None)
        super().__init__(*args, **kwargs)
        # Explicitly mark fields as required
        self.fields["bio"].required = False
        self.fields["date_of_birth"].required = False

        # Populate address fields if address exists
        if self.instance and getattr(self.instance, "address", None):
            address = self.instance.address
            self.initial.update({
                "street_address": address.street_address,
                "city": address.city,
                "state_province": address.state_province,
                "postal_code": address.postal_code,
                "country": address.country
            })

    def save(self, commit=True):
        profile = super().save(commit=False)

        # List of fields to preserve if empty
        fields_to_preserve = [
            "bio", "date_of_birth", "phone_number"
        ]

        # Fetch fresh values from DB
        if profile.pk:
            original = UserProfile.objects.get(pk=profile.pk)
        else:
            original = None

        for field in fields_to_preserve:
            form_value = self.cleaned_data.get(field)

            if form_value in [None, ""] and original:
                setattr(profile, field, getattr(original, field))

        # Save or update address
        address_data = {
            "street_address": self.cleaned_data.get("street_address"),
            "city": self.cleaned_data.get("city"),
            "state_province": self.cleaned_data.get("state_province"),
            "postal_code": self.cleaned_data.get("postal_code"),
            "country": self.cleaned_data.get("country"),
        }

        if profile.address:
            for field, value in address_data.items():
                # Preserve old value if input is empty
                if value in [None, ""]:
                    value = getattr(profile.address, field)
                setattr(profile.address, field, value)

            profile.address.save()

        else:
            # Only create address if at least one value is filled
            if any(address_data.values()):
                address = Address.objects.create(**address_data)
                profile.address = address

        if commit:
            profile.save()

        return profile


class MoodEntryForm(forms.ModelForm):
    class Meta:
        model = MoodEntry
        fields = ["score", "reflection"]
        widgets = {
            "score": forms.RadioSelect(),
            "reflection": forms.Textarea(attrs={"rows": 2, "placeholder": "How are you feeling today?"})
        }


class HabitForm(forms.ModelForm):
    class Meta:
        model = Habit
        fields = ["habit", "description", "periodicity"]
        widgets = {
            "habit": forms.Textarea(attrs={"class": "form-control text-white bg-dark p-2"}),
            "description": forms.Textarea(attrs={"class": "form-control text-white bg-dark p-2", "rows": 2}),
            "periodicity": forms.Select(attrs={"class": "form-control text-white bg-dark p-2"})
        }


class NotificationPreferencesForm(forms.ModelForm):
    class Meta:
        model = UserProfile
        fields = ["notify_low_mood", "low_mood_threshold",
                  "timezone", "reminder_hour_local"]
        widgets = {
            "notify_low_mood": forms.CheckboxInput(attrs={"class": "form-check-input"}),
            "low_mood_threshold": forms.NumberInput(attrs={"class": "form-control text-white bg-dark p-2", "min": 1, "max": 5}),
            "timezone": forms.TextInput(attrs={"class": "form-control text-white bg-dark p-2", "placeholder": "e.g. Europe/Paris"}),
            "reminder_hour_local": forms.NumberInput(attrs={"class": "form-control text-white bg-dark p-2", "min": 0, "max": 23}),
        }
