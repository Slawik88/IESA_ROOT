from django.urls import path
from django.views.generic import RedirectView
from . import views

app_name = 'users'

urlpatterns = [
    # Telegram webhook (public, called by Telegram servers)
    path('telegram/webhook/<slug:secret>/', views.telegram_webhook_view, name='telegram_webhook'),

    # Auth
    path('register/', views.RegisterView.as_view(), name='register'),
    path('login/',    views.LoginView.as_view(),    name='login'),
    path('logout/',   views.logout_view,             name='logout'),

    # Profile
    path('profile/',            views.ProfileView.as_view(),   name='profile'),
    path('profile/edit/',       views.ProfileEditView.as_view(), name='profile_edit'),
    path('profile/deactivate/', views.profile_deactivate,      name='profile_deactivate'),
    path('user/<str:username>/', views.profile_public_by_username, name='profile_public_username'),
    path('card/<uuid:permanent_id>/', views.profile_public_by_card, name='profile_by_card'),

    # Membership verification
    path('profile/<uuid:uuid>/public/', views.public_profile, name='public_profile'),
    # /cabinet/ removed — Block 1: 301 redirect to profile#pin-section
    path('cabinet/', RedirectView.as_view(url='/auth/profile/#pin-section', permanent=True), name='member_cabinet'),

    # Partner portal
    path('partner/dashboard/', views.partner_dashboard, name='partner_dashboard'),
    path('partner/analytics/', views.partner_analytics, name='partner_analytics'),
    path('partner/profile/',   views.partner_profile_edit, name='partner_profile_edit'),
    path('partner/visit/<int:member_id>/', views.log_visit, name='log_visit'),
    path('partner/member/<int:member_id>/', views.partner_member_visits, name='partner_member_visits'),
    path('partner/visit/<int:visit_id>/edit/',   views.edit_visit,   name='edit_visit'),
    path('partner/visit/<int:visit_id>/cancel/', views.cancel_visit, name='cancel_visit'),
    path('partner/test-telegram/', views.test_telegram_view, name='test_telegram'),
    # 7a/7b/7e: real-time stats, filtered history, CSV export
    path('partner/stats/',         views.partner_today_stats,    name='partner_today_stats'),
    path('partner/history/',       views.partner_visit_history,  name='partner_visit_history'),
    path('partner/visits.csv',     views.partner_visits_csv,     name='partner_visits_csv'),

    # Telegram linking
    path('connect-telegram/',          views.connect_telegram_code_view,   name='connect_telegram_code'),
    path('disconnect-telegram/',       views.disconnect_telegram_view,     name='disconnect_telegram'),
    path('telegram/login-callback/',   views.telegram_login_callback_view, name='telegram_login_callback'),

    # API
    path('api/time/', views.server_time, name='server_time'),

    # QR & search
    path('qr/<uuid:permanent_id>/',  views.qr_image,     name='user_qr'),
    path('search/',                  views.users_search, name='users_search'),
    path('activity-levels/',         views.activity_levels_info, name='activity_levels_info'),

    # Admin tools
    path('impersonate/<int:pk>/',  views.impersonate_user,              name='impersonate_user'),
    path('dashboard/',             views.dashboard_redirect,            name='dashboard'),
    path('account-upgrade/',       views.account_change_request_submit, name='account_upgrade'),

    # Invites
    path('invite/',                views.invite_list,     name='invite_list'),
    path('invite/generate/',       views.invite_generate, name='invite_generate'),
    path('invite/<uuid:token>/',   views.invite_register, name='invite_register'),

    # Calendar
    path('partner/calendar/',                  views.partner_calendar, name='partner_calendar'),
    path('partner/meeting/<int:meeting_id>/cancel/', views.delete_meeting, name='delete_meeting'),
    path('my-calendar/',                       views.user_calendar,    name='user_calendar'),
    path('my-calendar/export.ics',             views.user_calendar_ics, name='user_calendar_ics'),

    # Insurance agent
    path('insurance-agent/', views.insurance_agent_request, name='insurance_agent'),

    # Onboarding (Block 1)
    path('onboarded/',         views.mark_onboarded,    name='mark_onboarded'),
    path('check-username/',    views.username_available, name='username_available'),
    path('check-email/',       views.email_available,    name='email_available'),
    path('how-it-works/',                  views.how_it_works,        name='how_it_works'),
    path('partner/member-autocomplete/',   views.member_autocomplete, name='member_autocomplete'),
    path('profile/field-save/',            views.profile_field_save,  name='profile_field_save'),

    # Interactive tour completion (Tour system 2026-05-27)
    path('tour/<str:tour_name>/complete/', views.mark_tour_completed, name='mark_tour_completed'),
]
