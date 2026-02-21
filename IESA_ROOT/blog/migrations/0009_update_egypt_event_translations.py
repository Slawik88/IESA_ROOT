from datetime import datetime, timezone

from django.db import migrations


EVENT_TITLE_RU = "Неделя экстремального спорта и полной перезагрузки в Египте 🌊"
EVENT_TITLE_EN = "Week of Extreme Sports and Complete Reboot in Egypt 🌊"
EVENT_TITLE_DE = "Woche des Extremsports und der vollständigen Neustart in Ägypten 🌊"
EVENT_TITLE_FR = "Semaine de Sports Extrêmes et de Redémarrage Complet en Égypte 🌊"
EVENT_TITLE_UK = "Тиждень екстремального спорту та повної перезавантаження в Єгипті 🌊"

EVENT_LOCATION_RU = "Египет, Красное море"
EVENT_LOCATION_EN = "Egypt, Red Sea"
EVENT_LOCATION_DE = "Ägypten, Rotes Meer"
EVENT_LOCATION_FR = "Égypte, Mer Rouge"
EVENT_LOCATION_UK = "Єгипет, Червоне море"

EVENT_DESCRIPTION_RU = """Международная Ассоциация экстремального спорта приглашает вас на недельную выездную программу на Красном море.
Это формат активного времяпрепровождения, где смена среды, море и движение возвращают энергию и ясность.

Что вас ждет:

⛵ Проживание на яхте или в комфортном отеле минимум 4*, на берегу.
🤿 Ежедневные дайвинг-погружения с профессиональным сопровождением.
🌊 Водные виды спорта: яхтинг, виндсерф, кайтсерф.
⛵ Возможность обучения управлению парусным катамараном либо парусной яхтой.
🏛️ Возможность посещения нового Большого Египетского музея — 8-е чудо света.
📵 Снижение информационного мусора и ежедневной рутины.
🤝 Международная команда и среда единомышленников.

Условия участия:

💰 Стоимость: 1600 CHF при проживании на яхте с возможностью выбора дайвинга, кайтсёрфинга и релакса по вечерам, питание включено.
🏠 Проживание одна неделя в отеле с завтраком и/или обедом.
🍽️ Ужин до 20 EUR в хороших проверенных ресторанах за пределами отеля.

Программа подходит как для начинающих, так и для участников с опытом.
Количество мест не ограничено — ждём вас всех.

Напишите лично, чтобы получить подробную программу и забронировать участие.
Контакт: WhatsApp +41 79 943 35 79"""

EVENT_DESCRIPTION_EN = """The International Extreme Sports Association invites you to a week-long trip to the Red Sea.
This is a format of active pastime where a change of environment, sea and movement return energy and clarity.

What awaits you:

⛵ Accommodation on a yacht or in a comfortable 4* hotel minimum, on the shore.
🤿 Daily diving with professional supervision.
🌊 Water sports: yachting, windsurfing, kitesurfing.
⛵ Opportunity to learn sailing catamaran or sailing yacht management.
🏛️ Opportunity to visit the new Grand Egyptian Museum — the 8th wonder of the world.
📵 Reduction of information noise and daily routine.
🤝 International team and like-minded environment.

Participation conditions:

💰 Cost: 1600 CHF when staying on a yacht with the option to choose diving, kitesurfing and relaxation in the evenings, meals included.
🏠 Accommodation one week in a hotel with breakfast and/or lunch.
🍽️ Dinner up to 20 EUR in good proven restaurants outside the hotel.

The program is suitable for both beginners and experienced participants.
The number of places is unlimited — we are waiting for you all.

Write personally to get a detailed program and book your participation.
Contact: WhatsApp +41 79 943 35 79"""

EVENT_DESCRIPTION_DE = """Der Internationale Extremsportverband lädt Sie zu einem einwöchigen Ausflug ans Rote Meer ein.
Dies ist ein Format aktiver Freizeitgestaltung, bei dem ein Wechsel der Umgebung, Meer und Bewegung Energie und Klarheit zurückbringen.

Was Sie erwartet:

⛵ Unterkunft auf einer Yacht oder in einem komfortablen 4*-Hotel mindestens am Ufer.
🤿 Tägliches Tauchen mit professioneller Betreuung.
🌊 Wassersport: Segeln, Windsurfen, Kitesurfen.
⛵ Möglichkeit, das Segeln von Katamaranen oder Segelyachten zu erlernen.
🏛️ Möglichkeit, das neue Grand Egyptian Museum zu besuchen — das 8. Weltwunder.
📵 Reduzierung von Informationsrauschen und täglicher Routine.
🤝 Internationales Team und Gleichgesinnte.

Teilnahmebedingungen:

💰 Kosten: 1600 CHF bei Aufenthalt auf einer Yacht mit der Möglichkeit, Tauchen, Kitesurfen und Entspannung am Abend zu wählen, Verpflegung inklusive.
🏠 Unterkunft eine Woche im Hotel mit Frühstück und/oder Mittagessen.
🍽️ Abendessen bis zu 20 EUR in guten bewährten Restaurants außerhalb des Hotels.

Das Programm ist sowohl für Anfänger als auch für erfahrene Teilnehmer geeignet.
Die Anzahl der Plätze ist unbegrenzt — wir warten auf Sie alle.

Schreiben Sie persönlich, um ein detailliertes Programm zu erhalten und Ihre Teilnahme zu buchen.
Kontakt: WhatsApp +41 79 943 35 79"""

EVENT_DESCRIPTION_FR = """L'Association Internationale des Sports Extrêmes vous invite à un voyage d'une semaine à la Mer Rouge.
C'est un format de loisirs actifs où un changement d'environnement, la mer et le mouvement redonnent de l'énergie et de la clarté.

Ce qui vous attend :

⛵ Hébergement sur un yacht ou dans un hôtel confortable 4* minimum, en bord de mer.
🤿 Plongée quotidienne avec supervision professionnelle.
🌊 Sports nautiques : yachting, planche à voile, kitesurf.
⛵ Possibilité d'apprendre la gestion d'un catamaran à voile ou d'un yacht à voile.
🏛️ Possibilité de visiter le nouveau Grand Musée Égyptien — la 8e merveille du monde.
📵 Réduction du bruit d'information et de la routine quotidienne.
🤝 Équipe internationale et environnement de personnes partageant les mêmes idées.

Conditions de participation :

💰 Coût : 1600 CHF en séjournant sur un yacht avec la possibilité de choisir la plongée, le kitesurf et la détente le soir, repas inclus.
🏠 Hébergement une semaine dans un hôtel avec petit-déjeuner et/ou déjeuner.
🍽️ Dîner jusqu'à 20 EUR dans de bons restaurants éprouvés en dehors de l'hôtel.

Le programme convient aussi bien aux débutants qu'aux participants expérimentés.
Le nombre de places est illimité — nous vous attendons tous.

Écrivez personnellement pour obtenir un programme détaillé et réserver votre participation.
Contact : WhatsApp +41 79 943 35 79"""

EVENT_DESCRIPTION_UK = """Міжнародна Асоціація екстремального спорту запрошує вас на тижневу виїзну програму на Червоне море.
Це формат активного проведення часу, де зміна середовища, море і рух повертають енергію та ясність.

Що на вас чекає:

⛵ Проживання на яхті або в комфортному готелі мінімум 4*, на березі.
🤿 Щоденні дайвінг-занурення з професійним супроводом.
🌊 Водні види спорту: яхтинг, віндсерф, кайтсерф.
⛵ Можливість навчання керуванню вітрильним катамараном або вітрильною яхтою.
🏛️ Можливість відвідування нового Великого Єгипетського музею — 8-е диво світу.
📵 Зниження інформаційного шуму та щоденної рутини.
🤝 Міжнародна команда та середовище однодумців.

Умови участі:

💰 Вартість: 1600 CHF при проживанні на яхті з можливістю вибору дайвінгу, кайтсерфінгу та релаксу ввечері, харчування включено.
🏠 Проживання один тиждень у готелі зі сніданком та/або обідом.
🍽️ Вечеря до 20 EUR у хороших перевірених ресторанах за межами готелю.

Програма підходить як для початківців, так і для учасників з досвідом.
Кількість місць не обмежена — чекаємо на вас усіх.

Напишіть особисто, щоб отримати детальну програму та забронювати участь.
Контакт: WhatsApp +41 79 943 35 79"""


def update_event_translations(apps, schema_editor):
    Event = apps.get_model("blog", "Event")

    # Find the Egypt event
    event = Event.objects.filter(title_en=EVENT_TITLE_RU).first() or Event.objects.filter(title=EVENT_TITLE_RU).first()
    
    if event:
        # Update all language versions
        event.title = EVENT_TITLE_RU
        event.title_en = EVENT_TITLE_EN
        event.title_de = EVENT_TITLE_DE
        event.title_fr = EVENT_TITLE_FR
        event.title_uk = EVENT_TITLE_UK
        
        event.description = EVENT_DESCRIPTION_RU
        event.description_en = EVENT_DESCRIPTION_EN
        event.description_de = EVENT_DESCRIPTION_DE
        event.description_fr = EVENT_DESCRIPTION_FR
        event.description_uk = EVENT_DESCRIPTION_UK
        
        event.location = EVENT_LOCATION_RU
        event.location_en = EVENT_LOCATION_EN
        event.location_de = EVENT_LOCATION_DE
        event.location_fr = EVENT_LOCATION_FR
        event.location_uk = EVENT_LOCATION_UK
        
        event.save()


def reverse_noop(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ("blog", "0008_upsert_egypt_extreme_week_event"),
    ]

    operations = [
        migrations.RunPython(update_event_translations, reverse_noop),
    ]
