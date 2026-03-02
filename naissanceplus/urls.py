"""URL configuration for naissanceplus project."""
# Site admin Django natif.
from django.contrib import admin
# Routeur URL + inclusion de routeurs applicatifs.
from django.urls import path, include
# Settings pour servir les médias en dev.
from django.conf import settings
from django.conf.urls.static import static
urlpatterns = [
    # Back-office Django standard.
    path('admin/', admin.site.urls),
    # Routes applicatives comptes.
    path('accounts/', include('accounts.urls', namespace='accounts')),
    # Routes métier principales.
    path('', include('naissances.urls', namespace='naissances')),
    # Routes API.
    path('api/', include('naissances.api_urls', namespace='api')),
] + static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
