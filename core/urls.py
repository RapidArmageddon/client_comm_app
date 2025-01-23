from django.contrib.auth import views as auth_views
from django.urls import path  # Import path
from . import views  # Import your views module
from django.conf import settings
from django.conf.urls.static import static
urlpatterns = [
    # Main views
    path('', views.home, name='home'),
    path('profile/', views.profile, name='profile'),
    path('analytics/', views.analytics, name='analytics'),
    path('clients/', views.client_list, name='client_list'),
    path('calendar/', views.calendar_view, name='calendar'),
    path('messages/', views.messages_view, name='messages'),
    path('settings/', views.settings_view, name='settings'),
    path('purchase/', views.purchase_credit, name='purchase_credit'),

    # Authentication views
    path('login/', auth_views.LoginView.as_view(template_name='core/login.html'), name='login'),
    path('register/', views.register, name='register'),
    path('login-success/', views.login_view, name='login_success'),
    path('logout/', views.logout_view, name='logout'),

    # CSV upload and data management
    path('upload-csv/', views.upload_csv, name='upload_csv'),

    # Event APIs and functionality
    path('api/events/', views.fetch_events, name='fetch_events'),  # Fetch events dynamically
    path('add-event/', views.add_event, name='add_event'),  # Add new events
    path('delete-event/', views.delete_event, name='delete_event'),  # Delete events

    # Messages functionality
    path('message-summary/', views.message_summary, name='message_summary'),
    path('generate-ai-messages/', views.generate_ai_messages_page, name='generate_ai_messages_page'),  # Page rendering
    path('generate-ai-messages/stream/', views.generate_ai_messages_stream, name='generate_ai_messages_stream'),  # Streaming response

    # Analytics API
    path('api/analytics-data/', views.analytics_data, name='analytics_data'),

    # Policy Agreements
    path('policy-agreement/', views.policy_agreement, name='policy_agreement'),
    path('accept-policies/', views.accept_policies, name='accept_policies'),

    # Twilio Related
    path("send-message/", __import__('core.views').views.send_message_view, name="send_message"),

    path("add-organisation/", views.add_organisation, name="add_organisation"),
    path("join-organisation/", views.join_organisation, name="join_organisation"),

]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)