"""Admin configuration for naissances app."""
# API admin Django.
from django.contrib import admin
# Permet de retourner du HTML sécurisé pour certaines colonnes custom.
from django.utils.html import format_html
# Tous les modèles métiers exposés dans l'admin.
from .models import (
    Hopital, Mairie, DeclarationNaissance, ActeNaissance,
    DeclarationMariage, ActeMariage, DeclarationDeces, ActeDeces,
    HistoriqueNaissance, HistoriqueMariage, HistoriqueDeces,
)


@admin.register(Hopital)
class HopitalAdmin(admin.ModelAdmin):
    # Colonnes visibles dans la liste.
    list_display = ('nom', 'code', 'contact', 'adresse', 'created_at')
    search_fields = ('nom', 'code', 'contact')
    readonly_fields = ('code', 'created_at')


@admin.register(Mairie)
class MairieAdmin(admin.ModelAdmin):
    # Colonnes visibles dans la liste.
    list_display = ('nom', 'ville', 'contact', 'adresse', 'created_at')
    search_fields = ('nom', 'ville', 'contact')
    readonly_fields = ('created_at',)


@admin.register(DeclarationNaissance)
class DeclarationNaissanceAdmin(admin.ModelAdmin):
    # Vue tableau de l'admin pour les déclarations.
    list_display = ('reference', 'nom_enfant', 'date_naissance', 'hopital', 'mairie', 'priorite', 'statut_colored', 'date_creation')
    list_filter = ('statut', 'hopital', 'mairie', 'sexe', 'priorite')
    search_fields = ('reference', 'nom_enfant', 'nom_pere', 'nom_mere')
    readonly_fields = ('reference', 'date_creation', 'date_traitement', 'date_echeance')
    date_hierarchy = 'date_creation'

    # Organisation des champs dans le formulaire admin.
    fieldsets = (
        ('Reference', {'fields': ('reference', 'statut', 'motif_rejet', 'priorite')}),
        ('Enfant', {'fields': ('nom_enfant', 'prenom_enfant', 'sexe', 'date_naissance', 'heure_naissance', 'lieu_naissance')}),
        ('Pere', {'fields': ('nom_pere', 'date_naissance_pere', 'nationalite_pere', 'profession_pere')}),
        ('Mere', {'fields': ('nom_mere', 'date_naissance_mere', 'nationalite_mere', 'profession_mere')}),
        ('Contact', {'fields': ('email_parents', 'telephone_parents')}),
        ('Etablissements', {'fields': ('hopital', 'mairie', 'agent_hopital', 'agent_mairie')}),
        ('Dates', {'fields': ('date_creation', 'date_traitement', 'date_echeance')}),
    )

    def statut_colored(self, obj):
        # Mapping statut -> couleur d'affichage dans la colonne custom.
        colors = {'EN_ATTENTE': '#f59e0b', 'EN_VERIFICATION': '#2563eb', 'VALIDE': '#10b981', 'REJETE': '#ef4444'}
        color = colors.get(obj.statut, '#6b7280')
        # Retourne un span stylé lisible visuellement.
        return format_html('<span style="color: {}; font-weight: bold;">{}</span>', color, obj.get_statut_display())

    statut_colored.short_description = 'Statut'


@admin.register(ActeNaissance)
class ActeNaissanceAdmin(admin.ModelAdmin):
    list_display = ('numero_acte', 'declaration', 'date_generation', 'has_pdf')
    search_fields = ('numero_acte', 'declaration__reference', 'declaration__nom_enfant')
    readonly_fields = ('numero_acte', 'date_generation')

    def has_pdf(self, obj):
        # Affiche l'état du PDF (stocké ou généré à la volée).
        if obj.fichier_pdf:
            return format_html('<span style="color:green;">PDF disponible</span>')
        return format_html('<span style="color:orange;">Genere a la volee</span>')

    has_pdf.short_description = 'PDF'


@admin.register(DeclarationMariage)
class DeclarationMariageAdmin(admin.ModelAdmin):
    # Configuration liste/filtre/recherche pour les déclarations mariage.
    list_display = ('reference', 'nom_epoux', 'nom_epouse', 'date_mariage', 'mairie', 'priorite', 'statut', 'date_creation')
    list_filter = ('statut', 'mairie', 'date_mariage', 'priorite')
    search_fields = ('reference', 'nom_epoux', 'nom_epouse')
    readonly_fields = ('reference', 'date_creation', 'date_traitement', 'date_echeance')


@admin.register(ActeMariage)
class ActeMariageAdmin(admin.ModelAdmin):
    # Configuration standard acte mariage.
    list_display = ('numero_acte', 'declaration', 'date_generation')
    search_fields = ('numero_acte', 'declaration__reference')
    readonly_fields = ('numero_acte', 'date_generation')


@admin.register(DeclarationDeces)
class DeclarationDecesAdmin(admin.ModelAdmin):
    # Configuration standard déclaration décès.
    list_display = ('reference', 'nom_defunt', 'date_deces', 'mairie', 'hopital', 'priorite', 'statut', 'date_creation')
    list_filter = ('statut', 'sexe', 'mairie', 'hopital', 'date_deces', 'priorite')
    search_fields = ('reference', 'nom_defunt', 'prenom_defunt', 'declarant_nom')
    readonly_fields = ('reference', 'date_creation', 'date_traitement', 'date_echeance')


@admin.register(ActeDeces)
class ActeDecesAdmin(admin.ModelAdmin):
    # Configuration standard acte décès.
    list_display = ('numero_acte', 'declaration', 'date_generation')
    search_fields = ('numero_acte', 'declaration__reference')
    readonly_fields = ('numero_acte', 'date_generation')


@admin.register(HistoriqueNaissance)
class HistoriqueNaissanceAdmin(admin.ModelAdmin):
    # Historique en lecture seule.
    list_display = ('declaration', 'action', 'statut_avant', 'statut_apres', 'utilisateur', 'date_action')
    search_fields = ('declaration__reference', 'action', 'utilisateur__username')
    readonly_fields = ('declaration', 'action', 'statut_avant', 'statut_apres', 'commentaire', 'utilisateur', 'date_action')


@admin.register(HistoriqueMariage)
class HistoriqueMariageAdmin(admin.ModelAdmin):
    # Historique en lecture seule.
    list_display = ('declaration', 'action', 'statut_avant', 'statut_apres', 'utilisateur', 'date_action')
    search_fields = ('declaration__reference', 'action', 'utilisateur__username')
    readonly_fields = ('declaration', 'action', 'statut_avant', 'statut_apres', 'commentaire', 'utilisateur', 'date_action')


@admin.register(HistoriqueDeces)
class HistoriqueDecesAdmin(admin.ModelAdmin):
    # Historique en lecture seule.
    list_display = ('declaration', 'action', 'statut_avant', 'statut_apres', 'utilisateur', 'date_action')
    search_fields = ('declaration__reference', 'action', 'utilisateur__username')
    readonly_fields = ('declaration', 'action', 'statut_avant', 'statut_apres', 'commentaire', 'utilisateur', 'date_action')
