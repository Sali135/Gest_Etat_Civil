"""
Views for naissances app.
Handles dashboards, CRUD operations, validation workflow, and PDF generation.
"""
# Flux binaire mémoire (utile pour manipulations futures de documents).
import io
import logging
# Helpers classiques de vues Django (rendu, redirection, récupération avec 404 auto).
from django.shortcuts import render, redirect, get_object_or_404
# Décorateur imposant une session authentifiée.
from django.contrib.auth.decorators import login_required
# Messages flash (succès/erreur/warning) pour l'interface.
from django.contrib import messages
# Réponse HTTP + exception 404.
from django.http import HttpResponse, Http404
# Gestion des dates timezone-aware.
from django.utils import timezone
# Transactions DB pour sécuriser les opérations critiques.
from django.db import transaction
# Agrégations SQL pour dashboards et filtres dynamiques.
from django.db.models import Count, Q
# Envoi d'emails de notification.
from django.core.mail import send_mail
# Pagination des listes volumineuses.
from django.core.paginator import Paginator
# Accès à la configuration projet (email sender, etc.).
from django.conf import settings
# Rendu des templates HTML en chaîne (utilisé pour la génération PDF).
from django.template.loader import render_to_string

from .models import (
    DeclarationNaissance, ActeNaissance, Hopital, Mairie,
    DeclarationMariage, ActeMariage, DeclarationDeces, ActeDeces,
    HistoriqueNaissance, HistoriqueMariage, HistoriqueDeces,
)

# Logger applicatif pour tracer les erreurs non bloquantes (emails, etc.).
logger = logging.getLogger(__name__)
from .forms import (
    DeclarationNaissanceForm, RejectionForm, ParentStatusForm,
    DeclarationMariageForm, DeclarationDecesForm,
)


# ─────────────────────────────────────────────
# Helpers / Decorators
# ─────────────────────────────────────────────

def role_required(*roles):
    """Decorator to restrict access by user role."""
    def decorator(view_func):
        # On garde login_required au plus près pour empêcher l'accès anonyme.
        @login_required
        def wrapper(request, *args, **kwargs):
            # Autorise si le rôle utilisateur est dans la liste ou si superuser.
            if request.user.role in roles or request.user.is_superuser:
                return view_func(request, *args, **kwargs)
            # Sinon: message d'erreur + redirection vers le dashboard générique.
            messages.error(request, "Accès refusé. Vous n'avez pas les permissions nécessaires.")
            return redirect('naissances:dashboard')
        return wrapper
    return decorator


def _log_naissance(declaration, action, user, before='', after='', comment=''):
    # Enregistre un événement d'historique sur une déclaration de naissance.
    HistoriqueNaissance.objects.create(
        declaration=declaration,
        action=action,
        statut_avant=before or '',
        statut_apres=after or '',
        commentaire=comment or '',
        utilisateur=user if user and user.is_authenticated else None,
    )


def _log_mariage(declaration, action, user, before='', after='', comment=''):
    # Enregistre un événement d'historique sur une déclaration de mariage.
    HistoriqueMariage.objects.create(
        declaration=declaration,
        action=action,
        statut_avant=before or '',
        statut_apres=after or '',
        commentaire=comment or '',
        utilisateur=user if user and user.is_authenticated else None,
    )


def _log_deces(declaration, action, user, before='', after='', comment=''):
    # Enregistre un événement d'historique sur une déclaration de décès.
    HistoriqueDeces.objects.create(
        declaration=declaration,
        action=action,
        statut_avant=before or '',
        statut_apres=after or '',
        commentaire=comment or '',
        utilisateur=user if user and user.is_authenticated else None,
    )


def _assert_user_can_access_declaration(user, declaration):
    """Raise 404 if user is scoped to another establishment."""
    # Isolation des données: un agent hôpital ne voit que son hôpital.
    if user.role == 'HOPITAL' and getattr(declaration, 'hopital_id', None) != getattr(user, 'hopital_id', None):
        raise Http404
    # Isolation des données: un agent mairie ne voit que sa mairie.
    if user.role == 'MAIRIE' and getattr(declaration, 'mairie_id', None) != getattr(user, 'mairie_id', None):
        raise Http404


def _pdf_response_from_template(template_name, filename, context):
    # Transforme un template HTML en réponse PDF téléchargeable.
    html_content = render_to_string(template_name, context)
    response = HttpResponse(content_type='application/pdf')
    # Header HTTP forçant le téléchargement de fichier.
    response['Content-Disposition'] = f'attachment; filename="{filename}"'
    from xhtml2pdf import pisa
    pisa_status = pisa.CreatePDF(html_content, dest=response, encoding='utf-8')
    if pisa_status.err:
        # Retourne None en cas d'échec pour laisser la vue afficher un message propre.
        return None
    return response


# ─────────────────────────────────────────────
# Dashboard Router
# ─────────────────────────────────────────────

@login_required
def dashboard(request):
    """Route vers le bon dashboard selon le rôle de l'utilisateur."""
    user = request.user
    # Router centralisé par rôle.
    if user.is_superuser or user.role == 'ADMIN':
        return redirect('naissances:dashboard_admin')
    elif user.role == 'MAIRIE':
        return redirect('naissances:dashboard_mairie')
    elif user.role == 'HOPITAL':
        return redirect('naissances:dashboard_hopital')
    else:
        return redirect('accounts:login')


# ─────────────────────────────────────────────
# Hospital Dashboard & Views
# ─────────────────────────────────────────────

@login_required
@role_required('HOPITAL')
def dashboard_hopital(request):
    """Tableau de bord pour les agents d'hôpital."""
    hopital = request.user.hopital
    declarations = DeclarationNaissance.objects.filter(hopital=hopital) if hopital else DeclarationNaissance.objects.none()

    stats = {
        'total': declarations.count(),
        'en_attente': declarations.filter(statut='EN_ATTENTE').count(),
        'valides': declarations.filter(statut='VALIDE').count(),
        'rejetes': declarations.filter(statut='REJETE').count(),
        'en_retard': declarations.filter(statut__in=['EN_ATTENTE', 'EN_VERIFICATION'], date_echeance__lt=timezone.now()).count(),
    }
    recent = declarations[:5]

    return render(request, 'naissances/dashboard_hopital.html', {
        'stats': stats,
        'recent': recent,
        'hopital': hopital,
    })


@login_required
@role_required('HOPITAL')
def declaration_create(request):
    """Créer une nouvelle déclaration de naissance."""
    if not request.user.hopital:
        messages.error(
            request,
            "Votre compte n'est associé à aucun hôpital. Contactez l'administrateur."
        )
        return redirect('naissances:dashboard_hopital')

    if request.method == 'POST':
        form = DeclarationNaissanceForm(request.POST)
        if form.is_valid():
            declaration = form.save(commit=False)
            declaration.hopital = request.user.hopital
            declaration.agent_hopital = request.user
            declaration.statut = DeclarationNaissance.Statut.EN_ATTENTE
            declaration.save()
            _log_naissance(declaration, 'CREATION', request.user, after=declaration.statut)
            messages.success(
                request,
                f'✅ Déclaration créée avec succès ! Référence : <strong>{declaration.reference}</strong>',
                extra_tags='safe'
            )
            return redirect('naissances:declaration_detail', pk=declaration.pk)
    else:
        form = DeclarationNaissanceForm()

    return render(request, 'naissances/declaration_form.html', {'form': form, 'action': 'Créer'})


@login_required
@role_required('HOPITAL')
def declaration_edit(request, pk):
    """Modifier une déclaration (uniquement si en attente)."""
    declaration = get_object_or_404(DeclarationNaissance, pk=pk)

    # Vérifier que l'agent appartient à l'hôpital de la déclaration
    if declaration.hopital != request.user.hopital:
        messages.error(request, "Vous ne pouvez pas modifier cette déclaration.")
        return redirect('naissances:declaration_list')

    if declaration.statut != DeclarationNaissance.Statut.EN_ATTENTE:
        messages.warning(request, "Cette déclaration ne peut plus être modifiée car elle a déjà été traitée.")
        return redirect('naissances:declaration_detail', pk=pk)

    if request.method == 'POST':
        form = DeclarationNaissanceForm(request.POST, instance=declaration)
        if form.is_valid():
            old_status = declaration.statut
            form.save()
            _log_naissance(declaration, 'MODIFICATION', request.user, before=old_status, after=declaration.statut)
            messages.success(request, '✅ Déclaration mise à jour avec succès.')
            return redirect('naissances:declaration_detail', pk=pk)
    else:
        form = DeclarationNaissanceForm(instance=declaration)

    return render(request, 'naissances/declaration_form.html', {
        'form': form, 'action': 'Modifier', 'declaration': declaration
    })


# ─────────────────────────────────────────────
# Shared Views (Hospital + Mairie)
# ─────────────────────────────────────────────

@login_required
def declaration_list(request):
    """Liste des déclarations filtrée selon le rôle."""
    user = request.user
    qs = DeclarationNaissance.objects.select_related('hopital', 'mairie', 'agent_hopital')

    if user.role == 'HOPITAL' and user.hopital:
        qs = qs.filter(hopital=user.hopital)
    elif user.role == 'MAIRIE' and user.mairie:
        qs = qs.filter(mairie=user.mairie)
    elif not (user.is_superuser or user.role == 'ADMIN'):
        qs = qs.none()

    # Filtres
    statut_filter = request.GET.get('statut', '')
    search = request.GET.get('q', '')

    if statut_filter:
        qs = qs.filter(statut=statut_filter)
    if search:
        qs = qs.filter(
            Q(reference__icontains=search) |
            Q(nom_enfant__icontains=search) |
            Q(nom_pere__icontains=search) |
            Q(nom_mere__icontains=search)
        )

    paginator = Paginator(qs.order_by('-date_creation'), 20)
    page_obj = paginator.get_page(request.GET.get('page'))

    return render(request, 'naissances/declaration_list.html', {
        'declarations': page_obj,
        'page_obj': page_obj,
        'statut_filter': statut_filter,
        'search': search,
        'statut_choices': DeclarationNaissance.Statut.choices,
    })


@login_required
def declaration_detail(request, pk):
    """Détail d'une déclaration de naissance."""
    declaration = get_object_or_404(DeclarationNaissance, pk=pk)
    user = request.user

    # Contrôle d'accès
    if user.role == 'HOPITAL' and declaration.hopital != user.hopital:
        raise Http404
    if user.role == 'MAIRIE' and declaration.mairie != user.mairie:
        raise Http404

    acte = getattr(declaration, 'acte', None)
    rejection_form = RejectionForm()
    historique = declaration.historique.select_related('utilisateur')[:20]
    can_process = (
        declaration.statut in [DeclarationNaissance.Statut.EN_ATTENTE, DeclarationNaissance.Statut.EN_VERIFICATION] and
        (request.user.is_superuser or request.user.role in ['MAIRIE', 'ADMIN'])
    )

    return render(request, 'naissances/declaration_detail.html', {
        'declaration': declaration,
        'acte': acte,
        'rejection_form': rejection_form,
        'historique': historique,
        'can_process': can_process,
    })


# ─────────────────────────────────────────────
# Mairie Dashboard & Validation Views
# ─────────────────────────────────────────────

@login_required
@role_required('MAIRIE')
def dashboard_mairie(request):
    """Tableau de bord pour les agents de mairie."""
    mairie = request.user.mairie
    declarations = DeclarationNaissance.objects.filter(mairie=mairie) if mairie else DeclarationNaissance.objects.none()

    stats = {
        'total': declarations.count(),
        'en_attente': declarations.filter(statut='EN_ATTENTE').count(),
        'valides': declarations.filter(statut='VALIDE').count(),
        'rejetes': declarations.filter(statut='REJETE').count(),
        'mariages': DeclarationMariage.objects.filter(mairie=mairie).count(),
        'deces': DeclarationDeces.objects.filter(mairie=mairie).count(),
        'en_retard': declarations.filter(statut__in=['EN_ATTENTE', 'EN_VERIFICATION'], date_echeance__lt=timezone.now()).count(),
    }
    worklist = declarations.filter(statut='EN_ATTENTE').order_by('date_creation')[:10]

    return render(request, 'naissances/dashboard_mairie.html', {
        'stats': stats,
        'worklist': worklist,
        'mairie': mairie,
    })


@login_required
@role_required('MAIRIE', 'ADMIN')
def declaration_valider(request, pk):
    """Valider une déclaration et générer l'acte de naissance."""
    if request.method != 'POST':
        return redirect('naissances:declaration_detail', pk=pk)

    with transaction.atomic():
        declaration_qs = DeclarationNaissance.objects.select_for_update()
        if request.user.role == 'MAIRIE':
            declaration = get_object_or_404(declaration_qs, pk=pk, mairie=request.user.mairie)
        else:
            declaration = get_object_or_404(declaration_qs, pk=pk)

        if declaration.statut not in [DeclarationNaissance.Statut.EN_ATTENTE, DeclarationNaissance.Statut.EN_VERIFICATION]:
            messages.warning(request, "Cette déclaration a déjà été traitée.")
            return redirect('naissances:declaration_detail', pk=pk)

        # Mettre à jour le statut
        old_status = declaration.statut
        declaration.statut = DeclarationNaissance.Statut.VALIDE
        declaration.agent_mairie = request.user
        declaration.date_traitement = timezone.now()
        declaration.save()

        # Créer (ou récupérer) l'acte de naissance de façon idempotente
        acte, _ = ActeNaissance.objects.get_or_create(declaration=declaration)
        _log_naissance(declaration, 'VALIDATION', request.user, before=old_status, after=declaration.statut)

    # Envoyer notification email aux parents
    if declaration.email_parents:
        email_sent = _send_validation_email(declaration, acte)
        if not email_sent:
            messages.warning(
                request,
                "Acte généré, mais la notification email au parent a échoué. L'équipe technique a été alertée."
            )

    messages.success(
        request,
        f'✅ Déclaration validée ! Acte N° <strong>{acte.numero_acte}</strong> généré.',
        extra_tags='safe'
    )
    return redirect('naissances:declaration_detail', pk=pk)


@login_required
@role_required('MAIRIE', 'ADMIN')
def declaration_rejeter(request, pk):
    """Rejeter une déclaration avec un motif."""
    if request.user.role == 'MAIRIE':
        declaration = get_object_or_404(DeclarationNaissance, pk=pk, mairie=request.user.mairie)
    else:
        declaration = get_object_or_404(DeclarationNaissance, pk=pk)

    if declaration.statut not in [DeclarationNaissance.Statut.EN_ATTENTE, DeclarationNaissance.Statut.EN_VERIFICATION]:
        messages.warning(request, "Cette déclaration a déjà été traitée.")
        return redirect('naissances:declaration_detail', pk=pk)

    if request.method == 'POST':
        form = RejectionForm(request.POST)
        if form.is_valid():
            old_status = declaration.statut
            declaration.statut = DeclarationNaissance.Statut.REJETE
            declaration.motif_rejet = form.cleaned_data['motif_rejet']
            declaration.agent_mairie = request.user
            declaration.date_traitement = timezone.now()
            declaration.save()
            _log_naissance(
                declaration, 'REJET', request.user,
                before=old_status, after=declaration.statut,
                comment=declaration.motif_rejet,
            )

            # Envoyer notification email aux parents
            if declaration.email_parents:
                email_sent = _send_rejection_email(declaration)
                if not email_sent:
                    messages.warning(
                        request,
                        "Rejet enregistré, mais l'email parent n'a pas pu être envoyé. L'équipe technique a été alertée."
                    )

            messages.warning(request, '⚠️ Déclaration rejetée avec succès.')
            return redirect('naissances:declaration_detail', pk=pk)

    return redirect('naissances:declaration_detail', pk=pk)


@login_required
@role_required('MAIRIE', 'ADMIN')
def declaration_verification(request, pk):
    """Passer une déclaration en vérification."""
    if request.method != 'POST':
        return redirect('naissances:declaration_detail', pk=pk)
    declaration = get_object_or_404(DeclarationNaissance, pk=pk)
    if request.user.role == 'MAIRIE' and declaration.mairie != request.user.mairie:
        raise Http404
    if declaration.statut != DeclarationNaissance.Statut.EN_ATTENTE:
        messages.warning(request, "Seules les déclarations en attente peuvent être passées en vérification.")
        return redirect('naissances:declaration_detail', pk=pk)
    old_status = declaration.statut
    declaration.statut = DeclarationNaissance.Statut.EN_VERIFICATION
    declaration.agent_mairie = request.user
    declaration.save(update_fields=['statut', 'agent_mairie'])
    _log_naissance(declaration, 'MISE_EN_VERIFICATION', request.user, before=old_status, after=declaration.statut)
    messages.info(request, "Déclaration placée en vérification.")
    return redirect('naissances:declaration_detail', pk=pk)


# ─────────────────────────────────────────────
# Admin Dashboard
# ─────────────────────────────────────────────

@login_required
@role_required('ADMIN')
def dashboard_admin(request):
    """Tableau de bord administrateur global."""
    total = DeclarationNaissance.objects.count()
    stats = {
        'total': total,
        'en_attente': DeclarationNaissance.objects.filter(statut='EN_ATTENTE').count(),
        'valides': DeclarationNaissance.objects.filter(statut='VALIDE').count(),
        'rejetes': DeclarationNaissance.objects.filter(statut='REJETE').count(),
        'hopitaux': Hopital.objects.count(),
        'mairies': Mairie.objects.count(),
        'mariages': DeclarationMariage.objects.count(),
        'deces': DeclarationDeces.objects.count(),
        'en_retard': DeclarationNaissance.objects.filter(statut__in=['EN_ATTENTE', 'EN_VERIFICATION'], date_echeance__lt=timezone.now()).count(),
    }

    # Statistiques par hôpital
    hopitaux_stats = Hopital.objects.annotate(
        nb_declarations=Count('declarations'),
        nb_valides=Count('declarations', filter=Q(declarations__statut='VALIDE')),
    ).order_by('-nb_declarations')[:10]

    recent = DeclarationNaissance.objects.select_related('hopital', 'mairie')[:10]

    return render(request, 'naissances/dashboard_admin.html', {
        'stats': stats,
        'hopitaux_stats': hopitaux_stats,
        'recent': recent,
    })


# ─────────────────────────────────────────────
# PDF Generation
# ─────────────────────────────────────────────

@login_required
def telecharger_acte_pdf(request, pk):
    """Générer et télécharger l'acte de naissance en PDF."""
    acte = get_object_or_404(ActeNaissance, pk=pk)
    declaration = acte.declaration
    _assert_user_can_access_declaration(request.user, declaration)

    response = _pdf_response_from_template('naissances/acte_naissance_pdf.html', f'acte_{acte.numero_acte}.pdf', {
        'acte': acte,
        'declaration': declaration,
    })
    if response is None:
        messages.error(request, "Erreur lors de la génération du PDF.")
        return redirect('naissances:declaration_detail', pk=declaration.pk)
    return response


# ─────────────────────────────────────────────
# Mariages
# ─────────────────────────────────────────────

@login_required
@role_required('MAIRIE', 'ADMIN')
def mariage_dashboard(request):
    """Tableau de bord des mariages."""
    qs = DeclarationMariage.objects.select_related('mairie', 'agent_mairie')
    if request.user.role == 'MAIRIE' and request.user.mairie:
        qs = qs.filter(mairie=request.user.mairie)

    stats = {
        'total': qs.count(),
        'ce_mois': qs.filter(date_creation__month=timezone.now().month, date_creation__year=timezone.now().year).count(),
        'avec_temoins': qs.exclude(temoins='').count(),
        'en_attente': qs.filter(statut=DeclarationMariage.Statut.EN_ATTENTE).count(),
        'valides': qs.filter(statut=DeclarationMariage.Statut.VALIDE).count(),
        'rejetes': qs.filter(statut=DeclarationMariage.Statut.REJETE).count(),
        'en_retard': qs.filter(statut__in=[DeclarationMariage.Statut.EN_ATTENTE, DeclarationMariage.Statut.EN_VERIFICATION], date_echeance__lt=timezone.now()).count(),
    }
    recent = qs[:8]
    return render(request, 'naissances/dashboard_mariage.html', {
        'stats': stats,
        'recent': recent,
    })


@login_required
@role_required('MAIRIE', 'ADMIN')
def mariage_list(request):
    """Liste des déclarations de mariage."""
    qs = DeclarationMariage.objects.select_related('mairie', 'agent_mairie')
    user = request.user

    if user.role == 'MAIRIE' and user.mairie:
        qs = qs.filter(mairie=user.mairie)
    elif not (user.role == 'ADMIN' or user.is_superuser):
        qs = qs.none()

    search = request.GET.get('q', '')
    if search:
        qs = qs.filter(
            Q(reference__icontains=search) |
            Q(nom_epoux__icontains=search) |
            Q(nom_epouse__icontains=search)
        )
    statut = request.GET.get('statut')
    if statut:
        qs = qs.filter(statut=statut)

    return render(request, 'naissances/mariage_list.html', {
        'declarations': qs,
        'search': search,
        'statut': statut,
        'statut_choices': DeclarationMariage.Statut.choices,
    })


@login_required
@role_required('MAIRIE', 'ADMIN')
def mariage_create(request):
    """Créer une déclaration de mariage et générer l'acte."""
    if request.method == 'POST':
        form = DeclarationMariageForm(request.POST)
        if form.is_valid():
            declaration = form.save(commit=False)
            if request.user.role == 'MAIRIE' and request.user.mairie:
                declaration.mairie = request.user.mairie
            declaration.save()
            _log_mariage(declaration, 'CREATION', request.user, after=declaration.statut)
            messages.success(request, f'Déclaration de mariage enregistrée ({declaration.reference}).')
            return redirect('naissances:mariage_detail', pk=declaration.pk)
    else:
        form = DeclarationMariageForm()
        if request.user.role == 'MAIRIE' and request.user.mairie:
            form.fields['mairie'].initial = request.user.mairie
            form.fields['mairie'].widget.attrs['readonly'] = True

    return render(request, 'naissances/mariage_form.html', {
        'form': form,
        'action': 'Créer',
    })


@login_required
@role_required('MAIRIE', 'ADMIN')
def mariage_detail(request, pk):
    """Détail d'une déclaration de mariage."""
    declaration = get_object_or_404(DeclarationMariage, pk=pk)
    if request.user.role == 'MAIRIE' and declaration.mairie != request.user.mairie:
        raise Http404
    acte = getattr(declaration, 'acte', None)
    rejection_form = RejectionForm()
    historique = declaration.historique.select_related('utilisateur')[:20]
    can_process = (
        declaration.statut in [DeclarationMariage.Statut.EN_ATTENTE, DeclarationMariage.Statut.EN_VERIFICATION] and
        (request.user.is_superuser or request.user.role in ['MAIRIE', 'ADMIN'])
    )
    return render(request, 'naissances/mariage_detail.html', {
        'declaration': declaration,
        'acte': acte,
        'rejection_form': rejection_form,
        'can_process': can_process,
        'historique': historique,
    })


@login_required
@role_required('MAIRIE', 'ADMIN')
def mariage_valider(request, pk):
    """Valider une déclaration de mariage."""
    if request.method != 'POST':
        return redirect('naissances:mariage_detail', pk=pk)

    declaration = get_object_or_404(DeclarationMariage, pk=pk)
    if request.user.role == 'MAIRIE' and declaration.mairie != request.user.mairie:
        raise Http404
    if declaration.statut not in [DeclarationMariage.Statut.EN_ATTENTE, DeclarationMariage.Statut.EN_VERIFICATION]:
        messages.warning(request, "Cette déclaration de mariage a déjà été traitée.")
        return redirect('naissances:mariage_detail', pk=pk)

    old_status = declaration.statut
    declaration.statut = DeclarationMariage.Statut.VALIDE
    declaration.motif_rejet = ''
    declaration.agent_mairie = request.user
    declaration.date_traitement = timezone.now()
    declaration.save()
    acte, _ = ActeMariage.objects.get_or_create(declaration=declaration)
    _log_mariage(declaration, 'VALIDATION', request.user, before=old_status, after=declaration.statut)
    if declaration.email_contact:
        email_sent = _send_mariage_validation_email(declaration, acte)
        if not email_sent:
            messages.warning(
                request,
                "Acte de mariage généré, mais la notification email au contact a échoué. L'équipe technique a été alertée."
            )
    messages.success(request, f'✅ Mariage validé. Acte N° {acte.numero_acte} généré.')
    return redirect('naissances:mariage_detail', pk=pk)


@login_required
@role_required('MAIRIE', 'ADMIN')
def mariage_rejeter(request, pk):
    """Rejeter une déclaration de mariage."""
    declaration = get_object_or_404(DeclarationMariage, pk=pk)
    if request.user.role == 'MAIRIE' and declaration.mairie != request.user.mairie:
        raise Http404
    if declaration.statut not in [DeclarationMariage.Statut.EN_ATTENTE, DeclarationMariage.Statut.EN_VERIFICATION]:
        messages.warning(request, "Cette déclaration de mariage a déjà été traitée.")
        return redirect('naissances:mariage_detail', pk=pk)
    form = RejectionForm(request.POST)
    if form.is_valid():
        old_status = declaration.statut
        declaration.statut = DeclarationMariage.Statut.REJETE
        declaration.motif_rejet = form.cleaned_data['motif_rejet']
        declaration.agent_mairie = request.user
        declaration.date_traitement = timezone.now()
        declaration.save()
        _log_mariage(
            declaration, 'REJET', request.user,
            before=old_status, after=declaration.statut,
            comment=declaration.motif_rejet,
        )
        if declaration.email_contact:
            email_sent = _send_mariage_rejection_email(declaration)
            if not email_sent:
                messages.warning(
                    request,
                    "Rejet enregistré, mais l'email de notification n'a pas pu être envoyé. L'équipe technique a été alertée."
                )
        messages.warning(request, "Déclaration de mariage rejetée.")
    else:
        messages.error(request, "Motif de rejet invalide.")
    return redirect('naissances:mariage_detail', pk=pk)


@login_required
@role_required('MAIRIE', 'ADMIN')
def mariage_verification(request, pk):
    """Passer un mariage en vérification."""
    if request.method != 'POST':
        return redirect('naissances:mariage_detail', pk=pk)
    declaration = get_object_or_404(DeclarationMariage, pk=pk)
    if request.user.role == 'MAIRIE' and declaration.mairie != request.user.mairie:
        raise Http404
    if declaration.statut != DeclarationMariage.Statut.EN_ATTENTE:
        messages.warning(request, "Seules les déclarations en attente peuvent être passées en vérification.")
        return redirect('naissances:mariage_detail', pk=pk)
    old_status = declaration.statut
    declaration.statut = DeclarationMariage.Statut.EN_VERIFICATION
    declaration.agent_mairie = request.user
    declaration.save(update_fields=['statut', 'agent_mairie'])
    _log_mariage(declaration, 'MISE_EN_VERIFICATION', request.user, before=old_status, after=declaration.statut)
    messages.info(request, "Déclaration de mariage placée en vérification.")
    return redirect('naissances:mariage_detail', pk=pk)


@login_required
@role_required('MAIRIE', 'ADMIN')
def telecharger_acte_mariage_pdf(request, pk):
    """Télécharger un acte de mariage PDF."""
    acte = get_object_or_404(ActeMariage, pk=pk)
    declaration = acte.declaration
    if declaration.statut != DeclarationMariage.Statut.VALIDE:
        messages.error(request, "L'acte n'est disponible qu'après validation.")
        return redirect('naissances:mariage_detail', pk=declaration.pk)
    _assert_user_can_access_declaration(request.user, declaration)

    response = _pdf_response_from_template('naissances/acte_mariage_pdf.html', f'acte_mariage_{acte.numero_acte}.pdf', {
        'acte': acte,
        'declaration': declaration,
    })
    if response is None:
        messages.error(request, "Erreur lors de la génération du PDF de mariage.")
        return redirect('naissances:mariage_detail', pk=declaration.pk)
    return response


# ─────────────────────────────────────────────
# Décès
# ─────────────────────────────────────────────

@login_required
@role_required('HOPITAL', 'MAIRIE', 'ADMIN')
def deces_dashboard(request):
    """Tableau de bord des décès."""
    qs = DeclarationDeces.objects.select_related('hopital', 'mairie', 'agent_createur')
    user = request.user
    if user.role == 'HOPITAL' and user.hopital:
        qs = qs.filter(hopital=user.hopital)
    elif user.role == 'MAIRIE' and user.mairie:
        qs = qs.filter(mairie=user.mairie)
    elif not (user.role == 'ADMIN' or user.is_superuser):
        qs = qs.none()

    stats = {
        'total': qs.count(),
        'ce_mois': qs.filter(date_creation__month=timezone.now().month, date_creation__year=timezone.now().year).count(),
        'avec_cause': qs.exclude(cause_deces='').count(),
        'en_attente': qs.filter(statut=DeclarationDeces.Statut.EN_ATTENTE).count(),
        'valides': qs.filter(statut=DeclarationDeces.Statut.VALIDE).count(),
        'rejetes': qs.filter(statut=DeclarationDeces.Statut.REJETE).count(),
        'en_retard': qs.filter(statut__in=[DeclarationDeces.Statut.EN_ATTENTE, DeclarationDeces.Statut.EN_VERIFICATION], date_echeance__lt=timezone.now()).count(),
    }
    recent = qs[:8]
    return render(request, 'naissances/dashboard_deces.html', {
        'stats': stats,
        'recent': recent,
    })


@login_required
@role_required('HOPITAL', 'MAIRIE', 'ADMIN')
def deces_list(request):
    """Liste des déclarations de décès selon rôle."""
    qs = DeclarationDeces.objects.select_related('hopital', 'mairie', 'agent_createur')
    user = request.user

    if user.role == 'HOPITAL' and user.hopital:
        qs = qs.filter(hopital=user.hopital)
    elif user.role == 'MAIRIE' and user.mairie:
        qs = qs.filter(mairie=user.mairie)
    elif not (user.role == 'ADMIN' or user.is_superuser):
        qs = qs.none()

    search = request.GET.get('q', '')
    if search:
        qs = qs.filter(
            Q(reference__icontains=search) |
            Q(nom_defunt__icontains=search) |
            Q(prenom_defunt__icontains=search)
        )
    statut = request.GET.get('statut')
    if statut:
        qs = qs.filter(statut=statut)

    return render(request, 'naissances/deces_list.html', {
        'declarations': qs,
        'search': search,
        'statut': statut,
        'statut_choices': DeclarationDeces.Statut.choices,
    })


@login_required
@role_required('HOPITAL', 'MAIRIE', 'ADMIN')
def deces_create(request):
    """Créer une déclaration de décès et l'acte associé."""
    if request.method == 'POST':
        form = DeclarationDecesForm(request.POST)
        if form.is_valid():
            declaration = form.save(commit=False)
            if request.user.role == 'HOPITAL':
                declaration.hopital = request.user.hopital
            if request.user.role == 'MAIRIE' and request.user.mairie:
                declaration.mairie = request.user.mairie
            declaration.agent_createur = request.user
            declaration.save()
            _log_deces(declaration, 'CREATION', request.user, after=declaration.statut)
            messages.success(request, f'Déclaration de décès enregistrée ({declaration.reference}).')
            return redirect('naissances:deces_detail', pk=declaration.pk)
    else:
        form = DeclarationDecesForm()
        if request.user.role == 'HOPITAL' and request.user.hopital:
            form.fields['hopital'].initial = request.user.hopital
            form.fields['hopital'].widget.attrs['readonly'] = True
        if request.user.role == 'MAIRIE' and request.user.mairie:
            form.fields['mairie'].initial = request.user.mairie
            form.fields['mairie'].widget.attrs['readonly'] = True

    return render(request, 'naissances/deces_form.html', {
        'form': form,
        'action': 'Créer',
    })


@login_required
@role_required('HOPITAL', 'MAIRIE', 'ADMIN')
def deces_detail(request, pk):
    """Détail d'une déclaration de décès."""
    declaration = get_object_or_404(DeclarationDeces, pk=pk)
    user = request.user
    if user.role == 'HOPITAL' and declaration.hopital != user.hopital:
        raise Http404
    if user.role == 'MAIRIE' and declaration.mairie != user.mairie:
        raise Http404
    acte = getattr(declaration, 'acte', None)
    rejection_form = RejectionForm()
    historique = declaration.historique.select_related('utilisateur')[:20]
    can_process = (
        declaration.statut in [DeclarationDeces.Statut.EN_ATTENTE, DeclarationDeces.Statut.EN_VERIFICATION] and
        (request.user.is_superuser or request.user.role in ['MAIRIE', 'ADMIN'])
    )
    return render(request, 'naissances/deces_detail.html', {
        'declaration': declaration,
        'acte': acte,
        'rejection_form': rejection_form,
        'can_process': can_process,
        'historique': historique,
    })


@login_required
@role_required('MAIRIE', 'ADMIN')
def deces_valider(request, pk):
    """Valider une déclaration de décès."""
    if request.method != 'POST':
        return redirect('naissances:deces_detail', pk=pk)
    declaration = get_object_or_404(DeclarationDeces, pk=pk)
    if request.user.role == 'MAIRIE' and declaration.mairie != request.user.mairie:
        raise Http404
    if declaration.statut not in [DeclarationDeces.Statut.EN_ATTENTE, DeclarationDeces.Statut.EN_VERIFICATION]:
        messages.warning(request, "Cette déclaration de décès a déjà été traitée.")
        return redirect('naissances:deces_detail', pk=pk)

    old_status = declaration.statut
    declaration.statut = DeclarationDeces.Statut.VALIDE
    declaration.motif_rejet = ''
    declaration.agent_traitement = request.user
    declaration.date_traitement = timezone.now()
    declaration.save()
    acte, _ = ActeDeces.objects.get_or_create(declaration=declaration)
    _log_deces(declaration, 'VALIDATION', request.user, before=old_status, after=declaration.statut)
    if declaration.email_contact:
        email_sent = _send_deces_validation_email(declaration, acte)
        if not email_sent:
            messages.warning(
                request,
                "Acte de décès généré, mais la notification email au contact a échoué. L'équipe technique a été alertée."
            )
    messages.success(request, f'✅ Décès validé. Acte N° {acte.numero_acte} généré.')
    return redirect('naissances:deces_detail', pk=pk)


@login_required
@role_required('MAIRIE', 'ADMIN')
def deces_rejeter(request, pk):
    """Rejeter une déclaration de décès."""
    declaration = get_object_or_404(DeclarationDeces, pk=pk)
    if request.user.role == 'MAIRIE' and declaration.mairie != request.user.mairie:
        raise Http404
    if declaration.statut not in [DeclarationDeces.Statut.EN_ATTENTE, DeclarationDeces.Statut.EN_VERIFICATION]:
        messages.warning(request, "Cette déclaration de décès a déjà été traitée.")
        return redirect('naissances:deces_detail', pk=pk)
    form = RejectionForm(request.POST)
    if form.is_valid():
        old_status = declaration.statut
        declaration.statut = DeclarationDeces.Statut.REJETE
        declaration.motif_rejet = form.cleaned_data['motif_rejet']
        declaration.agent_traitement = request.user
        declaration.date_traitement = timezone.now()
        declaration.save()
        _log_deces(
            declaration, 'REJET', request.user,
            before=old_status, after=declaration.statut,
            comment=declaration.motif_rejet,
        )
        if declaration.email_contact:
            email_sent = _send_deces_rejection_email(declaration)
            if not email_sent:
                messages.warning(
                    request,
                    "Rejet enregistré, mais l'email de notification n'a pas pu être envoyé. L'équipe technique a été alertée."
                )
        messages.warning(request, "Déclaration de décès rejetée.")
    else:
        messages.error(request, "Motif de rejet invalide.")
    return redirect('naissances:deces_detail', pk=pk)


@login_required
@role_required('MAIRIE', 'ADMIN')
def deces_verification(request, pk):
    """Passer un décès en vérification."""
    if request.method != 'POST':
        return redirect('naissances:deces_detail', pk=pk)
    declaration = get_object_or_404(DeclarationDeces, pk=pk)
    if request.user.role == 'MAIRIE' and declaration.mairie != request.user.mairie:
        raise Http404
    if declaration.statut != DeclarationDeces.Statut.EN_ATTENTE:
        messages.warning(request, "Seules les déclarations en attente peuvent être passées en vérification.")
        return redirect('naissances:deces_detail', pk=pk)
    old_status = declaration.statut
    declaration.statut = DeclarationDeces.Statut.EN_VERIFICATION
    declaration.agent_traitement = request.user
    declaration.save(update_fields=['statut', 'agent_traitement'])
    _log_deces(declaration, 'MISE_EN_VERIFICATION', request.user, before=old_status, after=declaration.statut)
    messages.info(request, "Déclaration de décès placée en vérification.")
    return redirect('naissances:deces_detail', pk=pk)


@login_required
@role_required('HOPITAL', 'MAIRIE', 'ADMIN')
def telecharger_acte_deces_pdf(request, pk):
    """Télécharger un acte de décès PDF."""
    acte = get_object_or_404(ActeDeces, pk=pk)
    declaration = acte.declaration
    if declaration.statut != DeclarationDeces.Statut.VALIDE:
        messages.error(request, "L'acte n'est disponible qu'après validation.")
        return redirect('naissances:deces_detail', pk=declaration.pk)
    _assert_user_can_access_declaration(request.user, declaration)

    response = _pdf_response_from_template('naissances/acte_deces_pdf.html', f'acte_deces_{acte.numero_acte}.pdf', {
        'acte': acte,
        'declaration': declaration,
    })
    if response is None:
        messages.error(request, "Erreur lors de la génération du PDF de décès.")
        return redirect('naissances:deces_detail', pk=declaration.pk)
    return response


# ─────────────────────────────────────────────
# Parent Status Lookup (Public)
# ─────────────────────────────────────────────

def home_public(request):
    """Page d'accueil publique pour visiteurs et parents."""
    form = ParentStatusForm()
    return render(request, 'naissances/home_public.html', {'form': form})


def parent_status(request):
    """Consultation du statut par les parents via référence dossier."""
    # Supporte les 2 modes:
    # - POST depuis la page statut
    # - GET ?reference=... depuis la page d'accueil publique
    reference_query = request.GET.get('reference', '').strip()
    if request.method == 'POST':
        form = ParentStatusForm(request.POST)
    elif reference_query:
        form = ParentStatusForm({'reference': reference_query})
    else:
        form = ParentStatusForm()

    declaration = None
    error = None

    if form.is_bound and form.is_valid():
        reference = form.cleaned_data['reference'].strip().upper()
        try:
            declaration = DeclarationNaissance.objects.select_related(
                'hopital', 'mairie'
            ).get(reference=reference)
        except DeclarationNaissance.DoesNotExist:
            error = f"Aucun dossier trouvé avec la référence « {reference} »."

    return render(request, 'naissances/parent_status.html', {
        'form': form,
        'declaration': declaration,
        'error': error,
    })


# ─────────────────────────────────────────────
# Email Helpers
# ─────────────────────────────────────────────

def _send_validation_email(declaration, acte):
    """Envoyer un email de validation aux parents."""
    subject = f"[Gest_EtatCivil] Déclaration validée - {declaration.nom_complet_enfant}"
    message = f"""
Bonjour,

Nous avons le plaisir de vous informer que la déclaration de naissance de {declaration.nom_complet_enfant}
a été validée par la Mairie de {declaration.mairie.nom}.

Référence du dossier : {declaration.reference}
Numéro de l'acte    : {acte.numero_acte}
Date de validation  : {declaration.date_traitement.strftime('%d/%m/%Y à %H:%M')}

Vous pouvez récupérer l'acte de naissance auprès de la mairie ou le télécharger
en consultant votre dossier sur Gest_EtatCivil.

Cordialement,
L'équipe Gest_EtatCivil
    """
    return _send_email_safe(subject, message, [declaration.email_parents], context_ref=declaration.reference)


def _send_rejection_email(declaration):
    """Envoyer un email de rejet aux parents."""
    subject = f"[Gest_EtatCivil] Déclaration rejetée - {declaration.nom_complet_enfant}"
    message = f"""
Bonjour,

Nous vous informons que la déclaration de naissance de {declaration.nom_complet_enfant}
a été rejetée par la Mairie de {declaration.mairie.nom}.

Référence du dossier : {declaration.reference}
Motif du rejet       : {declaration.motif_rejet}

Veuillez contacter l'hôpital ou la mairie pour plus d'informations et corriger
les informations manquantes ou incorrectes.

Cordialement,
L'équipe Gest_EtatCivil
    """
    return _send_email_safe(subject, message, [declaration.email_parents], context_ref=declaration.reference)


def _send_mariage_validation_email(declaration, acte):
    """Envoyer un email de validation pour une déclaration de mariage."""
    subject = f"[Gest_EtatCivil] Mariage validé - {declaration.nom_epoux} & {declaration.nom_epouse}"
    message = f"""
Bonjour,

Votre déclaration de mariage a été validée par la Mairie de {declaration.mairie.nom}.

Référence dossier : {declaration.reference}
Numéro de l'acte  : {acte.numero_acte}
Date de validation: {declaration.date_traitement.strftime('%d/%m/%Y à %H:%M')}

Cordialement,
L'équipe Gest_EtatCivil
    """
    return _send_email_safe(subject, message, [declaration.email_contact], context_ref=declaration.reference)


def _send_mariage_rejection_email(declaration):
    """Envoyer un email de rejet pour une déclaration de mariage."""
    subject = f"[Gest_EtatCivil] Mariage rejeté - {declaration.nom_epoux} & {declaration.nom_epouse}"
    message = f"""
Bonjour,

Votre déclaration de mariage a été rejetée par la Mairie de {declaration.mairie.nom}.

Référence dossier : {declaration.reference}
Motif du rejet    : {declaration.motif_rejet}

Cordialement,
L'équipe Gest_EtatCivil
    """
    return _send_email_safe(subject, message, [declaration.email_contact], context_ref=declaration.reference)


def _send_deces_validation_email(declaration, acte):
    """Envoyer un email de validation pour une déclaration de décès."""
    subject = f"[Gest_EtatCivil] Décès validé - {declaration.nom_complet_defunt}"
    message = f"""
Bonjour,

La déclaration de décès de {declaration.nom_complet_defunt} a été validée par la Mairie de {declaration.mairie.nom}.

Référence dossier : {declaration.reference}
Numéro de l'acte  : {acte.numero_acte}
Date de validation: {declaration.date_traitement.strftime('%d/%m/%Y à %H:%M')}

Cordialement,
L'équipe Gest_EtatCivil
    """
    return _send_email_safe(subject, message, [declaration.email_contact], context_ref=declaration.reference)


def _send_deces_rejection_email(declaration):
    """Envoyer un email de rejet pour une déclaration de décès."""
    subject = f"[Gest_EtatCivil] Décès rejeté - {declaration.nom_complet_defunt}"
    message = f"""
Bonjour,

La déclaration de décès de {declaration.nom_complet_defunt} a été rejetée par la Mairie de {declaration.mairie.nom}.

Référence dossier : {declaration.reference}
Motif du rejet    : {declaration.motif_rejet}

Cordialement,
L'équipe Gest_EtatCivil
    """
    return _send_email_safe(subject, message, [declaration.email_contact], context_ref=declaration.reference)


def _send_email_safe(subject, message, recipients, context_ref=''):
    """
    Envoi email résilient:
    - retourne True si l'envoi a abouti
    - loggue l'erreur en cas d'échec
    - alerte les admins techniques si configurés
    """
    try:
        sent_count = send_mail(subject, message, settings.DEFAULT_FROM_EMAIL, recipients, fail_silently=False)
        return sent_count > 0
    except Exception:
        logger.exception(
            "Email delivery failure (reference=%s, recipients=%s, subject=%s)",
            context_ref,
            recipients,
            subject,
        )
        _notify_admin_email_failure(subject=subject, recipients=recipients, context_ref=context_ref)
        return False


def _notify_admin_email_failure(subject, recipients, context_ref=''):
    """Alerte opérationnelle aux admins quand un email parent n'est pas délivré."""
    admin_recipients = getattr(settings, 'ADMIN_ALERT_EMAILS', []) or []
    if not admin_recipients:
        return
    alert_subject = "[Gest_EtatCivil][ALERTE] Echec envoi email parent"
    alert_message = (
        "Un email parent n'a pas pu être envoyé.\n\n"
        f"Reference dossier : {context_ref or 'N/A'}\n"
        f"Sujet original    : {subject}\n"
        f"Destinataires     : {', '.join(recipients)}\n"
    )
    try:
        send_mail(alert_subject, alert_message, settings.DEFAULT_FROM_EMAIL, admin_recipients, fail_silently=True)
    except Exception:
        logger.exception("Failed to send admin alert for email delivery failure.")
