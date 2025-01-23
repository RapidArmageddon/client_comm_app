import csv
from django import forms
from django.core.validators import FileExtensionValidator
from django.contrib import admin
from django.contrib.auth.forms import UserCreationForm, get_user_model
from .models import CustomUser
from .models import Event, Client, CustomUser, Organisation


class RegisterForm(UserCreationForm):
    class Meta:
        model = CustomUser
        fields = ['username', 'email', 'password1', 'password2', 'name', 'dob', 'business', 'role', 'phone_number',
                  'membership']

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        # Set optional fields
        self.fields['dob'].required = False
        self.fields['business'].required = False
        self.fields['role'].required = False
        self.fields['phone_number'].required = False


class CSVUploadForm(forms.Form):
    csv_file = forms.FileField(
        validators=[FileExtensionValidator(allowed_extensions=['csv'])],
        widget=forms.FileInput(attrs={'accept': '.csv'})
    )

    def clean_csv_file(self):
        csv_file = self.cleaned_data['csv_file']
        decoded_file = csv_file.read().decode('utf-8').splitlines()
        csv_reader = csv.reader(decoded_file)
        try:
            next(csv_reader)  # Skip header row
            for row in csv_reader:
                if len(row) != 5:  # Adjust this based on expected columns
                    raise forms.ValidationError("Invalid CSV structure.")
        except Exception:
            raise forms.ValidationError("Invalid CSV content.")
        return csv_file

class EventForm(forms.ModelForm):
    """
    Form for creating or updating events.
    Filters clients to only those belonging to the logged-in user.
    Restricts non-superusers from creating global events.
    """
    is_global = forms.BooleanField(
        required=False,
        initial=False,
        help_text="Only superusers can create global events."
    )

    class Meta:
        model = Event
        fields = ['title', 'start', 'end', 'description', 'is_global', 'clients']

    def __init__(self, *args, **kwargs):
        user = kwargs.pop('user', None)  # Extract 'user' from kwargs
        super().__init__(*args, **kwargs)
        self.user = user  # Store the user for later validation

        if user:
            # Filter clients to those owned by the logged-in user
            self.fields['clients'].queryset = Client.objects.filter(user=user)

            # Hide the is_global field for non-superusers
            if not user.is_superuser:
                self.fields['is_global'].widget = forms.HiddenInput()

    def clean_is_global(self):
        """
        Validate the is_global field to ensure only superusers can create global events.
        """
        is_global = self.cleaned_data.get('is_global', False)

        if is_global and not self.user.is_superuser:
            raise forms.ValidationError("You do not have permission to create a global event.")
        return is_global

class SettingsForm(forms.ModelForm):
    """
    Form for user settings, including password changes.
    """
    password = forms.CharField(
        required=False,
        widget=forms.PasswordInput(attrs={
            'placeholder': 'Enter new password (leave blank to keep current)',
        })
    )

    class Meta:
        model = get_user_model()
        fields = ['profile_photo', 'name', 'business', 'phone_number', 'whatsapp_id']
        widgets = {
            'profile_photo': forms.FileInput(attrs={'class': 'form-control'}),
            'name': forms.TextInput(attrs={'class': 'form-control'}),
            'business': forms.TextInput(attrs={'class': 'form-control'}),
            'phone_number': forms.TextInput(attrs={'class': 'form-control'}),
            'whatsapp_id': forms.TextInput(attrs={'class': 'form-control'}),
        }

    def save(self, commit=True):
        """
        Overridden save method to handle password changes.
        """
        user = super().save(commit=False)
        password = self.cleaned_data.get('password')
        if password:
            user.set_password(password)
        if commit:
            user.save()
        return user

@admin.register(Organisation)
class OrganisationAdmin(admin.ModelAdmin):
    list_display = ("name", "organisation_id", "created_by", "created_at")
    search_fields = ("name", "organisation_id")

class OrganisationForm(forms.ModelForm):
    class Meta:
        model = Organisation
        fields = ["name", "description"]

class JoinOrganisationForm(forms.Form):
    organisation_id = forms.UUIDField(label="Organisation ID")