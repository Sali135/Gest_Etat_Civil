"""Forms for naissances app."""
# API formulaires Django.
from django import forms
# Modèles métiers concernés par ces formulaires.
from .models import DeclarationNaissance, DeclarationMariage, DeclarationDeces


class DeclarationNaissanceForm(forms.ModelForm):
    """Formulaire de déclaration de naissance pour les agents d'hôpital."""

    class Meta:
        # Modèle cible: chaque soumission crée/modifie une DeclarationNaissance.
        model = DeclarationNaissance
        # White-list explicite des champs autorisés dans le formulaire.
        fields = [
            'nom_enfant', 'prenom_enfant', 'sexe', 'date_naissance',
            'heure_naissance', 'lieu_naissance',
            'nom_pere', 'date_naissance_pere', 'nationalite_pere', 'profession_pere',
            'nom_mere', 'date_naissance_mere', 'nationalite_mere', 'profession_mere',
            'email_parents', 'telephone_parents',
            'mairie',
        ]
        # Widgets: apparence Bootstrap + placeholders orientant la saisie utilisateur.
        widgets = {
            'nom_enfant': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Nom de famille'}),
            'prenom_enfant': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Prénom(s)'}),
            'sexe': forms.Select(attrs={'class': 'form-select'}),
            'date_naissance': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
            'heure_naissance': forms.TimeInput(attrs={'class': 'form-control', 'type': 'time'}),
            'lieu_naissance': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Salle, service...'}),
            'nom_pere': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Nom complet du père'}),
            'date_naissance_pere': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
            'nationalite_pere': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Ex: Ivoirienne'}),
            'profession_pere': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Profession'}),
            'nom_mere': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Nom complet de la mère'}),
            'date_naissance_mere': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
            'nationalite_mere': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Ex: Ivoirienne'}),
            'profession_mere': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Profession'}),
            'email_parents': forms.EmailInput(attrs={'class': 'form-control', 'placeholder': 'email@exemple.com'}),
            'telephone_parents': forms.TextInput(attrs={'class': 'form-control', 'placeholder': '+225 XX XX XX XX'}),
            'mairie': forms.Select(attrs={'class': 'form-select'}),
        }
        # Labels UI en français métier.
        labels = {
            'nom_enfant': 'Nom de l\'enfant',
            'prenom_enfant': 'Prénom(s) de l\'enfant',
            'sexe': 'Sexe',
            'date_naissance': 'Date de naissance',
            'heure_naissance': 'Heure de naissance',
            'lieu_naissance': 'Lieu de naissance (service)',
            'nom_pere': 'Nom complet du père',
            'date_naissance_pere': 'Date de naissance du père',
            'nationalite_pere': 'Nationalité du père',
            'profession_pere': 'Profession du père',
            'nom_mere': 'Nom complet de la mère',
            'date_naissance_mere': 'Date de naissance de la mère',
            'nationalite_mere': 'Nationalité de la mère',
            'profession_mere': 'Profession de la mère',
            'email_parents': 'Email des parents (pour notifications)',
            'telephone_parents': 'Téléphone des parents',
            'mairie': 'Mairie destinataire',
        }


class RejectionForm(forms.Form):
    """Formulaire de rejet d'une déclaration."""
    # Un motif est obligatoire et doit contenir un minimum d'information.
    motif_rejet = forms.CharField(
        label='Motif du rejet',
        widget=forms.Textarea(attrs={
            'class': 'form-control',
            'rows': 4,
            'placeholder': 'Expliquez la raison du rejet de cette déclaration...',
        }),
        min_length=10,
    )


class ParentStatusForm(forms.Form):
    """Formulaire de consultation du statut par les parents."""
    # Référence de dossier saisie publiquement par les parents.
    reference = forms.CharField(
        label='Référence du dossier',
        max_length=20,
        widget=forms.TextInput(attrs={
            'class': 'form-control form-control-lg',
            'placeholder': 'Ex: DN-202501-ABC123',
        })
    )


class DeclarationMariageForm(forms.ModelForm):
    """Formulaire de déclaration de mariage."""

    class Meta:
        # Modèle cible.
        model = DeclarationMariage
        # Champs éditables pour constituer un dossier mariage.
        fields = [
            'nom_epoux', 'date_naissance_epoux', 'profession_epoux',
            'nom_epouse', 'date_naissance_epouse', 'profession_epouse',
            'email_contact', 'date_mariage', 'lieu_mariage', 'temoins', 'mairie',
        ]
        widgets = {
            'nom_epoux': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Nom complet de l\'époux'}),
            'date_naissance_epoux': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
            'profession_epoux': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Profession'}),
            'nom_epouse': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Nom complet de l\'épouse'}),
            'date_naissance_epouse': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
            'profession_epouse': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Profession'}),
            'email_contact': forms.EmailInput(attrs={'class': 'form-control', 'placeholder': 'contact@exemple.com'}),
            'date_mariage': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
            'lieu_mariage': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Lieu de célébration'}),
            'temoins': forms.Textarea(attrs={'class': 'form-control', 'rows': 3, 'placeholder': 'Noms des témoins'}),
            'mairie': forms.Select(attrs={'class': 'form-select'}),
        }


class DeclarationDecesForm(forms.ModelForm):
    """Formulaire de déclaration de décès."""

    class Meta:
        # Modèle cible.
        model = DeclarationDeces
        # Champs éditables pour constituer un dossier décès.
        fields = [
            'nom_defunt', 'prenom_defunt', 'sexe', 'date_naissance',
            'date_deces', 'lieu_deces', 'cause_deces',
            'declarant_nom', 'declarant_lien', 'email_contact', 'hopital', 'mairie',
        ]
        widgets = {
            'nom_defunt': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Nom du défunt'}),
            'prenom_defunt': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Prénom du défunt'}),
            'sexe': forms.Select(attrs={'class': 'form-select'}),
            'date_naissance': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
            'date_deces': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
            'lieu_deces': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Lieu du décès'}),
            'cause_deces': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Cause (optionnel)'}),
            'declarant_nom': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Nom du déclarant'}),
            'declarant_lien': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Lien avec le défunt'}),
            'email_contact': forms.EmailInput(attrs={'class': 'form-control', 'placeholder': 'contact@exemple.com'}),
            'hopital': forms.Select(attrs={'class': 'form-select'}),
            'mairie': forms.Select(attrs={'class': 'form-select'}),
        }
