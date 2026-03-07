"""API views for naissances app using Django REST Framework."""
# Gestion de transactions atomiques pour garantir la cohérence lors des validations/rejets.
from django.db import transaction
# Outil de dates timezone-aware.
from django.utils import timezone
# Vues génériques DRF + permissions.
from rest_framework import generics, permissions
# Exceptions API explicites (403 et 400).
from rest_framework.exceptions import PermissionDenied, ValidationError
# Réponses JSON DRF.
from rest_framework.response import Response
# Vue API de base quand on veut un contrôle total.
from rest_framework.views import APIView

from .models import (
    DeclarationNaissance, Hopital, Mairie,
    DeclarationMariage, ActeMariage, DeclarationDeces, ActeDeces,
)
from .serializers import (
    DeclarationNaissanceSerializer,
    DeclarationCreateSerializer,
    HopitalSerializer,
    MairieSerializer,
    DeclarationMariageSerializer,
    DeclarationMariageCreateSerializer,
    DeclarationDecesSerializer,
    DeclarationDecesCreateSerializer,
)


class IsHopitalAgent(permissions.BasePermission):
    """Permission: utilisateur authentifié et rattaché au rôle HOPITAL (ou superuser)."""
    def has_permission(self, request, view):
        return request.user.is_authenticated and (
            request.user.role == 'HOPITAL' or request.user.is_superuser
        )


class IsMairieAgent(permissions.BasePermission):
    """Permission: utilisateur authentifié et rattaché au rôle MAIRIE (ou superuser)."""
    def has_permission(self, request, view):
        return request.user.is_authenticated and (
            request.user.role == 'MAIRIE' or request.user.is_superuser
        )


class IsAdminRole(permissions.BasePermission):
    """Allow access to users with admin role, staff, or superuser."""

    def has_permission(self, request, view):
        user = request.user
        return (
            user.is_authenticated and
            (user.is_superuser or user.is_staff or getattr(user, 'role', None) == 'ADMIN')
        )


class IsMairieOrAdmin(permissions.BasePermission):
    """Permission: réservé mairie/admin/superuser pour les actions de traitement."""
    def has_permission(self, request, view):
        user = request.user
        return user.is_authenticated and (user.is_superuser or user.role in ['MAIRIE', 'ADMIN'])


def _api_validate_declaration_and_generate_acte(
    request,
    *,
    declaration_model,
    acte_model,
    serializer_class,
    pk,
    agent_field,
):
    """
    Shared API validation flow:
    - lock declaration row
    - validate permissions/status
    - set declaration to VALIDE
    - generate acte idempotently
    - return serialized declaration
    """
    declaration = generics.get_object_or_404(
        declaration_model.objects.select_for_update(),
        pk=pk,
    )

    if request.user.role == 'MAIRIE' and declaration.mairie != request.user.mairie:
        raise PermissionDenied("Vous ne pouvez pas traiter cette déclaration.")

    if declaration.statut not in [
        declaration_model.Statut.EN_ATTENTE,
        declaration_model.Statut.EN_VERIFICATION,
    ]:
        raise ValidationError("Cette déclaration a déjà été traitée.")

    declaration.statut = declaration_model.Statut.VALIDE
    declaration.motif_rejet = ''
    setattr(declaration, agent_field, request.user)
    declaration.date_traitement = timezone.now()
    declaration.save(update_fields=['statut', 'motif_rejet', agent_field, 'date_traitement'])

    acte_model.objects.get_or_create(declaration=declaration)
    return Response(serializer_class(declaration).data)


class DeclarationListCreateAPIView(generics.ListCreateAPIView):
    """Naissances: list and create."""
    # Auth obligatoire pour tout appel à cet endpoint.
    permission_classes = [permissions.IsAuthenticated]

    def get_serializer_class(self):
        # On utilise un serializer de création restreint en POST, et un serializer de lecture en GET.
        if self.request.method == 'POST':
            return DeclarationCreateSerializer
        return DeclarationNaissanceSerializer

    def get_queryset(self):
        # Le queryset est filtré par rôle pour éviter l'accès inter-établissements.
        user = self.request.user
        qs = DeclarationNaissance.objects.select_related('hopital', 'mairie')

        if user.role == 'HOPITAL' and user.hopital:
            qs = qs.filter(hopital=user.hopital)
        elif user.role == 'MAIRIE' and user.mairie:
            qs = qs.filter(mairie=user.mairie)
        elif not user.is_superuser:
            return qs.none()

        statut = self.request.query_params.get('statut')
        if statut:
            # Filtre optionnel par statut via query param ?statut=...
            qs = qs.filter(statut=statut)
        return qs

    def perform_create(self, serializer):
        # Création autorisée uniquement pour les agents hôpital.
        user = self.request.user
        if user.role != 'HOPITAL' or not user.hopital:
            raise PermissionDenied("Seuls les agents d'hôpital peuvent créer des déclarations.")
        # Le backend force l'hôpital et l'agent créateur (ne fait pas confiance au payload client).
        serializer.save(hopital=user.hopital, agent_hopital=user)


class DeclarationDetailAPIView(generics.RetrieveAPIView):
    """Naissances: detail."""
    serializer_class = DeclarationNaissanceSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        # Filtrage strict du détail selon le périmètre utilisateur.
        user = self.request.user
        qs = DeclarationNaissance.objects.select_related('hopital', 'mairie')
        if user.role == 'HOPITAL' and user.hopital:
            return qs.filter(hopital=user.hopital)
        if user.role == 'MAIRIE' and user.mairie:
            return qs.filter(mairie=user.mairie)
        if user.is_superuser or user.role == 'ADMIN':
            return qs
        return qs.none()


class MariageListCreateAPIView(generics.ListCreateAPIView):
    """Mariages: list and create."""
    permission_classes = [permissions.IsAuthenticated]

    def get_serializer_class(self):
        # Distinction serializer lecture vs écriture.
        if self.request.method == 'POST':
            return DeclarationMariageCreateSerializer
        return DeclarationMariageSerializer

    def get_queryset(self):
        # Les agents mairie ne voient que leur mairie.
        user = self.request.user
        qs = DeclarationMariage.objects.select_related('mairie', 'agent_mairie')
        if user.role == 'MAIRIE' and user.mairie:
            qs = qs.filter(mairie=user.mairie)
        elif not (user.is_superuser or user.role == 'ADMIN'):
            return qs.none()
        statut = self.request.query_params.get('statut')
        if statut:
            qs = qs.filter(statut=statut)
        return qs

    def perform_create(self, serializer):
        # Contrôle de permission métier.
        user = self.request.user
        if not (user.is_superuser or user.role in ['MAIRIE', 'ADMIN']):
            raise PermissionDenied("Seuls les agents mairie/admin peuvent créer un mariage.")
        # En mairie, on impose la mairie rattachée à l'utilisateur.
        if user.role == 'MAIRIE' and user.mairie:
            serializer.save(mairie=user.mairie)
        else:
            serializer.save()


class MariageDetailAPIView(generics.RetrieveAPIView):
    serializer_class = DeclarationMariageSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        user = self.request.user
        qs = DeclarationMariage.objects.select_related('mairie', 'agent_mairie')
        if user.role == 'MAIRIE' and user.mairie:
            return qs.filter(mairie=user.mairie)
        if user.is_superuser or user.role == 'ADMIN':
            return qs
        return qs.none()


class MariageValiderAPIView(APIView):
    # Endpoint de transition de statut.
    permission_classes = [IsMairieOrAdmin]

    @transaction.atomic
    def post(self, request, pk):
        return _api_validate_declaration_and_generate_acte(
            request,
            declaration_model=DeclarationMariage,
            acte_model=ActeMariage,
            serializer_class=DeclarationMariageSerializer,
            pk=pk,
            agent_field='agent_mairie',
        )


class MariageRejeterAPIView(APIView):
    permission_classes = [IsMairieOrAdmin]

    @transaction.atomic
    def post(self, request, pk):
        # Même logique de verrouillage que pour la validation.
        declaration = generics.get_object_or_404(DeclarationMariage.objects.select_for_update(), pk=pk)
        if request.user.role == 'MAIRIE' and declaration.mairie != request.user.mairie:
            raise PermissionDenied("Vous ne pouvez pas traiter cette déclaration.")
        if declaration.statut not in [DeclarationMariage.Statut.EN_ATTENTE, DeclarationMariage.Statut.EN_VERIFICATION]:
            raise ValidationError("Cette déclaration a déjà été traitée.")
        motif = (request.data.get('motif_rejet') or '').strip()
        # Validation métier minimale sur le motif.
        if len(motif) < 10:
            raise ValidationError("Le motif de rejet doit contenir au moins 10 caractères.")
        declaration.statut = DeclarationMariage.Statut.REJETE
        declaration.motif_rejet = motif
        declaration.agent_mairie = request.user
        declaration.date_traitement = timezone.now()
        declaration.save()
        return Response(DeclarationMariageSerializer(declaration).data)


class DecesListCreateAPIView(generics.ListCreateAPIView):
    """Décès: list and create."""
    permission_classes = [permissions.IsAuthenticated]

    def get_serializer_class(self):
        # Serializer d'entrée différent du serializer de sortie.
        if self.request.method == 'POST':
            return DeclarationDecesCreateSerializer
        return DeclarationDecesSerializer

    def get_queryset(self):
        # Filtre multi-rôle (hôpital/mairie/admin).
        user = self.request.user
        qs = DeclarationDeces.objects.select_related('hopital', 'mairie', 'agent_createur')
        if user.role == 'HOPITAL' and user.hopital:
            qs = qs.filter(hopital=user.hopital)
        elif user.role == 'MAIRIE' and user.mairie:
            qs = qs.filter(mairie=user.mairie)
        elif not (user.is_superuser or user.role == 'ADMIN'):
            return qs.none()
        statut = self.request.query_params.get('statut')
        if statut:
            qs = qs.filter(statut=statut)
        return qs

    def perform_create(self, serializer):
        # Autorisations métier de création décès.
        user = self.request.user
        if not (user.is_superuser or user.role in ['HOPITAL', 'MAIRIE', 'ADMIN']):
            raise PermissionDenied("Vous ne pouvez pas créer de déclaration de décès.")
        # Affectation automatique des entités en fonction du rôle appelant.
        if user.role == 'HOPITAL':
            serializer.save(hopital=user.hopital, agent_createur=user)
        elif user.role == 'MAIRIE':
            serializer.save(mairie=user.mairie, agent_createur=user)
        else:
            serializer.save(agent_createur=user)


class DecesDetailAPIView(generics.RetrieveAPIView):
    serializer_class = DeclarationDecesSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        user = self.request.user
        qs = DeclarationDeces.objects.select_related('hopital', 'mairie', 'agent_createur')
        if user.role == 'HOPITAL' and user.hopital:
            return qs.filter(hopital=user.hopital)
        if user.role == 'MAIRIE' and user.mairie:
            return qs.filter(mairie=user.mairie)
        if user.is_superuser or user.role == 'ADMIN':
            return qs
        return qs.none()


class DecesValiderAPIView(APIView):
    permission_classes = [IsMairieOrAdmin]

    @transaction.atomic
    def post(self, request, pk):
        return _api_validate_declaration_and_generate_acte(
            request,
            declaration_model=DeclarationDeces,
            acte_model=ActeDeces,
            serializer_class=DeclarationDecesSerializer,
            pk=pk,
            agent_field='agent_traitement',
        )


class DecesRejeterAPIView(APIView):
    permission_classes = [IsMairieOrAdmin]

    @transaction.atomic
    def post(self, request, pk):
        # Verrouillage transactionnel pour garantir une seule issue de traitement.
        declaration = generics.get_object_or_404(DeclarationDeces.objects.select_for_update(), pk=pk)
        if request.user.role == 'MAIRIE' and declaration.mairie != request.user.mairie:
            raise PermissionDenied("Vous ne pouvez pas traiter cette déclaration.")
        if declaration.statut not in [DeclarationDeces.Statut.EN_ATTENTE, DeclarationDeces.Statut.EN_VERIFICATION]:
            raise ValidationError("Cette déclaration a déjà été traitée.")
        motif = (request.data.get('motif_rejet') or '').strip()
        if len(motif) < 10:
            raise ValidationError("Le motif de rejet doit contenir au moins 10 caractères.")
        declaration.statut = DeclarationDeces.Statut.REJETE
        declaration.motif_rejet = motif
        declaration.agent_traitement = request.user
        declaration.date_traitement = timezone.now()
        declaration.save()
        return Response(DeclarationDecesSerializer(declaration).data)


class HopitalListAPIView(generics.ListAPIView):
    # Endpoint de référence pour alimenter des listes déroulantes côté UI/API clients.
    queryset = Hopital.objects.all()
    serializer_class = HopitalSerializer
    permission_classes = [permissions.IsAuthenticated]


class MairieListAPIView(generics.ListAPIView):
    # Endpoint de référence mairies.
    queryset = Mairie.objects.all()
    serializer_class = MairieSerializer
    permission_classes = [permissions.IsAuthenticated]


class APIStatsView(APIView):
    """GET /api/stats/ - Statistiques globales (admin uniquement)."""
    permission_classes = [IsAdminRole]

    def get(self, request):
        # Agrégats globaux centralisés pour dashboards admin.
        data = {
            'total_declarations_naissance': DeclarationNaissance.objects.count(),
            'naissances_en_attente': DeclarationNaissance.objects.filter(statut='EN_ATTENTE').count(),
            'naissances_valides': DeclarationNaissance.objects.filter(statut='VALIDE').count(),
            'naissances_rejetees': DeclarationNaissance.objects.filter(statut='REJETE').count(),
            'total_declarations_mariage': DeclarationMariage.objects.count(),
            'mariages_en_attente': DeclarationMariage.objects.filter(statut='EN_ATTENTE').count(),
            'mariages_valides': DeclarationMariage.objects.filter(statut='VALIDE').count(),
            'mariages_rejetes': DeclarationMariage.objects.filter(statut='REJETE').count(),
            'total_declarations_deces': DeclarationDeces.objects.count(),
            'deces_en_attente': DeclarationDeces.objects.filter(statut='EN_ATTENTE').count(),
            'deces_valides': DeclarationDeces.objects.filter(statut='VALIDE').count(),
            'deces_rejetes': DeclarationDeces.objects.filter(statut='REJETE').count(),
            'total_hopitaux': Hopital.objects.count(),
            'total_mairies': Mairie.objects.count(),
        }
        return Response(data)
