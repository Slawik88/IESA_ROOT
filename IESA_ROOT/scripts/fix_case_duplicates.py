"""audit v5: автоматически чинит дубли где разный регистр msgid → одинаковый msgstr.

Например:
  msgid "Published"  → msgstr "опубліковано"
  msgid "PUBLISHED"  → msgstr "опубліковано"   ← должно быть "ОПУБЛІКОВАНО"

Логика: если msgid в UPPER → msgstr тоже UPPER. Если msgid в Title → msgstr в Title.

Также чинит явно непереведённые строки (msgstr == msgid) для базовых терминов.
"""
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding='utf-8')
import polib

BASE = Path(__file__).resolve().parent.parent
LOCALES = BASE / 'locale'


def case_of(s: str) -> str:
    """Возвращает тип регистра: 'upper' | 'lower' | 'title' | 'mixed'."""
    if not s:
        return 'mixed'
    if s.isupper():
        return 'upper'
    if s.islower():
        return 'lower'
    if s == s.title() or (len(s) > 1 and s[0].isupper() and s[1:].islower()):
        return 'title'
    return 'mixed'


def force_case(s: str, case: str) -> str:
    """Приводит строку к нужному регистру."""
    if case == 'upper':
        return s.upper()
    if case == 'lower':
        return s.lower()
    if case == 'title':
        # capitalize only first letter, не трогаем остальные слова
        return s[0].upper() + s[1:] if s else s
    return s


# Базовые переводы для непереведённых брендов/общих терминов
PATCHES_GLOBAL = {
    'IESA ROOT':         {'uk': 'IESA ROOT',         'fr': 'IESA ROOT',          'de': 'IESA ROOT'},
    'Email IESA':        {'uk': 'Email IESA',        'fr': 'Email IESA',         'de': 'E-Mail IESA'},
    'Mobile navigation': {'uk': 'Мобільна навігація','fr': 'Navigation mobile',  'de': 'Mobile Navigation'},
    'Notification':      {'uk': 'Сповіщення',        'fr': 'Notification',       'de': 'Benachrichtigung'},
    'Description':       {'uk': 'Опис',              'fr': 'Description',        'de': 'Beschreibung'},
    'DESCRIPTION':       {'uk': 'ОПИС',              'fr': 'DESCRIPTION',        'de': 'BESCHREIBUNG'},
    'Information':       {'uk': 'Інформація',        'fr': 'Informations',       'de': 'Informationen'},
    'System':            {'uk': 'Система',           'fr': 'Système',            'de': 'System'},
    'Status':            {'uk': 'Статус',            'fr': 'Statut',             'de': 'Status'},
    'Details':           {'uk': 'Деталі',            'fr': 'Détails',            'de': 'Details'},
    'Position':          {'uk': 'Посада',            'fr': 'Position',           'de': 'Position'},
    'Multi-sport':       {'uk': 'Мульти-спорт',      'fr': 'Multisport',         'de': 'Multisport'},
    'International':     {'uk': 'Міжнародний',       'fr': 'International',      'de': 'International'},
    'Sponsor':           {'uk': 'Спонсор',           'fr': 'Sponsor',            'de': 'Sponsor'},
    'association':       {'uk': 'асоціація',         'fr': 'association',        'de': 'Verein'},
    'Photos':            {'uk': 'Фотографії',        'fr': 'Photos',             'de': 'Fotos'},
    'Message':           {'uk': 'Повідомлення',      'fr': 'Message',            'de': 'Nachricht'},
    'Notifications':     {'uk': 'Сповіщення',        'fr': 'Notifications',      'de': 'Benachrichtigungen'},
    'Community':         {'uk': 'Спільнота',         'fr': 'Communauté',         'de': 'Community'},
    'Community & Blog':  {'uk': 'Спільнота і блог',  'fr': 'Communauté & Blog',  'de': 'Community & Blog'},
    'Bio/Message':       {'uk': 'Біо / Повідомлення','fr': 'Bio/Message',        'de': 'Bio/Nachricht'},
    'Design':            {'uk': 'Дизайн',            'fr': 'Design',             'de': 'Design'},
    'Date ↑':            {'uk': 'Дата ↑',            'fr': 'Date ↑',             'de': 'Datum ↑'},
    'Date ↓':            {'uk': 'Дата ↓',            'fr': 'Date ↓',             'de': 'Datum ↓'},
}


def fix_lang(lang: str) -> tuple[int, int]:
    """Возвращает (case_fixed, untranslated_fixed)."""
    po_path = LOCALES / lang / 'LC_MESSAGES' / 'django.po'
    if not po_path.exists():
        return 0, 0
    po = polib.pofile(str(po_path))

    # Индекс msgstr → list of (entry, case)
    by_msgstr = {}
    for entry in po:
        if not entry.msgid or not entry.msgstr.strip():
            continue
        key = entry.msgstr.strip().lower()
        by_msgstr.setdefault(key, []).append(entry)

    case_fixed = 0
    untranslated_fixed = 0

    # 1. Чиним дубли с разным регистром msgid
    for key, entries in by_msgstr.items():
        if len(entries) < 2:
            continue
        # Группа: одинаковый msgstr, разные msgid
        for entry in entries:
            mid_case = case_of(entry.msgid.strip())
            mstr_case = case_of(entry.msgstr.strip())
            # Если регистр msgid и msgstr НЕ совпадает — корректируем msgstr под msgid
            if mid_case in ('upper', 'lower', 'title') and mid_case != mstr_case:
                new_msgstr = force_case(entry.msgstr, mid_case)
                if new_msgstr != entry.msgstr:
                    entry.msgstr = new_msgstr
                    case_fixed += 1

    # 2. Чиним непереведённые общие термины из PATCHES_GLOBAL
    for entry in po:
        if not entry.msgid:
            continue
        patch = PATCHES_GLOBAL.get(entry.msgid)
        if not patch:
            continue
        new_msgstr = patch.get(lang)
        if not new_msgstr:
            continue
        # Применяем только если msgstr пустой ИЛИ === msgid (т.е. не переведено)
        if not entry.msgstr.strip() or entry.msgstr.strip() == entry.msgid.strip():
            if entry.msgstr != new_msgstr:
                entry.msgstr = new_msgstr
                untranslated_fixed += 1

    po.save(str(po_path))
    # Перекомпилировать .mo
    mo_path = po_path.with_suffix('.mo')
    po.save_as_mofile(str(mo_path))

    return case_fixed, untranslated_fixed


def main():
    for lang in ('uk', 'fr', 'de'):
        case_fixed, untrans = fix_lang(lang)
        print(f'  {lang}: case-fixed {case_fixed}, untranslated-fixed {untrans}, .mo обновлён')


if __name__ == '__main__':
    main()
