from datetime import datetime, timezone

from django.db import migrations, models


TEEN_EVENT_TITLE = "Скаут-кэмп для подростков на берегу Красного моря в Хургаде, Египет"
TEEN_EVENT_LOCATION = "Хургада, Египет"
TEEN_EVENT_DESCRIPTION = """Международная ассоциация экстремального спорта IESA —
Для родителей, которые хотят для своих детей большего, чем просто каникулы.

Наш лагерь — это безопасная, дисциплинированная и вдохновляющая среда, где подростки учатся любить движение, спорт, жизнь и себя.
Мы соединяем физическое развитие, ментальное здоровье и осознанный отдых в одном продуманном формате международного выезда на море.

Что мы даём вашему ребёнку:
1. Любовь к спорту — без давления.
Подростки пробуют водные виды спорта в поддерживающей атмосфере. Формируется устойчивая мотивация к движению, спорту и здоровому образу жизни, учатся дисциплине.
2. Цифровой детокс.
Мы мягко переключаем внимание от постоянного использования телефонов к реальной жизни, телу, природе и живому общению.
3. Физическое и ментальное здоровье.
Ежедневная активность, режим, общение и спорт помогают укрепить физическую форму, уверенность в себе и эмоциональную устойчивость, снизить тревожность.
Стать более самостоятельным, уметь видеть и добиваться своих целей.
4. Присмотр и безопасность 24/7.
Дети находятся под постоянным контролем взрослых сопровождающих и профессиональных инструкторов.

Формат лагеря:
Продолжительность: 1 или 2 недели.
Выезд: из Швейцарии.
Возрастная группа: подростки 12-18 лет.

Что включено в программу:
✈️ Перелёт (Швейцария ↔ Египет)
🏨 Проживание в отеле
🍽 Полноценное питание
🚐 Все трансферы (аэропорт – отель – активности)
🧑‍🏫 Профессиональные инструкторы по водным видам спорта, а также курсы по дайвингу (занятия по желанию и уровню подготовки)
🧠 Ежедневные активности для физического и ментального здоровья
👥 Постоянный присмотр и сопровождение
📸 Фото- и видеоматериалы
📘 Итоговый отчёт для родителей и памятные материалы

Почему родители нам доверяют:
Международная ассоциация с чёткой структурой и стандартами.
Опыт работы с подростками и спортивными программами.
Фокус не только на физической активности, но и на психоэмоциональном состоянии.
Прозрачная организация поездки «под ключ».
Постоянная связь и отчётность.

Результат для ребёнка:
Подросток возвращается домой более самостоятельным, физически активным, с новым кругом общения и живым интересом к спорту и реальной жизни."""

ADULT_EVENT_TITLE_RU = "Неделя экстремального спорта и полной перезагрузки в Египте 🌊"
ADULT_EVENT_TITLE_EN = "Week of Extreme Sports and Complete Reboot in Egypt 🌊"


def seed_teen_event_and_normalize_adult(apps, schema_editor):
    Event = apps.get_model("blog", "Event")

    teen_defaults = {
        "title": TEEN_EVENT_TITLE,
        "title_en": "Teen Scout Camp on the Red Sea Coast in Hurghada, Egypt",
        "title_de": "Scout-Camp für Jugendliche am Roten Meer in Hurghada, Ägypten",
        "title_fr": "Camp scout pour adolescents sur la mer Rouge à Hurghada, Égypte",
        "title_uk": "Скаут-кемп для підлітків на узбережжі Червоного моря в Хургаді, Єгипет",
        "description": TEEN_EVENT_DESCRIPTION,
        "description_en": TEEN_EVENT_DESCRIPTION,
        "description_de": TEEN_EVENT_DESCRIPTION,
        "description_fr": TEEN_EVENT_DESCRIPTION,
        "description_uk": TEEN_EVENT_DESCRIPTION,
        "location": TEEN_EVENT_LOCATION,
        "location_en": "Hurghada, Egypt",
        "location_de": "Hurghada, Ägypten",
        "location_fr": "Hurghada, Égypte",
        "location_uk": "Хургада, Єгипет",
        "date": datetime(2026, 7, 6, 8, 0, tzinfo=timezone.utc),
        "end_date": datetime(2026, 7, 13, 18, 0, tzinfo=timezone.utc),
        "registration_deadline": datetime(2026, 6, 29, 18, 0, tzinfo=timezone.utc),
        "status": "upcoming",
        "max_participants": None,
        "min_age": 12,
        "max_age": 18,
    }

    teen_event = Event.objects.filter(title=TEEN_EVENT_TITLE).first() or Event.objects.filter(title_en=teen_defaults["title_en"]).first()
    if teen_event:
        for field_name, value in teen_defaults.items():
            setattr(teen_event, field_name, value)
        teen_event.save()
    else:
        Event.objects.create(**teen_defaults)

    adult_event = Event.objects.filter(title=ADULT_EVENT_TITLE_RU).first() or Event.objects.filter(title_en=ADULT_EVENT_TITLE_EN).first()
    if adult_event:
        adult_event.min_age = None
        adult_event.max_age = None
        adult_event.save(update_fields=["min_age", "max_age"])


def reverse_noop(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ("blog", "0009_update_egypt_event_translations"),
    ]

    operations = [
        migrations.AddField(
            model_name="event",
            name="min_age",
            field=models.PositiveSmallIntegerField(blank=True, null=True, verbose_name="Minimum Age"),
        ),
        migrations.AddField(
            model_name="event",
            name="max_age",
            field=models.PositiveSmallIntegerField(blank=True, null=True, verbose_name="Maximum Age"),
        ),
        migrations.RunPython(seed_teen_event_and_normalize_adult, reverse_noop),
    ]
