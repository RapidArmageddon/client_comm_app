import uuid
from django.db import models
from django import forms
from django.conf import settings
from django.contrib.auth.models import AbstractUser
from django.db.models import Manager
from django.utils.crypto import get_random_string
from django.contrib.auth import get_user_model

class OwnedByUserManager(Manager):
    def for_user(self, user):
        return self.filter(user=user)

class Organisation(models.Model):
    name = models.CharField(max_length=255, unique=True)
    organisation_id = models.CharField(max_length=10, unique=True)  # Short unique ID
    created_at = models.DateTimeField(auto_now_add=True)
    description = models.TextField(blank=True, null=True)

    created_by = models.ForeignKey(
        'core.CustomUser',  # Reference to your custom user model
        on_delete=models.CASCADE,
        related_name="created_organisations"
    )

    def save(self, *args, **kwargs):
        if not self.organisation_id:  # Generate only if not already set
            while True:
                organisation_id = get_random_string(6).upper()
                if not Organisation.objects.filter(organisation_id=organisation_id).exists():
                    self.organisation_id = organisation_id
                    break
        super().save(*args, **kwargs)

    def __str__(self):
        return self.name

class Client(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    organisation = models.ForeignKey(
        'Organisation', on_delete=models.CASCADE, related_name="clients", null=True, blank=True
    )
    name = models.CharField(max_length=200)
    email = models.EmailField()
    phone = models.CharField(max_length=15)
    total_spent = models.DecimalField(max_digits=10, decimal_places=2, default=0.0)
    last_purchase_date = models.DateField(null=True, blank=True)
    unsubscribed = models.BooleanField(default=False)

    objects = OwnedByUserManager()  # Custom manager

    def __str__(self):
        return self.name


class Event(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, null=True, blank=True)
    title = models.CharField(max_length=200)
    start = models.DateTimeField()  # Start time of the event
    end = models.DateTimeField()    # End time of the event
    description = models.TextField(blank=True, null=True)
    clients = models.ManyToManyField(Client, related_name="events", blank=True)  # Assign clients to events
    is_global = models.BooleanField(default=False)  # True for global events

    objects = OwnedByUserManager()  # Custom manager

    def __str__(self):
        return self.title



class Message(models.Model):
    client = models.ForeignKey(Client, on_delete=models.CASCADE)
    content = models.TextField()
    sent_date = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Message to {self.client.name} on {self.sent_date}"


class CustomUser(AbstractUser):
    # Additional fields
    name = models.CharField(max_length=255, blank=True, null=True)
    dob = models.DateField(blank=True, null=True)
    business = models.CharField(max_length=255, blank=True, null=True)
    role = models.CharField(max_length=100, blank=True, null=True)
    phone_number = models.CharField(max_length=15, blank=True, null=True)
    credits = models.PositiveIntegerField(default=0)  # Default to 0 credits
    has_accepted_policies = models.BooleanField(default=False)
    organisation = models.ForeignKey(
        Organisation, on_delete=models.SET_NULL, related_name="members", null=True, blank=True
    )

    MEMBERSHIP_CHOICES = [
        ('Basic', 'Basic'),
        ('Pro', 'Pro'),
        ('Enterprise', 'Enterprise'),
    ]

    membership = models.CharField(max_length=20, choices=MEMBERSHIP_CHOICES, default='Basic')


    # New fields for extended functionality
    profile_photo = models.ImageField(upload_to='profile_photos/', blank=True, null=True)
    whatsapp_id = models.CharField(max_length=100, blank=True, null=True)

    # Resolve related_name conflicts
    groups = models.ManyToManyField(
        'auth.Group',
        related_name='customuser_set',  # Unique related_name for CustomUser
        blank=True,
    )
    user_permissions = models.ManyToManyField(
        'auth.Permission',
        related_name='customuser_set',  # Unique related_name for CustomUser
        blank=True,
    )

    def __str__(self):
        return self.username

    class JoinOrganisationForm(forms.Form):
        organisation_id = forms.CharField(
            label="Organisation ID",
            max_length=10,
            widget=forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Enter Organisation ID (e.g., R08767)',
            })
        )

        def clean_organisation_id(self):
            organisation_id = self.cleaned_data['organisation_id']
            if not Organisation.objects.filter(organisation_id=organisation_id).exists():
                raise forms.ValidationError("Invalid Organisation ID.")
            return organisation_id