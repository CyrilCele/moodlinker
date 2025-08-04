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

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Explicitly mark fields as required
        self.fields["bio"].required = True
        self.fields["avatar"].required = True
        self.fields["date_of_birth"].required = True
        self.fields["preference"].required = True
