#!/usr/bin/env python
"""Django's command-line utility for administrative tasks."""
# Accès aux variables d'environnement.
import os
# Accès aux arguments CLI (sys.argv).
import sys


def main():
    """Run administrative tasks."""
    # Définit le module settings à utiliser pour initialiser Django.
    os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'naissanceplus.settings')
    try:
        # Point d'entrée officiel des commandes Django (runserver, migrate, test...).
        from django.core.management import execute_from_command_line
    except ImportError as exc:
        # Message explicite si Django n'est pas importable.
        raise ImportError(
            "Couldn't import Django. Are you sure it's installed and "
            "available on your PYTHONPATH environment variable? Did you "
            "forget to activate a virtual environment?"
        ) from exc
    # Exécute la commande demandée en terminal.
    execute_from_command_line(sys.argv)


if __name__ == '__main__':
    # Lance la fonction principale si le fichier est exécuté directement.
    main()
