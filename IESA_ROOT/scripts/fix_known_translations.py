"""audit v5: ручной фикс конкретных проблемных msgid с правильными переводами.

Этот скрипт целенаправленно исправляет переводы где:
- разный регистр msgid должен давать разный регистр msgstr
- общие термины должны иметь разные переводы по контексту
- автоматические переводчики допустили ошибки

После запуска: .po + .mo обновляются.
"""
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding='utf-8')
import polib

BASE = Path(__file__).resolve().parent.parent
LOCALES = BASE / 'locale'

# Карта: msgid → {lang: правильный_msgstr}
# Перезаписывает существующее значение (force update)
FIXES = {
    # === REGISTER cases ===
    'Published':        {'uk': 'Опубліковано',     'fr': 'Publié',          'de': 'Veröffentlicht'},
    'PUBLISHED':        {'uk': 'ОПУБЛІКОВАНО',     'fr': 'PUBLIÉ',          'de': 'VERÖFFENTLICHT'},
    'Pending':          {'uk': 'Очікує',           'fr': 'En attente',      'de': 'Ausstehend'},
    'PENDING':          {'uk': 'ОЧІКУЄ',           'fr': 'EN ATTENTE',      'de': 'AUSSTEHEND'},
    'Comments':         {'uk': 'Коментарі',        'fr': 'Commentaires',    'de': 'Kommentare'},
    'COMMENTS':         {'uk': 'КОМЕНТАРІ',        'fr': 'COMMENTAIRES',    'de': 'KOMMENTARE'},
    'Comments made':    {'uk': 'Залишено коментарів','fr': 'Commentaires laissés','de': 'Hinterlassene Kommentare'},
    'Events':           {'uk': 'Події',            'fr': 'Événements',      'de': 'Events'},
    'events':           {'uk': 'подій',            'fr': 'événements',      'de': 'events'},
    'EVENTS':           {'uk': 'ПОДІЇ',            'fr': 'ÉVÉNEMENTS',      'de': 'EVENTS'},
    'Posts':            {'uk': 'Дописи',           'fr': 'Publications',    'de': 'Beiträge'},
    'POSTS':            {'uk': 'ДОПИСИ',           'fr': 'PUBLICATIONS',    'de': 'BEITRÄGE'},
    'Views':            {'uk': 'Перегляди',        'fr': 'Vues',            'de': 'Aufrufe'},
    'views':            {'uk': 'переглядів',       'fr': 'vues',            'de': 'Aufrufe'},

    # === LIKE distinguishable ===
    'Like':             {'uk': 'Лайк',             'fr': "J'aime",          'de': 'Gefällt mir'},
    'Likes':            {'uk': 'Лайки',            'fr': "J'aime",          'de': 'Likes'},
    'Likes received':   {'uk': 'Отримано лайків',  'fr': "J'aime reçus",    'de': 'Erhaltene Likes'},

    # === STATISTICS vs STATS ===
    'Statistics':       {'uk': 'Статистика',       'fr': 'Statistiques',    'de': 'Statistik'},
    'Stats':            {'uk': 'Стат.',            'fr': 'Stats',           'de': 'Stats'},

    # === REGISTERED ===
    'Registered':       {'uk': 'Зареєстровано',    'fr': 'Inscrit',         'de': 'Registriert'},
    'Registered at':    {'uk': 'Дата реєстрації',  'fr': "Date d'inscription",'de': 'Registriert am'},

    # === DATE / TIME ===
    'Date & Time':      {'uk': 'Дата і час',       'fr': 'Date et heure',   'de': 'Datum & Uhrzeit'},
    'Date & time':      {'uk': 'Дата та час',      'fr': 'Date et heure',   'de': 'Datum & Uhrzeit'},
    'Date':             {'uk': 'Дата',             'fr': 'Date',            'de': 'Datum'},
    'Time':             {'uk': 'Час',              'fr': 'Heure',           'de': 'Uhrzeit'},

    # === DESCRIPTION/DETAILS ===
    'Description':      {'uk': 'Опис',             'fr': 'Description',     'de': 'Beschreibung'},
    'DESCRIPTION':      {'uk': 'ОПИС',             'fr': 'DESCRIPTION',     'de': 'BESCHREIBUNG'},
    'Details':          {'uk': 'Деталі',           'fr': 'Détails',         'de': 'Details'},
    'DETAILS':          {'uk': 'ДЕТАЛІ',           'fr': 'DÉTAILS',         'de': 'DETAILS'},

    # === Post / Publishing ===
    'Post':             {'uk': 'Допис',            'fr': 'Publication',     'de': 'Beitrag'},
    'Publishing':       {'uk': 'Публікація',       'fr': 'Publication',     'de': 'Veröffentlichung'},
    'Create a Post':    {'uk': 'Створити допис',   'fr': 'Créer une publication','de':'Beitrag erstellen'},

    # === Preview ===
    'Preview image':    {'uk': 'Превʼю зображення', 'fr': 'Image de prévisualisation','de':'Vorschaubild'},
    'Thumbnail':        {'uk': 'Мініатюра',        'fr': 'Miniature',       'de': 'Miniaturansicht'},

    # === Bio / Message variants ===
    'Bio/Message':      {'uk': 'Біо / Повідомлення','fr': 'Bio / Message',  'de': 'Bio / Nachricht'},
    'Bio':              {'uk': 'Біо',              'fr': 'Bio',             'de': 'Bio'},

    # === Complete ===
    'complete':         {'uk': 'заповнено',        'fr': 'complété',        'de': 'abgeschlossen'},
    'Completed':        {'uk': 'Виконано',         'fr': 'Terminé',         'de': 'Erledigt'},
    'COMPLETED':        {'uk': 'ВИКОНАНО',         'fr': 'TERMINÉ',         'de': 'ERLEDIGT'},

    # === Bot / Telegram ===
    'IESA ROOT':        {'uk': 'IESA ROOT',        'fr': 'IESA ROOT',       'de': 'IESA ROOT'},
    'Email IESA':       {'uk': 'Email IESA',       'fr': 'Email IESA',      'de': 'E-Mail IESA'},
    'Mobile navigation':{'uk': 'Мобільна навігація','fr': 'Navigation mobile','de': 'Mobile Navigation'},
    'TELEGRAM':         {'uk': 'TELEGRAM',         'fr': 'TELEGRAM',        'de': 'TELEGRAM'},
    'GitHub':           {'uk': 'GitHub',           'fr': 'GitHub',          'de': 'GitHub'},
    'Discord':          {'uk': 'Discord',          'fr': 'Discord',         'de': 'Discord'},
    'Telegram':         {'uk': 'Telegram',         'fr': 'Telegram',        'de': 'Telegram'},
    'E-mail':           {'uk': 'E-mail',           'fr': 'E-mail',          'de': 'E-Mail'},

    # === Notification ===
    'Notification':     {'uk': 'Сповіщення',       'fr': 'Notification',    'de': 'Benachrichtigung'},
    'Notifications':    {'uk': 'Сповіщення',       'fr': 'Notifications',   'de': 'Benachrichtigungen'},

    # === Common nouns ===
    'Information':      {'uk': 'Інформація',       'fr': 'Informations',    'de': 'Informationen'},
    'System':           {'uk': 'Система',          'fr': 'Système',         'de': 'System'},
    'Status':           {'uk': 'Статус',           'fr': 'Statut',          'de': 'Status'},
    'Photos':           {'uk': 'Фотографії',       'fr': 'Photos',          'de': 'Fotos'},
    'Message':          {'uk': 'Повідомлення',     'fr': 'Message',         'de': 'Nachricht'},
    'Position':         {'uk': 'Посада',           'fr': 'Poste',           'de': 'Position'},
    'Sponsor':          {'uk': 'Спонсор',          'fr': 'Sponsor',         'de': 'Sponsor'},
    'Multi-sport':      {'uk': 'Мульти-спорт',     'fr': 'Multisport',      'de': 'Multisport'},
    'International':    {'uk': 'Міжнародний',      'fr': 'International',   'de': 'International'},
    'association':      {'uk': 'асоціація',        'fr': 'association',     'de': 'Verein'},
    'Design':           {'uk': 'Дизайн',           'fr': 'Design',          'de': 'Design'},
    'Community':        {'uk': 'Спільнота',        'fr': 'Communauté',      'de': 'Community'},
    'COMMUNITY':        {'uk': 'СПІЛЬНОТА',        'fr': 'COMMUNAUTÉ',      'de': 'COMMUNITY'},
    'Community & Blog': {'uk': 'Спільнота і блог', 'fr': 'Communauté et Blog','de':'Community & Blog'},

    # === Date arrows ===
    'Date ↑':           {'uk': 'Дата ↑',           'fr': 'Date ↑',          'de': 'Datum ↑'},
    'Date ↓':           {'uk': 'Дата ↓',           'fr': 'Date ↓',          'de': 'Datum ↓'},
    'DATE ↑':           {'uk': 'ДАТА ↑',           'fr': 'DATE ↑',          'de': 'DATUM ↑'},
    'DATE ↓':           {'uk': 'ДАТА ↓',           'fr': 'DATE ↓',          'de': 'DATUM ↓'},

    # === Verified ===
    'Verified':         {'uk': 'Підтверджено',     'fr': 'Vérifié',         'de': 'Verifiziert'},
    'VERIFIED':         {'uk': 'ПІДТВЕРДЖЕНО',     'fr': 'VÉRIFIÉ',         'de': 'VERIFIZIERT'},
    'Pending verification':{'uk':'Очікує підтвердження','fr':'En attente de vérification','de':'Verifizierung ausstehend'},
    'Verified User':    {'uk': 'Перевірений користувач','fr':'Utilisateur vérifié','de':'Verifizierter Benutzer'},

    # === Member / Partner roles ===
    'Member':           {'uk': 'Учасник',          'fr': 'Membre',          'de': 'Mitglied'},
    'Members':          {'uk': 'Учасники',         'fr': 'Membres',         'de': 'Mitglieder'},
    'MEMBER':           {'uk': 'УЧАСНИК',          'fr': 'MEMBRE',          'de': 'MITGLIED'},
    'Partner':          {'uk': 'Партнер',          'fr': 'Partenaire',      'de': 'Partner'},
    'Partners':         {'uk': 'Партнери',         'fr': 'Partenaires',     'de': 'Partner'},
    'Staff':            {'uk': 'Персонал',         'fr': 'Personnel',       'de': 'Personal'},
    'Owner':            {'uk': 'Власник',          'fr': 'Propriétaire',    'de': 'Inhaber'},

    # === Levels ===
    'Beginner':         {'uk': 'Початківець',      'fr': 'Débutant',        'de': 'Anfänger'},
    'Intermediate':     {'uk': 'Середній',         'fr': 'Intermédiaire',   'de': 'Mittel'},
    'Advanced':         {'uk': 'Просунутий',       'fr': 'Avancé',          'de': 'Fortgeschritten'},
    'Expert':           {'uk': 'Експерт',          'fr': 'Expert',          'de': 'Experte'},
    'Legend':           {'uk': 'Легенда',          'fr': 'Légende',         'de': 'Legende'},

    # === Latest/Recent ===
    'Latest':           {'uk': 'Останні',          'fr': 'Récents',         'de': 'Neueste'},
    'LATEST':           {'uk': 'ОСТАННІ',          'fr': 'RÉCENTS',         'de': 'NEUESTE'},
    'Recent':           {'uk': 'Нещодавні',        'fr': 'Récents',         'de': 'Kürzlich'},

    # === Filter / Sort ===
    'Filters':          {'uk': 'Фільтри',          'fr': 'Filtres',         'de': 'Filter'},
    'FILTERS':          {'uk': 'ФІЛЬТРИ',          'fr': 'FILTRES',         'de': 'FILTER'},
    'Sort':             {'uk': 'Сортування',       'fr': 'Trier',           'de': 'Sortieren'},
    'ALL':              {'uk': 'УСІ',              'fr': 'TOUS',            'de': 'ALLE'},
    'All':              {'uk': 'Усі',              'fr': 'Tous',            'de': 'Alle'},

    # === Visits ===
    'Visit':            {'uk': 'Візит',            'fr': 'Visite',          'de': 'Besuch'},
    'Visits':           {'uk': 'Візити',           'fr': 'Visites',         'de': 'Besuche'},
    'VISITS':           {'uk': 'ВІЗИТИ',           'fr': 'VISITES',         'de': 'BESUCHE'},

    # === Pages ===
    'Home':             {'uk': 'Головна',          'fr': 'Accueil',         'de': 'Startseite'},
    'About':            {'uk': 'Про нас',          'fr': 'À propos',        'de': 'Über uns'},
    'Gallery':          {'uk': 'Галерея',          'fr': 'Galerie',         'de': 'Galerie'},
    'Profile':          {'uk': 'Профіль',          'fr': 'Profil',          'de': 'Profil'},
    'Settings':         {'uk': 'Налаштування',     'fr': 'Paramètres',      'de': 'Einstellungen'},
    'Search':           {'uk': 'Пошук',            'fr': 'Rechercher',      'de': 'Suchen'},
    'Calendar':         {'uk': 'Календар',         'fr': 'Calendrier',      'de': 'Kalender'},

    # === Common UI ===
    'Save':             {'uk': 'Зберегти',         'fr': 'Enregistrer',     'de': 'Speichern'},
    'Cancel':           {'uk': 'Скасувати',        'fr': 'Annuler',         'de': 'Abbrechen'},
    'Delete':           {'uk': 'Видалити',         'fr': 'Supprimer',       'de': 'Löschen'},
    'Edit':             {'uk': 'Редагувати',       'fr': 'Modifier',        'de': 'Bearbeiten'},
    'Close':            {'uk': 'Закрити',          'fr': 'Fermer',          'de': 'Schließen'},
    'Send':             {'uk': 'Надіслати',        'fr': 'Envoyer',         'de': 'Senden'},
    'Sign In':          {'uk': 'Увійти',           'fr': 'Connexion',       'de': 'Anmelden'},
    'Sign Up Now':      {'uk': 'Зареєструватися',  'fr': 'Inscrivez-vous',  'de': 'Jetzt registrieren'},
    'Logout':           {'uk': 'Вийти',            'fr': 'Déconnexion',     'de': 'Abmelden'},
    'Register':         {'uk': 'Зареєструватися',  'fr': "S'inscrire",      'de': 'Registrieren'},
}


def apply_fixes(lang: str) -> int:
    po_path = LOCALES / lang / 'LC_MESSAGES' / 'django.po'
    if not po_path.exists():
        return 0
    po = polib.pofile(str(po_path))
    by_msgid = {e.msgid: e for e in po}

    fixed = 0
    for msgid, by_lang in FIXES.items():
        new_msgstr = by_lang.get(lang)
        if not new_msgstr:
            continue
        entry = by_msgid.get(msgid)
        if not entry:
            continue
        if entry.msgstr != new_msgstr:
            old = entry.msgstr
            entry.msgstr = new_msgstr
            fixed += 1
    po.save(str(po_path))
    mo_path = po_path.with_suffix('.mo')
    po.save_as_mofile(str(mo_path))
    return fixed


def main():
    total = 0
    for lang in ('uk', 'fr', 'de'):
        n = apply_fixes(lang)
        print(f'  {lang}: исправлено {n} переводов, .mo обновлён')
        total += n
    print(f'\nИтого: {total} переводов исправлено')


if __name__ == '__main__':
    main()
