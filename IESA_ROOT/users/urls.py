from django.urls import path
from . import views
from . import views_verification

app_name = 'users'

urlpatterns = [
    # Telegram webhook (public endpoint for Telegram servers)
    path('telegram/webhook/<slug:secret>/', views_verification.telegram_webhook_view, name='telegram_webhook'),

    # Авторизация
    path('register/', views.RegisterView.as_view(), name='register'),
    path('login/', views.LoginView.as_view(), name='login'),
    path('logout/', views.logout_view, name='logout'),
    
    # Профиль
    path('profile/', views.ProfileView.as_view(), name='profile'),
    path('profile/edit/', views.ProfileEditView.as_view(), name='profile_edit'),
    path('profile/deactivate/', views.profile_deactivate, name='profile_deactivate'),
    # Public profiles by username and by permanent card ID (QR)
    path('user/<str:username>/', views.profile_public_by_username, name='profile_public_username'),
    path('card/<uuid:permanent_id>/', views.profile_public_by_card, name='profile_by_card'),
    
    # MEMBERSHIP VERIFICATION SYSTEM
    # Public profile view for QR code scanning
    path('profile/<uuid:uuid>/public/', views_verification.public_profile, name='public_profile'),
    # Member personal cabinet with current PIN
    path('cabinet/', views_verification.member_cabinet, name='member_cabinet'),
    # Partner dashboard
    path('partner/dashboard/', views_verification.partner_dashboard, name='partner_dashboard'),
    # Partner analytics
    path('partner/analytics/', views_verification.partner_analytics, name='partner_analytics'),
    # Partner profile edit
    path('partner/profile/', views_verification.partner_profile_edit, name='partner_profile_edit'),
    # Log visit for a specific member
    path('partner/visit/<int:member_id>/', views_verification.log_visit, name='log_visit'),
    # Per-member full visit history at this partner
    path('partner/member/<int:member_id>/', views_verification.partner_member_visits, name='partner_member_visits'),
    # Edit / cancel a visit (20-min window)
    path('partner/visit/<int:visit_id>/edit/', views_verification.edit_visit, name='edit_visit'),
    path('partner/visit/<int:visit_id>/cancel/', views_verification.cancel_visit, name='cancel_visit'),
    # Telegram bot test page (staff only)
    path('partner/test-telegram/', views_verification.test_telegram_view, name='test_telegram'),
    # Telegram linking (Method A: code from bot)
    path('connect-telegram/', views_verification.connect_telegram_code_view, name='connect_telegram_code'),
    path('disconnect-telegram/', views_verification.disconnect_telegram_view, name='disconnect_telegram'),
    # Telegram Login Widget callback (Method B)
    path('telegram/login-callback/', views_verification.telegram_login_callback_view, name='telegram_login_callback'),
    # Server time API
    path('api/time/', views_verification.server_time, name='server_time'),
    
    # Serve QR image (generates if missing). Use as image src and download link.
    path('qr/<uuid:permanent_id>/', views.qr_image, name='user_qr'),
    # User search
    path('search/', views.users_search, name='users_search'),
    # Activity levels info
    path('activity-levels/', views.activity_levels_info, name='activity_levels_info'),
    # Admin impersonation
    path('impersonate/<int:pk>/', views.impersonate_user, name='impersonate_user'),
]