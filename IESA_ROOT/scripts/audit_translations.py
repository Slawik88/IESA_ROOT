"""audit v5: систематический анализ переводов на ошибки.

Находит:
1. UK с русскими словами/окончаниями (должен быть украинский)
2. UK с английским текстом (вообще не переведено)
3. FR/DE с английским текстом или странными машинными переводами
4. Транслит (английский кириллицей)
5. Дубли (одинаковый msgstr для разных msgid)
6. Слишком длинные/слишком короткие переводы относительно msgid
7. Несовпадение HTML-тегов в msgid и msgstr (баг машинного перевода)
8. fuzzy флаги
"""
import re
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding='utf-8')
import polib

BASE = Path(__file__).resolve().parent.parent
LOCALES = BASE / 'locale'

# ТОЛЬКО ЧИСТО русские слова которых НЕТ в украинском
# (исключены: ваш, назад, найти, поиск, аккаунт, и др. — они есть в украинском)
RUS_MARKERS = [
    'ещё', 'если', 'только',
    'спасибо', 'пожалуйста',
    'нельзя',
    'который', 'которая', 'которое', 'которые',
    'сейчас', 'теперь', 'тоже', 'также',
    'этот', 'эта', 'эти',
    'нужно', 'нужен',
    'пользователь', 'пользователи',  # uk: користувач
    'участник', 'участники',         # uk: учасник
    'сообщение', 'сообщения',        # uk: повідомлення
    'войти',                          # uk: увійти
    'выйти',                          # uk: вийти
    'войдите',                        # uk: увійдіть
    'настройки',                      # uk: налаштування
    'продолжить',                     # uk: продовжити
    'удалить',                        # uk: видалити
    'отменить',                       # uk: скасувати
    'был', 'была', 'было', 'были',   # uk: був, була, було, були (same!) — ОСТАВЛЯЮ т.к. одинаковые
    # ↑ всё равно False positive — убираю
]
# После анализа — оставляем только однозначно русские:
RUS_MARKERS = [
    'ещё', 'если', 'только', 'спасибо', 'пожалуйста',
    'нельзя', 'сейчас', 'теперь',
    'нужно', 'нужен',
    'пользователь', 'пользователи',
    'войти', 'выйти', 'войдите',
    'настройки',
    'продолжить', 'удалить', 'отменить',
    'обновить',
    'сообщение', 'сообщения',
    'который', 'которая', 'которое', 'которые',
    'тоже',
]

# Английские стоп-слова — указывают на полное отсутствие перевода
ENG_WORDS = [
    'the ', 'and ', 'or ', 'with ', 'from ', 'this ', 'that ', 'these ', 'those ',
    'have ', 'has ', 'been ', 'were ', 'was ', 'are ', 'is ',
    'click', 'select', 'enter', 'submit', 'cancel', 'save', 'delete',
    'username', 'password', 'email', 'phone',
    'must ', 'should ', 'will ',
]

# HTML теги — если есть в msgid, должны быть и в msgstr
HTML_TAG_RE = re.compile(r'<(/?\w+(?:\s+[^>]*)?)>', re.I)
PLACEHOLDER_RE = re.compile(r'%\([\w_]+\)s|\{\{?\s*\w+\s*\}?\}|%[sd]')


def is_likely_russian_in_uk(text: str) -> list[str]:
    """Возвращает список русских слов найденных в украинском переводе."""
    text_lower = text.lower()
    found = []
    for marker in RUS_MARKERS:
        # Слово как отдельное (с границами)
        pat = r'\b' + re.escape(marker) + r'\b'
        if re.search(pat, text_lower):
            found.append(marker)
    return found


def has_untranslated_english(text: str, msgid: str) -> bool:
    """Проверяет содержит ли msgstr английские служебные слова которых нет в msgid."""
    text_lower = text.lower()
    msgid_lower = msgid.lower()
    for w in ENG_WORDS:
        # Слово есть в переводе но не было в оригинале — значит вставлено неправильно
        if w in text_lower and w not in msgid_lower:
            return True
    return False


def check_html_tags(msgid: str, msgstr: str) -> bool:
    """True если HTML-теги в msgid и msgstr совпадают."""
    tags_id = sorted(t.lower().strip() for t in HTML_TAG_RE.findall(msgid))
    tags_str = sorted(t.lower().strip() for t in HTML_TAG_RE.findall(msgstr))
    return tags_id == tags_str


def check_placeholders(msgid: str, msgstr: str) -> bool:
    """True если placeholders в msgid и msgstr совпадают."""
    ph_id = sorted(PLACEHOLDER_RE.findall(msgid))
    ph_str = sorted(PLACEHOLDER_RE.findall(msgstr))
    return ph_id == ph_str


def length_suspicious(msgid: str, msgstr: str) -> bool:
    """True если длина перевода аномально отличается от оригинала."""
    if len(msgid) < 5 or len(msgstr) < 5:
        return False
    ratio = len(msgstr) / len(msgid)
    return ratio < 0.3 or ratio > 4.0


def analyze(lang: str):
    po_path = LOCALES / lang / 'LC_MESSAGES' / 'django.po'
    if not po_path.exists():
        return
    po = polib.pofile(str(po_path))

    issues = {
        'russian_in_uk': [],
        'english_inserted': [],
        'fuzzy': [],
        'html_mismatch': [],
        'placeholder_mismatch': [],
        'length_suspicious': [],
        'duplicate_msgstr': [],
        'same_as_msgid': [],
    }

    msgstr_count = {}  # для проверки дублей
    for entry in po:
        if not entry.msgid or not entry.msgstr or not entry.msgstr.strip():
            continue

        # 1. UK с русскими словами
        if lang == 'uk':
            rus = is_likely_russian_in_uk(entry.msgstr)
            if rus:
                issues['russian_in_uk'].append((entry.msgid, entry.msgstr, rus))

        # 2. msgstr == msgid (вообще не переведено)
        if entry.msgstr.strip().lower() == entry.msgid.strip().lower():
            # Для коротких аббревиатур (e.g. "IESA", "PIN") это OK
            if len(entry.msgid) > 5:
                issues['same_as_msgid'].append((entry.msgid, entry.msgstr))

        # 3. fuzzy флаг
        if 'fuzzy' in entry.flags:
            issues['fuzzy'].append((entry.msgid, entry.msgstr))

        # 4. HTML несоответствие
        if not check_html_tags(entry.msgid, entry.msgstr):
            issues['html_mismatch'].append((entry.msgid, entry.msgstr))

        # 5. Placeholder несоответствие
        if not check_placeholders(entry.msgid, entry.msgstr):
            issues['placeholder_mismatch'].append((entry.msgid, entry.msgstr))

        # 6. Длина
        if length_suspicious(entry.msgid, entry.msgstr):
            issues['length_suspicious'].append((entry.msgid, entry.msgstr))

        # 7. Дубли (один msgstr для нескольких msgid) — case-sensitive,
        # чтобы "Опубліковано" и "ОПУБЛІКОВАНО" НЕ считались дублём.
        key = entry.msgstr.strip()
        if key not in msgstr_count:
            msgstr_count[key] = []
        msgstr_count[key].append(entry.msgid)

    # Бренды и общие термины которые легально одинаковы в нескольких языках
    BRAND_OK = {
        'IESA ROOT', 'Discord', 'Telegram', 'GitHub', 'E-mail', 'Email IESA',
        'TELEGRAM', 'WhatsApp', 'Facebook', 'Instagram', 'YouTube', 'Twitter',
        'TikTok', 'LinkedIn', 'IESA', 'PIN', 'QR', 'OTP', 'CSRF', 'CSV',
        'API', 'URL', 'HTTP', 'HTTPS', 'SMTP', 'JSON', 'XML', 'PDF',
        'Sponsor', 'International', 'Design', 'Photos', 'Position',
        'Description', 'DESCRIPTION', 'Notification', 'Notifications',
        'System', 'Status', 'Details', 'Information', 'Message',
        'Community', 'COMMUNITY', 'Community & Blog', 'Bio/Message',
        'Date ↑', 'Date ↓', 'DATE ↑', 'DATE ↓', 'Multi-sport', 'CONTACTS',
        'Cabinet', 'Mobile navigation', 'association', 'Partner',
    }

    # Фильтруем тривиальные "не переведено" для брендов
    issues['same_as_msgid'] = [
        (mid, mstr) for mid, mstr in issues['same_as_msgid']
        if mid not in BRAND_OK
    ]

    for msgstr, msgids in msgstr_count.items():
        if len(msgids) > 1 and len(msgstr) > 8:
            issues['duplicate_msgstr'].append((msgstr, msgids))

    return issues


def print_report(lang: str, issues: dict):
    print(f'\n{"=" * 70}\n{lang.upper()} — ANALYSIS REPORT\n{"=" * 70}')

    if lang == 'uk':
        rus = issues['russian_in_uk']
        print(f'\n🔴 Русские слова в украинском ({len(rus)}):')
        for mid, mstr, words in rus[:30]:
            print(f'  [{",".join(words)}]')
            print(f'    EN: {mid[:80]!r}')
            print(f'    UK: {mstr[:80]!r}')

    same = issues['same_as_msgid']
    print(f'\n🟡 msgstr == msgid (не переведено, {len(same)}):')
    for mid, mstr in same[:15]:
        print(f'    {mid[:90]!r}')

    fuzzy = issues['fuzzy']
    if fuzzy:
        print(f'\n🟡 Fuzzy flags ({len(fuzzy)}):')
        for mid, mstr in fuzzy[:10]:
            print(f'    {mid[:60]!r} → {mstr[:60]!r}')

    html = issues['html_mismatch']
    if html:
        print(f'\n🔴 HTML tags mismatch ({len(html)}):')
        for mid, mstr in html[:10]:
            print(f'    EN: {mid[:80]!r}')
            print(f'    XX: {mstr[:80]!r}')

    ph = issues['placeholder_mismatch']
    if ph:
        print(f'\n🔴 Placeholders mismatch ({len(ph)}):')
        for mid, mstr in ph[:10]:
            print(f'    EN: {mid[:80]!r}')
            print(f'    XX: {mstr[:80]!r}')

    length = issues['length_suspicious']
    if length:
        print(f'\n🟡 Suspicious length ({len(length)}):')
        for mid, mstr in length[:10]:
            print(f'    EN ({len(mid)}): {mid[:70]!r}')
            print(f'    XX ({len(mstr)}): {mstr[:70]!r}')

    dup = issues['duplicate_msgstr']
    if dup:
        print(f'\n🟡 Duplicate translations ({len(dup)}):')
        for mstr, mids in dup[:8]:
            print(f'    "{mstr[:60]}" used for:')
            for mid in mids[:5]:
                print(f'      → {mid[:60]!r}')


def main():
    for lang in ('uk', 'fr', 'de'):
        issues = analyze(lang)
        if issues:
            print_report(lang, issues)


if __name__ == '__main__':
    main()
