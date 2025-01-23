from django.contrib import admin
from django.urls import path, include  # Import include
from django.conf import settings
urlpatterns = [
    path('admin/', admin.site.urls),
    path('', include('core.urls')),  # Include URLs from the core app
]
# Add Debug Toolbar URLs when in DEBUG mode
if settings.DEBUG:
    import debug_toolbar
    urlpatterns = [
        path('__debug__/', include(debug_toolbar.urls)),
    ] + urlpatterns