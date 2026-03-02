"""Admin configuration for accounts app."""
# API admin Django.
from django.contrib import admin
# Admin utilisateur natif (base à étendre pour CustomUser).
from django.contrib.auth.admin import UserAdmin
# Modèles enregistrés dans le back-office.
from .models import CustomUser, AdminActionLog


@admin.register(CustomUser)
class CustomUserAdmin(UserAdmin):
    """Admin interface for CustomUser."""
    # Colonnes visibles dans la liste utilisateurs.
    list_display = ('username', 'email', 'first_name', 'last_name', 'role', 'hopital', 'mairie', 'is_active')
    # Filtres latéraux rapides.
    list_filter = ('role', 'is_active', 'is_staff')
    # Recherche textuelle.
    search_fields = ('username', 'email', 'first_name', 'last_name')
    # Tri par défaut.
    ordering = ('username',)

    # Ajoute nos champs métier dans l'écran d'édition.
    fieldsets = UserAdmin.fieldsets + (
        ('Rôle & Établissement', {
            'fields': ('role', 'hopital', 'mairie'),
        }),
    )
    # Ajoute nos champs métier dans l'écran de création.
    add_fieldsets = UserAdmin.add_fieldsets + (
        ('Rôle & Établissement', {
            'fields': ('role', 'hopital', 'mairie'),
        }),
    )


@admin.register(AdminActionLog)
class AdminActionLogAdmin(admin.ModelAdmin):
    # Colonnes du journal d'audit.
    list_display = ('created_at', 'actor', 'action_type', 'target_type', 'target_id', 'target_label')
    # Filtres disponibles.
    list_filter = ('action_type', 'target_type', 'created_at')
    # Recherche plein texte ciblée.
    search_fields = ('actor__username', 'target_label', 'target_id', 'description')
    # Empêche la modification du log depuis l'admin (audit immuable).
    readonly_fields = ('created_at', 'actor', 'action_type', 'target_type', 'target_id', 'target_label', 'description')
