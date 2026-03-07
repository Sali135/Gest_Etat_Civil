"""
Domain models for Gest_EtatCivil.
"""
# Génération d'identifiants pseudo-aléatoires pour références métiers.
import uuid
# Délais métier (date d'échéance calculée).
from datetime import timedelta
# Erreurs de validation applicatives (remontées par clean()).
from django.core.exceptions import ValidationError
# ORM Django.
from django.db import models
# Expressions ORM pour contraintes SQL (F/Q).
from django.db.models import F, Q
# Horodatage timezone-aware.
from django.utils import timezone


def _build_unique_act_number(model_cls, prefix, random_size=8, max_attempts=5):
    """Generate a unique act number with bounded collision retries."""
    year = timezone.now().year
    for _ in range(max_attempts):
        candidate = f"{prefix}-{year}-{uuid.uuid4().hex[:random_size].upper()}"
        if not model_cls.objects.filter(numero_acte=candidate).exists():
            return candidate
    return f"{prefix}-{year}-{uuid.uuid4().hex[:12].upper()}"


class _ActeNumberMixin:
    """Shared number assignment logic for acte models."""
    ACT_NUMBER_PREFIX = ''
    ACT_NUMBER_RANDOM_SIZE = 8
    ACT_NUMBER_MAX_ATTEMPTS = 5

    def _ensure_numero_acte(self):
        if self.numero_acte:
            return
        self.numero_acte = _build_unique_act_number(
            type(self),
            prefix=self.ACT_NUMBER_PREFIX,
            random_size=self.ACT_NUMBER_RANDOM_SIZE,
            max_attempts=self.ACT_NUMBER_MAX_ATTEMPTS,
        )


class Hopital(models.Model):
    """Etablissement hospitalier enregistrant les naissances."""
    nom = models.CharField(max_length=200, verbose_name="Nom de l'hopital")
    adresse = models.TextField(verbose_name='Adresse')
    contact = models.CharField(max_length=50, verbose_name='Contact / Telephone')
    code = models.CharField(max_length=20, unique=True, verbose_name='Code unique', blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = 'Hopital'
        verbose_name_plural = 'Hopitaux'
        ordering = ['nom']

    def __str__(self):
        return self.nom

    def save(self, *args, **kwargs):
        # Génère automatiquement un code unique lisible si absent.
        if not self.code:
            self.code = f"HOP-{uuid.uuid4().hex[:6].upper()}"
        super().save(*args, **kwargs)


class Mairie(models.Model):
    """Mairie / Commune recevant et validant les declarations."""
    nom = models.CharField(max_length=200, verbose_name='Nom de la mairie')
    adresse = models.TextField(verbose_name='Adresse')
    contact = models.CharField(max_length=50, verbose_name='Contact / Telephone')
    ville = models.CharField(max_length=100, verbose_name='Ville / Commune', blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = 'Mairie'
        verbose_name_plural = 'Mairies'
        ordering = ['nom']

    def __str__(self):
        return self.nom


class DeclarationNaissance(models.Model):
    class Statut(models.TextChoices):
        EN_ATTENTE = 'EN_ATTENTE', 'En attente'
        EN_VERIFICATION = 'EN_VERIFICATION', 'En verification'
        VALIDE = 'VALIDE', 'Valide'
        REJETE = 'REJETE', 'Rejete'

    reference = models.CharField(max_length=20, unique=True, verbose_name='Reference dossier', blank=True)

    nom_enfant = models.CharField(max_length=100, verbose_name="Nom de l'enfant")
    prenom_enfant = models.CharField(max_length=100, verbose_name="Prenom de l'enfant", blank=True)
    date_naissance = models.DateField(verbose_name='Date de naissance')
    heure_naissance = models.TimeField(verbose_name='Heure de naissance', null=True, blank=True)
    lieu_naissance = models.CharField(max_length=200, verbose_name='Lieu de naissance')
    sexe = models.CharField(max_length=1, choices=[('M', 'Masculin'), ('F', 'Feminin')], verbose_name='Sexe')

    nom_pere = models.CharField(max_length=150, verbose_name='Nom complet du pere')
    date_naissance_pere = models.DateField(verbose_name='Date de naissance du pere', null=True, blank=True)
    nationalite_pere = models.CharField(max_length=100, verbose_name='Nationalite du pere', blank=True)
    profession_pere = models.CharField(max_length=100, verbose_name='Profession du pere', blank=True)

    nom_mere = models.CharField(max_length=150, verbose_name='Nom complet de la mere')
    date_naissance_mere = models.DateField(verbose_name='Date de naissance de la mere', null=True, blank=True)
    nationalite_mere = models.CharField(max_length=100, verbose_name='Nationalite de la mere', blank=True)
    profession_mere = models.CharField(max_length=100, verbose_name='Profession de la mere', blank=True)

    email_parents = models.EmailField(verbose_name='Email des parents', blank=True)
    telephone_parents = models.CharField(max_length=20, verbose_name='Telephone des parents', blank=True)

    hopital = models.ForeignKey(Hopital, on_delete=models.PROTECT, related_name='declarations', verbose_name='Hopital declarant')
    mairie = models.ForeignKey(Mairie, on_delete=models.PROTECT, related_name='declarations', verbose_name='Mairie destinataire')

    statut = models.CharField(max_length=20, choices=Statut.choices, default=Statut.EN_ATTENTE, verbose_name='Statut')
    motif_rejet = models.TextField(verbose_name='Motif de rejet', blank=True)
    priorite = models.CharField(max_length=10, choices=[('NORMALE', 'Normale'), ('URGENTE', 'Urgente')], default='NORMALE', verbose_name='Priorite')

    agent_hopital = models.ForeignKey('accounts.CustomUser', on_delete=models.SET_NULL, null=True, blank=True, related_name='declarations_creees', verbose_name='Agent hopital')
    agent_mairie = models.ForeignKey('accounts.CustomUser', on_delete=models.SET_NULL, null=True, blank=True, related_name='declarations_traitees', verbose_name='Agent mairie')

    date_creation = models.DateTimeField(auto_now_add=True, verbose_name='Date de creation')
    date_traitement = models.DateTimeField(null=True, blank=True, verbose_name='Date de traitement')
    date_echeance = models.DateTimeField(null=True, blank=True, verbose_name='Date echeance')

    class Meta:
        verbose_name = 'Declaration de naissance'
        verbose_name_plural = 'Declarations de naissance'
        ordering = ['-date_creation']
        indexes = [
            models.Index(fields=['mairie', 'statut'], name='dn_mairie_statut_idx'),
            models.Index(fields=['hopital', 'statut'], name='dn_hopital_statut_idx'),
            models.Index(fields=['date_creation'], name='dn_date_creation_idx'),
            models.Index(fields=['date_echeance'], name='dn_date_echeance_idx'),
        ]
        constraints = [
            models.CheckConstraint(
                name='dn_pere_before_naissance',
                condition=Q(date_naissance_pere__isnull=True) | Q(date_naissance_pere__lt=F('date_naissance')),
            ),
            models.CheckConstraint(
                name='dn_mere_before_naissance',
                condition=Q(date_naissance_mere__isnull=True) | Q(date_naissance_mere__lt=F('date_naissance')),
            ),
        ]

    def __str__(self):
        return f"[{self.reference}] {self.nom_enfant} - {self.get_statut_display()}"

    def save(self, *args, **kwargs):
        # Référence dossier générée à la création (format métier DN-YYYYMM-XXXXXX).
        if not self.reference:
            self.reference = f"DN-{timezone.now().strftime('%Y%m')}-{uuid.uuid4().hex[:6].upper()}"
        # Date limite par défaut (SLA métier de 5 jours).
        if not self.date_echeance:
            self.date_echeance = timezone.now() + timedelta(days=5)
        super().save(*args, **kwargs)

    def clean(self):
        # Validation métier centralisée (s'applique au formulaire/admin/ORM si full_clean appelé).
        errors = {}
        today = timezone.localdate()
        if self.date_naissance and self.date_naissance > today:
            errors['date_naissance'] = "La date de naissance ne peut pas être dans le futur."
        if self.date_naissance_pere and self.date_naissance and self.date_naissance_pere >= self.date_naissance:
            errors['date_naissance_pere'] = "La date de naissance du père doit être antérieure à celle de l'enfant."
        if self.date_naissance_mere and self.date_naissance and self.date_naissance_mere >= self.date_naissance:
            errors['date_naissance_mere'] = "La date de naissance de la mère doit être antérieure à celle de l'enfant."
        if errors:
            raise ValidationError(errors)

    @property
    def nom_complet_enfant(self):
        return f"{self.prenom_enfant} {self.nom_enfant}".strip()


class ActeNaissance(_ActeNumberMixin, models.Model):
    ACT_NUMBER_PREFIX = 'ACT'
    declaration = models.OneToOneField(DeclarationNaissance, on_delete=models.CASCADE, related_name='acte', verbose_name='Declaration associee')
    numero_acte = models.CharField(max_length=30, unique=True, verbose_name="Numero d'acte")
    date_generation = models.DateTimeField(auto_now_add=True, verbose_name='Date de generation')
    fichier_pdf = models.FileField(upload_to='actes_naissance/', null=True, blank=True, verbose_name='Fichier PDF')

    class Meta:
        verbose_name = 'Acte de naissance'
        verbose_name_plural = 'Actes de naissance'
        ordering = ['-date_generation']

    def __str__(self):
        return f"Acte N{self.numero_acte} - {self.declaration.nom_complet_enfant}"

    def save(self, *args, **kwargs):
        self._ensure_numero_acte()
        super().save(*args, **kwargs)


class DeclarationMariage(models.Model):
    class Statut(models.TextChoices):
        EN_ATTENTE = 'EN_ATTENTE', 'En attente'
        EN_VERIFICATION = 'EN_VERIFICATION', 'En verification'
        VALIDE = 'VALIDE', 'Valide'
        REJETE = 'REJETE', 'Rejete'

    reference = models.CharField(max_length=20, unique=True, verbose_name='Reference dossier', blank=True)
    nom_epoux = models.CharField(max_length=150, verbose_name="Nom complet de l'epoux")
    nom_epouse = models.CharField(max_length=150, verbose_name="Nom complet de l'epouse")
    date_naissance_epoux = models.DateField(verbose_name="Date de naissance de l'epoux", null=True, blank=True)
    date_naissance_epouse = models.DateField(verbose_name="Date de naissance de l'epouse", null=True, blank=True)
    profession_epoux = models.CharField(max_length=100, verbose_name="Profession de l'epoux", blank=True)
    profession_epouse = models.CharField(max_length=100, verbose_name="Profession de l'epouse", blank=True)
    email_contact = models.EmailField(verbose_name='Email de contact (epoux/epouse)', blank=True)
    date_mariage = models.DateField(verbose_name='Date du mariage')
    lieu_mariage = models.CharField(max_length=200, verbose_name='Lieu du mariage')
    temoins = models.TextField(verbose_name='Temoins', blank=True)
    statut = models.CharField(max_length=20, choices=Statut.choices, default=Statut.EN_ATTENTE, verbose_name='Statut')
    motif_rejet = models.TextField(verbose_name='Motif de rejet', blank=True)
    priorite = models.CharField(max_length=10, choices=[('NORMALE', 'Normale'), ('URGENTE', 'Urgente')], default='NORMALE', verbose_name='Priorite')

    mairie = models.ForeignKey(Mairie, on_delete=models.PROTECT, related_name='declarations_mariage', verbose_name='Mairie')
    agent_mairie = models.ForeignKey('accounts.CustomUser', on_delete=models.SET_NULL, null=True, blank=True, related_name='mariages_enregistres', verbose_name='Agent mairie (traitement)')
    date_creation = models.DateTimeField(auto_now_add=True, verbose_name='Date de creation')
    date_traitement = models.DateTimeField(null=True, blank=True, verbose_name='Date de traitement')
    date_echeance = models.DateTimeField(null=True, blank=True, verbose_name='Date echeance')

    class Meta:
        verbose_name = 'Declaration de mariage'
        verbose_name_plural = 'Declarations de mariage'
        ordering = ['-date_creation']
        indexes = [
            models.Index(fields=['mairie', 'statut'], name='dm_mairie_statut_idx'),
            models.Index(fields=['date_creation'], name='dm_date_creation_idx'),
            models.Index(fields=['date_echeance'], name='dm_date_echeance_idx'),
        ]
        constraints = [
            models.CheckConstraint(
                name='dm_epoux_before_mariage',
                condition=Q(date_naissance_epoux__isnull=True) | Q(date_naissance_epoux__lt=F('date_mariage')),
            ),
            models.CheckConstraint(
                name='dm_epouse_before_mariage',
                condition=Q(date_naissance_epouse__isnull=True) | Q(date_naissance_epouse__lt=F('date_mariage')),
            ),
        ]

    def __str__(self):
        return f"[{self.reference}] {self.nom_epoux} & {self.nom_epouse}"

    def save(self, *args, **kwargs):
        # Référence dossier mariage auto-générée.
        if not self.reference:
            self.reference = f"DM-{timezone.now().strftime('%Y%m')}-{uuid.uuid4().hex[:6].upper()}"
        # SLA métier de traitement mariage (10 jours).
        if not self.date_echeance:
            self.date_echeance = timezone.now() + timedelta(days=10)
        super().save(*args, **kwargs)

    def clean(self):
        # Cohérence temporelle du dossier mariage.
        errors = {}
        today = timezone.localdate()
        if self.date_mariage and self.date_mariage > today:
            errors['date_mariage'] = "La date du mariage ne peut pas être dans le futur."
        if self.date_naissance_epoux and self.date_mariage and self.date_naissance_epoux >= self.date_mariage:
            errors['date_naissance_epoux'] = "La date de naissance de l'époux doit être antérieure à la date du mariage."
        if self.date_naissance_epouse and self.date_mariage and self.date_naissance_epouse >= self.date_mariage:
            errors['date_naissance_epouse'] = "La date de naissance de l'épouse doit être antérieure à la date du mariage."
        if errors:
            raise ValidationError(errors)


class ActeMariage(_ActeNumberMixin, models.Model):
    ACT_NUMBER_PREFIX = 'ACTM'
    declaration = models.OneToOneField(DeclarationMariage, on_delete=models.CASCADE, related_name='acte', verbose_name='Declaration associee')
    numero_acte = models.CharField(max_length=30, unique=True, verbose_name="Numero d'acte")
    date_generation = models.DateTimeField(auto_now_add=True, verbose_name='Date de generation')
    fichier_pdf = models.FileField(upload_to='actes_mariage/', null=True, blank=True, verbose_name='Fichier PDF')

    class Meta:
        verbose_name = 'Acte de mariage'
        verbose_name_plural = 'Actes de mariage'
        ordering = ['-date_generation']

    def __str__(self):
        return f"Acte mariage N{self.numero_acte}"

    def save(self, *args, **kwargs):
        self._ensure_numero_acte()
        super().save(*args, **kwargs)


class DeclarationDeces(models.Model):
    class Statut(models.TextChoices):
        EN_ATTENTE = 'EN_ATTENTE', 'En attente'
        EN_VERIFICATION = 'EN_VERIFICATION', 'En verification'
        VALIDE = 'VALIDE', 'Valide'
        REJETE = 'REJETE', 'Rejete'

    reference = models.CharField(max_length=20, unique=True, verbose_name='Reference dossier', blank=True)
    nom_defunt = models.CharField(max_length=100, verbose_name='Nom du defunt')
    prenom_defunt = models.CharField(max_length=100, verbose_name='Prenom du defunt', blank=True)
    sexe = models.CharField(max_length=1, choices=[('M', 'Masculin'), ('F', 'Feminin')], verbose_name='Sexe')
    date_naissance = models.DateField(verbose_name='Date de naissance', null=True, blank=True)
    date_deces = models.DateField(verbose_name='Date du deces')
    lieu_deces = models.CharField(max_length=200, verbose_name='Lieu du deces')
    cause_deces = models.CharField(max_length=200, verbose_name='Cause du deces', blank=True)
    declarant_nom = models.CharField(max_length=150, verbose_name='Nom du declarant')
    declarant_lien = models.CharField(max_length=100, verbose_name='Lien avec le defunt', blank=True)
    email_contact = models.EmailField(verbose_name='Email de contact du declarant', blank=True)
    statut = models.CharField(max_length=20, choices=Statut.choices, default=Statut.EN_ATTENTE, verbose_name='Statut')
    motif_rejet = models.TextField(verbose_name='Motif de rejet', blank=True)
    priorite = models.CharField(max_length=10, choices=[('NORMALE', 'Normale'), ('URGENTE', 'Urgente')], default='NORMALE', verbose_name='Priorite')

    hopital = models.ForeignKey(Hopital, on_delete=models.PROTECT, related_name='declarations_deces', verbose_name='Hopital declarant', null=True, blank=True)
    mairie = models.ForeignKey(Mairie, on_delete=models.PROTECT, related_name='declarations_deces', verbose_name='Mairie')
    agent_createur = models.ForeignKey('accounts.CustomUser', on_delete=models.SET_NULL, null=True, blank=True, related_name='deces_enregistres', verbose_name='Agent declarant')
    agent_traitement = models.ForeignKey('accounts.CustomUser', on_delete=models.SET_NULL, null=True, blank=True, related_name='deces_traites', verbose_name='Agent mairie (traitement)')
    date_creation = models.DateTimeField(auto_now_add=True, verbose_name='Date de creation')
    date_traitement = models.DateTimeField(null=True, blank=True, verbose_name='Date de traitement')
    date_echeance = models.DateTimeField(null=True, blank=True, verbose_name='Date echeance')

    class Meta:
        verbose_name = 'Declaration de deces'
        verbose_name_plural = 'Declarations de deces'
        ordering = ['-date_creation']
        indexes = [
            models.Index(fields=['mairie', 'statut'], name='dd_mairie_statut_idx'),
            models.Index(fields=['hopital', 'statut'], name='dd_hopital_statut_idx'),
            models.Index(fields=['date_creation'], name='dd_date_creation_idx'),
            models.Index(fields=['date_echeance'], name='dd_date_echeance_idx'),
        ]
        constraints = [
            models.CheckConstraint(
                name='dd_birth_before_death',
                condition=Q(date_naissance__isnull=True) | Q(date_naissance__lte=F('date_deces')),
            ),
        ]

    def __str__(self):
        return f"[{self.reference}] {self.nom_complet_defunt}"

    def save(self, *args, **kwargs):
        # Référence dossier décès auto-générée.
        if not self.reference:
            self.reference = f"DD-{timezone.now().strftime('%Y%m')}-{uuid.uuid4().hex[:6].upper()}"
        # SLA décès plus court (3 jours).
        if not self.date_echeance:
            self.date_echeance = timezone.now() + timedelta(days=3)
        super().save(*args, **kwargs)

    def clean(self):
        # Cohérence des dates naissance/décès.
        errors = {}
        today = timezone.localdate()
        if self.date_deces and self.date_deces > today:
            errors['date_deces'] = "La date du décès ne peut pas être dans le futur."
        if self.date_naissance and self.date_deces and self.date_naissance > self.date_deces:
            errors['date_naissance'] = "La date de naissance doit être antérieure ou égale à la date du décès."
        if errors:
            raise ValidationError(errors)

    @property
    def nom_complet_defunt(self):
        return f"{self.prenom_defunt} {self.nom_defunt}".strip()


class ActeDeces(_ActeNumberMixin, models.Model):
    ACT_NUMBER_PREFIX = 'ACTD'
    declaration = models.OneToOneField(DeclarationDeces, on_delete=models.CASCADE, related_name='acte', verbose_name='Declaration associee')
    numero_acte = models.CharField(max_length=30, unique=True, verbose_name="Numero d'acte")
    date_generation = models.DateTimeField(auto_now_add=True, verbose_name='Date de generation')
    fichier_pdf = models.FileField(upload_to='actes_deces/', null=True, blank=True, verbose_name='Fichier PDF')

    class Meta:
        verbose_name = 'Acte de deces'
        verbose_name_plural = 'Actes de deces'
        ordering = ['-date_generation']

    def __str__(self):
        return f"Acte deces N{self.numero_acte}"

    def save(self, *args, **kwargs):
        self._ensure_numero_acte()
        super().save(*args, **kwargs)


class HistoriqueNaissance(models.Model):
    declaration = models.ForeignKey(DeclarationNaissance, on_delete=models.CASCADE, related_name='historique')
    action = models.CharField(max_length=50)
    statut_avant = models.CharField(max_length=20, blank=True)
    statut_apres = models.CharField(max_length=20, blank=True)
    commentaire = models.TextField(blank=True)
    utilisateur = models.ForeignKey('accounts.CustomUser', null=True, blank=True, on_delete=models.SET_NULL)
    date_action = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-date_action']


class HistoriqueMariage(models.Model):
    declaration = models.ForeignKey(DeclarationMariage, on_delete=models.CASCADE, related_name='historique')
    action = models.CharField(max_length=50)
    statut_avant = models.CharField(max_length=20, blank=True)
    statut_apres = models.CharField(max_length=20, blank=True)
    commentaire = models.TextField(blank=True)
    utilisateur = models.ForeignKey('accounts.CustomUser', null=True, blank=True, on_delete=models.SET_NULL)
    date_action = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-date_action']


class HistoriqueDeces(models.Model):
    declaration = models.ForeignKey(DeclarationDeces, on_delete=models.CASCADE, related_name='historique')
    action = models.CharField(max_length=50)
    statut_avant = models.CharField(max_length=20, blank=True)
    statut_apres = models.CharField(max_length=20, blank=True)
    commentaire = models.TextField(blank=True)
    utilisateur = models.ForeignKey('accounts.CustomUser', null=True, blank=True, on_delete=models.SET_NULL)
    date_action = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-date_action']
