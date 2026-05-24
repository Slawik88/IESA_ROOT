"""Орфографическая проверка переводов uk/fr/de.

Стратегия:
- FR/DE: pyspellchecker (встроенные словари).
- UK:
    1. словарь известных украинских опечаток (русизмы, неверные окончания),
    2. проверка на запрещённые русские буквы (ё, ъ, ы, э),
    3. валидация известных правил украинской орфографии.
- EN (msgid): pyspellchecker для оригинального текста (там тоже бывают опечатки).

Ложноположительные срабатывания фильтруются через whitelist (бренды,
аббревиатуры, имена собственные).
"""
import re
import sys
from collections import defaultdict
from pathlib import Path

sys.stdout.reconfigure(encoding='utf-8')

import polib
from spellchecker import SpellChecker

BASE = Path(__file__).resolve().parent.parent
LOCALES = BASE / 'locale'

# Слова которые spell-checker не знает но они валидны
WHITELIST_COMMON = {
    # бренды, аббревиатуры, технические термины
    'iesa', 'sport', 'switzerland', 'suisse', 'schweiz', 'genève', 'geneva',
    'telegram', 'discord', 'github', 'whatsapp', 'instagram', 'facebook',
    'twitter', 'tiktok', 'youtube', 'linkedin', 'reddit', 'twitch', 'medium',
    'cleverreach', 'datenschutz', 'impressum', 'awesome', 'font',
    'agb', 'cgv', 'rgpd', 'gdpr', 'dsgvo', 'tva', 'mwst', 'fas', 'fab', 'far',
    'utf', 'json', 'http', 'https', 'url', 'qr', 'pin', 'otp', 'csv', 'pdf',
    'css', 'html', 'api', 'sms', 'email', 'wifi', 'ios', 'app', 'apps',
    'ics', 'ical', 'rss', 'xml', 'png', 'jpg', 'svg', 'gif', 'webp', 'mp4',
    'login', 'logout', 'signup', 'username', 'password', 'admin', 'admins',
    'dashboard', 'avatar', 'bio', 'nft', 'crm', 'pwa', 'spa', 'cms', 'seo',
    'ux', 'ui', 'dev', 'metadata', 'bot', 'bots', 'tech', 'offsites',
    'kitesurfing', 'kitesurf', 'kitesurfen', 'multi', 'multisport',
    'cafe', 'kids', 'count', 'analytics', 'analytic', 'timestamps',
    'wellbeing', 'personalise', 'prev', 'next', 'web', 'website',
    'dietology', 'doesn', 'etc', 'desn', 'wasn', 'isn', 'shouldn',
    'sea', 'ages', 'min', 'max',
    # FR заимствования и слова которых нет в словаре
    'partenair', 'partenaire', 'partenaires', 'événement', 'événements',
    'aime', 'avez', 'accéder', 'inscription', 'abonnement', 'âge',
    'inscrire', 'inscrivez', 'connectez', 'rejoignez', 'rejoindre',
    'nous', 'vous', 'votre', 'notre', 'tout', 'tous', 'toutes', 'toute',
    'réseautage', 'blog', 'blogs', 'résilience', 'métadonnées',
    'oups', 'quelqu', 'déc', 'week', 'end', 'ends', 'plonge', 'plongée',
    # DE заимствования и compound roots
    'events', 'likes', 'like', 'post', 'posts', 'feedback',
    'weiterlesen', 'networking', 'community', 'communities',
    'scout', 'yachting', 'lifestyle', 'extremsport', 'extrem',
    'resilienz', 'enddatum', 'höchstalter', 'angepinnt', 'kernprodukt',
    'partnername', 'produktname', 'produktbild', 'tauchgängen', 'seepassagen',
    'extremsport', 'beitragsinformationen', 'beitragstext', 'vorschaubild',
    'kommentartext', 'ansichtsdatum', 'beitragsaufruf', 'beitragsaufrufe',
    'veranstaltungstitel', 'veranstaltungsdatum', 'veranstaltungsbild',
    'veranstaltungsregistrierung', 'veranstaltungsregistrierungen',
    'abonnementdatum', 'altersbeschränkung',
}

# Слова длиннее этого порога в DE считаем compound — пропускаем
DE_COMPOUND_MIN_LEN = 10

# UK: запрещённые русские буквы (украинский алфавит не содержит ё, ъ, ы, э)
RUS_ONLY_LETTERS_RE = re.compile(r'[ёъыэЁЪЫЭ]')

# UK: типичные русизмы и опечатки → правильно
UK_FIXES = {
    # русские слова → украинские
    'если': 'якщо',
    'нужно': 'потрібно',
    'спасибо': 'дякую',
    'пожалуйста': 'будь ласка',
    'хорошо': 'добре',
    'плохо': 'погано',
    'сейчас': 'зараз',
    'теперь': 'тепер',
    'только': 'тільки',
    'ещё': 'ще',
    'войти': 'увійти',
    'выйти': 'вийти',
    'войдите': 'увійдіть',
    'войдите': 'увійдіть',
    'настройки': 'налаштування',
    'продолжить': 'продовжити',
    'удалить': 'видалити',
    'отменить': 'скасувати',
    'обновить': 'оновити',
    'пользователь': 'користувач',
    'пользователи': 'користувачі',
    'сообщение': 'повідомлення',
    'сообщения': 'повідомлення',
    'который': 'який',
    'которая': 'яка',
    'которое': 'яке',
    'которые': 'які',
    'этот': 'цей',
    'эта': 'ця',
    'это': 'це',
    'эти': 'ці',
    'тоже': 'також',
    'также': 'також',
    'нельзя': 'не можна',
    'нужен': 'потрібен',
    # частые орфографические ошибки в украинском
    'розписание': 'розклад',
    'график': 'графік',
    'дабавити': 'додати',
    'дабавить': 'додати',
    'роздділ': 'розділ',
    'улюблений': 'улюблений',  # OK
    'привітання': 'привітання',  # OK
}

# UK: типовые неверные окончания (русское окончание в украинском слове)
UK_BAD_ENDINGS = [
    ('ться$', 'тися'),  # русское -ться → укр -тися (rare cases)
    # Это правило не всегда — в украинском оба есть. Оставляем для других.
]


def normalize_word(w: str) -> str:
    """Приводит слово к нижнему регистру, убирает знаки препинания по краям."""
    return w.strip().strip('.,!?;:"«»()[]{}«»…—–-*_').lower()


def split_words(text: str) -> list[str]:
    """Разбивает текст на слова, исключая placeholders, числа, HTML.

    Разбивает по апострофу и дефису, чтобы spell-checker корректно
    проверял "J'aime" → "J" + "aime", "Multi-sport" → "Multi" + "sport".
    """
    # Убираем HTML, %(name)s, {var}, %s, числа, URL, email, времена
    text = re.sub(r'<[^>]+>', ' ', text)
    text = re.sub(r'%\([^)]+\)s', ' ', text)
    text = re.sub(r'\{\{?[^}]+\}?\}', ' ', text)
    text = re.sub(r'%[sd]', ' ', text)
    text = re.sub(r'\d+[:.]\d+', ' ', text)  # 10:30, 10.5
    text = re.sub(r'\d+', ' ', text)
    text = re.sub(r'https?://\S+', ' ', text)
    text = re.sub(r'\S+@\S+', ' ', text)
    # Заменяем апостроф/дефис на пробел для split
    text = re.sub(r"[''`-]", ' ', text)
    words = re.findall(r"[a-zA-ZÀ-ÿА-Яа-яЁёЇїІіЄєҐґ]+", text)
    return [w for w in words if len(w) >= 3]


def check_uk(po):
    """Возвращает {entry: list[issue]} для украинских ошибок."""
    issues = []
    for entry in po:
        if not entry.msgstr.strip():
            continue
        msgstr = entry.msgstr

        # 1. Русские-эксклюзивные буквы
        m = RUS_ONLY_LETTERS_RE.search(msgstr)
        if m:
            issues.append({
                'msgid': entry.msgid,
                'msgstr': msgstr,
                'reason': f'Російська буква {m.group()!r} в українському перекладі',
                'fix': None,
            })

        # 2. Известные русизмы
        for word in split_words(msgstr):
            w_norm = normalize_word(word)
            if w_norm in UK_FIXES:
                correct = UK_FIXES[w_norm]
                if correct != w_norm:
                    issues.append({
                        'msgid': entry.msgid,
                        'msgstr': msgstr,
                        'reason': f'Русизм {word!r} → має бути {correct!r}',
                        'fix': (word, correct),
                    })
    return issues


def check_lang(lang: str, spell: SpellChecker):
    po_path = LOCALES / lang / 'LC_MESSAGES' / 'django.po'
    if not po_path.exists():
        return [], None
    po = polib.pofile(str(po_path))

    issues = []
    for entry in po:
        if not entry.msgstr.strip():
            continue
        words = split_words(entry.msgstr)
        wrong = []
        for w in words:
            w_norm = normalize_word(w)
            if not w_norm or len(w_norm) < 3 or w_norm in WHITELIST_COMMON:
                continue
            # CamelCase / mixed case — технический термин, пропускаем
            if len(w) > 1 and any(c.isupper() for c in w[1:]):
                continue
            # Длинные слова в немецком — compound, spell-checker их не знает
            if lang == 'de' and len(w_norm) >= DE_COMPOUND_MIN_LEN:
                continue
            if w_norm not in spell:
                wrong.append(w)
        if wrong:
            # Только если 1-2 ошибки в строке (3+ обычно ложноположительно)
            if 1 <= len(wrong) <= 2:
                issues.append({
                    'msgid': entry.msgid,
                    'msgstr': entry.msgstr,
                    'wrong': wrong,
                    'suggestions': {w: list(spell.candidates(normalize_word(w)) or [])[:3] for w in wrong},
                })
    return issues, po


def main():
    print('=' * 70)
    print('ОРФОГРАФИЧЕСКИЙ АУДИТ ПЕРЕВОДОВ')
    print('=' * 70)

    # 1. Украинский — кастомные правила
    print('\n--- UK (украинский) ---')
    po_uk = polib.pofile(str(LOCALES / 'uk/LC_MESSAGES/django.po'))
    uk_issues = check_uk(po_uk)
    print(f'Найдено проблем: {len(uk_issues)}')
    for iss in uk_issues[:20]:
        print(f"  [{iss['reason']}]")
        print(f"    msgid: {iss['msgid'][:60]!r}")
        print(f"    msgstr: {iss['msgstr'][:60]!r}")

    # 2. Французский
    print('\n--- FR (французский) ---')
    spell_fr = SpellChecker(language='fr', distance=1)
    fr_issues, po_fr = check_lang('fr', spell_fr)
    print(f'Найдено потенциальных опечаток в {len(fr_issues)} строках:')
    for iss in fr_issues[:25]:
        print(f"  msgid: {iss['msgid'][:50]!r}")
        print(f"    msgstr: {iss['msgstr'][:70]!r}")
        for w in iss['wrong']:
            sug = iss['suggestions'].get(w, [])
            print(f"      ❌ {w!r} → {sug[:3] if sug else '?'}")

    # 3. Немецкий
    print('\n--- DE (немецкий) ---')
    spell_de = SpellChecker(language='de', distance=1)
    de_issues, po_de = check_lang('de', spell_de)
    print(f'Найдено потенциальных опечаток в {len(de_issues)} строках:')
    for iss in de_issues[:25]:
        print(f"  msgid: {iss['msgid'][:50]!r}")
        print(f"    msgstr: {iss['msgstr'][:70]!r}")
        for w in iss['wrong']:
            sug = iss['suggestions'].get(w, [])
            print(f"      ❌ {w!r} → {sug[:3] if sug else '?'}")

    # 4. Английский (msgid) — для контроля
    print('\n--- EN (msgid оригиналы) ---')
    spell_en = SpellChecker(language='en', distance=1)
    en_issues = []
    for entry in po_uk:  # читаем msgid из uk файла (одинаковые везде)
        if not entry.msgid:
            continue
        words = split_words(entry.msgid)
        wrong = []
        for w in words:
            w_norm = normalize_word(w)
            if not w_norm or w_norm in WHITELIST_COMMON:
                continue
            if len(w) > 1 and any(c.isupper() for c in w[1:]):
                continue
            if w_norm not in spell_en:
                wrong.append(w)
        if wrong and 1 <= len(wrong) <= 3:
            en_issues.append({'msgid': entry.msgid, 'wrong': wrong,
                              'suggestions': {w: list(spell_en.candidates(normalize_word(w)) or [])[:3] for w in wrong}})
    print(f'Найдено потенциальных опечаток в EN msgid в {len(en_issues)} строках:')
    for iss in en_issues[:25]:
        print(f"  msgid: {iss['msgid'][:80]!r}")
        for w in iss['wrong']:
            sug = iss['suggestions'].get(w, [])
            print(f"      ❌ {w!r} → {sug[:3] if sug else '?'}")


if __name__ == '__main__':
    main()
