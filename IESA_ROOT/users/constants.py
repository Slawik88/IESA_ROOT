"""User app constants and configuration data."""
from django.utils.translation import gettext_lazy as _

# ── PIN / TOTP ──────────────────────────────────────────────────────────────
PIN_INTERVAL = 720   # секунды между сменами PIN (12 мин)
PIN_LENGTH   = 6     # количество цифр в PIN

# ── QR-код ──────────────────────────────────────────────────────────────────
QR_CACHE_TTL = 3600  # секунды хранения QR в кэше (1 час)

# ── Telegram webhook ────────────────────────────────────────────────────────
WEBHOOK_RATE_LIMIT = 300  # максимум запросов/мин с одного IP

# ── Пагинация ────────────────────────────────────────────────────────────────
PROFILE_POSTS_PER_PAGE  = 12
SEARCH_RESULTS_PER_PAGE = 20
PARTNER_VISITS_PER_PAGE = 15
PARTNER_HISTORY_LIMIT   = 20
CABINET_VISITS_LIMIT    = 20  # последних визитов в истории кабинета

# Activity level definitions
# FIX: Extracted from views.py to make it reusable and testable
ACTIVITY_LEVELS = [
    {
        'name': _('Beginner'),
        'icon': 'leaf',
        'color': 'secondary',
        'min_points': 0,
        'max_points': 50,
        'description': _('Just starting your journey in the IESA community'),
        'tips': [
            _('Create your first blog post (10 points)'),
            _('Leave comments on other posts (1 point each)'),
            _('Engage with the community'),
        ]
    },
    {
        'name': _('Intermediate'),
        'icon': 'fire',
        'color': 'success',
        'min_points': 50,
        'max_points': 200,
        'description': _('You\'re becoming an active member'),
        'tips': [
            _('Publish 5-10 quality posts (10 points each)'),
            _('Receive 50+ likes on your posts (2 points each)'),
            _('Participate in discussions'),
        ]
    },
    {
        'name': _('Advanced'),
        'icon': 'rocket',
        'color': 'info',
        'min_points': 200,
        'max_points': 500,
        'description': _('You\'re a valuable contributor'),
        'tips': [
            _('Publish 15-25 popular posts'),
            _('Accumulate 100+ total likes'),
            _('Build a strong reputation'),
        ]
    },
    {
        'name': _('Expert'),
        'icon': 'star',
        'color': 'warning',
        'min_points': 500,
        'max_points': 1000,
        'description': _('You\'re a recognized authority'),
        'tips': [
            _('Publish 50+ high-quality posts'),
            _('Achieve 300+ total likes'),
            _('Mentor other members'),
        ]
    },
    {
        'name': _('Legend'),
        'icon': 'crown',
        'color': 'danger',
        'min_points': 1000,
        'max_points': _('Unlimited'),
        'description': _('You\'re a pillar of the IESA community'),
        'tips': [
            _('Maintain extraordinary engagement'),
            _('Lead by example'),
            _('Shape the future of IESA'),
        ]
    },
]

# Points breakdown for different actions
POINTS_BREAKDOWN = {
    'post': 10,
    'like': 2,
    'comment': 1,
}
