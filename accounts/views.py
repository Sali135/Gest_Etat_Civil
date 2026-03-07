"""Views for accounts app - Authentication."""
# Variables d'environnement pour mode démo/prototype.
import os
# Import des helpers d'authentification Django (connexion / déconnexion de session utilisateur).
from django.contrib.auth import login, logout
from django.contrib.auth.views import LoginView, LogoutView
# Import du framework de messages flash (succès, erreur, warning) affichés dans l'UI.
from django.contrib import messages
# Décorateur imposant qu'un utilisateur soit connecté pour accéder à une vue.
from django.contrib.auth.decorators import login_required
# Helpers de rendu/template, redirection, et récupération d'objet avec 404 auto.
from django.shortcuts import redirect, render, get_object_or_404
# Outil pour composer des filtres OR/AND dynamiques en base de données.
from django.db.models import Q
# Pagination pour découper les grandes listes dans l'interface.
from django.core.paginator import Paginator
# Génération d'URL à partir du nom de route.
from django.urls import reverse_lazy
# Modèles métiers importés depuis l'app naissances.
from naissances.models import Hopital, Mairie
# Formulaires utilisés pour les écrans d'administration.
from .forms import (
    LoginForm, CustomUserCreationForm, MairieCreationForm,
    CustomUserUpdateForm, MairieUpdateForm,
)
# Modèles de comptes + journal d'audit admin.
from .models import CustomUser, AdminActionLog


class CustomLoginView(LoginView):
    """Vue de connexion personnalisée."""
    # Formulaire HTML de login à utiliser.
    form_class = LoginForm
    # Template rendu pour la page de connexion.
    template_name = 'accounts/login.html'
    # Si l'utilisateur est déjà connecté, on le redirige sans réafficher le login.
    redirect_authenticated_user = True

    def dispatch(self, request, *args, **kwargs):
        # En mode prototype, s'assure que les comptes de démonstration existent.
        _ensure_demo_accounts()
        return super().dispatch(request, *args, **kwargs)

    def get_success_url(self):
        # Après connexion réussie, on envoie l'utilisateur vers son dashboard (router par rôle).
        return reverse_lazy('naissances:dashboard')


class CustomLogoutView(LogoutView):
    """Vue de déconnexion."""
    # URL de destination après fermeture de session.
    next_page = reverse_lazy('accounts:login')


def _is_platform_admin(user):
    # Retourne True si l'utilisateur est connecté et dispose des droits d'administration plateforme.
    return user.is_authenticated and (user.is_superuser or user.role == CustomUser.Role.ADMIN)


def _env_bool(name, default=False):
    # Convertit proprement une variable d'environnement texte en booléen.
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {'1', 'true', 'yes', 'on'}


def _ensure_demo_accounts():
    """Create demo entities/users if missing (prototype mode)."""
    if not _env_bool('DJANGO_ENABLE_DEMO_ACCOUNTS', default=True):
        return

    def _sync_demo_user(username, password, defaults):
        # Crée le compte s'il manque, et peut réaligner le mot de passe en mode prototype.
        user, _ = CustomUser.objects.get_or_create(username=username, defaults=defaults)
        dirty = False
        for field, value in defaults.items():
            if getattr(user, field) != value:
                setattr(user, field, value)
                dirty = True
        if _env_bool('DJANGO_DEMO_FORCE_PASSWORD_RESET', default=True):
            user.set_password(password)
            dirty = True
        if dirty:
            user.save()

    # Référentiels minimaux requis par les comptes de démonstration.
    hopital, _ = Hopital.objects.get_or_create(
        nom='CHU de Cocody',
        defaults={
            'adresse': 'Boulevard de la Paix, Cocody, Abidjan',
            'contact': '+225 27 22 44 00 00',
        },
    )
    mairie, _ = Mairie.objects.get_or_create(
        nom='Mairie de Cocody',
        defaults={
            'adresse': 'Avenue Houphouet-Boigny, Cocody',
            'contact': '+225 27 22 44 55 66',
            'ville': 'Cocody',
        },
    )

    _sync_demo_user(
        username='admin',
        password='admin123',
        defaults={
            'email': 'admin@gestetatcivil.cm',
            'first_name': 'Super',
            'last_name': 'Admin',
            'role': CustomUser.Role.ADMIN,
            'is_staff': True,
            'is_superuser': True,
            'is_active': True,
        },
    )
    _sync_demo_user(
        username='hopital1',
        password='demo1234',
        defaults={
            'email': 'hopital1@gestetatcivil.cm',
            'first_name': 'Kouame',
            'last_name': 'Assi',
            'role': CustomUser.Role.HOPITAL,
            'hopital': hopital,
            'is_active': True,
        },
    )
    _sync_demo_user(
        username='mairie1',
        password='demo1234',
        defaults={
            'email': 'mairie1@gestetatcivil.cm',
            'first_name': 'Adjoua',
            'last_name': 'Konan',
            'role': CustomUser.Role.MAIRIE,
            'mairie': mairie,
            'is_active': True,
        },
    )


def _log_admin_action(actor, action_type, target_type, target_id, target_label, description=''):
    # Enregistre toute action sensible effectuée en back-office pour traçabilité/audit.
    AdminActionLog.objects.create(
        # Si l'acteur n'est pas authentifié, on enregistre None.
        actor=actor if actor.is_authenticated else None,
        # Type d'action: CREATE / UPDATE / DELETE / TOGGLE.
        action_type=action_type,
        # Type d'objet ciblé (CustomUser, Mairie, etc.).
        target_type=target_type,
        # Identifiant cible converti en string pour uniformiser le stockage.
        target_id=str(target_id),
        # Libellé lisible de la cible (username, nom mairie, ...).
        target_label=target_label,
        # Description libre de contexte.
        description=description,
    )


@login_required
def admin_users(request):
    """Gestion applicative des utilisateurs (ADMIN)."""
    # Barrière d'accès: seuls les admins plateforme peuvent gérer les comptes.
    if not _is_platform_admin(request.user):
        messages.error(request, "Accès réservé aux administrateurs.")
        return redirect('naissances:dashboard')

    # Branche création d'utilisateur (submit du formulaire).
    if request.method == 'POST':
        form = CustomUserCreationForm(request.POST)
        if form.is_valid():
            # Création effective du compte.
            created_user = form.save()
            # Journalisation de l'opération pour audit.
            _log_admin_action(
                request.user,
                AdminActionLog.ActionType.CREATE,
                'CustomUser',
                created_user.pk,
                created_user.username,
                f"Creation utilisateur role={created_user.role}",
            )
            messages.success(request, "Utilisateur créé avec succès.")
            # PRG pattern: redirection après POST pour éviter re-soumission du formulaire.
            return redirect('accounts:admin_users')
    else:
        # Branche GET: formulaire vide.
        form = CustomUserCreationForm()

    # Paramètres de recherche/filtres récupérés dans l'URL.
    query = request.GET.get('q', '').strip()
    role_filter = request.GET.get('role', '').strip()
    active_filter = request.GET.get('active', '').strip()
    # Queryset principal avec préchargement des FK pour limiter les requêtes SQL.
    users = CustomUser.objects.select_related('hopital', 'mairie').all().order_by('-date_joined')
    # Filtre texte (username, nom, prénom, email).
    if query:
        users = users.filter(
            Q(username__icontains=query) |
            Q(first_name__icontains=query) |
            Q(last_name__icontains=query) |
            Q(email__icontains=query)
        )
    # Filtre par rôle.
    if role_filter:
        users = users.filter(role=role_filter)
    # Filtre par état actif/inactif (1/0).
    if active_filter in ['0', '1']:
        users = users.filter(is_active=(active_filter == '1'))

    # Pagination de la liste utilisateurs (20 lignes/page).
    paginator = Paginator(users, 20)
    page_obj = paginator.get_page(request.GET.get('page'))

    # Rendu de la page d'admin utilisateurs avec toutes les données d'écran.
    return render(request, 'accounts/admin_users.html', {
        'form': form,
        'users': page_obj,
        'page_obj': page_obj,
        'search': query,
        'role_filter': role_filter,
        'active_filter': active_filter,
        'role_choices': CustomUser.Role.choices,
        'logs': AdminActionLog.objects.select_related('actor')[:20],
    })


@login_required
def admin_mairies(request):
    """Gestion applicative des mairies (ADMIN)."""
    # Contrôle d'accès admin.
    if not _is_platform_admin(request.user):
        messages.error(request, "Accès réservé aux administrateurs.")
        return redirect('naissances:dashboard')

    # Création d'une nouvelle mairie via POST.
    if request.method == 'POST':
        form = MairieCreationForm(request.POST)
        if form.is_valid():
            mairie = form.save()
            # Trace admin.
            _log_admin_action(
                request.user,
                AdminActionLog.ActionType.CREATE,
                'Mairie',
                mairie.pk,
                mairie.nom,
                f"Creation mairie ville={mairie.ville or '-'}",
            )
            messages.success(request, "Mairie ajoutée avec succès.")
            return redirect('accounts:admin_mairies')
    else:
        # Affichage initial du formulaire.
        form = MairieCreationForm()

    # Filtres de liste.
    query = request.GET.get('q', '').strip()
    ville_filter = request.GET.get('ville', '').strip()
    # Liste des mairies triée alphabétiquement.
    mairies = Mairie.objects.all().order_by('nom')
    # Recherche libre.
    if query:
        mairies = mairies.filter(
            Q(nom__icontains=query) |
            Q(ville__icontains=query) |
            Q(contact__icontains=query)
        )
    # Filtre par ville.
    if ville_filter:
        mairies = mairies.filter(ville__icontains=ville_filter)

    # Pagination.
    paginator = Paginator(mairies, 20)
    page_obj = paginator.get_page(request.GET.get('page'))

    return render(request, 'accounts/admin_mairies.html', {
        'form': form,
        'mairies': page_obj,
        'page_obj': page_obj,
        'search': query,
        'ville_filter': ville_filter,
        'logs': AdminActionLog.objects.select_related('actor')[:20],
    })


@login_required
def admin_user_edit(request, pk):
    """Modifier un utilisateur."""
    # Protection admin.
    if not _is_platform_admin(request.user):
        messages.error(request, "Accès réservé aux administrateurs.")
        return redirect('naissances:dashboard')

    # Chargement de l'utilisateur cible.
    target = get_object_or_404(CustomUser, pk=pk)
    # Sauvegarde des modifications.
    if request.method == 'POST':
        form = CustomUserUpdateForm(request.POST, instance=target)
        if form.is_valid():
            form.save()
            # Trace d'audit.
            _log_admin_action(
                request.user,
                AdminActionLog.ActionType.UPDATE,
                'CustomUser',
                target.pk,
                target.username,
                f"Mise a jour utilisateur role={target.role} actif={target.is_active}",
            )
            messages.success(request, "Utilisateur mis à jour.")
            return redirect('accounts:admin_users')
    else:
        # Pré-remplissage du formulaire avec les données existantes.
        form = CustomUserUpdateForm(instance=target)

    return render(request, 'accounts/admin_user_edit.html', {'form': form, 'target': target})


@login_required
def admin_user_toggle_active(request, pk):
    """Activer/désactiver un utilisateur."""
    # Contrôle d'accès admin.
    if not _is_platform_admin(request.user):
        messages.error(request, "Accès réservé aux administrateurs.")
        return redirect('naissances:dashboard')
    # Action uniquement autorisée en POST pour éviter activation par simple lien GET.
    if request.method != 'POST':
        return redirect('accounts:admin_users')

    # Récupération du compte cible.
    target = get_object_or_404(CustomUser, pk=pk)
    # Empêche l'admin de se désactiver lui-même.
    if target == request.user:
        messages.warning(request, "Vous ne pouvez pas désactiver votre propre compte.")
        return redirect('accounts:admin_users')
    # Inversion booléenne de l'état actif.
    target.is_active = not target.is_active
    # Sauvegarde optimisée en ne mettant à jour qu'une seule colonne.
    target.save(update_fields=['is_active'])
    # Journalisation.
    _log_admin_action(
        request.user,
        AdminActionLog.ActionType.TOGGLE,
        'CustomUser',
        target.pk,
        target.username,
        f"Etat actif -> {target.is_active}",
    )
    messages.success(request, f"Compte {'activé' if target.is_active else 'désactivé'} pour {target.username}.")
    return redirect('accounts:admin_users')


@login_required
def admin_user_delete(request, pk):
    """Supprimer un utilisateur."""
    # Contrôle d'accès.
    if not _is_platform_admin(request.user):
        messages.error(request, "Accès réservé aux administrateurs.")
        return redirect('naissances:dashboard')
    # Suppression strictement en POST.
    if request.method != 'POST':
        return redirect('accounts:admin_users')

    # Compte ciblé.
    target = get_object_or_404(CustomUser, pk=pk)
    # Sécurité: interdit de supprimer son propre compte.
    if target == request.user:
        messages.warning(request, "Suppression de votre propre compte impossible.")
        return redirect('accounts:admin_users')
    # On garde les infos avant suppression pour journaliser correctement.
    username = target.username
    target_id = target.pk
    # Suppression en base.
    target.delete()
    # Audit.
    _log_admin_action(
        request.user,
        AdminActionLog.ActionType.DELETE,
        'CustomUser',
        target_id,
        username,
        "Suppression utilisateur",
    )
    messages.success(request, f"Utilisateur {username} supprimé.")
    return redirect('accounts:admin_users')


@login_required
def admin_mairie_edit(request, pk):
    """Modifier une mairie."""
    # Contrôle d'accès admin.
    if not _is_platform_admin(request.user):
        messages.error(request, "Accès réservé aux administrateurs.")
        return redirect('naissances:dashboard')

    # Chargement de l'entité à modifier.
    mairie = get_object_or_404(Mairie, pk=pk)
    # Branche sauvegarde.
    if request.method == 'POST':
        form = MairieUpdateForm(request.POST, instance=mairie)
        if form.is_valid():
            form.save()
            # Trace admin.
            _log_admin_action(
                request.user,
                AdminActionLog.ActionType.UPDATE,
                'Mairie',
                mairie.pk,
                mairie.nom,
                f"Mise a jour mairie ville={mairie.ville or '-'}",
            )
            messages.success(request, "Mairie mise à jour.")
            return redirect('accounts:admin_mairies')
    else:
        # Branche affichage formulaire pré-rempli.
        form = MairieUpdateForm(instance=mairie)
    return render(request, 'accounts/admin_mairie_edit.html', {'form': form, 'mairie': mairie})


@login_required
def admin_mairie_delete(request, pk):
    """Supprimer une mairie."""
    if not _is_platform_admin(request.user):
        messages.error(request, "Accès réservé aux administrateurs.")
        return redirect('naissances:dashboard')
    if request.method != 'POST':
        return redirect('accounts:admin_mairies')

    mairie = get_object_or_404(Mairie, pk=pk)
    if mairie.declarations.exists() or mairie.declarations_deces.exists() or mairie.declarations_mariage.exists():
        messages.warning(request, "Suppression impossible: cette mairie est liée à des dossiers.")
        return redirect('accounts:admin_mairies')
    nom = mairie.nom
    mairie_id = mairie.pk
    mairie.delete()
    _log_admin_action(
        request.user,
        AdminActionLog.ActionType.DELETE,
        'Mairie',
        mairie_id,
        nom,
        "Suppression mairie",
    )
    messages.success(request, f"Mairie {nom} supprimée.")
    return redirect('accounts:admin_mairies')
