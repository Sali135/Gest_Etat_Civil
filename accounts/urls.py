"""URL patterns for accounts app."""
# Routeur URL Django.
from django.urls import path
# Vues de l'application comptes.
from .views import (
    CustomLoginView, CustomLogoutView, admin_users, admin_mairies,
    admin_user_edit, admin_user_toggle_active, admin_user_delete,
    admin_mairie_edit, admin_mairie_delete,
)

app_name = 'accounts'

urlpatterns = [
    # Authentification (connexion/déconnexion).
    path('login/', CustomLoginView.as_view(), name='login'),
    path('logout/', CustomLogoutView.as_view(), name='logout'),
    # Administration applicative des utilisateurs.
    path('admin/utilisateurs/', admin_users, name='admin_users'),
    path('admin/utilisateurs/<int:pk>/modifier/', admin_user_edit, name='admin_user_edit'),
    path('admin/utilisateurs/<int:pk>/toggle-active/', admin_user_toggle_active, name='admin_user_toggle_active'),
    path('admin/utilisateurs/<int:pk>/supprimer/', admin_user_delete, name='admin_user_delete'),
    # Administration applicative des mairies.
    path('admin/mairies/', admin_mairies, name='admin_mairies'),
    path('admin/mairies/<int:pk>/modifier/', admin_mairie_edit, name='admin_mairie_edit'),
    path('admin/mairies/<int:pk>/supprimer/', admin_mairie_delete, name='admin_mairie_delete'),
]
