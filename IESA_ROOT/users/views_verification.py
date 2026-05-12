"""
Compatibility shim — Block 7 рефакторинг.

Весь код перенесён в users/views/ пакет (субмодули).
Этот файл сохраняется только для любых внешних импортов, которые ещё
не обновлены. Не добавляйте сюда новый код.
"""
from users.views import (  # noqa: F401
    _try_parse_uuid, is_partner, partner_required,
    public_profile, server_time,
    partner_dashboard, log_visit, edit_visit, cancel_visit,
    partner_member_visits, partner_analytics, partner_profile_edit,
    test_telegram_view, connect_telegram_code_view, disconnect_telegram_view,
    telegram_login_callback_view, telegram_webhook_view,
    invite_list, invite_generate, invite_register,
    MeetingForm, partner_calendar, delete_meeting, user_calendar,
    insurance_agent_request,
)
