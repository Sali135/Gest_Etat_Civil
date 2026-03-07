"""URL patterns for naissances app."""
# API URL Django.
from django.urls import path
# Module contenant les fonctions de vue.
from . import views

app_name = 'naissances'

urlpatterns = [
    # Landing page publique (visiteurs + parents).
    path('', views.home_public, name='home_public'),

    # Dashboard router
    path('dashboard/', views.dashboard, name='dashboard'),
    path('dashboard/hopital/', views.dashboard_hopital, name='dashboard_hopital'),
    path('dashboard/mairie/', views.dashboard_mairie, name='dashboard_mairie'),
    path('dashboard/admin/', views.dashboard_admin, name='dashboard_admin'),
    path('dashboard/anti-doublons/', views.duplicates_dashboard, name='duplicates_dashboard'),

    # Declarations CRUD
    path('declarations/', views.declaration_list, name='declaration_list'),
    path('declarations/nouvelle/', views.declaration_create, name='declaration_create'),
    path('declarations/<int:pk>/', views.declaration_detail, name='declaration_detail'),
    path('declarations/<int:pk>/modifier/', views.declaration_edit, name='declaration_edit'),

    # Mairie actions
    path('declarations/<int:pk>/valider/', views.declaration_valider, name='declaration_valider'),
    path('declarations/<int:pk>/rejeter/', views.declaration_rejeter, name='declaration_rejeter'),
    path('declarations/<int:pk>/verification/', views.declaration_verification, name='declaration_verification'),

    # PDF download
    path('actes/<int:pk>/pdf/', views.telecharger_acte_pdf, name='telecharger_pdf'),

    # Public parent status lookup
    path('statut/', views.parent_status, name='parent_status'),

    # Mariages
    path('mariages/dashboard/', views.mariage_dashboard, name='mariage_dashboard'),
    path('mariages/', views.mariage_list, name='mariage_list'),
    path('mariages/nouveau/', views.mariage_create, name='mariage_create'),
    path('mariages/<int:pk>/', views.mariage_detail, name='mariage_detail'),
    path('mariages/<int:pk>/valider/', views.mariage_valider, name='mariage_valider'),
    path('mariages/<int:pk>/rejeter/', views.mariage_rejeter, name='mariage_rejeter'),
    path('mariages/<int:pk>/verification/', views.mariage_verification, name='mariage_verification'),
    path('mariages/actes/<int:pk>/pdf/', views.telecharger_acte_mariage_pdf, name='telecharger_mariage_pdf'),

    # Décès
    path('deces/dashboard/', views.deces_dashboard, name='deces_dashboard'),
    path('deces/', views.deces_list, name='deces_list'),
    path('deces/nouveau/', views.deces_create, name='deces_create'),
    path('deces/<int:pk>/', views.deces_detail, name='deces_detail'),
    path('deces/<int:pk>/valider/', views.deces_valider, name='deces_valider'),
    path('deces/<int:pk>/rejeter/', views.deces_rejeter, name='deces_rejeter'),
    path('deces/<int:pk>/verification/', views.deces_verification, name='deces_verification'),
    path('deces/actes/<int:pk>/pdf/', views.telecharger_acte_deces_pdf, name='telecharger_deces_pdf'),
]
