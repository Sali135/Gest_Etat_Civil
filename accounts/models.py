"""
Custom User Model for Gest_EtatCivil.
Extends AbstractUser with role-based access control.
"""
# Base utilisateur Django (username, password hashé, permissions, etc.).
from django.contrib.auth.models import AbstractUser
# API ORM de Django pour définir les champs/base de données.
from django.db import models


class CustomUser(AbstractUser):
    """Utilisateur personnalisé avec gestion des rôles."""

    class Role(models.TextChoices):
        HOPITAL = 'HOPITAL', 'Agent Hôpital'
        MAIRIE = 'MAIRIE', 'Agent Mairie'
        ADMIN = 'ADMIN', 'Administrateur'

    # Rôle métier principal de l'utilisateur (utilisé dans les contrôles d'accès applicatifs).
    role = models.CharField(
        max_length=10,
        choices=Role.choices,
        default=Role.HOPITAL,
        verbose_name='Rôle'
    )

    # Lien optionnel vers l'établissement
    # Référence vers l'hôpital de rattachement (nullable pour les admins globaux).
    hopital = models.ForeignKey(
        'naissances.Hopital',
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='agents',
        verbose_name='Hôpital associé'
    )
    # Référence vers la mairie de rattachement (nullable pour les admins globaux).
    mairie = models.ForeignKey(
        'naissances.Mairie',
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='agents',
        verbose_name='Mairie associée'
    )

    class Meta:
        verbose_name = 'Utilisateur'
        verbose_name_plural = 'Utilisateurs'

    def __str__(self):
        # Représentation lisible dans l'admin/Django shell.
        return f"{self.get_full_name() or self.username} ({self.get_role_display()})"

    def save(self, *args, **kwargs):
        # Le rôle ADMIN doit pouvoir administrer toute la plateforme via /admin/.
        # On élève automatiquement les flags Django natifs pour éviter les incohérences.
        if self.role == self.Role.ADMIN:
            self.is_staff = True
            self.is_superuser = True
        super().save(*args, **kwargs)

    @property
    def is_hopital_agent(self):
        # Helper booléen pour simplifier la lecture des permissions dans le code.
        return self.role == self.Role.HOPITAL

    @property
    def is_mairie_agent(self):
        # Helper booléen: utilisateur de type mairie.
        return self.role == self.Role.MAIRIE

    @property
    def is_admin_user(self):
        # Helper booléen: admin métier OU superuser Django.
        return self.role == self.Role.ADMIN or self.is_superuser


class AdminActionLog(models.Model):
    """Journal des actions d'administration de la plateforme."""

    class ActionType(models.TextChoices):
        CREATE = 'CREATE', 'Creation'
        UPDATE = 'UPDATE', 'Modification'
        DELETE = 'DELETE', 'Suppression'
        TOGGLE = 'TOGGLE', 'Activation/Desactivation'

    # Admin qui a exécuté l'action (nullable si action système).
    actor = models.ForeignKey(
        CustomUser,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='admin_actions',
        verbose_name='Administrateur',
    )
    # Type d'action réalisée (création, modification, suppression, etc.).
    action_type = models.CharField(max_length=10, choices=ActionType.choices, verbose_name='Type')
    # Type métier de la cible affectée.
    target_type = models.CharField(max_length=50, verbose_name='Type de cible')
    # Identifiant de la cible (string pour supporter plusieurs formats d'ID).
    target_id = models.CharField(max_length=64, verbose_name='Identifiant cible')
    # Libellé humain de la cible (username, nom de mairie, etc.).
    target_label = models.CharField(max_length=255, verbose_name='Libelle cible')
    # Détails contextuels supplémentaires.
    description = models.TextField(blank=True, verbose_name='Description')
    # Date/heure de traçabilité.
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='Date action')

    class Meta:
        verbose_name = 'Journal admin'
        verbose_name_plural = 'Journaux admin'
        ordering = ['-created_at']

    def __str__(self):
        # Représentation synthétique pour lecture rapide dans l'admin.
        return f"{self.get_action_type_display()} - {self.target_type} ({self.target_label})"
