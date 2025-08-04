import json
from django import forms
from .models import UserProfile


class UserProfileForm(forms.ModelForm):
    class Meta:
        model = UserProfile
        fields = ["avatar", "bio", "date_of_birth", "preference"]
        widgets = {
            "date_of_birth": forms.DateInput(
                attrs={
                    "type": "date",
                    "class": "form-control text-white bg-dark p-2",
                }
            ),
            "bio": forms.Textarea(attrs={"class": "form-control text-white bg-dark p-2"}),
            "avatar": forms.ClearableFileInput(attrs={"class": "form-control text-white bg-dark p-2"}),
            "preference": forms.Textarea(attrs={"class": "form-control text-white bg-dark p-2", "placeholder": "e.g. theme: dark, notifications: on"})
        }
