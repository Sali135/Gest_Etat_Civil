"""Forms for accounts app - Login and User creation."""
# API formulaires Django.
from django import forms
# Formulaires auth de base fournis par Django.
from django.contrib.auth.forms import AuthenticationForm, UserCreationForm
# Modèle mairie pour le formulaire admin dédié.
from naissances.models import Mairie
# Modèle utilisateur personnalisé.
from .models import CustomUser


class LoginForm(AuthenticationForm):
    """Formulaire de connexion personnalisé."""
    # Champ username stylé pour Bootstrap + daisyUI.
    username = forms.CharField(
        label='Nom d\'utilisateur',
        widget=forms.TextInput(attrs={
            'class': 'input input-bordered w-full form-control form-control-lg',
            'placeholder': 'Nom d\'utilisateur',
            'autofocus': True,
        })
    )
    # Champ mot de passe stylé pour Bootstrap + daisyUI.
    password = forms.CharField(
        label='Mot de passe',
        widget=forms.PasswordInput(attrs={
            'class': 'input input-bordered w-full form-control form-control-lg',
            'placeholder': 'Mot de passe',
        })
    )


class CustomUserCreationForm(UserCreationForm):
    """Formulaire de création d'utilisateur avec rôle."""
    class Meta:
        # Modèle cible.
        model = CustomUser
        # Champs autorisés à la création.
        fields = ('username', 'first_name', 'last_name', 'email', 'role', 'hopital', 'mairie', 'password1', 'password2')
        # Widgets Bootstrap.
        widgets = {
            'username': forms.TextInput(attrs={'class': 'form-control'}),
            'first_name': forms.TextInput(attrs={'class': 'form-control'}),
            'last_name': forms.TextInput(attrs={'class': 'form-control'}),
            'email': forms.EmailInput(attrs={'class': 'form-control'}),
            'role': forms.Select(attrs={'class': 'form-select'}),
            'hopital': forms.Select(attrs={'class': 'form-select'}),
            'mairie': forms.Select(attrs={'class': 'form-select'}),
        }


class MairieCreationForm(forms.ModelForm):
    """Formulaire de création de mairie depuis le panel admin applicatif."""
    class Meta:
        # Modèle cible + champs exposés.
        model = Mairie
        fields = ('nom', 'ville', 'adresse', 'contact')
        widgets = {
            'nom': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Nom de la mairie'}),
            'ville': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Ville / Commune'}),
            'adresse': forms.Textarea(attrs={'class': 'form-control', 'rows': 3, 'placeholder': 'Adresse complète'}),
            'contact': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Téléphone / contact'}),
        }


class CustomUserUpdateForm(forms.ModelForm):
    """Formulaire de modification utilisateur (sans mot de passe)."""
    class Meta:
        # Mise à jour utilisateur sans toucher au mot de passe ici.
        model = CustomUser
        fields = ('first_name', 'last_name', 'email', 'role', 'hopital', 'mairie', 'is_active')
        widgets = {
            'first_name': forms.TextInput(attrs={'class': 'form-control'}),
            'last_name': forms.TextInput(attrs={'class': 'form-control'}),
            'email': forms.EmailInput(attrs={'class': 'form-control'}),
            'role': forms.Select(attrs={'class': 'form-select'}),
            'hopital': forms.Select(attrs={'class': 'form-select'}),
            'mairie': forms.Select(attrs={'class': 'form-select'}),
        }


class MairieUpdateForm(MairieCreationForm):
    """Formulaire de modification mairie."""
    # Hérite de MairieCreationForm: mêmes champs/widgets, usage en mode édition.
    pass
