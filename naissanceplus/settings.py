"""
Django settings for naissanceplus project.
Plateforme de gestion des déclarations de naissance.
"""

# Lecture des variables d'environnement (12-factor style).
import os
# Manipulation robuste des chemins de fichiers.
from pathlib import Path

# Racine du projet (dossier contenant manage.py).
BASE_DIR = Path(__file__).resolve().parent.parent

# Clé secrète: lue depuis l'environnement en priorité.
# Fallback de développement (long, non préfixé django-insecure pour éviter W009).
SECRET_KEY = os.getenv(
    'DJANGO_SECRET_KEY',
    'naissanceplus-dev-secret-key-change-me-please-2026'
)


def _env_bool(name, default=False):
    # Convertit une variable d'environnement texte en booléen.
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {'1', 'true', 'yes', 'on'}


def _env_csv(name, default=''):
    # Convertit une variable d'environnement CSV en liste.
    value = os.getenv(name, default)
    return [item.strip() for item in value.split(',') if item.strip()]


def _append_unique(items, value):
    # Ajoute une valeur dans une liste seulement si absente.
    if value and value not in items:
        items.append(value)


DEBUG = _env_bool('DJANGO_DEBUG', default=True)

# Hôtes autorisés (liste séparée par virgules en environnement).
ALLOWED_HOSTS = _env_csv('DJANGO_ALLOWED_HOSTS', '127.0.0.1,localhost')
_render_external_hostname = os.getenv('RENDER_EXTERNAL_HOSTNAME', '').strip()
if _render_external_hostname:
    _append_unique(ALLOWED_HOSTS, _render_external_hostname)

# Origines fiables pour formulaires CSRF (utile derrière reverse proxy).
CSRF_TRUSTED_ORIGINS = _env_csv('DJANGO_CSRF_TRUSTED_ORIGINS', '')
if _render_external_hostname:
    _append_unique(CSRF_TRUSTED_ORIGINS, f"https://{_render_external_hostname}")

INSTALLED_APPS = [
    # Apps natives Django.
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    # Apps tierces.
    'rest_framework',
    # Apps locales du projet.
    'accounts',
    'naissances',
]

MIDDLEWARE = [
    # Chaîne middleware standard Django.
    'django.middleware.security.SecurityMiddleware',
    'whitenoise.middleware.WhiteNoiseMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

ROOT_URLCONF = 'naissanceplus.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        # Répertoire templates global + templates d'app.
        'DIRS': [BASE_DIR / 'templates'],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.debug',
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
            ],
        },
    },
]

WSGI_APPLICATION = 'naissanceplus.wsgi.application'

# Base de données configurable (SQLite par défaut, PostgreSQL en Docker/prod).
_db_engine = os.getenv('DJANGO_DB_ENGINE', 'django.db.backends.sqlite3')
if _db_engine in {'postgres', 'postgresql'}:
    _db_engine = 'django.db.backends.postgresql'
if _db_engine == 'django.db.backends.sqlite3':
    _sqlite_name = os.getenv('DJANGO_DB_NAME', str(BASE_DIR / 'db.sqlite3'))
    DATABASES = {
        'default': {
            'ENGINE': 'django.db.backends.sqlite3',
            'NAME': _sqlite_name,
        }
    }
else:
    DATABASES = {
        'default': {
            'ENGINE': _db_engine,
            'NAME': os.getenv('DJANGO_DB_NAME', 'gest_etatcivil'),
            'USER': os.getenv('DJANGO_DB_USER', 'gest_user'),
            'PASSWORD': os.getenv('DJANGO_DB_PASSWORD', 'gest_password'),
            'HOST': os.getenv('DJANGO_DB_HOST', 'db'),
            'PORT': os.getenv('DJANGO_DB_PORT', '5432'),
        }
    }

AUTH_PASSWORD_VALIDATORS = [
    # Politiques minimales de robustesse mot de passe.
    {'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator'},
    {'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator'},
    {'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator'},
    {'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator'},
]

LANGUAGE_CODE = 'fr-fr'
TIME_ZONE = 'Africa/Abidjan'
USE_I18N = True
USE_TZ = True

# Fichiers statiques (css/js/images) et destination collectstatic.
STATIC_URL = '/static/'
STATICFILES_DIRS = [BASE_DIR / 'static']
STATIC_ROOT = BASE_DIR / 'staticfiles'
STORAGES = {
    # Stockage média (upload) standard sur le filesystem.
    'default': {'BACKEND': 'django.core.files.storage.FileSystemStorage'},
    # Stockage static compressé, servi par WhiteNoise en production.
    'staticfiles': {'BACKEND': 'whitenoise.storage.CompressedStaticFilesStorage'},
}
# Permet à WhiteNoise de retrouver les fichiers statiques même sans collectstatic.
WHITENOISE_USE_FINDERS = True

# Fichiers médias téléversés (PDF, etc.).
MEDIA_URL = '/media/'
MEDIA_ROOT = BASE_DIR / 'media'

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

# Custom User Model
AUTH_USER_MODEL = 'accounts.CustomUser'

# Login/Logout redirects
LOGIN_URL = '/accounts/login/'
LOGIN_REDIRECT_URL = '/dashboard/'
LOGOUT_REDIRECT_URL = '/accounts/login/'

# Django REST Framework
REST_FRAMEWORK = {
    # Auth API par session web (adapté à cette app serveur rendu HTML).
    'DEFAULT_AUTHENTICATION_CLASSES': [
        'rest_framework.authentication.SessionAuthentication',
    ],
    # Permission par défaut: utilisateur connecté.
    'DEFAULT_PERMISSION_CLASSES': [
        'rest_framework.permissions.IsAuthenticated',
    ],
    # Pagination standard pour éviter de grosses réponses.
    'DEFAULT_PAGINATION_CLASS': 'rest_framework.pagination.PageNumberPagination',
    'PAGE_SIZE': 20,
}

# Email configuration (console backend for development)
EMAIL_BACKEND = os.getenv(
    'DJANGO_EMAIL_BACKEND',
    'django.core.mail.backends.console.EmailBackend'
)
EMAIL_HOST = os.getenv('DJANGO_EMAIL_HOST', 'smtp.gmail.com')
EMAIL_PORT = int(os.getenv('DJANGO_EMAIL_PORT', '587'))
EMAIL_USE_TLS = _env_bool('DJANGO_EMAIL_USE_TLS', default=True)
EMAIL_TIMEOUT = int(os.getenv('DJANGO_EMAIL_TIMEOUT', '15'))
EMAIL_HOST_USER = os.getenv('DJANGO_EMAIL_HOST_USER', 'gestetatcivil@example.com')
EMAIL_HOST_PASSWORD = os.getenv('DJANGO_EMAIL_HOST_PASSWORD', '')
DEFAULT_FROM_EMAIL = os.getenv(
    'DJANGO_DEFAULT_FROM_EMAIL',
    'Gest_EtatCivil <gestetatcivil@example.com>'
)

# Emails d'alerte technique (notifications d'échec d'envoi mail parent).
ADMIN_ALERT_EMAILS = _env_csv('DJANGO_ADMIN_ALERT_EMAILS', '')

# Durcissement sécurité HTTP en environnement non-debug.
# En développement local, ces protections restent désactivées par défaut.
USE_X_FORWARDED_HOST = _env_bool('DJANGO_USE_X_FORWARDED_HOST', default=not DEBUG)
if _env_bool('DJANGO_USE_X_FORWARDED_PROTO', default=not DEBUG):
    SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')

SECURE_SSL_REDIRECT = _env_bool('DJANGO_SECURE_SSL_REDIRECT', default=not DEBUG)
SESSION_COOKIE_SECURE = _env_bool('DJANGO_SESSION_COOKIE_SECURE', default=not DEBUG)
CSRF_COOKIE_SECURE = _env_bool('DJANGO_CSRF_COOKIE_SECURE', default=not DEBUG)
SECURE_HSTS_SECONDS = int(
    os.getenv('DJANGO_SECURE_HSTS_SECONDS', '0' if DEBUG else '3600')
)
SECURE_HSTS_INCLUDE_SUBDOMAINS = _env_bool(
    'DJANGO_SECURE_HSTS_INCLUDE_SUBDOMAINS',
    default=not DEBUG,
)
SECURE_HSTS_PRELOAD = _env_bool('DJANGO_SECURE_HSTS_PRELOAD', default=not DEBUG)
SECURE_REFERRER_POLICY = os.getenv(
    'DJANGO_SECURE_REFERRER_POLICY',
    'strict-origin-when-cross-origin',
)
