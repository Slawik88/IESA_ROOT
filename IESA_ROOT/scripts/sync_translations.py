"""
BLOCK 12 (audit v3): синхронизация переводов без gettext.

1. Извлекает {% trans "X" %} из всех шаблонов
2. Сравнивает с .po файлами locale/<lang>/LC_MESSAGES/django.po
3. Добавляет недостающие msgid с переводами (если есть в KNOWN_TRANSLATIONS)
4. Компилирует .mo через polib (gettext не нужен)

Usage: python scripts/sync_translations.py
"""
import re
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding='utf-8')
import polib

BASE = Path(__file__).resolve().parent.parent
TEMPLATES_ROOTS = [
    BASE / 'users' / 'templates',
    BASE / 'core' / 'templates',
    BASE / 'blog' / 'templates',
    BASE / 'products' / 'templates',
    BASE / 'gallery' / 'templates',
    BASE / 'notifications' / 'templates',
    BASE / 'templates',
]

# Регулярка для {% trans "X" %}, {% trans 'X' %}, {% blocktrans %}X{% endblocktrans %}
_TRANS_RE = re.compile(
    r'\{%\s*trans\s+"([^"]*)"\s*(?:as\s+\w+\s*)?%\}'
    r"|\{%\s*trans\s+'([^']*)'\s*(?:as\s+\w+\s*)?%\}"
)
_BLOCKTRANS_RE = re.compile(
    r'\{%\s*blocktrans[^%]*%\}(.*?)\{%\s*endblocktrans\s*%\}', re.S
)


def extract_trans_from_template(path: Path) -> set[str]:
    try:
        content = path.read_text(encoding='utf-8', errors='ignore')
    except Exception:
        return set()
    res = set()
    for m in _TRANS_RE.finditer(content):
        s = (m.group(1) or m.group(2) or '').strip()
        if s:
            res.add(s)
    for m in _BLOCKTRANS_RE.finditer(content):
        s = m.group(1).strip()
        if s:
            res.add(s)
    return res


def all_template_msgids() -> set[str]:
    msgids = set()
    for root in TEMPLATES_ROOTS:
        if not root.exists():
            continue
        for p in root.rglob('*.html'):
            msgids |= extract_trans_from_template(p)
    return msgids


# ── Известные переводы для UK / FR / DE ────────────────────────────────────
# Покрывают основные UI-строки из login/register/profile/base
KNOWN: dict[str, dict[str, str]] = {
    # Login / Register
    'Welcome':                                                                    {'uk': 'Вітаємо',                          'fr': 'Bienvenue',                       'de': 'Willkommen'},
    'Back':                                                                       {'uk': 'Знову',                            'fr': 'Retour',                          'de': 'Zurück'},
    'Members Portal':                                                             {'uk': 'Портал учасників',                  'fr': 'Portail des membres',             'de': 'Mitglieder-Portal'},
    'Sign in and connect with the IESA community — posts, events, benefits and more.': {'uk': 'Увійдіть і приєднайтесь до спільноти IESA — пости, події, переваги та інше.', 'fr': 'Connectez-vous à la communauté IESA — publications, événements, avantages et plus.', 'de': 'Melden Sie sich an und verbinden Sie sich mit der IESA-Community — Beiträge, Veranstaltungen, Vorteile und mehr.'},
    'Digital card & PIN code':                                                    {'uk': 'Цифрова карта та PIN-код',          'fr': 'Carte numérique et code PIN',     'de': 'Digitale Karte & PIN-Code'},
    'Posts, feed & community':                                                    {'uk': 'Пости, стрічка та спільнота',       'fr': 'Publications, flux et communauté','de': 'Beiträge, Feed & Community'},
    'Events, RSVPs & benefits':                                                   {'uk': 'Події, реєстрації та переваги',     'fr': 'Événements, inscriptions et avantages','de':'Veranstaltungen, RSVPs & Vorteile'},
    'Access your account':                                                        {'uk': 'Доступ до вашого облікового запису','fr': 'Accédez à votre compte',          'de': 'Greifen Sie auf Ihr Konto zu'},
    'Enter your credentials to continue.':                                        {'uk': 'Введіть свої облікові дані для продовження.','fr': 'Saisissez vos identifiants pour continuer.','de': 'Geben Sie Ihre Anmeldedaten ein, um fortzufahren.'},
    'Join the Community':                                                         {'uk': 'Приєднатися до спільноти',          'fr': 'Rejoindre la communauté',         'de': 'Treten Sie der Community bei'},
    'Create your account and become part of IESA.':                               {'uk': 'Створіть обліковий запис і станьте частиною IESA.','fr': 'Créez votre compte et devenez membre d\'IESA.','de': 'Erstellen Sie Ihr Konto und werden Sie Teil von IESA.'},
    'NEW MEMBER':                                                                 {'uk': 'НОВИЙ УЧАСНИК',                     'fr': 'NOUVEAU MEMBRE',                  'de': 'NEUES MITGLIED'},
    'Account':                                                                    {'uk': 'Обліковий запис',                   'fr': 'Compte',                          'de': 'Konto'},
    'Confirm':                                                                    {'uk': 'Підтвердити',                       'fr': 'Confirmer',                       'de': 'Bestätigen'},
    'Continue':                                                                   {'uk': 'Продовжити',                        'fr': 'Continuer',                       'de': 'Weiter'},
    'PLATFORM':                                                                   {'uk': 'ПЛАТФОРМА',                         'fr': 'PLATEFORME',                      'de': 'PLATTFORM'},
    'ACCESS':                                                                     {'uk': 'ДОСТУП',                            'fr': 'ACCÈS',                           'de': 'ZUGRIFF'},
    'SECURE':                                                                     {'uk': 'БЕЗПЕЧНО',                          'fr': 'SÉCURISÉ',                        'de': 'SICHER'},
    # Profile completeness + activity
    'pts':                                                                        {'uk': 'очок',                              'fr': 'pts',                             'de': 'Pkt.'},
    'To Intermediate':                                                            {'uk': 'До «Середнього»',                   'fr': 'Vers Intermédiaire',              'de': 'Bis Mittel'},
    'To Expert':                                                                  {'uk': 'До «Експерта»',                     'fr': 'Vers Expert',                     'de': 'Bis Experte'},
    'To Advanced':                                                                {'uk': 'До «Просунутого»',                  'fr': 'Vers Avancé',                     'de': 'Bis Fortgeschritten'},
    'To Legend':                                                                  {'uk': 'До «Легенди»',                      'fr': 'Vers Légende',                    'de': 'Bis Legende'},
    'complete':                                                                   {'uk': 'заповнено',                         'fr': 'complété',                        'de': 'abgeschlossen'},
    'steps':                                                                      {'uk': 'кроків',                            'fr': 'étapes',                          'de': 'Schritte'},
    'Get started — quick actions':                                                {'uk': 'Почати — швидкі дії',               'fr': 'Commencer — actions rapides',     'de': 'Loslegen — Schnellaktionen'},
    'Show steps':                                                                 {'uk': 'Показати кроки',                    'fr': 'Afficher les étapes',             'de': 'Schritte anzeigen'},
    # PIN/Card
    'Not yet issued — contact iesa@iesasport.ch':                                 {'uk': 'Ще не випущена — звертайтесь на iesa@iesasport.ch', 'fr': 'Pas encore émise — contactez iesa@iesasport.ch', 'de': 'Noch nicht ausgestellt — wenden Sie sich an iesa@iesasport.ch'},
    # TG fallback
    "Bot link doesn't work? Find manually":                                       {'uk': 'Посилання не працює? Знайдіть вручну','fr': "Le lien ne fonctionne pas ? Recherchez manuellement",'de': 'Link funktioniert nicht? Manuell suchen'},
    'Open the Telegram app':                                                      {'uk': 'Відкрийте додаток Telegram',        'fr': "Ouvrez l'application Telegram",   'de': 'Öffnen Sie die Telegram-App'},
    'In the search field at the top, paste:':                                     {'uk': 'У полі пошуку зверху вставте:',     'fr': 'Dans le champ de recherche en haut, collez :', 'de': 'Fügen Sie im Suchfeld oben ein:'},
    'Open the bot and press the «Start» button':                                  {'uk': 'Відкрийте бота і натисніть «Start»','fr': "Ouvrez le bot et appuyez sur le bouton « Start »",'de': 'Öffnen Sie den Bot und drücken Sie „Start"'},
    'Copied':                                                                     {'uk': 'Скопійовано',                       'fr': 'Copié',                           'de': 'Kopiert'},
    'Toggle password visibility':                                                 {'uk': 'Показати/сховати пароль',           'fr': 'Afficher/masquer le mot de passe','de': 'Passwort ein-/ausblenden'},
    'Search posts':                                                               {'uk': 'Пошук дописів',                     'fr': 'Rechercher des publications',     'de': 'Beiträge suchen'},
    # Component playground (staff-only, можно оставить английским, но для полноты)
    'Like':                                                                       {'uk': 'Подобається',                       'fr': "J'aime",                          'de': 'Gefällt mir'},
    'Unlike':                                                                     {'uk': 'Не подобається',                    'fr': "Je n'aime plus",                  'de': 'Nicht mehr gefallen'},

    # Большой батч коротких UI-строк (батч 2)
    'ALL':              {'uk': 'УСІ',                'fr': 'TOUS',           'de': 'ALLE'},
    'All':              {'uk': 'Усі',                'fr': 'Tous',           'de': 'Alle'},
    'A→Z':              {'uk': 'А→Я',                'fr': 'A→Z',            'de': 'A→Z'},
    'Z→A':              {'uk': 'Я→А',                'fr': 'Z→A',            'de': 'Z→A'},
    'END':              {'uk': 'КІНЕЦЬ',             'fr': 'FIN',            'de': 'ENDE'},
    'Log':              {'uk': 'Журнал',             'fr': 'Journal',        'de': 'Log'},
    'PIN':              {'uk': 'PIN',                'fr': 'PIN',            'de': 'PIN'},
    'Set':              {'uk': 'Встановити',         'fr': 'Définir',        'de': 'Festlegen'},
    'Also':             {'uk': 'Також',              'fr': 'Aussi',          'de': 'Auch'},
    'BLOG':             {'uk': 'БЛОГ',               'fr': 'BLOG',           'de': 'BLOG'},
    'Blog':             {'uk': 'Блог',               'fr': 'Blog',           'de': 'Blog'},
    'DATE':             {'uk': 'ДАТА',               'fr': 'DATE',           'de': 'DATUM'},
    'Fair':             {'uk': 'Задовільно',         'fr': 'Correct',        'de': 'Mittel'},
    'PAST':             {'uk': 'МИНУЛІ',             'fr': 'PASSÉ',          'de': 'VERGANGEN'},
    'Show':             {'uk': 'Показати',           'fr': 'Afficher',       'de': 'Anzeigen'},
    'Your':             {'uk': 'Ваш',                'fr': 'Votre',          'de': 'Ihr'},
    'edit':             {'uk': 'редагувати',         'fr': 'modifier',       'de': 'bearbeiten'},
    'last':             {'uk': 'останні',            'fr': 'derniers',       'de': 'letzte'},
    'next':             {'uk': 'наступний',          'fr': 'suivant',        'de': 'nächste'},
    'prev':             {'uk': 'попередній',         'fr': 'précédent',      'de': 'vorherige'},
    'Clear':            {'uk': 'Очистити',           'fr': 'Effacer',        'de': 'Löschen'},
    'EMAIL':            {'uk': 'EMAIL',              'fr': 'E-MAIL',         'de': 'E-MAIL'},
    'Links':            {'uk': 'Посилання',          'fr': 'Liens',          'de': 'Links'},
    'NOTES':            {'uk': 'НОТАТКИ',            'fr': 'NOTES',          'de': 'NOTIZEN'},
    'POSTS':            {'uk': 'ДОПИСИ',             'fr': 'PUBLICATIONS',   'de': 'BEITRÄGE'},
    'START':            {'uk': 'СТАРТ',              'fr': 'DÉBUT',          'de': 'START'},
    'Saved':            {'uk': 'Збережено',          'fr': 'Enregistré',     'de': 'Gespeichert'},
    'TOTAL':            {'uk': 'ВСЬОГО',             'fr': 'TOTAL',          'de': 'GESAMT'},
    'Total':            {'uk': 'Всього',             'fr': 'Total',          'de': 'Gesamt'},
    'total':            {'uk': 'всього',             'fr': 'total',          'de': 'gesamt'},
    'words':            {'uk': 'слів',               'fr': 'mots',           'de': 'Wörter'},
    'years':            {'uk': 'років',              'fr': 'ans',            'de': 'Jahre'},
    'Access':           {'uk': 'Доступ',             'fr': 'Accès',          'de': 'Zugriff'},
    'Charts':           {'uk': 'Графіки',            'fr': 'Graphiques',     'de': 'Diagramme'},
    'DATE ↑':           {'uk': 'ДАТА ↑',             'fr': 'DATE ↑',         'de': 'DATUM ↑'},
    'DATE ↓':           {'uk': 'ДАТА ↓',             'fr': 'DATE ↓',         'de': 'DATUM ↓'},
    'E-mail':           {'uk': 'E-mail',             'fr': 'E-mail',         'de': 'E-Mail'},
    'EVENTS':           {'uk': 'ПОДІЇ',              'fr': 'ÉVÉNEMENTS',     'de': 'EVENTS'},
    'LATEST':           {'uk': 'НОВІ',               'fr': 'RÉCENTS',        'de': 'NEUESTE'},
    'Linked':           {'uk': 'Прив\'язано',        'fr': 'Lié',            'de': 'Verknüpft'},
    'MEMBER':           {'uk': 'УЧАСНИК',            'fr': 'MEMBRE',         'de': 'MITGLIED'},
    'Points':           {'uk': 'Очки',               'fr': 'Points',         'de': 'Punkte'},
    'Recent':           {'uk': 'Нещодавні',          'fr': 'Récents',        'de': 'Kürzlich'},
    'Review':           {'uk': 'Відгук',             'fr': 'Examen',         'de': 'Bewertung'},
    'STATUS':           {'uk': 'СТАТУС',             'fr': 'STATUT',         'de': 'STATUS'},
    'Secure':           {'uk': 'Безпечно',           'fr': 'Sécurisé',       'de': 'Sicher'},
    'Strong':           {'uk': 'Сильний',            'fr': 'Fort',           'de': 'Stark'},
    'VISITS':           {'uk': 'ВІЗИТИ',             'fr': 'VISITES',        'de': 'BESUCHE'},
    'cancel':           {'uk': 'скасувати',          'fr': 'annuler',        'de': 'abbrechen'},
    'number':           {'uk': 'цифра',              'fr': 'chiffre',        'de': 'Zahl'},
    'photos':           {'uk': 'фото',               'fr': 'photos',         'de': 'Fotos'},
    'unique':           {'uk': 'унікальний',         'fr': 'unique',         'de': 'einzigartig'},
    'ADDRESS':          {'uk': 'АДРЕСА',             'fr': 'ADRESSE',        'de': 'ADRESSE'},
    'Apparel':          {'uk': 'Одяг',               'fr': 'Vêtements',      'de': 'Kleidung'},
    'Card ID':          {'uk': 'ID карти',           'fr': 'ID carte',       'de': 'Karten-ID'},
    'Connect':          {'uk': 'Підключити',         'fr': 'Connecter',      'de': 'Verbinden'},
    'FILTERS':          {'uk': 'ФІЛЬТРИ',            'fr': 'FILTRES',        'de': 'FILTER'},
    'Filters':          {'uk': 'Фільтри',            'fr': 'Filtres',        'de': 'Filter'},
    'Go Back':          {'uk': 'Назад',              'fr': 'Retour',         'de': 'Zurück'},
    'Install':          {'uk': 'Встановити',         'fr': 'Installer',      'de': 'Installieren'},
    'Not now':          {'uk': 'Не зараз',           'fr': 'Pas maintenant', 'de': 'Nicht jetzt'},
    'PENDING':          {'uk': 'ОЧІКУВАННЯ',         'fr': 'EN ATTENTE',     'de': 'AUSSTEHEND'},
    'POPULAR':          {'uk': 'ПОПУЛЯРНІ',          'fr': 'POPULAIRES',     'de': 'BELIEBT'},
    'Revenue':          {'uk': 'Дохід',              'fr': 'Revenus',        'de': 'Einnahmen'},
    'SERVICE':          {'uk': 'ПОСЛУГА',            'fr': 'SERVICE',        'de': 'SERVICE'},
    'Savings':          {'uk': 'Економія',           'fr': 'Économies',      'de': 'Ersparnisse'},
    'Saving…':          {'uk': 'Збереження…',        'fr': 'Enregistrement…','de': 'Wird gespeichert…'},
    'Section':          {'uk': 'Розділ',             'fr': 'Section',        'de': 'Abschnitt'},
    'last 20':          {'uk': 'останні 20',         'fr': '20 derniers',    'de': 'letzte 20'},
    'min ago':          {'uk': 'хв тому',            'fr': 'min plus tôt',   'de': 'Min. her'},
    'Calendar':         {'uk': 'Календар',           'fr': 'Calendrier',     'de': 'Kalender'},
    'Capacity':         {'uk': 'Місткість',          'fr': 'Capacité',       'de': 'Kapazität'},
    'Collapse':         {'uk': 'Згорнути',           'fr': 'Réduire',        'de': 'Einklappen'},
    'Cost CHF':         {'uk': 'Вартість CHF',       'fr': 'Coût CHF',       'de': 'Kosten CHF'},
    'Featured':         {'uk': 'Рекомендовано',      'fr': 'En vedette',     'de': 'Empfohlen'},
    'My Posts':         {'uk': 'Мої дописи',         'fr': 'Mes publications','de': 'Meine Beiträge'},
    'NEW POST':         {'uk': 'НОВИЙ ДОПИС',        'fr': 'NOUVEAU POST',   'de': 'NEUER BEITRAG'},
    'Next Day':         {'uk': 'Наступний день',     'fr': 'Jour suivant',   'de': 'Nächster Tag'},
    'Notifications':    {'uk': 'Сповіщення',         'fr': 'Notifications',  'de': 'Benachrichtigungen'},
    'Overview':         {'uk': 'Огляд',              'fr': 'Aperçu',         'de': 'Überblick'},
    'Posts':            {'uk': 'Дописи',             'fr': 'Publications',   'de': 'Beiträge'},
    'Profile':          {'uk': 'Профіль',            'fr': 'Profil',         'de': 'Profil'},
    'Search':           {'uk': 'Пошук',              'fr': 'Rechercher',     'de': 'Suchen'},
    'Events':           {'uk': 'Події',              'fr': 'Événements',     'de': 'Events'},
    'Gallery':          {'uk': 'Галерея',            'fr': 'Galerie',        'de': 'Galerie'},
    'Members':          {'uk': 'Учасники',           'fr': 'Membres',        'de': 'Mitglieder'},
    'Products':         {'uk': 'Продукти',           'fr': 'Produits',       'de': 'Produkte'},
    'Settings':         {'uk': 'Налаштування',       'fr': 'Paramètres',     'de': 'Einstellungen'},
    'Community':        {'uk': 'Спільнота',          'fr': 'Communauté',     'de': 'Community'},
    'Home':             {'uk': 'Головна',            'fr': 'Accueil',        'de': 'Startseite'},
    'About':            {'uk': 'Про нас',            'fr': 'À propos',       'de': 'Über uns'},
    'Benefits':         {'uk': 'Переваги',           'fr': 'Avantages',      'de': 'Vorteile'},
    'Sign In':          {'uk': 'Увійти',             'fr': 'Connexion',      'de': 'Anmelden'},
    'Register':         {'uk': 'Зареєструватися',    'fr': 'S\'inscrire',    'de': 'Registrieren'},
    'Logout':           {'uk': 'Вийти',              'fr': 'Déconnexion',    'de': 'Abmelden'},
    'My Cabinet':       {'uk': 'Мій кабінет',        'fr': 'Mon espace',     'de': 'Mein Bereich'},
    'Edit Profile':     {'uk': 'Редагувати профіль', 'fr': 'Modifier le profil','de':'Profil bearbeiten'},
    'Partner Portal':   {'uk': 'Портал партнера',    'fr': 'Portail partenaire','de':'Partner-Portal'},
    'Dashboard & stats':{'uk': 'Кабінет та статистика','fr':'Tableau de bord et stats','de':'Dashboard & Statistik'},
    'Visits & analytics':{'uk':'Візити та аналітика','fr':'Visites et analytique','de':'Besuche & Analytik'},
    'Settings & links': {'uk': 'Налаштування та посилання','fr':'Paramètres et liens','de':'Einstellungen & Links'},
    'Sign out':         {'uk': 'Вийти',              'fr': 'Déconnexion',    'de': 'Abmelden'},
    'Toggle theme':     {'uk': 'Перемкнути тему',    'fr': 'Changer de thème','de': 'Thema wechseln'},
    'Toggle navigation':{'uk': 'Перемкнути меню',    'fr': 'Basculer le menu','de': 'Menü umschalten'},
    'Notifications':    {'uk': 'Сповіщення',         'fr': 'Notifications',  'de': 'Benachrichtigungen'},
    'Profile menu':     {'uk': 'Меню профілю',       'fr': 'Menu profil',    'de': 'Profilmenü'},
    'How it works':     {'uk': 'Як це працює',       'fr': 'Comment ça marche','de':'Wie es funktioniert'},
    'Send':             {'uk': 'Надіслати',          'fr': 'Envoyer',        'de': 'Senden'},
    'Send comment':     {'uk': 'Надіслати коментар', 'fr': 'Envoyer le commentaire','de':'Kommentar senden'},
    'Save':             {'uk': 'Зберегти',           'fr': 'Enregistrer',    'de': 'Speichern'},
    'Cancel':           {'uk': 'Скасувати',          'fr': 'Annuler',        'de': 'Abbrechen'},
    'Delete':           {'uk': 'Видалити',           'fr': 'Supprimer',      'de': 'Löschen'},
    'Edit':             {'uk': 'Редагувати',         'fr': 'Modifier',       'de': 'Bearbeiten'},
    'Close':            {'uk': 'Закрити',            'fr': 'Fermer',         'de': 'Schließen'},
    'Loading...':       {'uk': 'Завантаження...',    'fr': 'Chargement...',  'de': 'Laden...'},
    'Reply':            {'uk': 'Відповісти',         'fr': 'Répondre',       'de': 'Antworten'},
    'Comments':         {'uk': 'Коментарі',          'fr': 'Commentaires',   'de': 'Kommentare'},
    'COMMENTS':         {'uk': 'КОМЕНТАРІ',          'fr': 'COMMENTAIRES',   'de': 'KOMMENTARE'},
    'min read':         {'uk': 'хв читання',         'fr': 'min de lecture', 'de': 'Min. Lesezeit'},
    'views':            {'uk': 'переглядів',         'fr': 'vues',           'de': 'Aufrufe'},
    'Anonymous':        {'uk': 'Анонімно',           'fr': 'Anonyme',        'de': 'Anonym'},
    'Breadcrumb':       {'uk': 'Хлібні крихти',      'fr': 'Fil d\'Ariane',  'de': 'Breadcrumb'},
    'Reading time':     {'uk': 'Час читання',        'fr': 'Temps de lecture','de':'Lesezeit'},
    'Filters':          {'uk': 'Фільтри',            'fr': 'Filtres',        'de': 'Filter'},
    'PUBLISHED':        {'uk': 'ОПУБЛІКОВАНО',       'fr': 'PUBLIÉ',         'de': 'VERÖFFENTLICHT'},
    'ORDER':            {'uk': 'ПОРЯДОК',            'fr': 'ORDRE',          'de': 'REIHENFOLGE'},
    'TRENDING':         {'uk': 'В ТРЕНДІ',           'fr': 'TENDANCES',      'de': 'IM TREND'},
    'RECOMMENDED POSTS':{'uk': 'РЕКОМЕНДОВАНІ ДОПИСИ','fr':'PUBLICATIONS RECOMMANDÉES','de':'EMPFOHLENE BEITRÄGE'},
    'No Posts Yet':     {'uk': 'Поки немає дописів', 'fr': 'Pas encore de publications','de':'Noch keine Beiträge'},
    'Be the first to share news or ideas with the community': {
        'uk': 'Будь першим, хто поділиться новинами або ідеями зі спільнотою',
        'fr': 'Soyez le premier à partager des actualités ou des idées avec la communauté',
        'de': 'Seien Sie der Erste, der Neuigkeiten oder Ideen mit der Community teilt'
    },
    'Create First Post':{'uk': 'Створити перший допис','fr':'Créer la première publication','de':'Ersten Beitrag erstellen'},
    'Join Community':   {'uk': 'Приєднатися',        'fr': 'Rejoindre',      'de': 'Beitreten'},
    'sign in':          {'uk': 'увійдіть',           'fr': 'connectez-vous', 'de': 'anmelden'},
    'register':         {'uk': 'зареєструйтесь',     'fr': 'inscrivez-vous', 'de': 'registrieren'},
    'To comment, please':{'uk':'Щоб коментувати,',   'fr':'Pour commenter,', 'de':'Zum Kommentieren,'},
    'or':               {'uk': 'або',                'fr': 'ou',             'de': 'oder'},
    'type to search...':{'uk': 'почніть вводити...', 'fr': 'tapez pour rechercher...','de':'zum Suchen tippen...'},
    'Your comment...':  {'uk': 'Ваш коментар...',    'fr': 'Votre commentaire...','de':'Ihr Kommentar...'},
    # Quick Actions menu
    'QUICK ACTIONS':    {'uk': 'ШВИДКІ ДІЇ',         'fr': 'ACTIONS RAPIDES','de': 'SCHNELLAKTIONEN'},
    'Write Post':       {'uk': 'Написати пост',      'fr': 'Écrire un post', 'de': 'Beitrag schreiben'},
    'Actions':          {'uk': 'Дії',                'fr': 'Actions',        'de': 'Aktionen'},
    'Quick actions':    {'uk': 'Швидкі дії',         'fr': 'Actions rapides','de': 'Schnellaktionen'},
    'Quick Visit Log':  {'uk': 'Швидкий запис візиту','fr':'Visite rapide',  'de': 'Schneller Besuch'},
    'Show QR Code':     {'uk': 'Показати QR-код',    'fr': 'Afficher QR',    'de': 'QR-Code anzeigen'},
    'Visit':            {'uk': 'Візит',              'fr': 'Visite',         'de': 'Besuch'},
    'YOUR MEMBERSHIP QR':{'uk':'ВАШ QR УЧАСНИКА',    'fr':'VOTRE QR MEMBRE', 'de':'IHR MITGLIEDS-QR'},
    'Scan at partner location':{'uk':'Скануй у партнера','fr':'Scannez chez un partenaire','de':'Beim Partner scannen'},
    'Swipe down to close':{'uk':'Свайп вниз для закриття','fr':'Glissez vers le bas pour fermer','de':'Nach unten wischen zum Schließen'},
    # Alerts/Errors
    'Skip for now':     {'uk': 'Пропустити',         'fr': 'Passer',         'de': 'Überspringen'},
    'Skip to main content':{'uk':'Перейти до основного вмісту','fr':'Aller au contenu principal','de':'Zum Hauptinhalt springen'},
    'Mobile navigation':{'uk':'Мобільна навігація',  'fr':'Navigation mobile','de':'Mobile Navigation'},
    'Alerts':           {'uk':'Сповіщення',          'fr':'Alertes',         'de':'Warnungen'},
    'Back to top':      {'uk':'Нагору',              'fr':'Retour en haut',  'de':'Nach oben'},
    'Back to profile':  {'uk':'Назад до профілю',    'fr':'Retour au profil','de':'Zurück zum Profil'},
    # Connect Telegram
    'Connect Telegram': {'uk':'Підключити Telegram', 'fr':'Connecter Telegram','de':'Telegram verbinden'},
    'Telegram Connected!':{'uk':'Telegram підключено!','fr':'Telegram connecté !','de':'Telegram verbunden!'},
    'Redirecting…':     {'uk':'Перенаправлення…',    'fr':'Redirection…',    'de':'Weiterleitung…'},
    'Open in Telegram': {'uk':'Відкрити в Telegram', 'fr':'Ouvrir dans Telegram','de':'In Telegram öffnen'},
    'Instructions':     {'uk':'Інструкції',          'fr':'Instructions',    'de':'Anleitung'},
    'Open':             {'uk':'Відкрити',            'fr':'Ouvrir',          'de':'Öffnen'},
    'in Telegram':      {'uk':'у Telegram',          'fr':'dans Telegram',   'de':'in Telegram'},
    'Open the IESA Sport bot in Telegram':{'uk':'Відкрийте бот IESA Sport у Telegram','fr':'Ouvrez le bot IESA Sport dans Telegram','de':'Öffnen Sie den IESA Sport-Bot in Telegram'},
    'Press':            {'uk':'Натисніть',           'fr':'Appuyez sur',     'de':'Drücken Sie'},
    'Attach account':   {'uk':'Прив\'язати акаунт',  'fr':'Lier le compte',  'de':'Konto verknüpfen'},
    'or send':          {'uk':'або надішліть',       'fr':'ou envoyez',      'de':'oder senden Sie'},
    'Enter the 6-digit code from the bot below':{'uk':'Введіть 6-значний код від бота нижче','fr':'Saisissez le code à 6 chiffres ci-dessous','de':'Geben Sie den 6-stelligen Code unten ein'},
    'The code is valid for 10 minutes and can only be used once.':{'uk':'Код дійсний 10 хвилин і використовується одноразово.','fr':'Le code est valide 10 minutes et ne peut être utilisé qu\'une fois.','de':'Der Code ist 10 Minuten gültig und nur einmal verwendbar.'},
    '6-digit verification code':{'uk':'6-значний код підтвердження','fr':'Code de vérification à 6 chiffres','de':'6-stelliger Bestätigungscode'},
    'Confirm & Connect':{'uk':'Підтвердити та підключити','fr':'Confirmer & connecter','de':'Bestätigen & verbinden'},

    # HOTFIX 2026-05-23: ACR strings (audit feedback round 2)
    'Apply for partner':{'uk':'Стати партнером', 'fr':'Devenir partenaire', 'de':'Partner werden'},
    'Application pending':{'uk':'Заявка на розгляді', 'fr':'Demande en attente', 'de':'Antrag in Bearbeitung'},
    'STATUS UPGRADE':{'uk':'ПІДВИЩЕННЯ СТАТУСУ', 'fr':'PROMOTION DE STATUT', 'de':'STATUS-UPGRADE'},
    'Apply for a role upgrade':{'uk':'Подати заявку на підвищення ролі', 'fr':'Demander une promotion de rôle', 'de':'Rollen-Upgrade beantragen'},
    "Want to become an IESA partner or association staff? Submit a request — we'll review and contact you shortly.":{
        'uk':'Хочете стати партнером або співробітником асоціації IESA? Подайте заявку — ми розглянемо її та зв\'яжемось з вами.',
        'fr':'Voulez-vous devenir partenaire ou membre du personnel IESA ? Soumettez une demande — nous l\'examinerons et vous contacterons.',
        'de':'Möchten Sie IESA-Partner oder Mitarbeiter werden? Reichen Sie einen Antrag ein — wir prüfen ihn und melden uns bei Ihnen.'
    },
    'ROLE & ACTIVITY':{'uk':'РОЛЬ ТА ДІЯЛЬНІСТЬ', 'fr':'RÔLE ET ACTIVITÉ', 'de':'ROLLE UND TÄTIGKEIT'},
    'DESIRED ROLE':{'uk':'БАЖАНА РОЛЬ', 'fr':'RÔLE SOUHAITÉ', 'de':'GEWÜNSCHTE ROLLE'},
    'Your request is under review':{'uk':'Ваша заявка на розгляді', 'fr':'Votre demande est en cours d\'examen', 'de':'Ihr Antrag wird geprüft'},
    'Submitted':{'uk':'Подано', 'fr':'Soumis', 'de':'Eingereicht'},
    'Search activity area...':{'uk':'Пошук сфери діяльності...', 'fr':'Rechercher un domaine...', 'de':'Tätigkeitsbereich suchen...'},
    'No results found':{'uk':'Нічого не знайдено', 'fr':'Aucun résultat', 'de':'Keine Ergebnisse'},
    'Submit application':{'uk':'Подати заявку', 'fr':'Envoyer la demande', 'de':'Antrag senden'},
    'Tell us about yourself':{'uk':'Розкажіть про себе', 'fr':'Parlez-nous de vous', 'de':'Erzählen Sie von sich'},
    'Contact information':{'uk':'Контактна інформація', 'fr':'Informations de contact', 'de':'Kontaktdaten'},
    'City / Country':{'uk':'Місто / Країна', 'fr':'Ville / Pays', 'de':'Stadt / Land'},
    'Activity area':{'uk':'Сфера діяльності', 'fr':'Domaine d\'activité', 'de':'Tätigkeitsbereich'},
    'Your message':{'uk':'Ваше повідомлення', 'fr':'Votre message', 'de':'Ihre Nachricht'},

    # Батч 3: исправления + новые UI строки из .po (empty msgstr)
    'Platform':         {'uk':'Платформа',           'fr':'Plateforme',      'de':'Plattform'},
    'New Member':       {'uk':'Новий учасник',       'fr':'Nouveau membre',  'de':'Neues Mitglied'},
    'Activity Level':   {'uk':'Рівень активності',   'fr':'Niveau d\'activité','de':'Aktivitätsstufe'},
    'About levels':     {'uk':'Про рівні',           'fr':'À propos des niveaux','de':'Über Stufen'},
    'ACTIVE MEMBER':    {'uk':'АКТИВНИЙ УЧАСНИК',    'fr':'MEMBRE ACTIF',    'de':'AKTIVES MITGLIED'},
    'MEMBER / CLIENT':  {'uk':'УЧАСНИК / КЛІЄНТ',    'fr':'MEMBRE / CLIENT', 'de':'MITGLIED / KUNDE'},
    'Member Profile':   {'uk':'Профіль учасника',    'fr':'Profil du membre','de':'Mitgliedsprofil'},
    'NOTES FOR MEMBER': {'uk':'НОТАТКИ ДЛЯ УЧАСНИКА','fr':'NOTES POUR LE MEMBRE','de':'NOTIZEN FÜR DAS MITGLIED'},
    'No members found': {'uk':'Учасників не знайдено','fr':'Aucun membre trouvé','de':'Keine Mitglieder gefunden'},
    'Find Member & Log Visit':{'uk':'Знайти учасника та записати візит','fr':'Trouver un membre et enregistrer une visite','de':'Mitglied finden & Besuch eintragen'},
    'Member PIN Code (6 digits)':{'uk':'PIN-код учасника (6 цифр)','fr':'Code PIN du membre (6 chiffres)','de':'Mitglieds-PIN-Code (6 Ziffern)'},
    'Log a visit for this member':{'uk':'Записати візит для цього учасника','fr':'Enregistrer une visite pour ce membre','de':'Besuch für dieses Mitglied eintragen'},
    'Members (30d)':    {'uk':'Учасники (30 дн)',    'fr':'Membres (30j)',   'de':'Mitglieder (30T)'},
    'Member promotion &amp; support':{'uk':'Просування та підтримка учасників','fr':'Promotion et soutien des membres','de':'Mitgliederwerbung & Support'},
    'Member suggestions':{'uk':'Пропозиції учасників','fr':'Suggestions des membres','de':'Mitgliedervorschläge'},
    'Digital membership card':{'uk':'Цифрова членська карта','fr':'Carte de membre numérique','de':'Digitale Mitgliedskarte'},
    'Blog, events, members, and shared experiences':{'uk':'Блог, події, учасники та спільний досвід','fr':'Blog, événements, membres et expériences partagées','de':'Blog, Events, Mitglieder und gemeinsame Erfahrungen'},
    "Go to any IESA partner location — gym, spa, clinic, shop. Tell staff you're an IESA member and show your 6-digit PIN. It refreshes every 12 minutes.":{
        'uk':'Завітайте до будь-якої точки партнера IESA — спортзал, спа, клініка, магазин. Скажіть персоналу, що ви учасник IESA, і покажіть свій 6-значний PIN. Він оновлюється кожні 12 хвилин.',
        'fr':'Rendez-vous chez n\'importe quel partenaire IESA — salle de sport, spa, clinique, boutique. Dites au personnel que vous êtes membre IESA et montrez votre code PIN à 6 chiffres. Il se renouvelle toutes les 12 minutes.',
        'de':'Besuchen Sie eine beliebige IESA-Partnerlocation — Fitnessstudio, Spa, Klinik, Shop. Sagen Sie dem Personal, dass Sie IESA-Mitglied sind, und zeigen Sie Ihren 6-stelligen PIN. Er wird alle 12 Minuten aktualisiert.'
    },
    'Ask the member to show their current PIN from their personal cabinet':{
        'uk':'Попросіть учасника показати поточний PIN з особистого кабінету',
        'fr':'Demandez au membre de montrer son PIN actuel depuis son espace personnel',
        'de':'Bitten Sie das Mitglied, die aktuelle PIN aus seinem persönlichen Bereich anzuzeigen'
    },
    'Describe your business/role and why you want to join IESA. What value can you offer to members?':{
        'uk':'Опишіть свій бізнес/роль і чому ви хочете приєднатися до IESA. Яку цінність ви можете запропонувати учасникам?',
        'fr':'Décrivez votre activité/rôle et pourquoi vous souhaitez rejoindre IESA. Quelle valeur pouvez-vous offrir aux membres ?',
        'de':'Beschreiben Sie Ihr Geschäft/Ihre Rolle und warum Sie IESA beitreten möchten. Welchen Wert können Sie den Mitgliedern bieten?'
    },
    'Account / membership issue':{'uk':'Питання акаунта / членства','fr':'Problème de compte / d\'adhésion','de':'Konto-/Mitgliedschaftsproblem'},

    # blocktrans шаблоны (динамические)
    'To %(level)s:':    {'uk':'До «%(level)s»:',     'fr':'Vers %(level)s :','de':'Bis %(level)s:'},

    # Footer / navbar
    'ABOUT':            {'uk':'ПРО НАС',             'fr':'À PROPOS',        'de':'ÜBER UNS'},
    'LINKS':            {'uk':'ПОСИЛАННЯ',           'fr':'LIENS',           'de':'LINKS'},
    'CONTACTS':         {'uk':'КОНТАКТИ',            'fr':'CONTACTS',        'de':'KONTAKTE'},
    'SOCIAL':           {'uk':'СОЦМЕРЕЖІ',           'fr':'RÉSEAUX SOCIAUX', 'de':'SOZIAL'},
    'Switzerland':      {'uk':'Швейцарія',           'fr':'Suisse',          'de':'Schweiz'},
    'IESA Association. All rights reserved.':{'uk':'Асоціація IESA. Всі права захищені.','fr':'Association IESA. Tous droits réservés.','de':'IESA Verein. Alle Rechte vorbehalten.'},
    'IESA connects sports leaders and partners, creating a space for growth, projects and events worldwide.':{
        'uk':'IESA об\'єднує спортивних лідерів і партнерів, створюючи простір для зростання, проєктів та подій по всьому світу.',
        'fr':'IESA met en relation des leaders et partenaires du sport, créant un espace pour la croissance, les projets et les événements à travers le monde.',
        'de':'IESA verbindet Sportführungskräfte und Partner und schafft einen Raum für Wachstum, Projekte und Veranstaltungen weltweit.'
    },
    'Email IESA':       {'uk':'Email IESA',          'fr':'Email IESA',      'de':'E-Mail IESA'},
    'Call IESA':        {'uk':'Подзвонити IESA',     'fr':'Appeler IESA',    'de':'IESA anrufen'},

    # Hero IESA Sport intro
    'IESA brings together people who choose an active life.':{'uk':'IESA об\'єднує людей, які обирають активне життя.','fr':'IESA rassemble les gens qui choisissent une vie active.','de':'IESA verbindet Menschen, die ein aktives Leben wählen.'},
    'International Extreme Sports Association':{'uk':'Міжнародна асоціація екстремальних видів спорту','fr':'Association Internationale de Sports Extrêmes','de':'Internationaler Verband für Extremsport'},
    'COMMUNITY':        {'uk':'СПІЛЬНОТА',           'fr':'COMMUNAUTÉ',      'de':'COMMUNITY'},
    'Share Ideas, Events & News':{'uk':'Діліться ідеями, подіями та новинами','fr':'Partagez idées, événements et actualités','de':'Teilen Sie Ideen, Events und News'},
    'Connect with fellow extreme sports enthusiasts':{'uk':'Спілкуйтеся з іншими любителями екстремальних видів спорту','fr':'Connectez-vous avec d\'autres passionnés de sports extrêmes','de':'Vernetzen Sie sich mit anderen Extremsport-Enthusiasten'},
    'Sign in or register to access the community':{'uk':'Увійдіть або зареєструйтесь, щоб отримати доступ до спільноти','fr':'Connectez-vous ou inscrivez-vous pour accéder à la communauté','de':'Melden Sie sich an oder registrieren Sie sich, um auf die Community zuzugreifen'},
    'Join our community to create posts, comment and engage with members':{'uk':'Приєднайтесь до нашої спільноти, щоб створювати дописи, коментувати та спілкуватися з учасниками','fr':'Rejoignez notre communauté pour créer des publications, commenter et interagir avec les membres','de':'Treten Sie unserer Community bei, um Beiträge zu erstellen, zu kommentieren und mit Mitgliedern zu interagieren'},

    # Comments
    'sign in':          {'uk':'увійдіть',            'fr':'connectez-vous',  'de':'anmelden'},

    # Common partners / dashboard
    'Dashboard':        {'uk':'Кабінет',             'fr':'Tableau de bord', 'de':'Dashboard'},
    'Partner Dashboard':{'uk':'Кабінет партнера',    'fr':'Tableau de bord partenaire','de':'Partner-Dashboard'},
    'My Calendar':      {'uk':'Мій календар',        'fr':'Mon calendrier',  'de':'Mein Kalender'},
    'Username':         {'uk':'Ім\'я користувача',   'fr':'Nom d\'utilisateur','de':'Benutzername'},
    'Email':            {'uk':'E-mail',              'fr':'E-mail',          'de':'E-Mail'},
    'Full name':        {'uk':'Повне ім\'я',         'fr':'Nom complet',     'de':'Vollständiger Name'},
    'Phone':            {'uk':'Телефон',             'fr':'Téléphone',       'de':'Telefon'},
    'Account Info':     {'uk':'Інформація про акаунт','fr':'Infos du compte','de':'Konto-Info'},
    'Visit History':    {'uk':'Історія візитів',     'fr':'Historique des visites','de':'Besuchshistorie'},
    'Verified':         {'uk':'Підтверджено',        'fr':'Vérifié',         'de':'Verifiziert'},
    'Pending verification':{'uk':'Очікує підтвердження','fr':'En attente de vérification','de':'Verifizierung ausstehend'},
    'Member':           {'uk':'Учасник',             'fr':'Membre',          'de':'Mitglied'},
    'Partner':          {'uk':'Партнер',             'fr':'Partenaire',      'de':'Partner'},
    'User':             {'uk':'Користувач',          'fr':'Utilisateur',     'de':'Benutzer'},
    'QR Code':          {'uk':'QR-код',              'fr':'QR Code',         'de':'QR-Code'},
    'PIN & Card':       {'uk':'PIN та карта',        'fr':'PIN & Carte',     'de':'PIN & Karte'},
    'Your QR Card':     {'uk':'Ваша QR-карта',       'fr':'Votre carte QR',  'de':'Ihre QR-Karte'},
    'Scan to open your public profile':{'uk':'Скануй, щоб відкрити публічний профіль','fr':'Scannez pour ouvrir votre profil public','de':'Scannen, um Ihr öffentliches Profil zu öffnen'},
    'PIN & Membership Card':{'uk':'PIN та членська карта','fr':'PIN & Carte de membre','de':'PIN & Mitgliedskarte'},
    'Visit a partner': {'uk':'Завітайте до партнера','fr':'Rendez-vous chez un partenaire','de':'Besuchen Sie einen Partner'},
    'Identify yourself':{'uk':'Підтвердіть себе',    'fr':'Identifiez-vous', 'de':'Identifizieren Sie sich'},
    'Show the PIN':    {'uk':'Покажіть PIN',         'fr':'Montrez le PIN',  'de':'PIN zeigen'},
    'Get notified ✅':  {'uk':'Отримайте сповіщення ✅','fr':'Recevez la notification ✅','de':'Benachrichtigung erhalten ✅'},
    'Go to any partner gym, shop or clinic.':{'uk':'Завітайте до партнерського залу, магазину або клініки.','fr':'Rendez-vous dans n\'importe quelle salle, boutique ou clinique partenaire.','de':'Besuchen Sie ein Partner-Studio, Geschäft oder eine Klinik.'},
    "Tell staff you're an IESA Sport member.":{'uk':'Скажіть персоналу, що ви учасник IESA Sport.','fr':'Dites au personnel que vous êtes membre IESA Sport.','de':'Sagen Sie dem Personal, dass Sie IESA Sport-Mitglied sind.'},
    'Show this 6-digit code — staff enters it to confirm.':{'uk':'Покажіть цей 6-значний код — персонал його введе для підтвердження.','fr':'Montrez ce code à 6 chiffres — le personnel le saisit pour confirmer.','de':'Zeigen Sie diesen 6-stelligen Code — das Personal gibt ihn zur Bestätigung ein.'},
    'Visit is logged. Telegram confirmation incoming.':{'uk':'Візит записано. Підтвердження прийде в Telegram.','fr':'Visite enregistrée. Confirmation Telegram en cours.','de':'Besuch eingetragen. Telegram-Bestätigung folgt.'},
    'Membership Inactive':{'uk':'Членство неактивне','fr':'Adhésion inactive','de':'Mitgliedschaft inaktiv'},
    'Contact administrator to activate your account.':{'uk':'Зв\'яжіться з адміністратором для активації акаунта.','fr':'Contactez l\'administrateur pour activer votre compte.','de':'Wenden Sie sich an den Administrator, um Ihr Konto zu aktivieren.'},
    'Physical Card':    {'uk':'Фізична карта',       'fr':'Carte physique',  'de':'Physische Karte'},
    'Active — issued':  {'uk':'Активна — видана',    'fr':'Active — émise',  'de':'Aktiv — ausgestellt'},

    # ──────────────────────────────────────────────────────────────────────────
    # BLOCK 1 (audit v4): расширенный placeholder для ACR description
    # ──────────────────────────────────────────────────────────────────────────
    'Describe your activity and why you want to join IESA. You can also add extra contacts for feedback (Telegram, WhatsApp, work email), specialization, experience — anything that will help us process your application faster.': {
        'uk': "Опишіть свою діяльність та чому хочете приєднатися до IESA. Можете додати додаткові контакти для зворотного зв'язку (Telegram, WhatsApp, робочий email), спеціалізацію, досвід — усе, що допоможе нам швидше обробити заявку.",
        'fr': "Décrivez votre activité et pourquoi vous souhaitez rejoindre IESA. Vous pouvez également ajouter des contacts supplémentaires pour le retour (Telegram, WhatsApp, e-mail professionnel), votre spécialisation, votre expérience — tout ce qui nous aidera à traiter votre demande plus rapidement.",
        'de': "Beschreiben Sie Ihre Tätigkeit und warum Sie IESA beitreten möchten. Sie können auch zusätzliche Kontakte für Rückmeldungen (Telegram, WhatsApp, Arbeits-E-Mail), Spezialisierung, Erfahrung hinzufügen — alles, was uns hilft, Ihren Antrag schneller zu bearbeiten.",
    },
    'chars': {'uk':'символів', 'fr':'caractères', 'de':'Zeichen'},

    # ──────────────────────────────────────────────────────────────────────────
    # BLOCK 2 (audit v4): BUSINESS CATEGORY — 9 групп + 40+ опций
    # ──────────────────────────────────────────────────────────────────────────
    # Группы
    'Sports & Fitness':              {'uk':'Спорт і фітнес',            'fr':'Sports et fitness',         'de':'Sport & Fitness'},
    'Health & Wellness':             {'uk':"Здоров'я та велнес",        'fr':'Santé et bien-être',        'de':'Gesundheit & Wellness'},
    'Insurance & Financial Services':{'uk':'Страхування та фінансові послуги','fr':'Assurance et services financiers','de':'Versicherung & Finanzdienstleistungen'},
    'Retail & Equipment':            {'uk':'Роздрібна торгівля та обладнання','fr':'Commerce et équipement','de':'Einzelhandel & Ausrüstung'},
    'Professional Services':         {'uk':'Професійні послуги',        'fr':'Services professionnels',   'de':'Professionelle Dienstleistungen'},
    'Education & Events':            {'uk':'Освіта та події',           'fr':'Éducation et événements',   'de':'Bildung & Veranstaltungen'},
    'Travel & Outdoor':              {'uk':'Подорожі та активний відпочинок','fr':'Voyages et plein air','de':'Reisen & Outdoor'},
    'Food & Hospitality':            {'uk':'Харчування та гостинність', 'fr':'Restauration et hospitalité','de':'Gastronomie & Gastgewerbe'},
    'Other':                         {'uk':'Інше',                      'fr':'Autre',                     'de':'Sonstiges'},

    # Опции — Sports & Fitness
    'Gym / Fitness Center':          {'uk':'Спортзал / Фітнес-центр',   'fr':'Salle de sport / Centre de fitness','de':'Fitnessstudio / Fitnesscenter'},
    'Martial Arts School':           {'uk':'Школа бойових мистецтв',    'fr':"École d'arts martiaux",     'de':'Kampfsportschule'},
    'Yoga / Pilates Studio':         {'uk':'Студія йоги / пілатесу',    'fr':'Studio de yoga / pilates',  'de':'Yoga- / Pilates-Studio'},
    'Swimming Pool / Aquatics':      {'uk':'Басейн / Водні види спорту','fr':'Piscine / Sports aquatiques','de':'Schwimmbad / Wassersport'},
    'CrossFit / Functional Training':{'uk':'Кросфіт / Функціональний тренінг','fr':'CrossFit / Entraînement fonctionnel','de':'CrossFit / Funktionelles Training'},
    'Cycling / Indoor Cycling':      {'uk':'Велоспорт / Велотренажери', 'fr':'Cyclisme / Cyclisme indoor','de':'Radsport / Indoor Cycling'},
    'Dance School':                  {'uk':'Школа танців',              'fr':'École de danse',            'de':'Tanzschule'},
    'Climbing / Boulder':            {'uk':'Скелелазіння / Болдер',     'fr':'Escalade / Bloc',           'de':'Klettern / Bouldern'},
    'Sports Club / Team':            {'uk':'Спортивний клуб / Команда', 'fr':'Club / Équipe sportive',    'de':'Sportverein / Mannschaft'},
    'Personal Trainer / Coach':      {'uk':'Персональний тренер',       'fr':'Coach personnel',           'de':'Personal Trainer / Coach'},

    # Опции — Health & Wellness
    'Physiotherapy / Rehabilitation':{'uk':'Фізіотерапія / Реабілітація','fr':'Physiothérapie / Réadaptation','de':'Physiotherapie / Rehabilitation'},
    'Massage / SPA / Wellness':      {'uk':'Масаж / СПА / Велнес',      'fr':'Massage / SPA / Bien-être', 'de':'Massage / SPA / Wellness'},
    'Nutrition / Dietology':         {'uk':'Харчування / Дієтологія',   'fr':'Nutrition / Diététique',    'de':'Ernährung / Diätologie'},
    'Medical / Healthcare':          {'uk':"Медицина / Охорона здоров'я",'fr':'Médical / Santé',          'de':'Medizin / Gesundheitswesen'},
    'Psychology / Mental Health':    {'uk':"Психологія / Психічне здоров'я",'fr':'Psychologie / Santé mentale','de':'Psychologie / Psychische Gesundheit'},
    'Chiropractic / Manual Therapy': {'uk':'Хіропрактика / Мануальна терапія','fr':'Chiropratique / Thérapie manuelle','de':'Chiropraktik / Manuelle Therapie'},

    # Опции — Insurance & Financial Services
    'Insurance Agent / Broker':      {'uk':'Страховий агент / Брокер',  'fr':"Agent d'assurance / Courtier",'de':'Versicherungsagent / Makler'},
    'Bank / Banking Services':       {'uk':'Банк / Банківські послуги', 'fr':'Banque / Services bancaires','de':'Bank / Bankdienstleistungen'},
    'Financial Advisor':             {'uk':'Фінансовий консультант',    'fr':'Conseiller financier',      'de':'Finanzberater'},

    # Опции — Retail & Equipment
    'Sports Equipment Shop':         {'uk':'Магазин спортивного інвентарю','fr':"Magasin d'équipement sportif",'de':'Sportgeschäft'},
    'Sports Clothing / Gear':        {'uk':'Спортивний одяг / Спорядження','fr':'Vêtements de sport / Équipement','de':'Sportbekleidung / Ausrüstung'},
    'Sports Supplements / Nutrition':{'uk':'Спортивне харчування',      'fr':'Compléments sportifs / Nutrition','de':'Sportergänzungen / Ernährung'},
    'Bike Shop / Service':           {'uk':'Веломагазин / Сервіс',      'fr':'Magasin de vélos / Service','de':'Fahrradgeschäft / Service'},

    # Опции — Professional Services
    'Legal Services / Lawyer':       {'uk':'Юридичні послуги / Адвокат','fr':'Services juridiques / Avocat','de':'Rechtsdienstleistungen / Anwalt'},
    'Accounting / Finance':          {'uk':'Бухгалтерія / Фінанси',     'fr':'Comptabilité / Finance',    'de':'Buchhaltung / Finanzen'},
    'Business Consulting':           {'uk':'Бізнес-консалтинг',         'fr':'Conseil en affaires',       'de':'Unternehmensberatung'},
    'Marketing / PR / Design':       {'uk':'Маркетинг / PR / Дизайн',   'fr':'Marketing / RP / Design',   'de':'Marketing / PR / Design'},
    'IT / Technology / Software':    {'uk':'IT / Технології / ПЗ',      'fr':'IT / Technologie / Logiciel','de':'IT / Technologie / Software'},

    # Опции — Education & Events
    'Professional Coaching':         {'uk':'Професійний коучинг',       'fr':'Coaching professionnel',    'de':'Professionelles Coaching'},
    'School / Educational Center':   {'uk':'Школа / Освітній центр',    'fr':'École / Centre éducatif',   'de':'Schule / Bildungszentrum'},
    'Event Organization':            {'uk':'Організація подій',         'fr':"Organisation d'événements", 'de':'Veranstaltungsorganisation'},
    'Seminar / Workshop Host':       {'uk':'Семінари / Майстер-класи',  'fr':'Hôte de séminaires / ateliers','de':'Seminar- / Workshop-Veranstalter'},

    # Опции — Travel & Outdoor
    'Travel / Tourism / Adventure':  {'uk':'Подорожі / Туризм / Пригоди','fr':'Voyages / Tourisme / Aventure','de':'Reisen / Tourismus / Abenteuer'},
    'Outdoor Activities / Hiking':   {'uk':'Активний відпочинок / Походи','fr':'Activités plein air / Randonnée','de':'Outdoor-Aktivitäten / Wandern'},
    'Water Sports / Diving / Surfing':{'uk':'Водні види спорту / Дайвінг / Серфінг','fr':'Sports nautiques / Plongée / Surf','de':'Wassersport / Tauchen / Surfen'},
    'Winter Sports / Ski':           {'uk':'Зимові види спорту / Лижі', 'fr':"Sports d'hiver / Ski",      'de':'Wintersport / Ski'},

    # Опции — Food & Hospitality
    'Restaurant / Cafe / Bar':       {'uk':'Ресторан / Кафе / Бар',     'fr':'Restaurant / Café / Bar',   'de':'Restaurant / Café / Bar'},
    'Healthy Food / Catering':       {'uk':'Здорове харчування / Кейтеринг','fr':'Alimentation saine / Traiteur','de':'Gesunde Ernährung / Catering'},
    'Hotel / Accommodation':         {'uk':'Готель / Розміщення',       'fr':'Hôtel / Hébergement',       'de':'Hotel / Unterkunft'},

    # Опции — Other
    'Media / Content / Photography': {'uk':'Медіа / Контент / Фото',    'fr':'Médias / Contenu / Photographie','de':'Medien / Content / Fotografie'},
    'eSports / Gaming':              {'uk':'Кіберспорт / Геймінг',      'fr':'eSports / Jeux',            'de':'eSports / Gaming'},
    'Other (describe below)':        {'uk':'Інше (опишіть нижче)',      'fr':'Autre (décrire ci-dessous)','de':'Sonstiges (unten beschreiben)'},

    # Связанные ACR метки
    'BUSINESS CATEGORY':             {'uk':'КАТЕГОРІЯ БІЗНЕСУ',         'fr':"CATÉGORIE D'ACTIVITÉ",      'de':'GESCHÄFTSKATEGORIE'},
    'your area':                     {'uk':'ваша сфера',                'fr':'votre domaine',             'de':'Ihr Bereich'},
    'choose':                        {'uk':'оберіть',                   'fr':'choisir',                   'de':'wählen'},
    'External Partner':              {'uk':'Зовнішній партнер',         'fr':'Partenaire externe',        'de':'Externer Partner'},
    'Association Staff':             {'uk':'Співробітник асоціації',    'fr':"Personnel de l'association",'de':'Vereinsmitarbeiter'},
    'DESCRIPTION OF ACTIVITY':       {'uk':'ОПИС ДІЯЛЬНОСТІ',           'fr':"DESCRIPTION DE L'ACTIVITÉ", 'de':'TÄTIGKEITSBESCHREIBUNG'},
    'CONTACT DETAILS':               {'uk':'КОНТАКТНІ ДАНІ',            'fr':'COORDONNÉES',               'de':'KONTAKTDATEN'},
    'FULL NAME':                     {'uk':"ПОВНЕ ІМ'Я",                'fr':'NOM COMPLET',               'de':'VOLLSTÄNDIGER NAME'},
    'PHONE / WHATSAPP':              {'uk':'ТЕЛЕФОН / WHATSAPP',        'fr':'TÉLÉPHONE / WHATSAPP',      'de':'TELEFON / WHATSAPP'},
    'TELEGRAM':                      {'uk':'TELEGRAM',                  'fr':'TELEGRAM',                  'de':'TELEGRAM'},
    'ADDRESS / LOCATION':            {'uk':'АДРЕСА / МІСЦЕЗНАХОДЖЕННЯ', 'fr':'ADRESSE / LOCALISATION',    'de':'ADRESSE / STANDORT'},
    'City, street, or region where you operate':{
        'uk':'Місто, вулиця або регіон роботи',
        'fr':'Ville, rue ou région où vous opérez',
        'de':'Stadt, Straße oder Region, in der Sie tätig sind',
    },
    'Submit Request':                {'uk':'Надіслати заявку',          'fr':'Envoyer la demande',        'de':'Antrag senden'},
    'Submitting...':                 {'uk':'Надсилається...',           'fr':'Envoi en cours...',         'de':'Wird gesendet...'},
    'Request submitted!':            {'uk':'Заявку надіслано!',         'fr':'Demande envoyée !',         'de':'Antrag gesendet!'},
    'We will review your application and contact you via email or Telegram.':{
        'uk':"Ми розглянемо вашу заявку та зв'яжемося з вами електронною поштою або в Telegram.",
        'fr':'Nous examinerons votre demande et vous contacterons par e-mail ou Telegram.',
        'de':'Wir prüfen Ihren Antrag und kontaktieren Sie per E-Mail oder Telegram.',
    },
    'Network error. Please try again.':{
        'uk':'Помилка мережі. Спробуйте ще раз.',
        'fr':'Erreur réseau. Veuillez réessayer.',
        'de':'Netzwerkfehler. Bitte erneut versuchen.',
    },

    # ──────────────────────────────────────────────────────────────────────────
    # BLOCK 6-7 (audit v4): динамическая ACR форма + president + first/last name
    # ──────────────────────────────────────────────────────────────────────────
    'President of Association': {'uk':'Президент асоціації',     'fr':'Président de l\'association', 'de':'Präsident des Vereins'},
    'President of the Association — only for board members. Submit your contact details, admin will verify.': {
        'uk':'Президент асоціації — лише для членів правління. Надішліть контактні дані, адміністратор перевірить.',
        'fr':"Président de l'association — réservé aux membres du conseil. Soumettez vos coordonnées, l'admin vérifiera.",
        'de':'Präsident des Vereins — nur für Vorstandsmitglieder. Senden Sie Ihre Kontaktdaten, der Admin prüft.',
    },
    'External Partner — for businesses (gym, clinic, shop, insurance agency, etc.). You will need to provide business category and address.': {
        'uk':'Зовнішній партнер — для бізнесу (спортзал, клініка, магазин, страхове агентство тощо). Потрібно вказати категорію бізнесу та адресу.',
        'fr':"Partenaire externe — pour les entreprises (salle de sport, clinique, magasin, agence d'assurance, etc.). Vous devrez fournir la catégorie d'activité et l'adresse.",
        'de':'Externer Partner — für Unternehmen (Fitnessstudio, Klinik, Geschäft, Versicherungsagentur usw.). Sie müssen die Geschäftskategorie und die Adresse angeben.',
    },
    'Association Staff — for individuals helping IESA (programmer, lawyer, designer, coordinator, etc.). No business or address needed.': {
        'uk':'Співробітник асоціації — для приватних осіб, які допомагають IESA (програміст, юрист, дизайнер, координатор тощо). Бізнес чи адреса не потрібні.',
        'fr':"Personnel de l'association — pour les particuliers aidant IESA (programmeur, avocat, designer, coordinateur, etc.). Aucune entreprise ni adresse requise.",
        'de':'Vereinsmitarbeiter — für Privatpersonen, die IESA unterstützen (Programmierer, Anwalt, Designer, Koordinator usw.). Kein Unternehmen oder Adresse erforderlich.',
    },
    'FIRST NAME':       {'uk':"ІМ'Я",          'fr':'PRÉNOM',           'de':'VORNAME'},
    'LAST NAME':        {'uk':'ПРІЗВИЩЕ',      'fr':'NOM',              'de':'NACHNAME'},
    'e.g. John':        {'uk':'напр. Іван',    'fr':'p.ex. Jean',       'de':'z.B. Johann'},
    'e.g. Doe':         {'uk':'напр. Петренко','fr':'p.ex. Dupont',     'de':'z.B. Mustermann'},
    'e.g. John Doe':    {'uk':'напр. Іван Петренко','fr':'p.ex. Jean Dupont','de':'z.B. Johann Mustermann'},
    'you@example.com':  {'uk':'ви@example.com','fr':'vous@exemple.com', 'de':'sie@beispiel.com'},
    'First Name':       {'uk':"Ім'я",          'fr':'Prénom',           'de':'Vorname'},
    'Last Name':        {'uk':'Прізвище',      'fr':'Nom',              'de':'Nachname'},
    'Please choose your business category.': {
        'uk':'Будь ласка, виберіть категорію вашого бізнесу.',
        'fr':"Veuillez choisir la catégorie de votre activité.",
        'de':'Bitte wählen Sie Ihre Geschäftskategorie.',
    },
    'Please specify your address or location.': {
        'uk':'Будь ласка, вкажіть вашу адресу або місцезнаходження.',
        'fr':'Veuillez préciser votre adresse ou votre emplacement.',
        'de':'Bitte geben Sie Ihre Adresse oder Ihren Standort an.',
    },

    # ──────────────────────────────────────────────────────────────────────────
    # BLOCK 8 (audit v4): PIN display
    # ──────────────────────────────────────────────────────────────────────────
    'Your current PIN':  {'uk':'Ваш поточний PIN',    'fr':'Votre PIN actuel',    'de':'Ihr aktueller PIN'},
    'Refreshes in':      {'uk':'Оновлення через',     'fr':'Renouvellement dans', 'de':'Erneuert in'},
    'sec':               {'uk':'сек',                 'fr':'sec',                 'de':'Sek.'},
    'Copy':              {'uk':'Копіювати',           'fr':'Copier',              'de':'Kopieren'},
    'Copy PIN to clipboard':{'uk':'Скопіювати PIN',   'fr':'Copier le PIN',       'de':'PIN kopieren'},

    # audit v5: новые UI строки
    'Quick actions':           {'uk':'Швидкі дії',          'fr':'Actions rapides',     'de':'Schnellaktionen'},
    'QUICK ACTIONS':           {'uk':'ШВИДКІ ДІЇ',          'fr':'ACTIONS RAPIDES',     'de':'SCHNELLAKTIONEN'},
    'YOUR MEMBERSHIP':         {'uk':'ВАШЕ ЧЛЕНСТВО',       'fr':'VOTRE ADHÉSION',      'de':'IHRE MITGLIEDSCHAFT'},
    'PARTNER ACTIONS':         {'uk':'ДІЇ ПАРТНЕРА',        'fr':'ACTIONS PARTENAIRE',  'de':'PARTNER-AKTIONEN'},
    'Log Visit':               {'uk':'Записати візит',      'fr':'Enregistrer visite',  'de':'Besuch eintragen'},
    # Поиск с фильтрами
    'Role':                    {'uk':'Роль',                'fr':'Rôle',                'de':'Rolle'},
    'Partners':                {'uk':'Партнери',            'fr':'Partenaires',         'de':'Partner'},
    'Staff':                   {'uk':'Персонал',            'fr':'Personnel',           'de':'Personal'},
    'Members':                 {'uk':'Учасники',            'fr':'Membres',             'de':'Mitglieder'},
    'Verified':                {'uk':'Підтверджені',        'fr':'Vérifiés',            'de':'Verifizierte'},
    'President':               {'uk':'Президент',           'fr':'Président',           'de':'Präsident'},
    'Relevance':               {'uk':'За релевантністю',    'fr':'Pertinence',          'de':'Relevanz'},
    'Newest first':            {'uk':'Спочатку нові',       'fr':"Plus récents d'abord",'de':'Neueste zuerst'},
    'Oldest first':            {'uk':'Спочатку старі',      'fr':"Plus anciens d'abord",'de':'Älteste zuerst'},
    'Showing all users with role': {'uk':'Усі користувачі з роллю','fr':"Tous les utilisateurs avec le rôle",'de':'Alle Benutzer mit der Rolle'},
    # Rate limiting
    'Too many requests. Please wait an hour before submitting another application.': {
        'uk':'Забагато запитів. Зачекайте годину перед подачею нової заявки.',
        'fr':"Trop de demandes. Veuillez attendre une heure avant d'en soumettre une autre.",
        'de':'Zu viele Anfragen. Bitte warten Sie eine Stunde, bevor Sie einen weiteren Antrag stellen.',
    },
    # ACR Audit Trail
    'Rejection Reason':        {'uk':'Причина відхилення',  'fr':'Motif de refus',      'de':'Ablehnungsgrund'},
    'Reviewed At':             {'uk':'Розглянуто',          'fr':'Examiné le',          'de':'Geprüft am'},
    'Reviewed By':             {'uk':'Розглянув',           'fr':'Examiné par',         'de':'Geprüft von'},
    'Approved':                {'uk':'Схвалено',            'fr':'Approuvé',            'de':'Genehmigt'},
    'Cancelled by user':       {'uk':'Скасовано користувачем','fr':"Annulé par l'utilisateur",'de':'Vom Benutzer storniert'},
    'President of Association':{'uk':'Президент асоціації', 'fr':"Président de l'association",'de':'Vereinspräsident'},
}


def sync_lang(lang: str) -> tuple[int, int]:
    """Возвращает (добавлено, переведено)."""
    po_path = BASE / 'locale' / lang / 'LC_MESSAGES' / 'django.po'
    if not po_path.exists():
        print(f'  {lang}: .po не существует, пропуск')
        return 0, 0
    po = polib.pofile(str(po_path))
    existing = {e.msgid for e in po}
    template_msgids = all_template_msgids()
    new_msgids = template_msgids - existing
    added = 0
    translated = 0
    for msgid in sorted(new_msgids):
        translation = KNOWN.get(msgid, {}).get(lang, '')
        entry = polib.POEntry(msgid=msgid, msgstr=translation)
        po.append(entry)
        added += 1
        if translation:
            translated += 1
    # Также добавляем переводы для существующих пустых msgid если они в KNOWN
    for entry in po:
        if entry.msgid in KNOWN and not entry.msgstr.strip():
            t = KNOWN[entry.msgid].get(lang, '')
            if t:
                entry.msgstr = t
                translated += 1
    po.save(str(po_path))
    # Компилируем .mo через polib
    mo_path = po_path.with_suffix('.mo')
    po.save_as_mofile(str(mo_path))
    print(f'  {lang}: добавлено {added} msgid, переведено {translated}, .mo обновлён')
    return added, translated


def main():
    print(f'Шаблонов сканировано из {len(TEMPLATES_ROOTS)} корней')
    template_msgids = all_template_msgids()
    print(f'Всего уникальных msgid в шаблонах: {len(template_msgids)}')
    print()
    print('Известных переводов в KNOWN_TRANSLATIONS:', len(KNOWN))
    print()
    total_added = 0
    total_translated = 0
    for lang in ('uk', 'fr', 'de'):
        a, t = sync_lang(lang)
        total_added += a
        total_translated += t
    print()
    print(f'Итого: добавлено {total_added} новых записей, переведено {total_translated}')


if __name__ == '__main__':
    main()
