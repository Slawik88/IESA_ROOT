"""
core/constants.py
Именованные константы «Домового». Любое число из логики живёт здесь.
"""

# ── Неделя ───────────────────────────────────────────────────────────────────
# Номера совпадают с date.weekday(): 0 — понедельник … 6 — воскресенье.
WEEKDAY_NAMES = ("Понедельник", "Вторник", "Среда", "Четверг", "Пятница", "Суббота", "Воскресенье")
WEEKDAY_SHORT = ("Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс")

# ── График уборки ────────────────────────────────────────────────────────────
# На сколько дней вперёд планировщик раскладывает дни уборки.
SCHEDULE_HORIZON_DAYS = 14
# Шаблон графика v1: у каждого свой день недели. День без уборки — None.
NO_CLEANING_DAY = None

# ── Уведомления ──────────────────────────────────────────────────────────────
DEFAULT_MORNING_HOUR = 9
DEFAULT_EVENING_HOUR = 20
DEFAULT_MONTHLY_REPORT_HOUR = 10
SCHEDULER_TICK_SECONDS = 60

# ── Деньги ───────────────────────────────────────────────────────────────────
# Все суммы хранятся целыми копейками (CLEAN_CODE 5.7).
KOPECKS_IN_RUBLE = 100
MAX_AMOUNT_RUBLES = 10_000_000
DEFAULT_CURRENCY = "CHF"

# ── Чеки ─────────────────────────────────────────────────────────────────────
MAX_PHOTOS_PER_EXPENSE = 10

# ── Списки ───────────────────────────────────────────────────────────────────
RECENT_EXPENSES_LIMIT = 10
MAX_HOUSE_NAME_LEN = 32
MAX_MEMBER_NAME_LEN = 32
MAX_DESCRIPTION_LEN = 200
MAX_CATEGORY_NAME_LEN = 24
TRANSFER_MAX_BYTES = 2 * 1024 * 1024
TRANSFER_MAX_ROWS = 1000
WORKBOOK_MAX_UNPACKED_BYTES = 4 * 1024 * 1024
WORKBOOK_MAX_PARTS = 64
WORKBOOK_MAX_COLUMNS = 32
TRANSACTION_PAGE_SIZE = 8
WEB_JOURNAL_PAGE_SIZE = 20
WEB_HOME_RECENT_LIMIT = 5
QUICK_TRANSACTION_LIMIT = 4
JOURNAL_SEARCH_LIMIT = 80

# ── Категории трат по умолчанию (сидятся при создании дома) ──────────────────
DEFAULT_CATEGORIES = ("Продукты", "Бытовая химия", "Коммуналка", "Ремонт", "Прочее")

# ── Служебное ────────────────────────────────────────────────────────────────
DATE_FMT = "%Y-%m-%d"
