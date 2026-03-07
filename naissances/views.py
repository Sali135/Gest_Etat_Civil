"""
Views for naissances app.
Handles dashboards, CRUD operations, validation workflow, and PDF generation.
"""
# Flux binaire mémoire (utile pour manipulations futures de documents).
import io
import logging
import unicodedata
from collections import defaultdict
from difflib import SequenceMatcher
from itertools import combinations
from datetime import timedelta
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
from django.urls import reverse

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


def _mark_declaration_validated(declaration, user, agent_field):
    """Apply common validation state transition before acte generation."""
    old_status = declaration.statut
    declaration.statut = declaration.__class__.Statut.VALIDE
    if hasattr(declaration, 'motif_rejet'):
        declaration.motif_rejet = ''
    setattr(declaration, agent_field, user)
    declaration.date_traitement = timezone.now()
    declaration.save()
    return old_status


def _telecharger_acte_pdf(
    request,
    *,
    acte_model,
    pk,
    template_name,
    filename_prefix,
    detail_url_name,
    required_status=None,
    unavailable_message="L'acte n'est disponible qu'après validation.",
    pdf_error_message="Erreur lors de la génération du PDF.",
):
    """Shared PDF download flow for acte models."""
    acte = get_object_or_404(acte_model, pk=pk)
    declaration = acte.declaration

    if required_status is not None and declaration.statut != required_status:
        messages.error(request, unavailable_message)
        return redirect(detail_url_name, pk=declaration.pk)

    _assert_user_can_access_declaration(request.user, declaration)

    response = _pdf_response_from_template(
        template_name,
        f'{filename_prefix}_{acte.numero_acte}.pdf',
        {'acte': acte, 'declaration': declaration},
    )
    if response is None:
        messages.error(request, pdf_error_message)
        return redirect(detail_url_name, pk=declaration.pk)
    return response


# ─────────────────────────────────────────────
# Anti-duplication helpers
# ─────────────────────────────────────────────

def _normalize_text(value):
    """Normalize text for duplicate matching."""
    if not value:
        return ''
    normalized = unicodedata.normalize('NFKD', str(value))
    ascii_only = ''.join(char for char in normalized if not unicodedata.combining(char))
    return ' '.join(ascii_only.lower().strip().split())


def _similarity_ratio(left, right):
    """Compute a 0..1 similarity score between two strings."""
    if not left and not right:
        return 1.0
    if not left or not right:
        return 0.0
    return SequenceMatcher(None, _normalize_text(left), _normalize_text(right)).ratio()


def _merge_name_parts(*parts):
    """Build a full-name string from optional parts."""
    return ' '.join(str(part).strip() for part in parts if part).strip()


def _severity_rank(severity):
    return 0 if severity == 'EXACT' else 1


def _evaluate_naissance_pair(left, right):
    """Return duplicate evaluation for two naissance declarations."""
    left_child = _merge_name_parts(left.prenom_enfant, left.nom_enfant)
    right_child = _merge_name_parts(right.prenom_enfant, right.nom_enfant)
    left_mother = _normalize_text(left.nom_mere)
    right_mother = _normalize_text(right.nom_mere)
    left_place = _normalize_text(left.lieu_naissance)
    right_place = _normalize_text(right.lieu_naissance)

    if (
        _normalize_text(left_child) == _normalize_text(right_child)
        and left_mother == right_mother
        and left_place == right_place
    ):
        return {
            'severity': 'EXACT',
            'score': 100,
            'rule': "Même enfant, même mère, même date et même lieu de naissance",
        }

    child_score = _similarity_ratio(left_child, right_child)
    mother_score = _similarity_ratio(left.nom_mere, right.nom_mere)
    place_score = _similarity_ratio(left.lieu_naissance, right.lieu_naissance)
    score = round((child_score * 0.55 + mother_score * 0.35 + place_score * 0.10) * 100)
    if score < 88:
        return None

    return {
        'severity': 'PROBABLE',
        'score': score,
        'rule': "Même date/mairie avec forte similarité enfant et filiation",
    }


def _evaluate_mariage_pair(left, right):
    """Return duplicate evaluation for two mariage declarations."""
    direct_score = (
        _similarity_ratio(left.nom_epoux, right.nom_epoux)
        + _similarity_ratio(left.nom_epouse, right.nom_epouse)
    ) / 2
    swapped_score = (
        _similarity_ratio(left.nom_epoux, right.nom_epouse)
        + _similarity_ratio(left.nom_epouse, right.nom_epoux)
    ) / 2
    pair_score = max(direct_score, swapped_score)
    place_score = _similarity_ratio(left.lieu_mariage, right.lieu_mariage)
    score = round((pair_score * 0.85 + place_score * 0.15) * 100)

    left_signature = sorted([_normalize_text(left.nom_epoux), _normalize_text(left.nom_epouse)])
    right_signature = sorted([_normalize_text(right.nom_epoux), _normalize_text(right.nom_epouse)])
    if left_signature == right_signature and _normalize_text(left.lieu_mariage) == _normalize_text(right.lieu_mariage):
        return {
            'severity': 'EXACT',
            'score': 100,
            'rule': "Même époux/épouse, même date et même lieu de mariage",
        }

    if score < 90:
        return None

    return {
        'severity': 'PROBABLE',
        'score': score,
        'rule': "Même date/mairie avec forte similarité sur les époux",
    }


def _evaluate_deces_pair(left, right):
    """Return duplicate evaluation for two décès declarations."""
    left_deceased = _merge_name_parts(left.prenom_defunt, left.nom_defunt)
    right_deceased = _merge_name_parts(right.prenom_defunt, right.nom_defunt)

    if (
        _normalize_text(left_deceased) == _normalize_text(right_deceased)
        and _normalize_text(left.lieu_deces) == _normalize_text(right.lieu_deces)
    ):
        return {
            'severity': 'EXACT',
            'score': 100,
            'rule': "Même défunt, même date et même lieu de décès",
        }

    deceased_score = _similarity_ratio(left_deceased, right_deceased)
    declarant_score = _similarity_ratio(left.declarant_nom, right.declarant_nom)
    place_score = _similarity_ratio(left.lieu_deces, right.lieu_deces)
    score = round((deceased_score * 0.75 + declarant_score * 0.15 + place_score * 0.10) * 100)
    if score < 88:
        return None

    return {
        'severity': 'PROBABLE',
        'score': score,
        'rule': "Même date/mairie avec forte similarité défunt/déclarant",
    }


def _user_scoped_duplicate_querysets(user):
    """Return duplicate-analysis querysets restricted by current user scope."""
    naissance_qs = DeclarationNaissance.objects.select_related('hopital', 'mairie')
    mariage_qs = DeclarationMariage.objects.select_related('mairie')
    deces_qs = DeclarationDeces.objects.select_related('hopital', 'mairie')

    if user.is_superuser or user.role == 'ADMIN':
        return {
            'naissance': naissance_qs,
            'mariage': mariage_qs,
            'deces': deces_qs,
        }

    if user.role == 'MAIRIE' and user.mairie:
        return {
            'naissance': naissance_qs.filter(mairie=user.mairie),
            'mariage': mariage_qs.filter(mairie=user.mairie),
            'deces': deces_qs.filter(mairie=user.mairie),
        }

    if user.role == 'HOPITAL' and user.hopital:
        return {
            'naissance': naissance_qs.filter(hopital=user.hopital),
            'mariage': mariage_qs.none(),
            'deces': deces_qs.filter(hopital=user.hopital),
        }

    return {
        'naissance': naissance_qs.none(),
        'mariage': mariage_qs.none(),
        'deces': deces_qs.none(),
    }


def _build_duplicate_alert(
    *,
    module_key,
    module_label,
    left,
    right,
    evaluation,
    left_url_name,
    right_url_name,
    event_date,
):
    """Build one dashboard duplicate alert payload."""
    detected_at = max(
        getattr(left, 'date_creation', timezone.now()),
        getattr(right, 'date_creation', timezone.now()),
    )
    return {
        'module': module_key,
        'module_label': module_label,
        'severity': evaluation['severity'],
        'score': evaluation['score'],
        'rule': evaluation['rule'],
        'left_reference': left.reference,
        'right_reference': right.reference,
        'left_url': reverse(left_url_name, kwargs={'pk': left.pk}),
        'right_url': reverse(right_url_name, kwargs={'pk': right.pk}),
        'event_date': event_date,
        'detected_at': detected_at,
    }


def _detect_duplicates_for_model(
    queryset,
    *,
    module_key,
    module_label,
    date_attr,
    evaluator,
    detail_url_name,
):
    """Find duplicate pairs in a scoped queryset for one model."""
    grouped = defaultdict(list)
    for record in queryset.order_by('-date_creation'):
        group_key = (getattr(record, 'mairie_id', None), getattr(record, date_attr, None))
        grouped[group_key].append(record)

    alerts = []
    for records in grouped.values():
        if len(records) < 2:
            continue
        for left, right in combinations(records, 2):
            evaluation = evaluator(left, right)
            if not evaluation:
                continue
            alerts.append(
                _build_duplicate_alert(
                    module_key=module_key,
                    module_label=module_label,
                    left=left,
                    right=right,
                    evaluation=evaluation,
                    left_url_name=detail_url_name,
                    right_url_name=detail_url_name,
                    event_date=getattr(left, date_attr, None),
                )
            )
    return alerts


def _build_duplicates_dashboard_payload(user):
    """Compute anti-duplicate dashboard data for the current user."""
    scoped_qs = _user_scoped_duplicate_querysets(user)
    alerts = []
    alerts.extend(
        _detect_duplicates_for_model(
            scoped_qs['naissance'],
            module_key='NAISSANCE',
            module_label='Naissance',
            date_attr='date_naissance',
            evaluator=_evaluate_naissance_pair,
            detail_url_name='naissances:declaration_detail',
        )
    )
    alerts.extend(
        _detect_duplicates_for_model(
            scoped_qs['mariage'],
            module_key='MARIAGE',
            module_label='Mariage',
            date_attr='date_mariage',
            evaluator=_evaluate_mariage_pair,
            detail_url_name='naissances:mariage_detail',
        )
    )
    alerts.extend(
        _detect_duplicates_for_model(
            scoped_qs['deces'],
            module_key='DECES',
            module_label='Décès',
            date_attr='date_deces',
            evaluator=_evaluate_deces_pair,
            detail_url_name='naissances:deces_detail',
        )
    )

    alerts.sort(
        key=lambda item: (
            _severity_rank(item['severity']),
            -item['score'],
            -(item['detected_at'].timestamp() if item['detected_at'] else 0),
        )
    )

    stats = {
        'total': len(alerts),
        'exact': sum(1 for alert in alerts if alert['severity'] == 'EXACT'),
        'probable': sum(1 for alert in alerts if alert['severity'] == 'PROBABLE'),
        'naissance': sum(1 for alert in alerts if alert['module'] == 'NAISSANCE'),
        'mariage': sum(1 for alert in alerts if alert['module'] == 'MARIAGE'),
        'deces': sum(1 for alert in alerts if alert['module'] == 'DECES'),
    }
    return {'alerts': alerts, 'stats': stats}


def _collect_duplicate_matches(record, queryset, *, evaluator, detail_url_name, limit=3):
    """Return duplicate candidates for one declaration record (pre-save)."""
    matches = []
    for existing in queryset:
        evaluation = evaluator(record, existing)
        if not evaluation:
            continue
        matches.append({
            'severity': evaluation['severity'],
            'score': evaluation['score'],
            'reference': existing.reference,
            'url': reverse(detail_url_name, kwargs={'pk': existing.pk}),
            'created_at': existing.date_creation,
        })

    matches.sort(
        key=lambda item: (
            _severity_rank(item['severity']),
            -item['score'],
            -(item['created_at'].timestamp() if item['created_at'] else 0),
        )
    )
    return matches[:limit]


def _find_naissance_duplicate_matches(declaration, limit=3):
    if not declaration.date_naissance or not declaration.mairie_id:
        return []
    queryset = DeclarationNaissance.objects.filter(
        date_naissance=declaration.date_naissance,
        mairie_id=declaration.mairie_id,
    )
    if declaration.pk:
        queryset = queryset.exclude(pk=declaration.pk)
    return _collect_duplicate_matches(
        declaration,
        queryset.select_related('mairie', 'hopital'),
        evaluator=_evaluate_naissance_pair,
        detail_url_name='naissances:declaration_detail',
        limit=limit,
    )


def _find_mariage_duplicate_matches(declaration, limit=3):
    if not declaration.date_mariage or not declaration.mairie_id:
        return []
    queryset = DeclarationMariage.objects.filter(
        date_mariage=declaration.date_mariage,
        mairie_id=declaration.mairie_id,
    )
    if declaration.pk:
        queryset = queryset.exclude(pk=declaration.pk)
    return _collect_duplicate_matches(
        declaration,
        queryset.select_related('mairie'),
        evaluator=_evaluate_mariage_pair,
        detail_url_name='naissances:mariage_detail',
        limit=limit,
    )


def _find_deces_duplicate_matches(declaration, limit=3):
    if not declaration.date_deces or not declaration.mairie_id:
        return []
    queryset = DeclarationDeces.objects.filter(
        date_deces=declaration.date_deces,
        mairie_id=declaration.mairie_id,
    )
    if declaration.pk:
        queryset = queryset.exclude(pk=declaration.pk)
    return _collect_duplicate_matches(
        declaration,
        queryset.select_related('mairie', 'hopital'),
        evaluator=_evaluate_deces_pair,
        detail_url_name='naissances:deces_detail',
        limit=limit,
    )


def _build_duplicate_warning_message(domain_label, matches):
    """Render one safe HTML warning message listing duplicate candidates."""
    if not matches:
        return ''
    links = [
        f'<a href="{match["url"]}">{match["reference"]}</a> ({match["score"]}%)'
        for match in matches
    ]
    return (
        f"Alerte anti-doublon ({domain_label}) : dossier(s) similaire(s) détecté(s) "
        f"-> {', '.join(links)}."
    )


# Filtres communs pour les dashboards dynamiques (HTMX ou page complète).
DASHBOARD_PERIOD_OPTIONS = (
    ('7', '7 derniers jours'),
    ('30', '30 derniers jours'),
    ('90', '90 derniers jours'),
    ('all', 'Depuis le début'),
)
DASHBOARD_PERIOD_DAYS = {
    '7': 7,
    '30': 30,
    '90': 90,
    'all': None,
}
DASHBOARD_LIMIT_OPTIONS = (5, 10, 20)


def _parse_dashboard_filters(request, *, default_period='30', default_limit=10):
    if default_period not in DASHBOARD_PERIOD_DAYS:
        default_period = '30'
    if default_limit not in DASHBOARD_LIMIT_OPTIONS:
        default_limit = 10

    periode = request.GET.get('periode', default_period)
    if periode not in DASHBOARD_PERIOD_DAYS:
        periode = default_period

    try:
        limite = int(request.GET.get('limite', str(default_limit)))
    except (TypeError, ValueError):
        limite = default_limit
    if limite not in DASHBOARD_LIMIT_OPTIONS:
        limite = default_limit

    period_days = DASHBOARD_PERIOD_DAYS[periode]
    period_label = dict(DASHBOARD_PERIOD_OPTIONS)[periode]
    return {
        'periode': periode,
        'period_days': period_days,
        'period_label': period_label,
        'limite': limite,
    }


def _build_hopital_dashboard_context(user, filters):
    hopital = user.hopital
    declarations = DeclarationNaissance.objects.filter(hopital=hopital) if hopital else DeclarationNaissance.objects.none()

    period_days = filters['period_days']
    period_start = timezone.now() - timedelta(days=period_days) if period_days else None
    if period_start:
        declarations = declarations.filter(date_creation__gte=period_start)

    now = timezone.now()
    total = declarations.count()
    stats = {
        'total': total,
        'en_attente': declarations.filter(statut=DeclarationNaissance.Statut.EN_ATTENTE).count(),
        'valides': declarations.filter(statut=DeclarationNaissance.Statut.VALIDE).count(),
        'rejetes': declarations.filter(statut=DeclarationNaissance.Statut.REJETE).count(),
        'en_retard': declarations.filter(
            statut__in=[DeclarationNaissance.Statut.EN_ATTENTE, DeclarationNaissance.Statut.EN_VERIFICATION],
            date_echeance__lt=now,
        ).count(),
    }
    stats['taux_validite'] = round((stats['valides'] / total) * 100) if total else 0

    recent = (
        declarations.select_related('mairie')
        .order_by('-date_creation')[:filters['limite']]
    )

    return {
        'stats': stats,
        'recent': recent,
        'hopital': hopital,
        'filters': filters,
        'period_options': DASHBOARD_PERIOD_OPTIONS,
        'limit_options': DASHBOARD_LIMIT_OPTIONS,
    }


def _build_mairie_dashboard_context(user, filters):
    mairie = user.mairie
    declarations = DeclarationNaissance.objects.filter(mairie=mairie) if mairie else DeclarationNaissance.objects.none()
    mariage_qs = DeclarationMariage.objects.filter(mairie=mairie) if mairie else DeclarationMariage.objects.none()
    deces_qs = DeclarationDeces.objects.filter(mairie=mairie) if mairie else DeclarationDeces.objects.none()

    period_days = filters['period_days']
    period_start = timezone.now() - timedelta(days=period_days) if period_days else None
    if period_start:
        declarations = declarations.filter(date_creation__gte=period_start)
        mariage_qs = mariage_qs.filter(date_creation__gte=period_start)
        deces_qs = deces_qs.filter(date_creation__gte=period_start)

    now = timezone.now()
    total = declarations.count()
    stats = {
        'total': total,
        'en_attente': declarations.filter(statut=DeclarationNaissance.Statut.EN_ATTENTE).count(),
        'valides': declarations.filter(statut=DeclarationNaissance.Statut.VALIDE).count(),
        'rejetes': declarations.filter(statut=DeclarationNaissance.Statut.REJETE).count(),
        'mariages': mariage_qs.count(),
        'deces': deces_qs.count(),
        'en_retard': declarations.filter(
            statut__in=[DeclarationNaissance.Statut.EN_ATTENTE, DeclarationNaissance.Statut.EN_VERIFICATION],
            date_echeance__lt=now,
        ).count(),
    }
    stats['taux_validite'] = round((stats['valides'] / total) * 100) if total else 0

    worklist = (
        declarations.filter(statut=DeclarationNaissance.Statut.EN_ATTENTE)
        .select_related('hopital')
        .order_by('date_creation')[:filters['limite']]
    )

    return {
        'stats': stats,
        'worklist': worklist,
        'mairie': mairie,
        'filters': filters,
        'period_options': DASHBOARD_PERIOD_OPTIONS,
        'limit_options': DASHBOARD_LIMIT_OPTIONS,
    }


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
    filters = _parse_dashboard_filters(request, default_period='30', default_limit=5)
    context = _build_hopital_dashboard_context(request.user, filters)

    if request.headers.get('HX-Request') == 'true':
        return render(request, 'naissances/partials/dashboard_hopital_content.html', context)
    return render(request, 'naissances/dashboard_hopital.html', context)


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
            duplicate_matches = _find_naissance_duplicate_matches(declaration)
            declaration.save()
            _log_naissance(declaration, 'CREATION', request.user, after=declaration.statut)
            messages.success(
                request,
                f'Déclaration créée avec succès ! Référence : <strong>{declaration.reference}</strong>',
                extra_tags='safe'
            )
            if duplicate_matches:
                messages.warning(
                    request,
                    _build_duplicate_warning_message('naissance', duplicate_matches),
                    extra_tags='safe',
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
            messages.success(request, 'Déclaration mise à jour avec succès.')
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
    filters = _parse_dashboard_filters(request, default_period='30', default_limit=10)
    context = _build_mairie_dashboard_context(request.user, filters)

    if request.headers.get('HX-Request') == 'true':
        return render(request, 'naissances/partials/dashboard_mairie_content.html', context)
    return render(request, 'naissances/dashboard_mairie.html', context)


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
        old_status = _mark_declaration_validated(
            declaration,
            request.user,
            agent_field='agent_mairie',
        )

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
        f'Déclaration validée ! Acte N° <strong>{acte.numero_acte}</strong> généré.',
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

            messages.warning(request, 'Déclaration rejetée avec succès.')
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

def _parse_admin_dashboard_filters(request):
    return _parse_dashboard_filters(request, default_period='30', default_limit=10)


def _build_admin_dashboard_context(filters):
    now = timezone.now()
    period_days = filters['period_days']
    period_start = now - timedelta(days=period_days) if period_days else None

    naissance_qs = DeclarationNaissance.objects.all()
    mariage_qs = DeclarationMariage.objects.all()
    deces_qs = DeclarationDeces.objects.all()
    if period_start:
        naissance_qs = naissance_qs.filter(date_creation__gte=period_start)
        mariage_qs = mariage_qs.filter(date_creation__gte=period_start)
        deces_qs = deces_qs.filter(date_creation__gte=period_start)

    total = naissance_qs.count()
    stats = {
        'total': total,
        'en_attente': naissance_qs.filter(statut=DeclarationNaissance.Statut.EN_ATTENTE).count(),
        'valides': naissance_qs.filter(statut=DeclarationNaissance.Statut.VALIDE).count(),
        'rejetes': naissance_qs.filter(statut=DeclarationNaissance.Statut.REJETE).count(),
        'hopitaux': Hopital.objects.count(),
        'mairies': Mairie.objects.count(),
        'mariages': mariage_qs.count(),
        'deces': deces_qs.count(),
        'en_retard': naissance_qs.filter(
            statut__in=[DeclarationNaissance.Statut.EN_ATTENTE, DeclarationNaissance.Statut.EN_VERIFICATION],
            date_echeance__lt=now,
        ).count(),
    }
    stats['taux_validite'] = round((stats['valides'] / total) * 100) if total else 0

    declarations_filter = Q()
    declarations_valides_filter = Q(declarations__statut=DeclarationNaissance.Statut.VALIDE)
    if period_start:
        declarations_filter &= Q(declarations__date_creation__gte=period_start)
        declarations_valides_filter &= Q(declarations__date_creation__gte=period_start)

    hopitaux_stats = list(
        Hopital.objects.annotate(
            nb_declarations=Count('declarations', filter=declarations_filter),
            nb_valides=Count('declarations', filter=declarations_valides_filter),
        )
        .filter(nb_declarations__gt=0)
        .order_by('-nb_declarations', 'nom')[:10]
    )
    for hopital in hopitaux_stats:
        if hopital.nb_declarations:
            hopital.taux_validite = round((hopital.nb_valides / hopital.nb_declarations) * 100)
        else:
            hopital.taux_validite = 0

    recent = (
        naissance_qs.select_related('hopital', 'mairie')
        .order_by('-date_creation')[:filters['limite']]
    )

    return {
        'stats': stats,
        'hopitaux_stats': hopitaux_stats,
        'recent': recent,
        'filters': filters,
        'period_options': DASHBOARD_PERIOD_OPTIONS,
        'limit_options': DASHBOARD_LIMIT_OPTIONS,
        'chart_payload': {
            'statuses': [stats['en_attente'], stats['valides'], stats['rejetes']],
            'hospital_labels': [h.nom for h in hopitaux_stats],
            'hospital_totals': [h.nb_declarations for h in hopitaux_stats],
            'hospital_valides': [h.nb_valides for h in hopitaux_stats],
        },
    }


@login_required
@role_required('ADMIN')
def dashboard_admin(request):
    """Tableau de bord administrateur global."""
    filters = _parse_admin_dashboard_filters(request)
    context = _build_admin_dashboard_context(filters)

    if request.headers.get('HX-Request') == 'true':
        return render(request, 'naissances/partials/dashboard_admin_content.html', context)
    return render(request, 'naissances/dashboard_admin.html', context)


# ─────────────────────────────────────────────
# Anti-duplication dashboard
# ─────────────────────────────────────────────

@login_required
@role_required('HOPITAL', 'MAIRIE', 'ADMIN')
def duplicates_dashboard(request):
    """Dashboard anti-doublon multi-actes (naissance, mariage, décès)."""
    payload = _build_duplicates_dashboard_payload(request.user)
    return render(request, 'naissances/duplicates_dashboard.html', payload)


# ─────────────────────────────────────────────
# PDF Generation
# ─────────────────────────────────────────────

@login_required
def telecharger_acte_pdf(request, pk):
    """Générer et télécharger l'acte de naissance en PDF."""
    return _telecharger_acte_pdf(
        request,
        acte_model=ActeNaissance,
        pk=pk,
        template_name='naissances/acte_naissance_pdf.html',
        filename_prefix='acte',
        detail_url_name='naissances:declaration_detail',
        pdf_error_message="Erreur lors de la génération du PDF.",
    )


# ─────────────────────────────────────────────
# Mariages
# ─────────────────────────────────────────────


def _build_mariage_dashboard_context(user, filters):
    qs = DeclarationMariage.objects.select_related('mairie', 'agent_mairie')
    if user.role == 'MAIRIE' and user.mairie:
        qs = qs.filter(mairie=user.mairie)
    elif not (user.role == 'ADMIN' or user.is_superuser):
        qs = qs.none()

    period_days = filters['period_days']
    period_start = timezone.now() - timedelta(days=period_days) if period_days else None
    if period_start:
        qs = qs.filter(date_creation__gte=period_start)

    now = timezone.now()
    stats = {
        'total': qs.count(),
        'ce_mois': qs.filter(
            date_creation__month=now.month,
            date_creation__year=now.year,
        ).count(),
        'avec_temoins': qs.exclude(temoins='').count(),
        'en_attente': qs.filter(statut=DeclarationMariage.Statut.EN_ATTENTE).count(),
        'valides': qs.filter(statut=DeclarationMariage.Statut.VALIDE).count(),
        'rejetes': qs.filter(statut=DeclarationMariage.Statut.REJETE).count(),
        'en_retard': qs.filter(
            statut__in=[DeclarationMariage.Statut.EN_ATTENTE, DeclarationMariage.Statut.EN_VERIFICATION],
            date_echeance__lt=now,
        ).count(),
    }
    stats['taux_validite'] = round((stats['valides'] / stats['total']) * 100) if stats['total'] else 0
    recent = qs.order_by('-date_creation')[:filters['limite']]

    return {
        'stats': stats,
        'recent': recent,
        'filters': filters,
        'period_options': DASHBOARD_PERIOD_OPTIONS,
        'limit_options': DASHBOARD_LIMIT_OPTIONS,
    }


@login_required
@role_required('MAIRIE', 'ADMIN')
def mariage_dashboard(request):
    """Tableau de bord des mariages."""
    filters = _parse_dashboard_filters(request, default_period='30', default_limit=10)
    context = _build_mariage_dashboard_context(request.user, filters)

    if request.headers.get('HX-Request') == 'true':
        return render(request, 'naissances/partials/dashboard_mariage_content.html', context)
    return render(request, 'naissances/dashboard_mariage.html', context)


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
            duplicate_matches = _find_mariage_duplicate_matches(declaration)
            declaration.save()
            _log_mariage(declaration, 'CREATION', request.user, after=declaration.statut)
            messages.success(request, f'Déclaration de mariage enregistrée ({declaration.reference}).')
            if duplicate_matches:
                messages.warning(
                    request,
                    _build_duplicate_warning_message('mariage', duplicate_matches),
                    extra_tags='safe',
                )
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

    old_status = _mark_declaration_validated(
        declaration,
        request.user,
        agent_field='agent_mairie',
    )
    acte, _ = ActeMariage.objects.get_or_create(declaration=declaration)
    _log_mariage(declaration, 'VALIDATION', request.user, before=old_status, after=declaration.statut)
    if declaration.email_contact:
        email_sent = _send_mariage_validation_email(declaration, acte)
        if not email_sent:
            messages.warning(
                request,
                "Acte de mariage généré, mais la notification email au contact a échoué. L'équipe technique a été alertée."
            )
    messages.success(request, f'Mariage validé. Acte N° {acte.numero_acte} généré.')
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
    return _telecharger_acte_pdf(
        request,
        acte_model=ActeMariage,
        pk=pk,
        template_name='naissances/acte_mariage_pdf.html',
        filename_prefix='acte_mariage',
        detail_url_name='naissances:mariage_detail',
        required_status=DeclarationMariage.Statut.VALIDE,
        unavailable_message="L'acte n'est disponible qu'après validation.",
        pdf_error_message="Erreur lors de la génération du PDF de mariage.",
    )


# ─────────────────────────────────────────────
# Décès
# ─────────────────────────────────────────────


def _build_deces_dashboard_context(user, filters):
    qs = DeclarationDeces.objects.select_related('hopital', 'mairie', 'agent_createur')
    if user.role == 'HOPITAL' and user.hopital:
        qs = qs.filter(hopital=user.hopital)
    elif user.role == 'MAIRIE' and user.mairie:
        qs = qs.filter(mairie=user.mairie)
    elif not (user.role == 'ADMIN' or user.is_superuser):
        qs = qs.none()

    period_days = filters['period_days']
    period_start = timezone.now() - timedelta(days=period_days) if period_days else None
    if period_start:
        qs = qs.filter(date_creation__gte=period_start)

    now = timezone.now()
    stats = {
        'total': qs.count(),
        'ce_mois': qs.filter(
            date_creation__month=now.month,
            date_creation__year=now.year,
        ).count(),
        'avec_cause': qs.exclude(cause_deces='').count(),
        'en_attente': qs.filter(statut=DeclarationDeces.Statut.EN_ATTENTE).count(),
        'valides': qs.filter(statut=DeclarationDeces.Statut.VALIDE).count(),
        'rejetes': qs.filter(statut=DeclarationDeces.Statut.REJETE).count(),
        'en_retard': qs.filter(
            statut__in=[DeclarationDeces.Statut.EN_ATTENTE, DeclarationDeces.Statut.EN_VERIFICATION],
            date_echeance__lt=now,
        ).count(),
    }
    stats['taux_validite'] = round((stats['valides'] / stats['total']) * 100) if stats['total'] else 0
    recent = qs.order_by('-date_creation')[:filters['limite']]

    return {
        'stats': stats,
        'recent': recent,
        'filters': filters,
        'period_options': DASHBOARD_PERIOD_OPTIONS,
        'limit_options': DASHBOARD_LIMIT_OPTIONS,
    }


@login_required
@role_required('HOPITAL', 'MAIRIE', 'ADMIN')
def deces_dashboard(request):
    """Tableau de bord des décès."""
    filters = _parse_dashboard_filters(request, default_period='30', default_limit=10)
    context = _build_deces_dashboard_context(request.user, filters)

    if request.headers.get('HX-Request') == 'true':
        return render(request, 'naissances/partials/dashboard_deces_content.html', context)
    return render(request, 'naissances/dashboard_deces.html', context)


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
            duplicate_matches = _find_deces_duplicate_matches(declaration)
            declaration.save()
            _log_deces(declaration, 'CREATION', request.user, after=declaration.statut)
            messages.success(request, f'Déclaration de décès enregistrée ({declaration.reference}).')
            if duplicate_matches:
                messages.warning(
                    request,
                    _build_duplicate_warning_message('décès', duplicate_matches),
                    extra_tags='safe',
                )
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

    old_status = _mark_declaration_validated(
        declaration,
        request.user,
        agent_field='agent_traitement',
    )
    acte, _ = ActeDeces.objects.get_or_create(declaration=declaration)
    _log_deces(declaration, 'VALIDATION', request.user, before=old_status, after=declaration.statut)
    if declaration.email_contact:
        email_sent = _send_deces_validation_email(declaration, acte)
        if not email_sent:
            messages.warning(
                request,
                "Acte de décès généré, mais la notification email au contact a échoué. L'équipe technique a été alertée."
            )
    messages.success(request, f'Décès validé. Acte N° {acte.numero_acte} généré.')
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
    return _telecharger_acte_pdf(
        request,
        acte_model=ActeDeces,
        pk=pk,
        template_name='naissances/acte_deces_pdf.html',
        filename_prefix='acte_deces',
        detail_url_name='naissances:deces_detail',
        required_status=DeclarationDeces.Statut.VALIDE,
        unavailable_message="L'acte n'est disponible qu'après validation.",
        pdf_error_message="Erreur lors de la génération du PDF de décès.",
    )


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
