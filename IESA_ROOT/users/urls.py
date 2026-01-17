from django.urls import path
from . import views
from django.contrib.auth import views as auth_views

urlpatterns = [
    # Авторизация
    path('register/', views.RegisterView.as_view(), name='register'),
    path('login/', views.LoginView.as_view(), name='login'),
    path('logout/', views.logout_view, name='logout'),
    
    # Профиль
    path('profile/', views.ProfileView.as_view(), name='profile'),
    path('profile/edit/', views.ProfileEditView.as_view(), name='profile_edit'),
    # Public profiles by username and by permanent card ID (QR)
    path('user/<str:username>/', views.profile_public_by_username, name='profile_public_username'),
    path('card/<uuid:permanent_id>/', views.profile_public_by_card, name='profile_by_card'),
    # Serve QR image (generates if missing). Use as image src and download link.
    path('qr/<uuid:permanent_id>/', views.qr_image, name='user_qr'),
    # User search
    path('search/', views.users_search, name='users_search'),
    # Activity levels info
    path('activity-levels/', views.activity_levels_info, name='activity_levels_info'),
    # Admin impersonation
    path('impersonate/<int:pk>/', views.impersonate_user, name='impersonate_user'),
]