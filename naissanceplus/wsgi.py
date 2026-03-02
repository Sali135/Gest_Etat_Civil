"""
WSGI config for naissanceplus project.

It exposes the WSGI callable as a module-level variable named ``application``.

For more information on this file, see
https://docs.djangoproject.com/en/5.1/howto/deployment/wsgi/
"""

# Gestion des variables d'environnement.
import os

# Fabrique l'application WSGI Django.
from django.core.wsgi import get_wsgi_application

# Définit le module settings utilisé par Django.
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'naissanceplus.settings')

# Objet WSGI exporté pour les serveurs compatibles (gunicorn/mod_wsgi...).
application = get_wsgi_application()
