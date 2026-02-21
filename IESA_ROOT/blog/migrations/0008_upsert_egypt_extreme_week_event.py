from datetime import datetime, timezone

from django.db import migrations


EVENT_TITLE = "Неделя экстремального спорта и полной перезагрузки в Египте 🌊"
EVENT_LOCATION = "Египет, Красное море"
EVENT_DESCRIPTION = """Международная Ассоциация экстремального спорта приглашает вас на недельную выездную программу на Красном море.
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


def upsert_event(apps, schema_editor):
    Event = apps.get_model("blog", "Event")

    event_defaults = {
        "title": EVENT_TITLE,
        "title_en": EVENT_TITLE,
        "description": EVENT_DESCRIPTION,
        "description_en": EVENT_DESCRIPTION,
        "location": EVENT_LOCATION,
        "location_en": EVENT_LOCATION,
        "date": datetime(2026, 6, 1, 9, 0, tzinfo=timezone.utc),
        "end_date": datetime(2026, 6, 7, 18, 0, tzinfo=timezone.utc),
        "registration_deadline": datetime(2026, 5, 30, 18, 0, tzinfo=timezone.utc),
        "status": "upcoming",
        "max_participants": None,
    }

    event = Event.objects.filter(title_en=EVENT_TITLE).first() or Event.objects.filter(title=EVENT_TITLE).first()
    if event:
        for field_name, value in event_defaults.items():
            setattr(event, field_name, value)
        event.save()
    else:
        Event.objects.create(**event_defaults)


def reverse_noop(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ("blog", "0007_event_description_de_event_description_en_and_more"),
    ]

    operations = [
        migrations.RunPython(upsert_event, reverse_noop),
    ]
