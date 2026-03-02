"""
ASGI config for naissanceplus project.

It exposes the ASGI callable as a module-level variable named ``application``.

For more information on this file, see
https://docs.djangoproject.com/en/5.1/howto/deployment/asgi/
"""

# Gestion des variables d'environnement.
import os

# Fabrique l'application ASGI Django.
from django.core.asgi import get_asgi_application

# Définit le module settings utilisé par Django.
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'naissanceplus.settings')

# Objet ASGI exporté pour les serveurs compatibles (uvicorn/daphne...).
application = get_asgi_application()
