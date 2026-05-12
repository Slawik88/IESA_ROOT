"""
Скрипт добавления переводов для системы AccountChangeRequest во все .po файлы.
Запускается вручную (без gettext) через polib.
"""
import os
import polib

BASE = os.path.dirname(os.path.abspath(__file__))

# Новые строки: msgid -> {lang: msgstr}
NEW_STRINGS = {
    # --- Модель ---
    "Desired Account Type": {
        "uk": "Бажаний тип акаунта",
        "fr": "Type de compte souhaité",
        "de": "Gewünschter Kontotyp",
    },
    "External Partner": {
        "uk": "Зовнішній партнер",
        "fr": "Partenaire externe",
        "de": "Externer Partner",
    },
    "Association Staff (IESA)": {
        "uk": "Персонал асоціації (IESA)",
        "fr": "Personnel de l'association (IESA)",
        "de": "Vereinspersonal (IESA)",
    },
    "Pending Review": {
        "uk": "Очікує розгляду",
        "fr": "En attente de révision",
        "de": "Zur Prüfung ausstehend",
    },
    "Reviewed": {
        "uk": "Розглянуто",
        "fr": "Examiné",
        "de": "Überprüft",
    },
    "Rejected": {
        "uk": "Відхилено",
        "fr": "Rejeté",
        "de": "Abgelehnt",
    },
    "Reason / Description of Activity": {
        "uk": "Причина / Опис діяльності",
        "fr": "Raison / Description de l'activité",
        "de": "Grund / Tätigkeitsbeschreibung",
    },
    "Describe why you want to change your account type and what you do.": {
        "uk": "Опишіть, чому ви хочете змінити тип акаунта та чим займаєтесь.",
        "fr": "Décrivez pourquoi vous voulez changer de type de compte et ce que vous faites.",
        "de": "Beschreiben Sie, warum Sie Ihren Kontotyp ändern möchten und was Sie tun.",
    },
    "Admin Note": {
        "uk": "Нотатка адміністратора",
        "fr": "Note administrateur",
        "de": "Admin-Notiz",
    },
    "Internal note for the administrator (not shown to user).": {
        "uk": "Внутрішня нотатка для адміністратора (не відображається користувачеві).",
        "fr": "Note interne pour l'administrateur (non visible par l'utilisateur).",
        "de": "Interne Notiz für den Administrator (dem Benutzer nicht angezeigt).",
    },
    "Account Change Request": {
        "uk": "Заявка на зміну типу акаунта",
        "fr": "Demande de changement de compte",
        "de": "Kontotyp-Änderungsanfrage",
    },
    "Account Change Requests": {
        "uk": "Заявки на зміну типу акаунта",
        "fr": "Demandes de changement de compte",
        "de": "Kontotyp-Änderungsanfragen",
    },
    "Created At": {
        "uk": "Дата створення",
        "fr": "Créé le",
        "de": "Erstellt am",
    },
    "Status": {
        "uk": "Статус",
        "fr": "Statut",
        "de": "Status",
    },
    "User": {
        "uk": "Користувач",
        "fr": "Utilisateur",
        "de": "Benutzer",
    },
    # --- Форма ---
    "Why do you want to change your account type?": {
        "uk": "Чому ви хочете змінити тип акаунта?",
        "fr": "Pourquoi souhaitez-vous changer de type de compte ?",
        "de": "Warum möchten Sie Ihren Kontotyp ändern?",
    },
    "Describe your activity, role and goals. Minimum 50 characters.": {
        "uk": "Опишіть свою діяльність, роль та цілі. Мінімум 50 символів.",
        "fr": "Décrivez votre activité, votre rôle et vos objectifs. Minimum 50 caractères.",
        "de": "Beschreiben Sie Ihre Tätigkeit, Rolle und Ziele. Mindestens 50 Zeichen.",
    },
    "Please describe your activity in at least 50 characters.": {
        "uk": "Будь ласка, опишіть свою діяльність щонайменше у 50 символах.",
        "fr": "Veuillez décrire votre activité en au moins 50 caractères.",
        "de": "Bitte beschreiben Sie Ihre Tätigkeit mit mindestens 50 Zeichen.",
    },
    # --- Шаблон ---
    "STATUS UPGRADE": {
        "uk": "ПІДВИЩЕННЯ СТАТУСУ",
        "fr": "MISE À NIVEAU DU STATUT",
        "de": "STATUS-UPGRADE",
    },
    "Apply for a role upgrade": {
        "uk": "Подати заявку на підвищення ролі",
        "fr": "Demander une mise à niveau du rôle",
        "de": "Rollenaufwertung beantragen",
    },
    "Want to become an IESA partner or association staff member? Submit a request — we'll review it and contact you.": {
        "uk": "Хочете стати партнером або співробітником IESA? Надішліть заявку — ми розглянемо її та зв'яжемось з вами.",
        "fr": "Vous souhaitez devenir partenaire ou membre du personnel de l'IESA ? Soumettez une demande — nous l'examinerons et vous contacterons.",
        "de": "Möchten Sie IESA-Partner oder Vereinsmitarbeiter werden? Reichen Sie eine Anfrage ein — wir prüfen diese und melden uns bei Ihnen.",
    },
    "DESIRED ROLE": {
        "uk": "БАЖАНА РОЛЬ",
        "fr": "RÔLE SOUHAITÉ",
        "de": "GEWÜNSCHTE ROLLE",
    },
    "choose": {
        "uk": "оберіть",
        "fr": "choisir",
        "de": "wählen",
    },
    "gym, shop, service": {
        "uk": "зал, магазин, послуги",
        "fr": "salle, boutique, service",
        "de": "Fitnessstudio, Laden, Dienstleistung",
    },
    "lawyer, accountant, manager": {
        "uk": "юрист, бухгалтер, менеджер",
        "fr": "avocat, comptable, manager",
        "de": "Anwalt, Buchhalter, Manager",
    },
    "REASON / DESCRIPTION": {
        "uk": "ПРИЧИНА / ОПИС",
        "fr": "RAISON / DESCRIPTION",
        "de": "GRUND / BESCHREIBUNG",
    },
    "Describe your activity, role and why you want to join as a partner or staff...": {
        "uk": "Опишіть свою діяльність, роль та причину, чому ви хочете приєднатись як партнер або співробітник...",
        "fr": "Décrivez votre activité, votre rôle et pourquoi vous souhaitez rejoindre en tant que partenaire ou personnel...",
        "de": "Beschreiben Sie Ihre Tätigkeit, Ihre Rolle und warum Sie als Partner oder Mitarbeiter beitreten möchten...",
    },
    "chars": {
        "uk": "символів",
        "fr": "caractères",
        "de": "Zeichen",
    },
    "min. 50": {
        "uk": "мін. 50",
        "fr": "min. 50",
        "de": "min. 50",
    },
    "Submit Request": {
        "uk": "Надіслати заявку",
        "fr": "Soumettre la demande",
        "de": "Anfrage senden",
    },
    "Submitting...": {
        "uk": "Надсилаємо...",
        "fr": "Envoi en cours...",
        "de": "Wird gesendet...",
    },
    "Network error. Please try again.": {
        "uk": "Помилка мережі. Будь ласка, спробуйте ще раз.",
        "fr": "Erreur réseau. Veuillez réessayer.",
        "de": "Netzwerkfehler. Bitte versuchen Sie es erneut.",
    },
    "Your request is under review": {
        "uk": "Ваша заявка на розгляді",
        "fr": "Votre demande est en cours d'examen",
        "de": "Ihre Anfrage wird geprüft",
    },
    "Submitted": {
        "uk": "Надіслано",
        "fr": "Soumis",
        "de": "Eingereicht",
    },
    "Request submitted!": {
        "uk": "Заявку надіслано!",
        "fr": "Demande soumise !",
        "de": "Anfrage eingereicht!",
    },
    "We will review your application and contact you via email or Telegram.": {
        "uk": "Ми розглянемо вашу заявку та зв'яжемось з вами через email або Telegram.",
        "fr": "Nous examinerons votre candidature et vous contacterons par e-mail ou Telegram.",
        "de": "Wir werden Ihre Bewerbung prüfen und Sie per E-Mail oder Telegram kontaktieren.",
    },
    "Your request has been submitted! We will contact you soon.": {
        "uk": "Вашу заявку надіслано! Ми зв'яжемось з вами найближчим часом.",
        "fr": "Votre demande a été soumise ! Nous vous contacterons bientôt.",
        "de": "Ihre Anfrage wurde eingereicht! Wir werden Sie bald kontaktieren.",
    },
    "You already have a pending request. Please wait for it to be reviewed.": {
        "uk": "У вас вже є заявка на розгляді. Будь ласка, зачекайте.",
        "fr": "Vous avez déjà une demande en attente. Veuillez patienter.",
        "de": "Sie haben bereits eine ausstehende Anfrage. Bitte warten Sie.",
    },
}


def add_translations():
    for lang, translations in [(l, NEW_STRINGS) for l in ['uk', 'fr', 'de']]:
        po_path = os.path.join(BASE, f'locale/{lang}/LC_MESSAGES/django.po')
        if not os.path.exists(po_path):
            print(f'SKIP {lang}: файл не найден')
            continue

        po = polib.pofile(po_path, encoding='utf-8')
        existing_msgids = {e.msgid for e in po}
        added = 0

        for msgid, lang_map in NEW_STRINGS.items():
            if msgid in existing_msgids:
                # Обновляем если msgstr пустой
                for entry in po:
                    if entry.msgid == msgid and not entry.msgstr:
                        entry.msgstr = lang_map.get(lang, '')
                        added += 1
                continue

            msgstr = lang_map.get(lang, '')
            entry = polib.POEntry(msgid=msgid, msgstr=msgstr)
            po.append(entry)
            added += 1

        po.save()

        # Компилируем .mo файл
        mo_path = po_path.replace('.po', '.mo')
        po.save_as_mofile(mo_path)
        print(f'{lang}: добавлено/обновлено {added} строк → скомпилировано {mo_path}')

    print('\nГотово!')


if __name__ == '__main__':
    add_translations()
