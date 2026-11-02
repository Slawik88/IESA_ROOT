'use strict';

window.DomovoyI18n = (() => {
  const messages = {
  "Сменить дом": [
    "Змінити дім",
    "Changer de foyer",
    "Haushalt wechseln"
  ],
  "Сегодня": [
    "Сьогодні",
    "Aujourd’hui",
    "Heute"
  ],
  "Указать дату": [
    "Указати дату",
    "Choisir une date",
    "Datum wählen"
  ],
  " · за {0}": [
    " · за {0}",
    " · pour {0}",
    " · für {0}"
  ],
  "{0}{1} · изменить дату": [
    "{0}{1} · змінити дату",
    "{0}{1} · modifier la date",
    "{0}{1} · Datum ändern"
  ],
  "Сохранить изменения": [
    "Зберегти зміни",
    "Enregistrer les modifications",
    "Änderungen speichern"
  ],
  "Внести деньги": [
    "Внести гроші",
    "Ajouter une contribution",
    "Geld einzahlen"
  ],
  "Записать расход": [
    "Записати витрату",
    "Ajouter une dépense",
    "Ausgabe erfassen"
  ],
  "Не удалось выполнить действие. Попробуйте ещё раз.": [
    "Не вдалося виконати дію. Спробуйте ще раз.",
    "Action impossible. Réessayez.",
    "Aktion fehlgeschlagen. Bitte erneut versuchen."
  ],
  "Вход недоступен. Откройте приложение заново из личного чата.": [
    "Вхід недоступний. Відкрийте застосунок знову з особистого чату.",
    "Accès indisponible. Rouvrez l’application depuis la conversation privée.",
    "Zugriff nicht verfügbar. Öffne die App erneut über den privaten Chat."
  ],
  "Сервис временно недоступен. Введённые поля сохранены — попробуйте ещё раз чуть позже.": [
    "Сервіс тимчасово недоступний. Уведені поля збережено — спробуйте пізніше.",
    "Service temporairement indisponible. Votre saisie est conservée ; réessayez plus tard.",
    "Der Dienst ist vorübergehend nicht verfügbar. Deine Eingaben bleiben erhalten. Versuche es später erneut."
  ],
  "Файл слишком большой. Выберите файл до 2 МБ.": [
    "Файл завеликий. Виберіть файл до 2 МБ.",
    "Fichier trop volumineux. Limite : 2 Mo.",
    "Datei zu gross. Wähle eine Datei bis 2 MB."
  ],
  "Нет соединения. Введённые данные сохранены в форме.": [
    "Немає з’єднання. Уведені дані залишилися у формі.",
    "Pas de connexion. Votre saisie reste dans le formulaire.",
    "Keine Verbindung. Deine Eingaben bleiben im Formular."
  ],
  "К отметке": [
    "До відмітки",
    "À confirmer",
    "Noch offen"
  ],
  "Свободны": [
    "Вільні",
    "Rien à faire",
    "Alles erledigt"
  ],
  "Незакрытых дней нет.": [
    "Невідмічених днів немає.",
    "Aucun jour à valider.",
    "Keine offenen Reinigungstage."
  ],
  "Сегодня ваша очередь": [
    "Сьогодні ваша черга",
    "C’est votre tour aujourd’hui",
    "Heute bist du dran"
  ],
  "За {0}": [
    "За {0}",
    "Pour le {0}",
    "Für den {0}"
  ],
  "Когда закончите — отметьте здесь": [
    "Коли завершите — відмітьте тут",
    "Validez ici une fois terminé",
    "Nach dem Putzen hier bestätigen"
  ],
  "Ещё не отмечено": [
    "Ще не відмічено",
    "Pas encore validé",
    "Noch nicht bestätigt"
  ],
  "Готово": [
    "Готово",
    "Terminé",
    "Erledigt"
  ],
  "Уборка отмечена": [
    "Прибирання відмічено",
    "Ménage validé",
    "Reinigung bestätigt"
  ],
  "Свернуть": [
    "Згорнути",
    "Réduire",
    "Einklappen"
  ],
  "Ещё дней: {0}": [
    "Ще днів: {0}",
    "Autres jours : {0}",
    "Weitere Tage: {0}"
  ],
  "Принять": [
    "Прийняти",
    "Accepter",
    "Annehmen"
  ],
  "Отклонить": [
    "Відхилити",
    "Refuser",
    "Ablehnen"
  ],
  "Записей: {0}{1}": [
    "Записів: {0}{1}",
    "Écritures : {0}{1}",
    "Einträge: {0}{1}"
  ],
  " · за всё время": [
    " · за весь час",
    " · toutes les périodes",
    " · gesamter Zeitraum"
  ],
  "Фильтры{0}": [
    "Фільтри{0}",
    "Filtres{0}",
    "Filter{0}"
  ],
  "Траты": [
    "Витрати",
    "Dépenses",
    "Ausgaben"
  ],
  "Зачтённые взносы": [
    "Зараховані внески",
    "Contributions validées",
    "Bestätigte Einzahlungen"
  ],
  "Ждут подтверждения": [
    "Очікують підтвердження",
    "En attente de validation",
    "Warten auf Bestätigung"
  ],
  "Ждут возврата": [
    "Очікують повернення",
    "À rembourser",
    "Noch zu erstatten"
  ],
  "Нет совпадений": [
    "Збігів немає",
    "Aucun résultat",
    "Keine Treffer"
  ],
  "Измените фильтры или выберите другой месяц.": [
    "Змініть фільтри або виберіть інший місяць.",
    "Modifiez les filtres ou choisissez un autre mois.",
    "Ändere die Filter oder wähle einen anderen Monat."
  ],
  "Искать за всё время": [
    "Шукати за весь час",
    "Rechercher sur toutes les périodes",
    "Im gesamten Zeitraum suchen"
  ],
  "Пока нет записей": [
    "Записів ще немає",
    "Aucune écriture pour le moment",
    "Noch keine Einträge"
  ],
  "Запишите расход или внесите деньги в общий котёл.": [
    "Запишіть витрату або внесіть гроші до спільної каси.",
    "Ajoutez une dépense ou une contribution à la caisse commune.",
    "Erfasse eine Ausgabe oder zahle Geld in die gemeinsame Kasse ein."
  ],
  "В выбранных записях нет расходов.": [
    "У вибраних записах немає витрат.",
    "Aucune dépense dans cette sélection.",
    "Diese Auswahl enthält keine Ausgaben."
  ],
  "{0}: {1} из {2}": [
    "{0}: {1} із {2}",
    "{0} : {1} sur {2}",
    "{0}: {1} von {2}"
  ],
  "Внёс": [
    "Внесено",
    "Contributions",
    "Eingezahlt"
  ],
  "Записал расходов": [
    "Записано витрат",
    "Dépenses enregistrées",
    "Erfasste Ausgaben"
  ],
  "Ждёт возврата": [
    "Очікує повернення",
    "À rembourser",
    "Noch zu erstatten"
  ],
  "Нет записей по выбранным условиям.": [
    "Немає записів за вибраними умовами.",
    "Aucune écriture avec ces critères.",
    "Keine Einträge mit diesen Kriterien."
  ],
  "Вся история дома. Фильтры не применяются.": [
    "Уся історія дому. Фільтри не застосовуються.",
    "Tout l’historique du foyer, sans filtres.",
    "Gesamter Verlauf des Haushalts, ohne Filter."
  ],
  "{0} · все записи месяца без фильтров.": [
    "{0} · усі записи місяця без фільтрів.",
    "{0} · toutes les écritures du mois, sans filtres.",
    "{0} · alle Einträge des Monats, ohne Filter."
  ],
  "{0} · записей с текущими фильтрами: {1}": [
    "{0} · записів із поточними фільтрами: {1}",
    "{0} · écritures avec les filtres actuels : {1}",
    "{0} · Einträge mit aktuellen Filtern: {1}"
  ],
  "Всё время": [
    "Увесь час",
    "Toutes les périodes",
    "Gesamter Zeitraum"
  ],
  "ждёт подтверждения": [
    "очікує підтвердження",
    "en attente de validation",
    "wartet auf Bestätigung"
  ],
  "отклонён": [
    "відхилено",
    "refusée",
    "abgelehnt"
  ],
  "зачтён": [
    "зараховано",
    "validée",
    "bestätigt"
  ],
  "Взнос": [
    "Внесок",
    "Contribution",
    "Einzahlung"
  ],
  "Расход": [
    "Витрата",
    "Dépense",
    "Ausgabe"
  ],
  "за свои · возвращено": [
    "за власні · повернено",
    "avance personnelle · remboursée",
    "privat bezahlt · erstattet"
  ],
  "за свои · ждёт возврата": [
    "за власні · очікує повернення",
    "avance personnelle · à rembourser",
    "privat bezahlt · noch zu erstatten"
  ],
  "из котла": [
    "зі спільної каси",
    "caisse commune",
    "aus der gemeinsamen Kasse"
  ],
  "за свои · ": [
    "за власні · ",
    "avance personnelle · ",
    "privat bezahlt · "
  ],
  "Жилец": [
    "Мешканець",
    "Membre",
    "Mitglied"
  ],
  "Повторить": [
    "Повторити",
    "Répéter",
    "Wiederholen"
  ],
  "Изменить": [
    "Змінити",
    "Modifier",
    "Bearbeiten"
  ],
  "Чеки": [
    "Чеки",
    "Justificatifs",
    "Belege"
  ],
  "Вернуть из котла": [
    "Повернути зі спільної каси",
    "Rembourser depuis la caisse",
    "Aus der Kasse erstatten"
  ],
  "Отметить возврат {0} для {1}? Сумма спишется из котла.": [
    "Відмітити повернення {0} для {1}? Суму буде списано зі спільної каси.",
    "Confirmer le remboursement de {0} à {1} ? Ce montant sera déduit de la caisse.",
    "Erstattung von {0} an {1} bestätigen? Der Betrag wird von der Kasse abgezogen."
  ],
  "Возврат отмечен": [
    "Повернення відмічено",
    "Remboursement confirmé",
    "Erstattung bestätigt"
  ],
  "Удалить": [
    "Видалити",
    "Supprimer",
    "Löschen"
  ],
  "Удалить расход {0} за {1}? Остаток пересчитается. Вернуть запись кнопкой отмены будет нельзя.": [
    "Видалити витрату {0} за {1}? Залишок буде перераховано. Скасувати видалення кнопкою не вийде.",
    "Supprimer la dépense de {0} du {1} ? Le solde sera recalculé. Cette suppression ne peut pas être annulée.",
    "Ausgabe von {0} vom {1} löschen? Der Saldo wird neu berechnet. Dies lässt sich nicht rückgängig machen."
  ],
  "Расход удалён": [
    "Витрату видалено",
    "Dépense supprimée",
    "Ausgabe gelöscht"
  ],
  "Вы не закончили запись": [
    "Ви не завершили запис",
    "Une saisie est en cours",
    "Ein Eintrag ist noch offen"
  ],
  "Продолжить правку": [
    "Продовжити редагування",
    "Reprendre la modification",
    "Bearbeitung fortsetzen"
  ],
  "Продолжить расход": [
    "Продовжити витрату",
    "Reprendre la dépense",
    "Ausgabe fortsetzen"
  ],
  "Продолжить взнос": [
    "Продовжити внесок",
    "Reprendre la contribution",
    "Einzahlung fortsetzen"
  ],
  "Внесено {0} · потрачено и возвращено {1}": [
    "Внесено {0} · витрачено й повернено {1}",
    "Contributions : {0} · dépenses et remboursements : {1}",
    "Eingezahlt: {0} · ausgegeben und erstattet: {1}"
  ],
  "Все жильцы": [
    "Усі мешканці",
    "Tous les membres",
    "Alle Mitglieder"
  ],
  "Все категории": [
    "Усі категорії",
    "Toutes les catégories",
    "Alle Kategorien"
  ],
  "Повторить недавнее: ": [
    "Повторити недавнє: ",
    "Répéter une saisie récente : ",
    "Kürzlichen Eintrag wiederholen: "
  ],
  "Трата": [
    "Витрата",
    "Dépense",
    "Ausgabe"
  ],
  "Изменить расход": [
    "Змінити витрату",
    "Modifier la dépense",
    "Ausgabe bearbeiten"
  ],
  "Правка сохранит историю изменений. Если запись уже изменили, она не будет перезаписана.": [
    "Історія змін збережеться. Чужі нові зміни не буде перезаписано.",
    "L’historique des modifications sera conservé. Les modifications plus récentes ne seront pas écrasées.",
    "Der Änderungsverlauf bleibt erhalten. Neuere Änderungen werden nicht überschrieben."
  ],
  "Взнос будет зачтён по правилам дома.": [
    "Внесок буде зараховано за правилами дому.",
    "La contribution sera validée selon les règles du foyer.",
    "Die Einzahlung wird nach den Regeln des Haushalts bestätigt."
  ],
  "«За свои» ждёт возврата, «Из котла» уменьшает общий остаток.": [
    "«За власні» очікує повернення, «Зі спільної каси» зменшує спільний залишок.",
    "Une avance personnelle reste à rembourser ; une dépense de la caisse réduit le solde commun.",
    "Privat bezahlte Ausgaben warten auf Erstattung. Ausgaben aus der Kasse verringern den gemeinsamen Saldo."
  ],
  "Без категории": [
    "Без категорії",
    "Sans catégorie",
    "Ohne Kategorie"
  ],
  "Сохраняю…": [
    "Зберігаю…",
    "Enregistrement…",
    "Wird gespeichert…"
  ],
  "Изменения сохранены": [
    "Зміни збережено",
    "Modifications enregistrées",
    "Änderungen gespeichert"
  ],
  "Взнос ждёт подтверждения": [
    "Внесок очікує підтвердження",
    "Contribution en attente de validation",
    "Einzahlung wartet auf Bestätigung"
  ],
  "Запись сохранена": [
    "Запис збережено",
    "Écriture enregistrée",
    "Eintrag gespeichert"
  ],
  "Запись сохранена. Список пока не обновился — нажмите «Обновить».": [
    "Запис збережено. Список ще не оновився — натисніть «Оновити».",
    "Écriture enregistrée. La liste n’est pas encore à jour ; appuyez sur « Actualiser ».",
    "Eintrag gespeichert. Die Liste ist noch nicht aktuell. Tippe auf «Aktualisieren»."
  ],
  "Расход сохранён, но чеки не открылись.": [
    "Витрату збережено, але чеки не відкрилися.",
    "Dépense enregistrée, mais les justificatifs ne se sont pas ouverts.",
    "Ausgabe gespeichert, aber die Belege konnten nicht geöffnet werden."
  ],
  "Нет соединения. Поля сохранены; можно повторить отправку.": [
    "Немає з’єднання. Поля збережено; можна повторити надсилання.",
    "Pas de connexion. Les champs sont conservés ; vous pouvez réessayer.",
    "Keine Verbindung. Die Felder bleiben erhalten. Du kannst erneut senden."
  ],
  "Выберите месяц от 0001 до 9999 года": [
    "Виберіть місяць від 0001 до 9999 року",
    "Choisissez un mois entre les années 0001 et 9999",
    "Wähle einen Monat zwischen den Jahren 0001 und 9999"
  ],
  "Открываю выбранный дом…": [
    "Відкриваю вибраний дім…",
    "Ouverture du foyer…",
    "Haushalt wird geöffnet…"
  ],
  "Создайте пространство для своего дома или присоединитесь к соседям.": [
    "Створіть простір для свого дому або приєднайтеся до сусідів.",
    "Créez votre foyer ou rejoignez vos colocataires.",
    "Erstelle einen Haushalt oder tritt deinen Mitbewohnern bei."
  ],
  "Файл подготовлен": [
    "Файл підготовлено",
    "Fichier prêt",
    "Datei ist bereit"
  ],
  "Максимальный размер — 2 МБ": [
    "Максимальний розмір — 2 МБ",
    "Taille maximale : 2 Mo",
    "Maximale Grösse: 2 MB"
  ],
  "Выберите Excel, CSV, TSV или JSON": [
    "Виберіть Excel, CSV, TSV або JSON",
    "Choisissez Excel, CSV, TSV ou JSON",
    "Wähle Excel, CSV, TSV oder JSON"
  ],
  "Новых: {0} · дублей: {1} · ошибок: {2}. Изменение котла: {3}": [
    "Нових: {0} · дублів: {1} · помилок: {2}. Зміна каси: {3}",
    "Nouvelles : {0} · doublons : {1} · erreurs : {2}. Variation de la caisse : {3}",
    "Neu: {0} · Duplikate: {1} · Fehler: {2}. Änderung der Kasse: {3}"
  ],
  "Добавлено: {0}, дублей: {1}": [
    "Додано: {0}, дублів: {1}",
    "Ajoutées : {0}, doublons : {1}",
    "Hinzugefügt: {0}, Duplikate: {1}"
  ],
  "Люди и приглашения": [
    "Люди та запрошення",
    "Membres et invitations",
    "Mitglieder und Einladungen"
  ],
  "График уборки": [
    "Графік прибирання",
    "Planning du ménage",
    "Putzplan"
  ],
  "Деньги и категории": [
    "Гроші та категорії",
    "Argent et catégories",
    "Geld und Kategorien"
  ],
  "Мои уведомления": [
    "Мої сповіщення",
    "Mes notifications",
    "Meine Benachrichtigungen"
  ],
  "Настройки дома": [
    "Налаштування дому",
    "Réglages du foyer",
    "Haushaltseinstellungen"
  ],
  "Ещё один дом": [
    "Ще один дім",
    "Un autre foyer",
    "Ein weiterer Haushalt"
  ],
  "Понедельник": [
    "Понеділок",
    "Lundi",
    "Montag"
  ],
  "Вторник": [
    "Вівторок",
    "Mardi",
    "Dienstag"
  ],
  "Среда": [
    "Середа",
    "Mercredi",
    "Mittwoch"
  ],
  "Четверг": [
    "Четвер",
    "Jeudi",
    "Donnerstag"
  ],
  "Пятница": [
    "П’ятниця",
    "Vendredi",
    "Freitag"
  ],
  "Суббота": [
    "Субота",
    "Samedi",
    "Samstag"
  ],
  "Воскресенье": [
    "Неділя",
    "Dimanche",
    "Sonntag"
  ],
  "Нет соединения. Попробуйте ещё раз.": [
    "Немає з’єднання. Спробуйте ще раз.",
    "Pas de connexion. Réessayez.",
    "Keine Verbindung. Bitte erneut versuchen."
  ],
  "Нет соединения. Введённые поля сохранены.": [
    "Немає з’єднання. Уведені поля збережено.",
    "Pas de connexion. Votre saisie est conservée.",
    "Keine Verbindung. Deine Eingaben bleiben erhalten."
  ],
  "Ваш дом": [
    "Ваш дім",
    "Votre foyer",
    "Dein Haushalt"
  ],
  "Открываем…": [
    "Відкриваємо…",
    "Ouverture…",
    "Wird geöffnet…"
  ],
  "Попробовать ещё раз": [
    "Спробувати ще раз",
    "Réessayer",
    "Erneut versuchen"
  ],
  "Добавить дом": [
    "Додати дім",
    "Ajouter un foyer",
    "Haushalt hinzufügen"
  ],
  "Создайте дом или войдите по приглашению. Данные разных домов не смешиваются.": [
    "Створіть дім або приєднайтеся за запрошенням. Дані різних домів не змішуються.",
    "Créez un foyer ou rejoignez-en un sur invitation. Les données de chaque foyer restent séparées.",
    "Erstelle einen Haushalt oder tritt per Einladung bei. Die Daten der Haushalte bleiben getrennt."
  ],
  "Ваше имя в доме": [
    "Ваше ім’я в домі",
    "Votre nom dans le foyer",
    "Dein Name im Haushalt"
  ],
  "Код или ссылка приглашения": [
    "Код або посилання запрошення",
    "Code ou lien d’invitation",
    "Einladungscode oder Einladungslink"
  ],
  "Название дома": [
    "Назва дому",
    "Nom du foyer",
    "Name des Haushalts"
  ],
  "Вставьте приглашение": [
    "Вставте запрошення",
    "Collez l’invitation",
    "Einladung einfügen"
  ],
  "Например, Дом на Садовой": [
    "Наприклад, Дім біля парку",
    "Par exemple, Chez nous",
    "Zum Beispiel, WG am Park"
  ],
  "Присоединиться": [
    "Приєднатися",
    "Rejoindre",
    "Beitreten"
  ],
  "Создать дом": [
    "Створити дім",
    "Créer un foyer",
    "Haushalt erstellen"
  ],
  "Вы вступили в дом": [
    "Ви приєдналися до дому",
    "Vous avez rejoint le foyer",
    "Du bist dem Haushalt beigetreten"
  ],
  "Вы уже живёте в этом доме": [
    "Ви вже живете в цьому домі",
    "Vous faites déjà partie de ce foyer",
    "Du bist bereits Mitglied dieses Haushalts"
  ],
  "Дом создан": [
    "Дім створено",
    "Foyer créé",
    "Haushalt erstellt"
  ],
  "Открыли ваш существующий дом": [
    "Відкрито ваш наявний дім",
    "Votre foyer existant a été ouvert",
    "Dein bestehender Haushalt wurde geöffnet"
  ],
  "Новый дом": [
    "Новий дім",
    "Nouveau foyer",
    "Neuer Haushalt"
  ],
  "Приглашение": [
    "Запрошення",
    "Invitation",
    "Einladung"
  ],
  "Пригласить соседей": [
    "Запросити сусідів",
    "Inviter des colocataires",
    "Mitbewohner einladen"
  ],
  "Отправьте код человеку, с которым живёте. Он сможет вступить в этот дом на сайте.": [
    "Надішліть код людині, з якою живете. Вона зможе приєднатися до цього дому на сайті.",
    "Envoyez ce code à la personne avec qui vous vivez. Elle pourra rejoindre ce foyer sur le site.",
    "Sende den Code an deine Mitbewohner. Sie können damit auf der Website diesem Haushalt beitreten."
  ],
  "Показать приглашение": [
    "Показати запрошення",
    "Afficher l’invitation",
    "Einladung anzeigen"
  ],
  "Код приглашения": [
    "Код запрошення",
    "Code d’invitation",
    "Einladungscode"
  ],
  "Скопировать код": [
    "Скопіювати код",
    "Copier le code",
    "Code kopieren"
  ],
  "Код скопирован": [
    "Код скопійовано",
    "Code copié",
    "Code kopiert"
  ],
  "Выделили код — скопируйте его": [
    "Код виділено — скопіюйте його",
    "Code sélectionné : copiez-le",
    "Code markiert – bitte kopieren"
  ],
  "Обновить код": [
    "Оновити код",
    "Renouveler le code",
    "Code erneuern"
  ],
  "Создать новый код? Старые приглашения перестанут работать. Жильцы останутся в доме.": [
    "Створити новий код? Старі запрошення перестануть працювати. Мешканці залишаться в домі.",
    "Créer un nouveau code ? Les anciennes invitations ne fonctionneront plus. Les membres resteront dans le foyer.",
    "Neuen Code erstellen? Alte Einladungen funktionieren danach nicht mehr. Die Mitglieder bleiben im Haushalt."
  ],
  "Приглашение в дом": [
    "Запрошення до дому",
    "Invitation au foyer",
    "Einladung zum Haushalt"
  ],
  "Делитесь только с будущими жильцами.": [
    "Діліться лише з майбутніми мешканцями.",
    "À partager uniquement avec les futurs membres.",
    "Nur mit zukünftigen Mitgliedern teilen."
  ],
  "Жильцы": [
    "Мешканці",
    "Membres",
    "Mitglieder"
  ],
  "Владелец дома": [
    "Власник дому",
    "Créateur du foyer",
    "Haushaltsadmin"
  ],
  "Это вы": [
    "Це ви",
    "C’est vous",
    "Das bist du"
  ],
  "Доступ и права": [
    "Доступ і права",
    "Accès et permissions",
    "Zugriff und Rechte"
  ],
  "{0} «{1}» для {2}?": [
    "{0} «{1}» для {2}?",
    "{0} « {1} » pour {2} ?",
    "«{1}» für {2} {0}?"
  ],
  "Разрешить": [
    "Дозволити",
    "Autoriser",
    "erlauben"
  ],
  "Запретить": [
    "Заборонити",
    "Interdire",
    "entziehen"
  ],
  "Права обновлены": [
    "Права оновлено",
    "Permissions mises à jour",
    "Rechte aktualisiert"
  ],
  "Дни недели": [
    "Дні тижня",
    "Jours de la semaine",
    "Wochentage"
  ],
  "Каждому жильцу можно выбрать день. Изменения касаются будущих открытых дней; прошлые отметки останутся в истории.": [
    "Кожному мешканцю можна вибрати день. Зміни стосуються майбутніх відкритих днів; минулі відмітки залишаться в історії.",
    "Attribuez un jour à chaque membre. Les changements concernent les jours futurs non validés ; les validations passées restent dans l’historique.",
    "Wähle für jedes Mitglied einen Tag. Änderungen betreffen zukünftige offene Tage. Frühere Bestätigungen bleiben im Verlauf."
  ],
  "Без дня": [
    "Без дня",
    "Aucun jour",
    "Kein Tag"
  ],
  "Сохранить график": [
    "Зберегти графік",
    "Enregistrer le planning",
    "Putzplan speichern"
  ],
  "График обновлён": [
    "Графік оновлено",
    "Planning mis à jour",
    "Putzplan aktualisiert"
  ],
  "Дни и отметки": [
    "Дні та відмітки",
    "Jours et validations",
    "Tage und Bestätigungen"
  ],
  "Показан {0}.": [
    "Показано {0}.",
    "Période : {0}.",
    "Zeitraum: {0}."
  ],
  "Месяц истории": [
    "Місяць історії",
    "Mois de l’historique",
    "Monat im Verlauf"
  ],
  "Дней за этот месяц пока нет.": [
    "За цей місяць днів ще немає.",
    "Aucun jour pour ce mois.",
    "Für diesen Monat gibt es noch keine Tage."
  ],
  "Впереди": [
    "Попереду",
    "À venir",
    "Bevorstehend"
  ],
  "Ждёт отметки": [
    "Очікує відмітки",
    "À valider",
    "Noch offen"
  ],
  "Убрано": [
    "Прибрано",
    "Fait",
    "Geputzt"
  ],
  "Пропущено": [
    "Пропущено",
    "Passé",
    "Ausgelassen"
  ],
  "Отметить уборку": [
    "Відмітити прибирання",
    "Valider le ménage",
    "Reinigung bestätigen"
  ],
  "Пропустить": [
    "Пропустити",
    "Passer",
    "Auslassen"
  ],
  "Отметить день {0} для {1} как пропущенный?": [
    "Відмітити день {0} для {1} як пропущений?",
    "Marquer le {0} de {1} comme passé ?",
    "Den {0} für {1} als ausgelassen markieren?"
  ],
  "Включено": [
    "Увімкнено",
    "Activé",
    "Aktiviert"
  ],
  "Выключено": [
    "Вимкнено",
    "Désactivé",
    "Deaktiviert"
  ],
  "Личный чат": [
    "Особистий чат",
    "Conversation privée",
    "Privater Chat"
  ],
  "Общий чат дома": [
    "Спільний чат дому",
    "Groupe du foyer",
    "Haushaltschat"
  ],
  "Не присылать": [
    "Не надсилати",
    "Ne pas envoyer",
    "Nicht senden"
  ],
  "Сохранить": [
    "Зберегти",
    "Enregistrer",
    "Speichern"
  ],
  "Изменить обозначение валюты у всех записей дома? Суммы останутся прежними — пересчёта по курсу не будет.": [
    "Змінити позначення валюти в усіх записах дому? Суми залишаться без змін — перерахунку за курсом не буде.",
    "Changer la devise affichée pour toutes les écritures ? Les montants resteront identiques ; aucune conversion ne sera effectuée.",
    "Währungsbezeichnung für alle Einträge ändern? Die Beträge bleiben gleich. Es findet keine Umrechnung statt."
  ],
  "Сохранено": [
    "Збережено",
    "Enregistré",
    "Gespeichert"
  ],
  "Категории расходов": [
    "Категорії витрат",
    "Catégories de dépenses",
    "Ausgabenkategorien"
  ],
  "Названия помогают находить покупки в истории. Категория с расходами не удаляется.": [
    "Назви допомагають знаходити покупки в історії. Категорію з витратами не можна видалити.",
    "Les catégories facilitent la recherche. Une catégorie utilisée par des dépenses ne peut pas être supprimée.",
    "Kategorien helfen beim Suchen. Kategorien mit Ausgaben können nicht gelöscht werden."
  ],
  "Убрать": [
    "Прибрати",
    "Retirer",
    "Entfernen"
  ],
  "Убрать категорию «{0}»?": [
    "Прибрати категорію «{0}»?",
    "Retirer la catégorie « {0} » ?",
    "Kategorie «{0}» entfernen?"
  ],
  "Новая категория": [
    "Нова категорія",
    "Nouvelle catégorie",
    "Neue Kategorie"
  ],
  "Например, Для кухни": [
    "Наприклад, Для кухні",
    "Par exemple, Cuisine",
    "Zum Beispiel, Küche"
  ],
  "Добавить категорию": [
    "Додати категорію",
    "Ajouter une catégorie",
    "Kategorie hinzufügen"
  ],
  "Категория добавлена": [
    "Категорію додано",
    "Catégorie ajoutée",
    "Kategorie hinzugefügt"
  ],
  "Это только ваши настройки. Уведомления приходят в личный чат или общий чат дома, если он подключён.": [
    "Це лише ваші налаштування. Сповіщення надходять в особистий чат або спільний чат дому, якщо він підключений.",
    "Ces réglages sont personnels. Les notifications vont dans votre conversation privée ou dans le groupe du foyer s’il est connecté.",
    "Das sind deine persönlichen Einstellungen. Benachrichtigungen kommen in deinen privaten Chat oder in den verbundenen Haushaltschat."
  ],
  "Общий чат пока не подключён. Чтобы получать сообщения сейчас, выбирайте «Личный чат».": [
    "Спільний чат ще не підключено. Щоб отримувати повідомлення зараз, виберіть «Особистий чат».",
    "Le groupe n’est pas encore connecté. Choisissez « Conversation privée » pour recevoir les messages dès maintenant.",
    "Der Haushaltschat ist noch nicht verbunden. Wähle «Privater Chat», um jetzt Nachrichten zu erhalten."
  ],
  "Как называется ваш дом": [
    "Як називається ваш дім",
    "Comment s’appelle votre foyer ?",
    "Wie heisst dein Haushalt?"
  ],
  "Сохранить название": [
    "Зберегти назву",
    "Enregistrer le nom",
    "Namen speichern"
  ],
  "Название обновлено": [
    "Назву оновлено",
    "Nom mis à jour",
    "Name aktualisiert"
  ],
  "Как к вам обращаться": [
    "Як до вас звертатися",
    "Comment vous appeler ?",
    "Wie sollen wir dich nennen?"
  ],
  "Ваше имя в этом доме": [
    "Ваше ім’я в цьому домі",
    "Votre nom dans ce foyer",
    "Dein Name in diesem Haushalt"
  ],
  "Сохранить имя": [
    "Зберегти ім’я",
    "Enregistrer mon nom",
    "Meinen Namen speichern"
  ],
  "Имя обновлено": [
    "Ім’я оновлено",
    "Nom mis à jour",
    "Name aktualisiert"
  ],
  "Правила дома меняет владелец или участник с соответствующим доступом.": [
    "Правила дому змінює власник або учасник із відповідним доступом.",
    "Seul le créateur ou un membre autorisé peut modifier les règles.",
    "Die Haushaltsregeln können nur vom Admin oder berechtigten Mitgliedern geändert werden."
  ],
  "Выйти из дома": [
    "Вийти з дому",
    "Quitter le foyer",
    "Haushalt verlassen"
  ],
  "Доступ к данным этого дома закроется. Старые записи сохранятся у жильцов.": [
    "Доступ до даних цього дому закриється. Старі записи залишаться у мешканців.",
    "Vous perdrez l’accès aux données de ce foyer. Les anciennes écritures resteront pour les autres membres.",
    "Du verlierst den Zugriff auf diesen Haushalt. Frühere Einträge bleiben für die anderen Mitglieder erhalten."
  ],
  "Выйти из «{0}»? Вы потеряете доступ к этому дому.": [
    "Вийти з «{0}»? Ви втратите доступ до цього дому.",
    "Quitter « {0} » ? Vous perdrez l’accès à ce foyer.",
    "«{0}» verlassen? Du verlierst den Zugriff auf diesen Haushalt."
  ],
  "Дом": [
    "Дім",
    "Foyer",
    "Haushalt"
  ],
  "Жильцов: {0}": [
    "Мешканців: {0}",
    "Membres : {0}",
    "Mitglieder: {0}"
  ],
  "Валюта дома · {0}": [
    "Валюта дому · {0}",
    "Devise du foyer · {0}",
    "Haushaltswährung · {0}"
  ],
  "Открываем чеки…": [
    "Відкриваємо чеки…",
    "Ouverture des justificatifs…",
    "Belege werden geöffnet…"
  ],
  "Хранилище чеков временно недоступно. Сам расход сохранён.": [
    "Сховище чеків тимчасово недоступне. Витрату збережено.",
    "Les justificatifs sont temporairement indisponibles. La dépense est enregistrée.",
    "Belege sind vorübergehend nicht verfügbar. Die Ausgabe ist gespeichert."
  ],
  "Чеков пока нет. Можно добавить фото.": [
    "Чеків ще немає. Можна додати фото.",
    "Aucun justificatif. Vous pouvez ajouter une photo.",
    "Noch keine Belege. Du kannst ein Foto hinzufügen."
  ],
  "Открываем чек {0}…": [
    "Відкриваємо чек {0}…",
    "Ouverture du justificatif {0}…",
    "Beleg {0} wird geöffnet…"
  ],
  "Чек {0}": [
    "Чек {0}",
    "Justificatif {0}",
    "Beleg {0}"
  ],
  "Увеличить чек {0}": [
    "Збільшити чек {0}",
    "Agrandir le justificatif {0}",
    "Beleg {0} vergrössern"
  ],
  "{0} чек {1}": [
    "{0} чек {1}",
    "{0} le justificatif {1}",
    "Beleg {1}: {0}"
  ],
  "Уменьшить": [
    "Зменшити",
    "Réduire",
    "Verkleinern"
  ],
  "Увеличить": [
    "Збільшити",
    "Agrandir",
    "Vergrössern"
  ],
  "Открыть ещё раз": [
    "Відкрити ще раз",
    "Ouvrir à nouveau",
    "Erneut öffnen"
  ],
  "Чек не открылся": [
    "Чек не відкрився",
    "Le justificatif ne s’est pas ouvert",
    "Beleg konnte nicht geöffnet werden"
  ],
  "Фото JPEG или PNG · до {0} МБ": [
    "Фото JPEG або PNG · до {0} МБ",
    "Photo JPEG ou PNG · jusqu’à {0} Mo",
    "JPEG- oder PNG-Foto · bis {0} MB"
  ],
  "{0}. Фото доступны только участникам дома.": [
    "{0}. Фото доступні лише учасникам дому.",
    "{0}. Les photos sont réservées aux membres du foyer.",
    "{0}. Fotos sind nur für Haushaltsmitglieder sichtbar."
  ],
  "Повторить загрузку чека": [
    "Повторити завантаження чека",
    "Réessayer l’envoi du justificatif",
    "Beleg erneut hochladen"
  ],
  "Прикрепить чек": [
    "Прикріпити чек",
    "Joindre le justificatif",
    "Beleg anhängen"
  ],
  "Убрать выбранное фото": [
    "Прибрати вибране фото",
    "Retirer la photo sélectionnée",
    "Ausgewähltes Foto entfernen"
  ],
  "Выберите фото не больше 2 МБ": [
    "Виберіть фото до 2 МБ",
    "Choisissez une photo de 2 Mo maximum",
    "Wähle ein Foto bis 2 MB"
  ],
  "Подойдёт фото JPEG или PNG": [
    "Підійде фото JPEG або PNG",
    "Choisissez une photo JPEG ou PNG",
    "Wähle ein JPEG- oder PNG-Foto"
  ],
  "Чек прикреплён": [
    "Чек прикріплено",
    "Justificatif joint",
    "Beleg angehängt"
  ],
  "Связь прервалась. Расход сохранён. Можно повторить только загрузку этого чека.": [
    "З’єднання перервано. Витрату збережено. Можна повторити лише завантаження цього чека.",
    "Connexion interrompue. La dépense est enregistrée. Réessayez seulement l’envoi du justificatif.",
    "Verbindung unterbrochen. Die Ausgabe ist gespeichert. Du kannst nur den Beleg erneut hochladen."
  ],
  "Чеки пока не открылись": [
    "Чеки ще не відкрилися",
    "Les justificatifs ne se sont pas ouverts",
    "Belege konnten nicht geöffnet werden"
  ],
  "Закрытое приложение": [
    "Закритий застосунок",
    "Application privée",
    "Private Anwendung"
  ],
  "К содержимому": [
    "До вмісту",
    "Aller au contenu",
    "Zum Inhalt"
  ],
  "Вход в приложение": [
    "Вхід до застосунку",
    "Accéder à l’application",
    "App öffnen"
  ],
  "Откройте эту страницу из личного чата, где вы получили ссылку.": [
    "Відкрийте цю сторінку з особистого чату, де отримали посилання.",
    "Ouvrez cette page depuis la conversation privée où vous avez reçu le lien.",
    "Öffne diese Seite über den privaten Chat, in dem du den Link erhalten hast."
  ],
  "Нет сети. Ваш ввод останется в форме. Попробуйте сохранить, когда связь вернётся.": [
    "Немає мережі. Уведені дані залишаться у формі. Збережіть їх, коли з’єднання відновиться.",
    "Hors connexion. Votre saisie reste dans le formulaire. Enregistrez-la une fois la connexion rétablie.",
    "Offline. Deine Eingaben bleiben im Formular. Speichere sie, sobald die Verbindung wieder da ist."
  ],
  "Деньги дома": [
    "Гроші дому",
    "Finances du foyer",
    "Haushaltsfinanzen"
  ],
  "Общий котёл": [
    "Спільна каса",
    "Caisse commune",
    "Gemeinsame Kasse"
  ],
  "Как рассчитан остаток": [
    "Як розраховано залишок",
    "Comment le solde est calculé",
    "So wird der Saldo berechnet"
  ],
  "Движение денег за всё время": [
    "Рух грошей за весь час",
    "Mouvements depuis le début",
    "Geldbewegungen im gesamten Zeitraum"
  ],
  "Внесено за всё время": [
    "Внесено за весь час",
    "Total des contributions",
    "Insgesamt eingezahlt"
  ],
  "Траты и возвраты": [
    "Витрати та повернення",
    "Dépenses et remboursements",
    "Ausgaben und Erstattungen"
  ],
  "Действия с деньгами": [
    "Дії з грошима",
    "Actions financières",
    "Geld verwalten"
  ],
  "История": [
    "Історія",
    "Historique",
    "Verlauf"
  ],
  "Моя уборка": [
    "Моє прибирання",
    "Mon ménage",
    "Mein Putzdienst"
  ],
  "Проверить взносы": [
    "Перевірити внески",
    "Vérifier les contributions",
    "Einzahlungen prüfen"
  ],
  "Лента дома": [
    "Стрічка дому",
    "Activité du foyer",
    "Haushaltsaktivität"
  ],
  "Вся история": [
    "Уся історія",
    "Tout l’historique",
    "Gesamter Verlauf"
  ],
  "Файлы": [
    "Файли",
    "Fichiers",
    "Dateien"
  ],
  "Предыдущий месяц": [
    "Попередній місяць",
    "Mois précédent",
    "Vorheriger Monat"
  ],
  "Месяц учёта": [
    "Місяць обліку",
    "Mois comptable",
    "Buchungsmonat"
  ],
  "Следующий месяц": [
    "Наступний місяць",
    "Mois suivant",
    "Nächster Monat"
  ],
  "Фильтры": [
    "Фільтри",
    "Filtres",
    "Filter"
  ],
  "Поиск операций": [
    "Пошук операцій",
    "Rechercher des opérations",
    "Buchungen suchen"
  ],
  "Покупка, имя или дата": [
    "Покупка, ім’я або дата",
    "Achat, nom ou date",
    "Einkauf, Name oder Datum"
  ],
  "Сбросить": [
    "Скинути",
    "Réinitialiser",
    "Zurücksetzen"
  ],
  "Быстрые фильтры": [
    "Швидкі фільтри",
    "Filtres rapides",
    "Schnellfilter"
  ],
  "Мои записи": [
    "Мої записи",
    "Mes écritures",
    "Meine Einträge"
  ],
  "Ждут возврата · всё время": [
    "Очікують повернення · увесь час",
    "À rembourser · toutes périodes",
    "Zu erstatten · alle Zeiträume"
  ],
  "Итоги и разбор расходов": [
    "Підсумки та розбір витрат",
    "Totaux et répartition des dépenses",
    "Summen und Ausgabenübersicht"
  ],
  "Разбор выбранных записей": [
    "Розбір вибраних записів",
    "Analyse de la sélection",
    "Übersicht der ausgewählten Einträge"
  ],
  "На что потратили": [
    "На що витратили",
    "Où va l’argent",
    "Wofür wurde Geld ausgegeben?"
  ],
  "По всей выборке, включая покупки за свои. Возврат не считается второй покупкой.": [
    "За всією вибіркою, включно з покупками за власні. Повернення не рахується другою покупкою.",
    "Pour toute la sélection, avances personnelles comprises. Un remboursement ne compte pas comme un deuxième achat.",
    "Für die gesamte Auswahl, einschliesslich privater Auslagen. Eine Erstattung zählt nicht als zweiter Einkauf."
  ],
  "По жильцам": [
    "За мешканцями",
    "Par membre",
    "Nach Mitgliedern"
  ],
  "Записи": [
    "Записи",
    "Écritures",
    "Einträge"
  ],
  "Предыдущая страница": [
    "Попередня сторінка",
    "Page précédente",
    "Vorherige Seite"
  ],
  "Следующая страница": [
    "Наступна сторінка",
    "Page suivante",
    "Nächste Seite"
  ],
  "Скачать или загрузить записи": [
    "Завантажити або вивантажити записи",
    "Exporter ou importer des écritures",
    "Einträge exportieren oder importieren"
  ],
  "Дни, отметки и история": [
    "Дні, відмітки та історія",
    "Jours, validations et historique",
    "Tage, Bestätigungen und Verlauf"
  ],
  "Что и куда присылать": [
    "Що й куди надсилати",
    "Quoi envoyer et où",
    "Was wohin gesendet wird"
  ],
  "Правила, время и мой профиль": [
    "Правила, час і мій профіль",
    "Règles, horaires et mon profil",
    "Regeln, Zeiten und mein Profil"
  ],
  "Обновить данные": [
    "Оновити дані",
    "Actualiser les données",
    "Daten aktualisieren"
  ],
  "Другой дом": [
    "Інший дім",
    "Autre foyer",
    "Anderer Haushalt"
  ],
  "← К дому": [
    "← До дому",
    "← Au foyer",
    "← Zum Haushalt"
  ],
  "Основная навигация": [
    "Основна навігація",
    "Navigation principale",
    "Hauptnavigation"
  ],
  "Главная": [
    "Головна",
    "Accueil",
    "Start"
  ],
  "Записи и файлы": [
    "Записи та файли",
    "Écritures et fichiers",
    "Einträge und Dateien"
  ],
  "Закрыть файлы": [
    "Закрити файли",
    "Fermer les fichiers",
    "Dateien schliessen"
  ],
  "Скачайте историю или добавьте записи из файла.": [
    "Вивантажте історію або додайте записи з файлу.",
    "Exportez l’historique ou ajoutez des écritures depuis un fichier.",
    "Exportiere den Verlauf oder füge Einträge aus einer Datei hinzu."
  ],
  "Скачать записи": [
    "Вивантажити записи",
    "Exporter les écritures",
    "Einträge exportieren"
  ],
  "Какие записи": [
    "Які записи",
    "Quelles écritures",
    "Welche Einträge"
  ],
  "Из истории с текущими фильтрами": [
    "Із історії з поточними фільтрами",
    "Historique avec les filtres actuels",
    "Verlauf mit aktuellen Filtern"
  ],
  "За выбранный месяц": [
    "За вибраний місяць",
    "Pour le mois sélectionné",
    "Für den gewählten Monat"
  ],
  "За всё время": [
    "За весь час",
    "Toutes les périodes",
    "Gesamter Zeitraum"
  ],
  "Загрузить из файла": [
    "Завантажити з файлу",
    "Importer un fichier",
    "Datei importieren"
  ],
  "Файл Excel, CSV, TSV или JSON": [
    "Файл Excel, CSV, TSV або JSON",
    "Fichier Excel, CSV, TSV ou JSON",
    "Excel-, CSV-, TSV- oder JSON-Datei"
  ],
  "До 2 МБ и 1000 строк. Сначала проверим файл; добавим записи после вашего подтверждения.": [
    "До 2 МБ і 1000 рядків. Спочатку перевіримо файл; додамо записи після вашого підтвердження.",
    "Jusqu’à 2 Mo et 1000 lignes. Le fichier sera vérifié avant votre confirmation.",
    "Bis 2 MB und 1000 Zeilen. Wir prüfen die Datei vor deiner Bestätigung."
  ],
  "Шаблоны и заполнение": [
    "Шаблони та заповнення",
    "Modèles et instructions",
    "Vorlagen und Ausfüllhilfe"
  ],
  "Скачайте шаблон или используйте свой экспорт. Excel: один лист «Операции», значения без формул; ID и суммы в шаблоне — текст. Даты — YYYY-MM-DD, суммы — с точкой или запятой. Для каждой новой строки нужен свой source_key.": [
    "Скачайте шаблон або використайте свій експорт. Excel: один аркуш «Операции», значення без формул; ID та суми в шаблоні — текст. Дати — YYYY-MM-DD, суми — з крапкою або комою. Кожен новий рядок має мати власний source_key.",
    "Téléchargez le modèle ou utilisez votre export. Excel : une seule feuille « Операции », des valeurs sans formules ; les ID et montants du modèle sont du texte. Dates : YYYY-MM-DD ; montants avec un point ou une virgule. Chaque nouvelle ligne doit avoir son propre source_key.",
    "Lade die Vorlage herunter oder nutze deinen Export. Excel: ein Blatt «Операции», Werte ohne Formeln; IDs und Beträge sind in der Vorlage Text. Datum: YYYY-MM-DD; Beträge mit Punkt oder Komma. Jede neue Zeile braucht einen eigenen source_key."
  ],
  "Авторы записей · member_tg_id": [
    "Автори записів · member_tg_id",
    "Auteurs des écritures · member_tg_id",
    "Autoren der Einträge · member_tg_id"
  ],
  "kind: expense — расход, contribution — взнос. mode: house — из котла, personal — за свои. Валюта должна совпадать с валютой дома.": [
    "kind: expense — витрата, contribution — внесок. mode: house — зі спільної каси, personal — за власні. Валюта має збігатися з валютою дому.",
    "kind : expense = dépense, contribution = contribution. mode : house = caisse commune, personal = avance personnelle. La devise doit correspondre à celle du foyer.",
    "kind: expense = Ausgabe, contribution = Einzahlung. mode: house = gemeinsame Kasse, personal = privat bezahlt. Die Währung muss der Haushaltswährung entsprechen."
  ],
  "Добавить записи": [
    "Додати записи",
    "Ajouter les écritures",
    "Einträge hinzufügen"
  ],
  "Отмена": [
    "Скасувати",
    "Annuler",
    "Abbrechen"
  ],
  "Остаток в котле": [
    "Залишок у спільній касі",
    "Solde de la caisse commune",
    "Saldo der gemeinsamen Kasse"
  ],
  "Закрыть сведения о балансе": [
    "Закрити відомості про баланс",
    "Fermer les détails du solde",
    "Saldodetails schliessen"
  ],
  "Подтверждённые взносы за всё время за вычетом общих трат и возвратов. Личные покупки уменьшают котёл только после возврата.": [
    "Підтверджені внески за весь час мінус спільні витрати та повернення. Особисті покупки зменшують касу лише після повернення.",
    "Contributions validées depuis le début, moins les dépenses communes et les remboursements. Les avances personnelles réduisent la caisse seulement après remboursement.",
    "Alle bestätigten Einzahlungen abzüglich gemeinsamer Ausgaben und Erstattungen. Private Auslagen verringern die Kasse erst nach der Erstattung."
  ],
  "В каком вы доме?": [
    "У якому ви домі?",
    "Dans quel foyer êtes-vous ?",
    "Welcher Haushalt?"
  ],
  "Закрыть выбор дома": [
    "Закрити вибір дому",
    "Fermer le choix du foyer",
    "Haushaltsauswahl schliessen"
  ],
  "Ваши дома": [
    "Ваші доми",
    "Vos foyers",
    "Deine Haushalte"
  ],
  "Выбрать дом": [
    "Вибрати дім",
    "Choisir un foyer",
    "Haushalt wählen"
  ],
  "Создать дом или вступить": [
    "Створити дім або приєднатися",
    "Créer ou rejoindre un foyer",
    "Haushalt erstellen oder beitreten"
  ],
  "Найти нужное": [
    "Знайти потрібне",
    "Trouver une écriture",
    "Einträge finden"
  ],
  "Закрыть фильтры": [
    "Закрити фільтри",
    "Fermer les filtres",
    "Filter schliessen"
  ],
  "Текущий месяц": [
    "Поточний місяць",
    "Mois en cours",
    "Aktueller Monat"
  ],
  "Тип записи": [
    "Тип запису",
    "Type d’écriture",
    "Art des Eintrags"
  ],
  "Все записи": [
    "Усі записи",
    "Toutes les écritures",
    "Alle Einträge"
  ],
  "Расходы": [
    "Витрати",
    "Dépenses",
    "Ausgaben"
  ],
  "Взносы": [
    "Внески",
    "Contributions",
    "Einzahlungen"
  ],
  "Кто": [
    "Хто",
    "Qui",
    "Wer"
  ],
  "Категория": [
    "Категорія",
    "Catégorie",
    "Kategorie"
  ],
  "Откуда деньги": [
    "Звідки гроші",
    "Source de l’argent",
    "Woher kommt das Geld?"
  ],
  "Любой источник": [
    "Будь-яке джерело",
    "Toutes les sources",
    "Alle Quellen"
  ],
  "Из общего котла": [
    "Зі спільної каси",
    "Caisse commune",
    "Gemeinsame Kasse"
  ],
  "За свои": [
    "За власні",
    "Avance personnelle",
    "Privat bezahlt"
  ],
  "Порядок": [
    "Порядок",
    "Tri",
    "Sortierung"
  ],
  "Сначала новые": [
    "Спочатку нові",
    "Plus récentes d’abord",
    "Neueste zuerst"
  ],
  "Сначала старые": [
    "Спочатку старі",
    "Plus anciennes d’abord",
    "Älteste zuerst"
  ],
  "Сначала крупные": [
    "Спочатку великі",
    "Montants les plus élevés",
    "Grösste Beträge zuerst"
  ],
  "Сначала небольшие": [
    "Спочатку невеликі",
    "Montants les plus faibles",
    "Kleinste Beträge zuerst"
  ],
  "Показать записи": [
    "Показати записи",
    "Afficher les écritures",
    "Einträge anzeigen"
  ],
  "Закрыть форму": [
    "Закрити форму",
    "Fermer le formulaire",
    "Formular schliessen"
  ],
  "Сумма": [
    "Сума",
    "Montant",
    "Betrag"
  ],
  "Из котла": [
    "Із каси",
    "Caisse commune",
    "Aus der Kasse"
  ],
  "Дом будет должен вам эту сумму.": [
    "Дім буде винен вам цю суму.",
    "Le foyer vous devra ce montant.",
    "Der Haushalt schuldet dir diesen Betrag."
  ],
  "На что": [
    "На що",
    "Pour quoi",
    "Wofür"
  ],
  "необязательно": [
    "необов’язково",
    "facultatif",
    "optional"
  ],
  "Например, продукты к ужину": [
    "Наприклад, продукти до вечері",
    "Par exemple, courses du dîner",
    "Zum Beispiel, Einkauf fürs Abendessen"
  ],
  "После сохранения добавить чек": [
    "Після збереження додати чек",
    "Ajouter un justificatif après l’enregistrement",
    "Nach dem Speichern einen Beleg hinzufügen"
  ],
  "Сегодня · изменить дату": [
    "Сьогодні · змінити дату",
    "Aujourd’hui · modifier la date",
    "Heute · Datum ändern"
  ],
  "Когда была операция": [
    "Коли була операція",
    "Date de l’opération",
    "Datum der Buchung"
  ],
  "Вчера": [
    "Учора",
    "Hier",
    "Gestern"
  ],
  "За какой месяц взнос": [
    "За який місяць внесок",
    "Mois de la contribution",
    "Monat der Einzahlung"
  ],
  "Заполнить из недавнего": [
    "Заповнити з недавнього",
    "Reprendre une saisie récente",
    "Kürzlichen Eintrag übernehmen"
  ],
  "Недавние суммы": [
    "Недавні суми",
    "Montants récents",
    "Kürzliche Beträge"
  ],
  "Черновик хранится до перезагрузки приложения.": [
    "Чернетка зберігається до перезавантаження застосунку.",
    "Le brouillon est conservé jusqu’au rechargement de l’application.",
    "Der Entwurf bleibt bis zum Neuladen der App erhalten."
  ],
  "Удалить черновик": [
    "Видалити чернетку",
    "Supprimer le brouillon",
    "Entwurf löschen"
  ],
  "Сохранить и записать ещё": [
    "Зберегти й записати ще",
    "Enregistrer et ajouter une autre écriture",
    "Speichern und weiteren Eintrag erfassen"
  ],
  "Чеки к расходу": [
    "Чеки до витрати",
    "Justificatifs de la dépense",
    "Belege zur Ausgabe"
  ],
  "Закрыть чеки": [
    "Закрити чеки",
    "Fermer les justificatifs",
    "Belege schliessen"
  ],
  "Подтверждение взносов владельцем": [
    "Підтвердження внесків власником",
    "Validation des contributions par le créateur",
    "Einzahlungen durch den Admin bestätigen lassen"
  ],
  "Час утреннего напоминания": [
    "Година ранкового нагадування",
    "Heure du rappel du matin",
    "Uhrzeit der Morgenerinnerung"
  ],
  "Час вечернего напоминания": [
    "Година вечірнього нагадування",
    "Heure du rappel du soir",
    "Uhrzeit der Abenderinnerung"
  ],
  "Напоминать о пропущенном дне каждый вечер": [
    "Нагадувати про пропущений день щовечора",
    "Rappeler chaque soir les jours non validés",
    "Jeden Abend an offene Tage erinnern"
  ],
  "Ежемесячный отчёт по балансу": [
    "Щомісячний звіт про баланс",
    "Rapport financier mensuel",
    "Monatlicher Finanzbericht"
  ],
  "Валюта дома": [
    "Валюта дому",
    "Devise du foyer",
    "Haushaltswährung"
  ],
  "Часовой пояс дома (UTC+)": [
    "Часовий пояс дому (UTC+)",
    "Fuseau horaire du foyer (UTC+)",
    "Zeitzone des Haushalts (UTC+)"
  ],
  "Утром: «сегодня твой день уборки»": [
    "Уранці: «сьогодні ваш день прибирання»",
    "Le matin : c’est votre jour de ménage",
    "Morgens: Heute bist du mit Putzen dran"
  ],
  "Вечером: «день не закрыт»": [
    "Увечері: «день не відмічено»",
    "Le soir : journée non validée",
    "Abends: Tag noch offen"
  ],
  "Кто-то отметил/пропустил уборку": [
    "Хтось відмітив або пропустив прибирання",
    "Un membre a validé ou passé le ménage",
    "Jemand hat den Putzdienst bestätigt oder ausgelassen"
  ],
  "Кто-то добавил трату": [
    "Хтось додав витрату",
    "Un membre a ajouté une dépense",
    "Jemand hat eine Ausgabe hinzugefügt"
  ],
  "Жилец заявил взнос (для подтвердившего право)": [
    "Мешканець заявив внесок (для тих, хто має право підтвердження)",
    "Contribution déclarée (pour les membres autorisés à valider)",
    "Einzahlung gemeldet (für Bestätigungsberechtigte)"
  ],
  "Мой взнос подтверждён/отклонён": [
    "Мій внесок підтверджено або відхилено",
    "Ma contribution a été validée ou refusée",
    "Meine Einzahlung wurde bestätigt oder abgelehnt"
  ],
  "Ежемесячный отчёт": [
    "Щомісячний звіт",
    "Rapport mensuel",
    "Monatsbericht"
  ],
  "тг": [
    "тг",
    "тг",
    "тг"
  ],
  "CHF — швейцарский франк": [
    "CHF — швейцарський франк",
    "CHF — franc suisse",
    "CHF – Schweizer Franken"
  ],
  "личка": [
    "особистий чат",
    "privé",
    "privat"
  ],
  "чат": [
    "чат",
    "groupe",
    "Chat"
  ],
  "выкл": [
    "вимкнено",
    "désactivé",
    "aus"
  ],
  "Владелец — всё; остальные — только явно выданное.": [
    "Власник має всі права; решта — лише явно надані.",
    "Le créateur a tous les droits ; les autres, uniquement ceux accordés.",
    "Der Admin hat alle Rechte, andere nur ausdrücklich erteilte Rechte."
  ],
  "менять график и переносить дни": [
    "змінювати графік і переносити дні",
    "modifier le planning et déplacer des jours",
    "Putzplan ändern und Tage verschieben"
  ],
  "Чужие дни": [
    "Чужі дні",
    "Jours des autres",
    "Tage anderer Mitglieder"
  ],
  "закрывать дни уборки за других": [
    "закривати дні прибирання за інших",
    "valider le ménage des autres membres",
    "Putztage anderer Mitglieder bestätigen"
  ],
  "подтверждать взносы жильцов": [
    "підтверджувати внески мешканців",
    "valider les contributions des membres",
    "Einzahlungen von Mitgliedern bestätigen"
  ],
  "Чужие траты": [
    "Чужі витрати",
    "Dépenses des autres",
    "Ausgaben anderer Mitglieder"
  ],
  "править и удалять чужие траты": [
    "редагувати й видаляти чужі витрати",
    "modifier et supprimer les dépenses des autres",
    "Ausgaben anderer bearbeiten und löschen"
  ],
  "Категории": [
    "Категорії",
    "Catégories",
    "Kategorien"
  ],
  "добавлять и убирать категории трат": [
    "додавати й прибирати категорії витрат",
    "ajouter et retirer des catégories de dépenses",
    "Ausgabenkategorien hinzufügen und entfernen"
  ],
  "менять настройки дома": [
    "змінювати налаштування дому",
    "modifier les réglages du foyer",
    "Haushaltseinstellungen ändern"
  ],
  "Участники": [
    "Учасники",
    "Membres",
    "Mitglieder"
  ],
  "приглашать и назначать права другим": [
    "запрошувати й надавати права іншим",
    "inviter des membres et attribuer des droits",
    "Andere einladen und Rechte vergeben"
  ],
  "Импорт денег": [
    "Імпорт грошей",
    "Import financier",
    "Finanzimport"
  ],
  "загружать историю взносов и трат из файлов": [
    "завантажувати історію внесків і витрат із файлів",
    "importer l’historique des contributions et dépenses",
    "Einzahlungen und Ausgaben aus Dateien importieren"
  ],
  "Неизвестное право:": [
    "Невідоме право:",
    "Permission inconnue :",
    "Unbekanntes Recht:"
  ],
  "Язык": [
    "Мова",
    "Langue",
    "Sprache"
  ],
  "Смена языка перезагрузит страницу. Несохранённый ввод и черновики будут потеряны. Продолжить?": [
    "Зміна мови перезавантажить сторінку. Незбережені дані та чернетки буде втрачено. Продовжити?",
    "Changer de langue rechargera la page. La saisie non enregistrée et les brouillons seront perdus. Continuer ?",
    "Ein Sprachwechsel lädt die Seite neu. Nicht gespeicherte Eingaben und Entwürfe gehen verloren. Fortfahren?"
  ],
  "Строка {0}: {1}": [
    "Рядок {0}: {1}",
    "Ligne {0} : {1}",
    "Zeile {0}: {1}"
  ],
  "Фото также появится в вашем личном чате с ботом": [
    "Фото також з’явиться у вашому особистому чаті з ботом",
    "La photo apparaîtra aussi dans votre conversation privée avec le bot",
    "Das Foto erscheint auch in deinem privaten Chat mit dem Bot"
  ],
  "Это может делать только владелец дома или тот, кому он выдал право.": [
    "Це може робити лише власник дому або уповноважений учасник.",
    "Seul le créateur ou un membre autorisé peut effectuer cette action.",
    "Nur der Haushaltsadmin oder ein berechtigtes Mitglied darf das tun."
  ],
  "Неверное приглашение. Попросите у соседа актуальный код.": [
    "Неправильне запрошення. Попросіть у сусіда актуальний код.",
    "Invitation invalide. Demandez un code à jour à votre colocataire.",
    "Ungültige Einladung. Bitte deinen Mitbewohner um einen aktuellen Code."
  ],
  "Вы больше не участник этого дома. Выберите другой дом.": [
    "Ви більше не учасник цього дому. Виберіть інший.",
    "Vous ne faites plus partie de ce foyer. Choisissez-en un autre.",
    "Du bist nicht mehr Mitglied dieses Haushalts. Wähle einen anderen."
  ],
  "Имя не может быть пустым или слишком длинным": [
    "Ім’я не може бути порожнім або задовгим",
    "Le nom ne peut pas être vide ou trop long",
    "Der Name darf nicht leer oder zu lang sein"
  ],
  "Расход не найден": [
    "Витрату не знайдено",
    "Dépense introuvable",
    "Ausgabe nicht gefunden"
  ],
  "Выберите фото JPEG или PNG": [
    "Виберіть фото JPEG або PNG",
    "Choisissez une photo JPEG ou PNG",
    "Wähle ein JPEG- oder PNG-Foto"
  ],
  "Не удалось прочитать фото": [
    "Не вдалося прочитати фото",
    "Impossible de lire la photo",
    "Foto konnte nicht gelesen werden"
  ],
  "Фото должно быть не больше 2 МБ": [
    "Розмір фото має бути до 2 МБ",
    "La photo ne doit pas dépasser 2 Mo",
    "Das Foto darf höchstens 2 MB gross sein"
  ],
  "Чек не найден": [
    "Чек не знайдено",
    "Justificatif introuvable",
    "Beleg nicht gefunden"
  ],
  "Сумма должна быть числом, например: 1200 или 1200.50": [
    "Сума має бути числом, наприклад: 1200 або 1200.50",
    "Le montant doit être un nombre, par exemple 1200 ou 1200.50",
    "Der Betrag muss eine Zahl sein, zum Beispiel 1200 oder 1200.50"
  ],
  "После запятой — максимум два знака: 1200.50": [
    "Після коми — щонайбільше два знаки: 1200.50",
    "Deux décimales maximum : 1200.50",
    "Höchstens zwei Nachkommastellen: 1200.50"
  ],
  "Сумма должна быть больше нуля": [
    "Сума має бути більшою за нуль",
    "Le montant doit être supérieur à zéro",
    "Der Betrag muss grösser als null sein"
  ],
  "Слишком большая сумма": [
    "Завелика сума",
    "Montant trop élevé",
    "Betrag zu gross"
  ],
  "Лишние точки в сумме": [
    "Зайві крапки в сумі",
    "Trop de points dans le montant",
    "Zu viele Punkte im Betrag"
  ],
  "Дата не может быть в будущем": [
    "Дата не може бути в майбутньому",
    "La date ne peut pas être dans le futur",
    "Das Datum darf nicht in der Zukunft liegen"
  ],
  "Категория не найдена в этом доме": [
    "Категорію не знайдено в цьому домі",
    "Catégorie introuvable dans ce foyer",
    "Kategorie in diesem Haushalt nicht gefunden"
  ],
  "Эту запись уже изменили. Обновите историю и откройте её заново; ваш текст оставлен в форме.": [
    "Цей запис уже змінено. Оновіть історію й відкрийте його знову; ваш текст залишився у формі.",
    "Cette écriture a été modifiée. Actualisez l’historique et rouvrez-la ; votre saisie reste dans le formulaire.",
    "Dieser Eintrag wurde bereits geändert. Aktualisiere den Verlauf und öffne ihn erneut. Dein Text bleibt im Formular."
  ],
  "Запись изменилась во время сохранения. Обновите историю и проверьте её.": [
    "Запис змінився під час збереження. Оновіть історію та перевірте його.",
    "L’écriture a changé pendant l’enregistrement. Actualisez l’historique pour la vérifier.",
    "Der Eintrag wurde während des Speicherns geändert. Aktualisiere den Verlauf und prüfe ihn."
  ],
  "Расход уже возвращён из котла; его нельзя изменять": [
    "Витрату вже повернуто з каси; її не можна змінювати",
    "Cette dépense a déjà été remboursée ; elle ne peut plus être modifiée",
    "Die Ausgabe wurde bereits aus der Kasse erstattet und kann nicht geändert werden"
  ],
  "Эта трата уже возвращена. Проведённый возврат не редактируется.": [
    "Цю витрату вже повернуто. Проведене повернення не редагується.",
    "Cette dépense a déjà été remboursée. Un remboursement effectué ne peut pas être modifié.",
    "Diese Ausgabe wurde bereits erstattet. Eine erfolgte Erstattung kann nicht bearbeitet werden."
  ],
  "Не удалось прочитать Excel. Нужен неповреждённый XLSX без пароля.": [
    "Не вдалося прочитати Excel. Потрібен непошкоджений XLSX без пароля.",
    "Impossible de lire le fichier Excel. Utilisez un XLSX valide sans mot de passe.",
    "Excel-Datei konnte nicht gelesen werden. Verwende eine gültige XLSX-Datei ohne Passwort."
  ],
  "В Excel нет операций. Заполните строки под заголовками.": [
    "В Excel немає операцій. Заповніть рядки під заголовками.",
    "Aucune opération dans le fichier Excel. Remplissez les lignes sous les en-têtes.",
    "Die Excel-Datei enthält keine Buchungen. Fülle die Zeilen unter den Überschriften aus."
  ],
  "Валюта файла отличается от валюты дома; конвертация не выполняется": [
    "Валюта файлу відрізняється від валюти дому; перерахунок не виконується",
    "La devise du fichier diffère de celle du foyer ; aucune conversion n’est effectuée",
    "Die Dateiwährung unterscheidet sich von der Haushaltswährung. Es findet keine Umrechnung statt."
  ],
  "Не удалось прочитать файл. Нужен UTF-8 CSV/TSV или JSON Домового.": [
    "Не вдалося прочитати файл. Потрібен UTF-8 CSV/TSV або JSON Домового.",
    "Impossible de lire le fichier. Utilisez un CSV/TSV en UTF-8 ou un JSON de Домовой.",
    "Datei konnte nicht gelesen werden. Verwende CSV/TSV in UTF-8 oder eine JSON-Datei von Домовой."
  ],
  "Файл повреждён. Выберите его заново.": [
    "Файл пошкоджено. Виберіть його знову.",
    "Fichier endommagé. Sélectionnez-le à nouveau.",
    "Die Datei ist beschädigt. Wähle sie erneut aus."
  ],
  "Сменить язык": [
    "Змінити мову",
    "Changer de langue",
    "Sprache wechseln"
  ],
  "Дома": [
    "Доми",
    "Foyers",
    "Haushalte"
  ]
};
  const languages = { ru: 'ru-RU', uk: 'uk-UA', fr: 'fr-CH', de: 'de-CH' };
  const supported = value => Object.hasOwn(languages, value);
  let saved = '';
  try { saved = localStorage.getItem('domovoy.locale') || ''; } catch { /* Storage may be disabled. */ }
  const fragment = new URLSearchParams(location.hash.slice(1)).get('lang');
  const telegramLanguage = window.Telegram?.WebApp?.initDataUnsafe?.user?.language_code?.split('-')[0];
  const language = [fragment, saved, telegramLanguage, navigator.language?.split('-')[0], 'ru'].find(supported);
  const locale = languages[language], column = { uk: 0, fr: 1, de: 2 }[language];
  document.documentElement.lang = language;
  let dirtyCheck = () => false, pendingLanguage = null;
  const languageDialog = document.getElementById('language-dialog');
  function applyLanguage(next) {
    window.dispatchEvent(new Event('domovoy:languagechanging'));
    const parameters = new URLSearchParams(location.hash.slice(1));
    try {
      localStorage.setItem('domovoy.locale', next);
      if (parameters.has('lang')) { parameters.delete('lang'); location.hash = parameters.toString(); }
    } catch {
      parameters.set('lang', next);
      location.hash = parameters.toString();
    }
    location.reload();
  }
  document.getElementById('confirm-language').onclick = () => { if (supported(pendingLanguage)) applyLanguage(pendingLanguage); };
  document.getElementById('cancel-language').onclick = () => languageDialog.close();
  languageDialog.addEventListener('close', () => { pendingLanguage = null; });

  function t(source, values = []) {
    if (source === undefined || source === null) return '';
    const text = String(source);
    const translated = language === 'ru' ? text : messages[text]?.[column] ?? text;
    return translated.replace(/\{(\d+)\}/g, (match, index) => index < values.length ? String(values[index]) : match);
  }

  function error(source) {
    return String(source || '').split('\n').map(line => {
      const row = /^Строка (\d+): (.*)$/.exec(line);
      return row ? t('Строка {0}: {1}', [row[1], t(row[2])]) : t(line);
    }).join('\n');
  }

  // Only the authored HTML is visited, before app.js inserts any user content.
  const walker = document.createTreeWalker(document.documentElement, NodeFilter.SHOW_TEXT);
  const authored = [];
  while (walker.nextNode()) authored.push(walker.currentNode);
  for (const node of authored) {
    if (['SCRIPT', 'STYLE'].includes(node.parentElement?.tagName)) continue;
    const key = node.textContent.trim();
    if (Object.hasOwn(messages, key)) node.textContent = node.textContent.replace(key, t(key));
  }
  for (const node of document.querySelectorAll('[aria-label], [placeholder], [title]')) {
    for (const name of ['aria-label', 'placeholder', 'title']) {
      const value = node.getAttribute(name);
      if (value) node.setAttribute(name, t(value));
    }
  }
  document.addEventListener('input', event => {
    const form = event.target.closest('form');
    if (form) form.dataset.dirty = 'true';
  });
  for (const select of document.querySelectorAll('[data-language]')) {
    select.value = language;
    select.onchange = () => {
      const next = select.value;
      if (!supported(next) || next === language) return;
      if (dirtyCheck() || document.querySelector('form[data-dirty=true]')) {
        pendingLanguage = next;
        select.value = language;
        languageDialog.showModal();
        window.dispatchEvent(new Event('domovoy:modalchange'));
        return;
      }
      applyLanguage(next);
    };
  }
  return { t, error, language, locale, setDirtyCheck(check) { dirtyCheck = check; } };
})();
