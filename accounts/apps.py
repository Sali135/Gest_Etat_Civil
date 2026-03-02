# Configuration d'application Django.
from django.apps import AppConfig


class AccountsConfig(AppConfig):
    # Type d'ID auto par défaut pour les modèles.
    default_auto_field = 'django.db.models.BigAutoField'
    # Nom technique de l'app dans INSTALLED_APPS.
    name = 'accounts'
