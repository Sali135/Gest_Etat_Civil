"""API URL patterns for naissances app."""
# Définition des routes API DRF.
from django.urls import path
# Classes de vues API.
from .api_views import (
    DeclarationListCreateAPIView,
    DeclarationDetailAPIView,
    MariageListCreateAPIView,
    MariageDetailAPIView,
    MariageValiderAPIView,
    MariageRejeterAPIView,
    DecesListCreateAPIView,
    DecesDetailAPIView,
    DecesValiderAPIView,
    DecesRejeterAPIView,
    HopitalListAPIView,
    MairieListAPIView,
    APIStatsView,
)

app_name = 'api'

urlpatterns = [
    # Naissances
    path('declarations/', DeclarationListCreateAPIView.as_view(), name='declaration-list'),
    path('declarations/<int:pk>/', DeclarationDetailAPIView.as_view(), name='declaration-detail'),
    # Mariages
    path('mariages/', MariageListCreateAPIView.as_view(), name='mariage-list'),
    path('mariages/<int:pk>/', MariageDetailAPIView.as_view(), name='mariage-detail'),
    path('mariages/<int:pk>/valider/', MariageValiderAPIView.as_view(), name='mariage-valider'),
    path('mariages/<int:pk>/rejeter/', MariageRejeterAPIView.as_view(), name='mariage-rejeter'),
    # Décès
    path('deces/', DecesListCreateAPIView.as_view(), name='deces-list'),
    path('deces/<int:pk>/', DecesDetailAPIView.as_view(), name='deces-detail'),
    path('deces/<int:pk>/valider/', DecesValiderAPIView.as_view(), name='deces-valider'),
    path('deces/<int:pk>/rejeter/', DecesRejeterAPIView.as_view(), name='deces-rejeter'),
    # Référentiels et statistiques
    path('hopitaux/', HopitalListAPIView.as_view(), name='hopital-list'),
    path('mairies/', MairieListAPIView.as_view(), name='mairie-list'),
    path('stats/', APIStatsView.as_view(), name='stats'),
]
