from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from .models import CustomUser, Client, Event, Message, Organisation


# Define a single CustomUserAdmin class that extends UserAdmin
@admin.register(CustomUser)
class CustomUserAdmin(UserAdmin):
    model = CustomUser

    # Extend the existing fieldsets for viewing/editing users
    fieldsets = UserAdmin.fieldsets + (
        (None, {
            'fields': (
                'dob', 'business', 'role',
                'phone_number', 'membership', 'credits',  # Include 'credits'
            ),
        }),
    )

    # Add fieldsets for creating new users
    add_fieldsets = (
        (None, {
            'classes': ('wide',),
            'fields': (
                'username', 'password1', 'password2',
                'dob', 'business', 'role', 'phone_number',
                'membership', 'credits',  # Include 'credits'
            ),
        }),
    )

    # Customize the list display in the admin interface
    list_display = ('username', 'email', 'credits', 'is_staff', 'is_active')
    list_filter = ('is_staff', 'is_active', 'role', 'membership')

    # Allow searching by username and email
    search_fields = ('username', 'email')
    ordering = ('username',)


# Register other models normally
@admin.register(Client)
class ClientAdmin(admin.ModelAdmin):
    list_display = ('name', 'email', 'phone', 'user')
    search_fields = ('name', 'email', 'phone')
    list_filter = ('user',)


@admin.register(Event)
class EventAdmin(admin.ModelAdmin):
    list_display = ('title', 'start', 'end', 'is_global', 'user')
    search_fields = ('title', 'description')
    list_filter = ('is_global', 'user')


@admin.register(Message)
class MessageAdmin(admin.ModelAdmin):
    list_display = ('client', 'sent_date', 'content')
    search_fields = ('content',)
    list_filter = ('sent_date',)

