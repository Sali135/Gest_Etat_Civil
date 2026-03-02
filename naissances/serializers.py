"""DRF Serializers for naissances app."""
# Utilisé pour les validations dépendantes de la date courante.
from django.utils import timezone
# Base serializers DRF.
from rest_framework import serializers
# Modèles métier sérialisés en JSON.
from .models import (
    DeclarationNaissance, ActeNaissance, Hopital, Mairie,
    DeclarationMariage, ActeMariage, DeclarationDeces, ActeDeces,
)


class HopitalSerializer(serializers.ModelSerializer):
    """Serializer de lecture des hôpitaux (données de référence)."""
    class Meta:
        model = Hopital
        # Champs exposés dans l'API.
        fields = ['id', 'nom', 'code', 'adresse', 'contact']


class MairieSerializer(serializers.ModelSerializer):
    """Serializer de lecture des mairies (données de référence)."""
    class Meta:
        model = Mairie
        fields = ['id', 'nom', 'ville', 'adresse', 'contact']


class ActeNaissanceSerializer(serializers.ModelSerializer):
    """Serializer compact d'un acte de naissance."""
    class Meta:
        model = ActeNaissance
        fields = ['id', 'numero_acte', 'date_generation']


class DeclarationNaissanceSerializer(serializers.ModelSerializer):
    # Ces champs imbriqués sont en lecture seule pour éviter des updates FK non désirés via ce serializer.
    hopital = HopitalSerializer(read_only=True)
    mairie = MairieSerializer(read_only=True)
    acte = ActeNaissanceSerializer(read_only=True)
    # Expose le libellé humain du statut en plus de sa valeur technique.
    statut_display = serializers.CharField(source='get_statut_display', read_only=True)

    class Meta:
        model = DeclarationNaissance
        fields = [
            'id', 'reference', 'statut', 'statut_display',
            'nom_enfant', 'prenom_enfant', 'sexe', 'date_naissance', 'lieu_naissance',
            'nom_pere', 'nom_mere',
            'hopital', 'mairie',
            'priorite', 'date_echeance', 'date_creation', 'date_traitement',
            'acte',
        ]
        read_only_fields = ['reference', 'date_creation', 'date_traitement']


class DeclarationCreateSerializer(serializers.ModelSerializer):
    """Serializer for creating a new declaration (hospital agent)."""
    class Meta:
        model = DeclarationNaissance
        fields = [
            'priorite',
            'nom_enfant', 'prenom_enfant', 'sexe', 'date_naissance',
            'heure_naissance', 'lieu_naissance',
            'nom_pere', 'date_naissance_pere', 'nationalite_pere', 'profession_pere',
            'nom_mere', 'date_naissance_mere', 'nationalite_mere', 'profession_mere',
            'email_parents', 'telephone_parents',
            'mairie',
        ]

    def validate(self, attrs):
        # Validation croisée des dates pour protéger la qualité des données côté API.
        date_naissance = attrs.get('date_naissance')
        date_naissance_pere = attrs.get('date_naissance_pere')
        date_naissance_mere = attrs.get('date_naissance_mere')
        today = timezone.localdate()

        if date_naissance and date_naissance > today:
            raise serializers.ValidationError({
                'date_naissance': "La date de naissance ne peut pas être dans le futur."
            })
        if date_naissance_pere and date_naissance and date_naissance_pere >= date_naissance:
            raise serializers.ValidationError({
                'date_naissance_pere': "La date de naissance du père doit être antérieure à celle de l'enfant."
            })
        if date_naissance_mere and date_naissance and date_naissance_mere >= date_naissance:
            raise serializers.ValidationError({
                'date_naissance_mere': "La date de naissance de la mère doit être antérieure à celle de l'enfant."
            })
        return attrs


class ActeMariageSerializer(serializers.ModelSerializer):
    """Serializer compact d'un acte de mariage."""
    class Meta:
        model = ActeMariage
        fields = ['id', 'numero_acte', 'date_generation']


class DeclarationMariageSerializer(serializers.ModelSerializer):
    # Données liées exposées en lecture seule.
    mairie = MairieSerializer(read_only=True)
    acte = ActeMariageSerializer(read_only=True)
    statut_display = serializers.CharField(source='get_statut_display', read_only=True)

    class Meta:
        model = DeclarationMariage
        fields = [
            'id', 'reference', 'statut', 'statut_display', 'motif_rejet', 'priorite', 'date_echeance',
            'nom_epoux', 'nom_epouse', 'date_naissance_epoux', 'date_naissance_epouse',
            'profession_epoux', 'profession_epouse', 'date_mariage', 'lieu_mariage',
            'temoins', 'email_contact', 'mairie', 'date_creation', 'date_traitement', 'acte',
        ]
        read_only_fields = ['reference', 'date_creation', 'date_traitement']


class DeclarationMariageCreateSerializer(serializers.ModelSerializer):
    """Serializer d'écriture (création) pour les déclarations de mariage."""
    class Meta:
        model = DeclarationMariage
        fields = [
            'priorite',
            'nom_epoux', 'nom_epouse', 'date_naissance_epoux', 'date_naissance_epouse',
            'profession_epoux', 'profession_epouse', 'date_mariage', 'lieu_mariage',
            'temoins', 'email_contact', 'mairie',
        ]

    def validate(self, attrs):
        # Règles de cohérence temporelle du dossier mariage.
        date_mariage = attrs.get('date_mariage')
        date_naissance_epoux = attrs.get('date_naissance_epoux')
        date_naissance_epouse = attrs.get('date_naissance_epouse')
        today = timezone.localdate()

        if date_mariage and date_mariage > today:
            raise serializers.ValidationError({
                'date_mariage': "La date du mariage ne peut pas être dans le futur."
            })
        if date_naissance_epoux and date_mariage and date_naissance_epoux >= date_mariage:
            raise serializers.ValidationError({
                'date_naissance_epoux': "La date de naissance de l'époux doit être antérieure à la date du mariage."
            })
        if date_naissance_epouse and date_mariage and date_naissance_epouse >= date_mariage:
            raise serializers.ValidationError({
                'date_naissance_epouse': "La date de naissance de l'épouse doit être antérieure à la date du mariage."
            })
        return attrs


class ActeDecesSerializer(serializers.ModelSerializer):
    """Serializer compact d'un acte de décès."""
    class Meta:
        model = ActeDeces
        fields = ['id', 'numero_acte', 'date_generation']


class DeclarationDecesSerializer(serializers.ModelSerializer):
    # Champs imbriqués de contexte en lecture.
    hopital = HopitalSerializer(read_only=True)
    mairie = MairieSerializer(read_only=True)
    acte = ActeDecesSerializer(read_only=True)
    statut_display = serializers.CharField(source='get_statut_display', read_only=True)

    class Meta:
        model = DeclarationDeces
        fields = [
            'id', 'reference', 'statut', 'statut_display', 'motif_rejet', 'priorite', 'date_echeance',
            'nom_defunt', 'prenom_defunt', 'sexe', 'date_naissance',
            'date_deces', 'lieu_deces', 'cause_deces', 'declarant_nom',
            'declarant_lien', 'email_contact', 'hopital', 'mairie', 'date_creation',
            'date_traitement', 'acte',
        ]
        read_only_fields = ['reference', 'date_creation', 'date_traitement']


class DeclarationDecesCreateSerializer(serializers.ModelSerializer):
    """Serializer d'écriture (création) pour les déclarations de décès."""
    class Meta:
        model = DeclarationDeces
        fields = [
            'priorite',
            'nom_defunt', 'prenom_defunt', 'sexe', 'date_naissance',
            'date_deces', 'lieu_deces', 'cause_deces', 'declarant_nom',
            'declarant_lien', 'email_contact', 'hopital', 'mairie',
        ]

    def validate(self, attrs):
        # Validation des dates (pas de décès dans le futur, naissance <= décès).
        date_naissance = attrs.get('date_naissance')
        date_deces = attrs.get('date_deces')
        today = timezone.localdate()

        if date_deces and date_deces > today:
            raise serializers.ValidationError({
                'date_deces': "La date du décès ne peut pas être dans le futur."
            })
        if date_naissance and date_deces and date_naissance > date_deces:
            raise serializers.ValidationError({
                'date_naissance': "La date de naissance doit être antérieure ou égale à la date du décès."
            })
        return attrs
