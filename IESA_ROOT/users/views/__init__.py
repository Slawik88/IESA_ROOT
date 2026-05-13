"""
users/views/ — пакет представлений (Block 7 рефакторинг).

Ранее всё находилось в:
  - users/views.py (авторизация, профиль, поиск, QR)
  - users/views_verification.py (партнёрский портал, TG, инвайты, календарь, страхование)

Теперь разбито по тематическим модулям. Этот __init__.py re-экспортирует
все публичные view-функции для обратной совместимости с urls.py.
"""

# ── Auth ─────────────────────────────────────────────────────────────────────
from .auth import RegisterView, LoginView, logout_view

# ── Profile ───────────────────────────────────────────────────────────────────
from .profile import (
    ProfileView, ProfileEditView,
    _get_public_profile_context,
    profile_public_by_username,
    profile_public_by_card,
    profile_deactivate,
    dashboard_redirect,
)

# ── Search ────────────────────────────────────────────────────────────────────
from .search import users_search

# ── QR & Activity ─────────────────────────────────────────────────────────────
from .qr import qr_image, activity_levels_info

# ── Admin utilities ───────────────────────────────────────────────────────────
from .admin_utils import impersonate_user, account_change_request_submit

# ── Shared utilities (partner_required, public_profile, server_time, etc.) ────
from .utils import (
    _try_parse_uuid, is_partner, partner_required,
    public_profile, server_time,
)

# ── Partner portal ────────────────────────────────────────────────────────────
from .partner import (
    partner_dashboard,
    log_visit, edit_visit, cancel_visit,
    partner_member_visits,
    partner_analytics,
    partner_profile_edit,
    partner_today_stats,
    partner_visit_history,
    partner_visits_csv,
)

# ── Calendar ──────────────────────────────────────────────────────────────────
from .calendar import (
    MeetingForm,
    partner_calendar, delete_meeting, user_calendar, user_calendar_ics,
)

# ── Telegram views ────────────────────────────────────────────────────────────
from .telegram_views import (
    test_telegram_view,
    connect_telegram_code_view,
    disconnect_telegram_view,
    telegram_login_callback_view,
    telegram_webhook_view,
)

# ── Invites ───────────────────────────────────────────────────────────────────
from .invites import invite_list, invite_generate, invite_register

# ── Insurance ─────────────────────────────────────────────────────────────────
from .insurance import insurance_agent_request

# ── Onboarding (Block 1) ──────────────────────────────────────────────────────
from .onboarding import (
    mark_onboarded, username_available, email_available,
    how_it_works, member_autocomplete, profile_field_save,
)

__all__ = [
    'RegisterView', 'LoginView', 'logout_view',
    'ProfileView', 'ProfileEditView', '_get_public_profile_context',
    'profile_public_by_username', 'profile_public_by_card',
    'profile_deactivate', 'dashboard_redirect',
    'users_search',
    'qr_image', 'activity_levels_info',
    'impersonate_user', 'account_change_request_submit',
    '_try_parse_uuid', 'is_partner', 'partner_required',
    'public_profile', 'server_time',
    'partner_dashboard', 'log_visit', 'edit_visit', 'cancel_visit',
    'partner_member_visits', 'partner_analytics', 'partner_profile_edit',
    'MeetingForm', 'partner_calendar', 'delete_meeting', 'user_calendar',
    'test_telegram_view', 'connect_telegram_code_view', 'disconnect_telegram_view',
    'telegram_login_callback_view', 'telegram_webhook_view',
    'invite_list', 'invite_generate', 'invite_register',
    'insurance_agent_request',
]
