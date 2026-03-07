# Récupère dynamiquement le modèle utilisateur actif (CustomUser ici).
from django.contrib.auth import get_user_model
# Base de test Django.
from django.test import TestCase
# Reverse URL par nom de route.
from django.urls import reverse
# Utilitaires date/heure.
from django.utils import timezone
from datetime import timedelta
from unittest.mock import patch

# Formulaire testé.
from .forms import DeclarationNaissanceForm
# Modèles métiers testés.
from .models import ActeNaissance, DeclarationNaissance, Hopital, Mairie
from .models import DeclarationMariage, DeclarationDeces
# Serializer testé.
from .serializers import DeclarationDecesCreateSerializer

# Alias du modèle utilisateur pour les fixtures de test.
User = get_user_model()


class WorkflowSecurityTests(TestCase):
    """Tests couvrant sécurité workflow + validations critiques."""
    def setUp(self):
        # Données de base communes à tous les tests.
        self.hopital = Hopital.objects.create(
            nom='CHU Test',
            adresse='Adresse Test',
            contact='+22500000000'
        )
        self.mairie = Mairie.objects.create(
            nom='Mairie Test',
            adresse='Adresse Mairie',
            contact='+22511111111',
            ville='Testville'
        )

    def test_hopital_agent_without_hopital_cannot_create_declaration(self):
        # Cas: agent hôpital non affecté -> création interdite.
        user = User.objects.create_user(
            username='hopital_sans_affectation',
            password='testpass123',
            role='HOPITAL',
        )
        self.client.login(username='hopital_sans_affectation', password='testpass123')

        response = self.client.post(
            reverse('naissances:declaration_create'),
            data={
                'nom_enfant': 'Bamba',
                'prenom_enfant': 'Aya',
                'sexe': 'F',
                'date_naissance': '2026-01-15',
                'lieu_naissance': 'Maternite A',
                'nom_pere': 'Koffi Bamba',
                'nom_mere': 'Awa Bamba',
                'mairie': self.mairie.id,
            }
        )

        self.assertRedirects(response, reverse('naissances:dashboard_hopital'))
        # Aucun enregistrement ne doit être créé.
        self.assertEqual(DeclarationNaissance.objects.count(), 0)

    def test_validation_creates_single_acte(self):
        # Cas: double clic / double POST de validation ne doit pas dupliquer l'acte.
        mairie_user = User.objects.create_user(
            username='agent_mairie',
            password='testpass123',
            role='MAIRIE',
            mairie=self.mairie,
        )
        declaration = DeclarationNaissance.objects.create(
            nom_enfant='Nguessan',
            prenom_enfant='Junior',
            date_naissance='2026-01-02',
            lieu_naissance='Salle 2',
            sexe='M',
            nom_pere='Yao Nguessan',
            nom_mere='Akissi Nguessan',
            hopital=self.hopital,
            mairie=self.mairie,
        )

        self.client.login(username='agent_mairie', password='testpass123')
        url = reverse('naissances:declaration_valider', kwargs={'pk': declaration.pk})

        first_response = self.client.post(url)
        declaration.refresh_from_db()

        self.assertEqual(first_response.status_code, 302)
        self.assertEqual(declaration.statut, DeclarationNaissance.Statut.VALIDE)
        # Idempotence: exactement un acte après première validation.
        self.assertEqual(ActeNaissance.objects.filter(declaration=declaration).count(), 1)

        second_response = self.client.post(url)
        self.assertEqual(second_response.status_code, 302)
        # Idempotence: toujours un seul acte après deuxième validation.
        self.assertEqual(ActeNaissance.objects.filter(declaration=declaration).count(), 1)

    def test_api_stats_allows_admin_role(self):
        # Cas: rôle ADMIN applicatif (sans flag staff initial) autorisé à /api/stats/.
        admin_role_user = User.objects.create_user(
            username='admin_role_user',
            password='testpass123',
            role='ADMIN',
            is_staff=False,
        )
        self.client.login(username='admin_role_user', password='testpass123')

        response = self.client.get(reverse('api:stats'))
        self.assertEqual(response.status_code, 200)

    def test_api_stats_denies_non_admin(self):
        # Cas: agent MAIRIE non admin -> accès refusé.
        mairie_user = User.objects.create_user(
            username='agent_mairie_2',
            password='testpass123',
            role='MAIRIE',
            mairie=self.mairie,
        )
        self.client.login(username='agent_mairie_2', password='testpass123')

        response = self.client.get(reverse('api:stats'))
        self.assertEqual(response.status_code, 403)

    def test_admin_dashboard_htmx_returns_partial_with_filters(self):
        admin_user = User.objects.create_user(
            username='admin_dashboard_htmx',
            password='testpass123',
            role='ADMIN',
        )
        DeclarationNaissance.objects.create(
            nom_enfant='Kaba',
            prenom_enfant='Noe',
            date_naissance='2026-01-05',
            lieu_naissance='Hopital Central',
            sexe='M',
            nom_pere='Jean Kaba',
            nom_mere='Maya Kaba',
            hopital=self.hopital,
            mairie=self.mairie,
            statut=DeclarationNaissance.Statut.VALIDE,
        )

        self.client.login(username='admin_dashboard_htmx', password='testpass123')
        response = self.client.get(
            reverse('naissances:dashboard_admin'),
            {'periode': '30', 'limite': '5'},
            HTTP_HX_REQUEST='true',
        )

        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'naissances/partials/dashboard_admin_content.html')
        self.assertContains(response, 'id="dashboard-admin-content"', html=False)
        self.assertContains(response, 'dashboard-admin-chart-data')
        self.assertEqual(response.context['filters']['periode'], '30')
        self.assertEqual(response.context['filters']['limite'], 5)

    def test_hopital_dashboard_htmx_returns_partial_with_filters(self):
        hopital_user = User.objects.create_user(
            username='hopital_dashboard_htmx',
            password='testpass123',
            role='HOPITAL',
            hopital=self.hopital,
        )
        DeclarationNaissance.objects.create(
            nom_enfant='Mina',
            prenom_enfant='Kai',
            date_naissance='2026-01-08',
            lieu_naissance='Maternite A',
            sexe='F',
            nom_pere='Paul Mina',
            nom_mere='Anne Mina',
            hopital=self.hopital,
            mairie=self.mairie,
            statut=DeclarationNaissance.Statut.EN_ATTENTE,
        )

        self.client.login(username='hopital_dashboard_htmx', password='testpass123')
        response = self.client.get(
            reverse('naissances:dashboard_hopital'),
            {'periode': '30', 'limite': '5'},
            HTTP_HX_REQUEST='true',
        )

        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'naissances/partials/dashboard_hopital_content.html')
        self.assertContains(response, 'id="dashboard-hopital-content"', html=False)
        self.assertEqual(response.context['filters']['periode'], '30')
        self.assertEqual(response.context['filters']['limite'], 5)

    def test_mairie_dashboard_htmx_returns_partial_with_filters(self):
        mairie_user = User.objects.create_user(
            username='mairie_dashboard_htmx',
            password='testpass123',
            role='MAIRIE',
            mairie=self.mairie,
        )
        DeclarationNaissance.objects.create(
            nom_enfant='Mina',
            prenom_enfant='Noa',
            date_naissance='2026-01-09',
            lieu_naissance='Maternite A',
            sexe='M',
            nom_pere='Paul Mina',
            nom_mere='Anne Mina',
            hopital=self.hopital,
            mairie=self.mairie,
            statut=DeclarationNaissance.Statut.EN_ATTENTE,
        )

        self.client.login(username='mairie_dashboard_htmx', password='testpass123')
        response = self.client.get(
            reverse('naissances:dashboard_mairie'),
            {'periode': '30', 'limite': '5'},
            HTTP_HX_REQUEST='true',
        )

        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'naissances/partials/dashboard_mairie_content.html')
        self.assertContains(response, 'id="dashboard-mairie-content"', html=False)
        self.assertEqual(response.context['filters']['periode'], '30')
        self.assertEqual(response.context['filters']['limite'], 5)

    def test_mariage_dashboard_htmx_returns_partial_with_filters(self):
        mairie_user = User.objects.create_user(
            username='mairie_dashboard_mariage_htmx',
            password='testpass123',
            role='MAIRIE',
            mairie=self.mairie,
        )
        DeclarationMariage.objects.create(
            nom_epoux='Paul Test',
            nom_epouse='Anne Test',
            date_mariage='2026-01-10',
            lieu_mariage='Salle des fêtes',
            mairie=self.mairie,
            statut=DeclarationMariage.Statut.EN_ATTENTE,
        )

        self.client.login(username='mairie_dashboard_mariage_htmx', password='testpass123')
        response = self.client.get(
            reverse('naissances:mariage_dashboard'),
            {'periode': '30', 'limite': '5'},
            HTTP_HX_REQUEST='true',
        )

        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'naissances/partials/dashboard_mariage_content.html')
        self.assertContains(response, 'id="dashboard-mariage-content"', html=False)
        self.assertEqual(response.context['filters']['periode'], '30')
        self.assertEqual(response.context['filters']['limite'], 5)

    def test_deces_dashboard_htmx_returns_partial_with_filters(self):
        mairie_user = User.objects.create_user(
            username='mairie_dashboard_deces_htmx',
            password='testpass123',
            role='MAIRIE',
            mairie=self.mairie,
        )
        DeclarationDeces.objects.create(
            nom_defunt='Doe',
            prenom_defunt='John',
            sexe='M',
            date_deces='2026-01-11',
            lieu_deces='Hopital Central',
            declarant_nom='Jane Doe',
            hopital=self.hopital,
            mairie=self.mairie,
            statut=DeclarationDeces.Statut.EN_ATTENTE,
        )

        self.client.login(username='mairie_dashboard_deces_htmx', password='testpass123')
        response = self.client.get(
            reverse('naissances:deces_dashboard'),
            {'periode': '30', 'limite': '5'},
            HTTP_HX_REQUEST='true',
        )

        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'naissances/partials/dashboard_deces_content.html')
        self.assertContains(response, 'id="dashboard-deces-content"', html=False)
        self.assertEqual(response.context['filters']['periode'], '30')
        self.assertEqual(response.context['filters']['limite'], 5)

    def test_naissance_form_rejects_future_birth_date(self):
        # Cas: date naissance future refusée par validation formulaire.
        future_date = timezone.localdate() + timedelta(days=1)
        form = DeclarationNaissanceForm(data={
            'nom_enfant': 'Bamba',
            'prenom_enfant': 'Aya',
            'sexe': 'F',
            'date_naissance': future_date,
            'lieu_naissance': 'Maternite A',
            'nom_pere': 'Koffi Bamba',
            'nom_mere': 'Awa Bamba',
            'mairie': self.mairie.id,
        })
        self.assertFalse(form.is_valid())
        self.assertIn('date_naissance', form.errors)

    def test_deces_create_serializer_rejects_future_death_date(self):
        # Cas: date décès future refusée côté serializer API.
        future_date = timezone.localdate() + timedelta(days=1)
        serializer = DeclarationDecesCreateSerializer(data={
            'priorite': 'NORMALE',
            'nom_defunt': 'Doe',
            'prenom_defunt': 'John',
            'sexe': 'M',
            'date_deces': future_date,
            'lieu_deces': 'Hopital Central',
            'cause_deces': 'N/A',
            'declarant_nom': 'Jane Doe',
            'declarant_lien': 'Soeur',
            'hopital': self.hopital.id,
            'mairie': self.mairie.id,
        })
        self.assertFalse(serializer.is_valid())
        self.assertIn('date_deces', serializer.errors)

    def test_expected_declaration_indexes_are_present(self):
        # Vérifie que les index critiques existent côté metadata modèle.
        index_names = {index.name for index in DeclarationNaissance._meta.indexes}
        self.assertIn('dn_mairie_statut_idx', index_names)
        self.assertIn('dn_hopital_statut_idx', index_names)
        self.assertIn('dn_date_creation_idx', index_names)
        self.assertIn('dn_date_echeance_idx', index_names)

    def test_public_home_page_is_available(self):
        response = self.client.get(reverse('naissances:home_public'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Vérifier un acte')

    def test_parent_status_allows_get_reference_lookup(self):
        declaration = DeclarationNaissance.objects.create(
            nom_enfant='Nina',
            prenom_enfant='Dia',
            date_naissance='2026-01-03',
            lieu_naissance='Maternite B',
            sexe='F',
            nom_pere='Jean Dia',
            nom_mere='Marie Dia',
            hopital=self.hopital,
            mairie=self.mairie,
        )
        url = f"{reverse('naissances:parent_status')}?reference={declaration.reference}"
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, declaration.reference)

    @patch('naissances.views.send_mail', return_value=1)
    def test_mariage_validation_sends_contact_email(self, mock_send_mail):
        mairie_user = User.objects.create_user(
            username='agent_mairie_mail_m',
            password='testpass123',
            role='MAIRIE',
            mairie=self.mairie,
        )
        declaration = DeclarationMariage.objects.create(
            nom_epoux='Paul Test',
            nom_epouse='Anne Test',
            date_mariage='2026-01-10',
            lieu_mariage='Salle des fetes',
            mairie=self.mairie,
            email_contact='couple@example.com',
        )
        self.client.login(username='agent_mairie_mail_m', password='testpass123')
        response = self.client.post(reverse('naissances:mariage_valider', kwargs={'pk': declaration.pk}))
        self.assertEqual(response.status_code, 302)
        self.assertTrue(mock_send_mail.called)

    @patch('naissances.views.send_mail', return_value=1)
    def test_deces_validation_sends_contact_email(self, mock_send_mail):
        mairie_user = User.objects.create_user(
            username='agent_mairie_mail_d',
            password='testpass123',
            role='MAIRIE',
            mairie=self.mairie,
        )
        declaration = DeclarationDeces.objects.create(
            nom_defunt='Doe',
            prenom_defunt='John',
            sexe='M',
            date_deces='2026-01-11',
            lieu_deces='Hopital',
            declarant_nom='Jane Doe',
            mairie=self.mairie,
            email_contact='contact@example.com',
        )
        self.client.login(username='agent_mairie_mail_d', password='testpass123')
        response = self.client.post(reverse('naissances:deces_valider', kwargs={'pk': declaration.pk}))
        self.assertEqual(response.status_code, 302)
        self.assertTrue(mock_send_mail.called)

    def test_duplicates_dashboard_lists_exact_duplicates_for_mairie(self):
        mairie_user = User.objects.create_user(
            username='agent_mairie_duplicates',
            password='testpass123',
            role='MAIRIE',
            mairie=self.mairie,
        )
        d1 = DeclarationNaissance.objects.create(
            nom_enfant='Kouassi',
            prenom_enfant='Nina',
            date_naissance='2026-02-12',
            lieu_naissance='Maternite Centrale',
            sexe='F',
            nom_pere='Kouassi Paul',
            nom_mere='Awa Nina',
            hopital=self.hopital,
            mairie=self.mairie,
        )
        d2 = DeclarationNaissance.objects.create(
            nom_enfant='Kouassi',
            prenom_enfant='Nina',
            date_naissance='2026-02-12',
            lieu_naissance='Maternite Centrale',
            sexe='F',
            nom_pere='Kouassi Paul',
            nom_mere='Awa Nina',
            hopital=self.hopital,
            mairie=self.mairie,
        )

        self.client.login(username='agent_mairie_duplicates', password='testpass123')
        response = self.client.get(reverse('naissances:duplicates_dashboard'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Contrôle anti-doublons')
        self.assertContains(response, d1.reference)
        self.assertContains(response, d2.reference)
        self.assertContains(response, 'Exact')

    def test_naissance_create_shows_duplicate_warning(self):
        hopital_user = User.objects.create_user(
            username='agent_hopital_duplicates',
            password='testpass123',
            role='HOPITAL',
            hopital=self.hopital,
        )
        DeclarationNaissance.objects.create(
            nom_enfant='Bamba',
            prenom_enfant='Aya',
            date_naissance='2026-02-15',
            lieu_naissance='Maternite A',
            sexe='F',
            nom_pere='Koffi Bamba',
            nom_mere='Awa Bamba',
            hopital=self.hopital,
            mairie=self.mairie,
        )

        self.client.login(username='agent_hopital_duplicates', password='testpass123')
        response = self.client.post(
            reverse('naissances:declaration_create'),
            data={
                'nom_enfant': 'Bamba',
                'prenom_enfant': 'Aya',
                'sexe': 'F',
                'date_naissance': '2026-02-15',
                'lieu_naissance': 'Maternite A',
                'nom_pere': 'Koffi Bamba',
                'nom_mere': 'Awa Bamba',
                'mairie': self.mairie.id,
            },
            follow=True,
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(DeclarationNaissance.objects.count(), 2)
        self.assertContains(response, 'Alerte anti-doublon (naissance)')
