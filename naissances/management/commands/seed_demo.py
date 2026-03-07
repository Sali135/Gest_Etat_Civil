"""
Management command to seed demo data for Gest_EtatCivil.
Creates hospitals, mairies, and test users.
Usage: python manage.py seed_demo
"""
# Classe de base pour créer des commandes management Django.
from django.core.management.base import BaseCommand
# Récupère le modèle utilisateur actif du projet.
from django.contrib.auth import get_user_model
# Modèles de référence à injecter.
from naissances.models import Hopital, Mairie

# Alias du modèle utilisateur.
User = get_user_model()


class Command(BaseCommand):
    # Texte affiché dans `python manage.py help`.
    help = 'Seed demo data: hospitals, mairies, and test users'

    def handle(self, *args, **options):
        # Message de démarrage lisible en console.
        self.stdout.write(self.style.MIGRATE_HEADING('[START] Seeding demo data...'))

        # Create Hospitals
        # get_or_create: idempotent, évite les doublons si relancé.
        h1, _ = Hopital.objects.get_or_create(
            nom='CHU de Cocody',
            defaults={'adresse': 'Boulevard de la Paix, Cocody, Abidjan', 'contact': '+225 27 22 44 00 00'}
        )
        h2, _ = Hopital.objects.get_or_create(
            nom='Clinique Sainte Marie',
            defaults={'adresse': 'Rue des Jardins, Plateau, Abidjan', 'contact': '+225 27 22 33 11 22'}
        )
        self.stdout.write(f'  [OK] Hôpitaux créés: {h1.nom}, {h2.nom}')

        # Create Mairies
        # Création idempotente des mairies de démo.
        m1, _ = Mairie.objects.get_or_create(
            nom='Mairie de Cocody',
            defaults={'adresse': 'Avenue Houphouët-Boigny, Cocody', 'contact': '+225 27 22 44 55 66', 'ville': 'Cocody'}
        )
        m2, _ = Mairie.objects.get_or_create(
            nom='Mairie du Plateau',
            defaults={'adresse': 'Place de la République, Plateau', 'contact': '+225 27 22 33 44 55', 'ville': 'Plateau'}
        )
        self.stdout.write(f'  [OK] Mairies créées: {m1.nom}, {m2.nom}')

        # Create Admin
        # Crée le compte admin seulement s'il n'existe pas déjà.
        if not User.objects.filter(username='admin').exists():
            User.objects.create_superuser(
                username='admin',
                email='admin@gestetatcivil.cm',
                password='admin123',
                first_name='Super',
                last_name='Admin',
                role='ADMIN',
            )
            self.stdout.write('  [OK] Admin créé: admin / admin123')

        # Create Hospital Agent
        # Crée un agent hôpital de démo lié à h1.
        if not User.objects.filter(username='hopital1').exists():
            User.objects.create_user(
                username='hopital1',
                email='hopital1@gestetatcivil.cm',
                password='demo1234',
                first_name='Kouamé',
                last_name='Assi',
                role='HOPITAL',
                hopital=h1,
            )
            self.stdout.write(f'  [OK] Agent hôpital créé: hopital1 / demo1234 ({h1.nom})')

        # Create Mairie Agent
        # Crée un agent mairie de démo lié à m1.
        if not User.objects.filter(username='mairie1').exists():
            User.objects.create_user(
                username='mairie1',
                email='mairie1@gestetatcivil.cm',
                password='demo1234',
                first_name='Adjoua',
                last_name='Konan',
                role='MAIRIE',
                mairie=m1,
            )
            self.stdout.write(f'  [OK] Agent mairie créé: mairie1 / demo1234 ({m1.nom})')

        # Résumé final pour l'utilisateur.
        self.stdout.write(self.style.SUCCESS('\n[OK] Données de démonstration créées avec succès !'))
        self.stdout.write('\n[INFO] Comptes disponibles:')
        self.stdout.write('   admin    / admin123  → Administrateur')
        self.stdout.write('   hopital1 / demo1234  → Agent CHU de Cocody')
        self.stdout.write('   mairie1  / demo1234  → Agent Mairie de Cocody')
        self.stdout.write('\n[RUN] Lancez: python manage.py runserver')
