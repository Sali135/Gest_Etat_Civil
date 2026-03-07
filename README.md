# Gest_EtatCivil

**Plateforme de gestion des déclarations de naissance**

Application web Django professionnelle permettant de numériser la communication entre les maternités (hôpitaux) et les mairies pour la déclaration des naissances.

---

## Installation rapide

### 1. Prérequis
- Python 3.10+
- pip

### 2. Cloner / accéder au projet
```bash
cd d:\abdoul1
```

### 3. Créer et activer un environnement virtuel (recommandé)
```bash
python -m venv venv
# Windows:
venv\Scripts\activate
# Linux/Mac:
source venv/bin/activate
```

### 4. Installer les dépendances
```bash
pip install -r requirements.txt
```

### 5. Appliquer les migrations
```bash
python manage.py migrate
```

### 6. Créer un superutilisateur (Administrateur)
```bash
python manage.py createsuperuser
```

### 7. Charger les données de démonstration (optionnel)
```bash
python manage.py seed_demo
```
> Crée des hôpitaux, mairies, et utilisateurs de test prêts à l'emploi.

### 8. Lancer le serveur
```bash
python manage.py runserver
```

Accédez à : **http://127.0.0.1:8000/**

---

## Déploiement avec Docker

### Prérequis
- Docker Desktop (ou Docker Engine + Docker Compose v2)

### 1. Préparer les variables d'environnement
```bash
cp .env.example .env
```
> Sous Windows PowerShell:
```powershell
Copy-Item .env.example .env
```

### 2. Construire et lancer les services
```bash
docker compose up -d --build
```
> Si votre installation utilise l'ancien binaire Compose, utilisez `docker-compose up -d --build`.

Services lancés:
- `web` (Django + Gunicorn)
- `db` (PostgreSQL)
- `nginx` (reverse proxy + static/media)

### 3. Appliquer migrations / créer un admin
```bash
docker compose exec web python manage.py migrate
docker compose exec web python manage.py createsuperuser
```
> Variante ancienne commande: `docker-compose exec web ...`

### 4. Charger les données de démonstration (optionnel)
```bash
docker compose exec web python manage.py seed_demo
```

### 5. Accès application
- http://localhost

### Commandes utiles
```bash
docker compose logs -f web
docker compose down
docker compose down -v   # supprime aussi les volumes (base de données incluse)
```

---

## Comptes de démonstration (après `seed_demo`)

| Rôle | Identifiant | Mot de passe |
|------|-------------|--------------|
| Admin | `admin` | `admin123` |
| Agent Hôpital | `hopital1` | `demo1234` |
| Agent Mairie | `mairie1` | `demo1234` |

---

## Architecture du projet

```
naissanceplus/          # Configuration Django
accounts/               # Authentification & Custom User
naissances/             # Logique métier principale
  models.py             # Hopital, Mairie, Declaration, Acte
  views.py              # Dashboards, CRUD, PDF, API
  forms.py              # Formulaires
  admin.py              # Interface admin
  serializers.py        # DRF serializers
  api_views.py          # API REST endpoints
  api_urls.py           # API URL patterns
templates/              # Templates HTML Bootstrap 5
  base.html             # Layout avec sidebar
  accounts/login.html   # Page de connexion
  naissances/           # Tous les templates métier
static/css/style.css    # CSS premium personnalisé
```

---

## Fonctionnalités

### Agent Hôpital
- Tableau de bord avec statistiques
- Créer une déclaration de naissance (formulaire complet)
- Modifier une déclaration en attente
- Consulter le statut de ses déclarations

### Agent Mairie
- Tableau de bord avec file de travail
- Consulter les déclarations reçues
- Valider une déclaration -> génération automatique de l'acte
- Rejeter une déclaration avec motif
- Télécharger l'acte de naissance en PDF

### Parents
- Consulter le statut via référence dossier (sans connexion)
- Voir le numéro d'acte si validé
- Voir le motif de rejet si rejeté

### Administrateur
- Tableau de bord global avec statistiques
- Gestion complète via l'interface Django Admin
- Accès à l'API REST

---

## API REST

Base URL : `/api/`

| Endpoint | Méthode | Description |
|----------|---------|-------------|
| `/api/declarations/` | GET | Liste des déclarations (filtrée par rôle) |
| `/api/declarations/` | POST | Créer une déclaration (hôpital) |
| `/api/declarations/<id>/` | GET | Détail d'une déclaration |
| `/api/hopitaux/` | GET | Liste des hôpitaux |
| `/api/mairies/` | GET | Liste des mairies |
| `/api/stats/` | GET | Statistiques globales (admin) |

---

## Notifications Email

Par défaut, les emails sont affichés dans la console (backend de développement).
Pour activer l'envoi réel, modifiez `settings.py` :

```python
EMAIL_BACKEND = 'django.core.mail.backends.smtp.EmailBackend'
EMAIL_HOST_USER = 'votre@email.com'
EMAIL_HOST_PASSWORD = 'votre-mot-de-passe'
```

---

## Technologies

- **Backend** : Django 5.x, Django REST Framework
- **Base de données** : SQLite (développement)
- **Frontend** : Bootstrap 5, Bootstrap Icons, Google Fonts (Inter)
- **PDF** : xhtml2pdf
- **Auth** : Django Auth + Custom User Model avec rôles

---

*Projet de fin d'études - Génie Logiciel | Gest_EtatCivil (c) 2025*
