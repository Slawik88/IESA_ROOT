#!/usr/bin/env python3
"""
tg_export_converter.py
──────────────────────
Конвертирует стандартный Telegram-экспорт истории чата (result.json)
в import_data.json для команды «бот загрузить данные» бота Предвестник.

Что делает:
  1. Читает result.json (экспорт из Telegram Desktop → "Экспорт истории чата")
  2. Считает количество сообщений каждого реального пользователя
  3. Рассчитывает оценку XP и Моры по формулам бота
  4. Создаёт import_data.json в формате, который принимает бот
  5. Выводит краткий отчёт в консоль

Требования: Python 3.8+, никаких дополнительных пакетов не нужно.

Запуск:
  python tg_export_converter.py
  python tg_export_converter.py --input path/to/result.json --output import_data.json
  python tg_export_converter.py --min-messages 10   # пропустить пользователей с < 10 сообщ.
"""

import argparse
import json
import math
import sys
from collections import defaultdict
from pathlib import Path

# ── Формулы из конфига бота (config.py) ──────────────────────────────────────
# Синхронизируй эти значения с config.py, если они менялись.

XP_PER_MESSAGE   = 2      # XP за одно сообщение (config.XP_PER_MESSAGE)
XP_COOLDOWN      = 60     # секунд между начислениями XP (config.XP_COOLDOWN)

MORA_MSG_CHANCE  = 0.17   # 17% шанс выпадения Моры за сообщение (config.MORA_MSG_CHANCE)
MORA_MSG_MIN     = 1      # минимум Моры за одно выпадение (config.MORA_MSG_MIN)
MORA_MSG_MAX     = 3      # максимум Моры за одно выпадение (config.MORA_MSG_MAX)
MORA_MSG_COOLDOWN = 180   # секунд между выпадениями Моры (config.MORA_MSG_COOLDOWN)

# Средний дроп Моры за одно «удачное» сообщение
_MORA_AVG_DROP = (MORA_MSG_MIN + MORA_MSG_MAX) / 2  # = 2.0

# ─────────────────────────────────────────────────────────────────────────────


def _parse_user_id(from_id: str) -> int | None:
    """
    Конвертирует from_id из Telegram-экспорта в числовой user_id.

    Telegram Desktop добавляет префикс:
      "user123456789"    → 123456789   (обычный пользователь)
      "channel123456789" → None        (канал — игнорируем)
      "bot123456789"     → None        (боты — игнорируем)

    Если значение уже числовое — возвращаем как есть.
    """
    if not from_id:
        return None
    s = str(from_id).strip()
    if s.startswith("user"):
        numeric = s[4:]  # убираем "user"
        return int(numeric) if numeric.isdigit() else None
    if s.isdigit() or (s.startswith("-") and s[1:].isdigit()):
        # некоторые версии экспорта дают просто число
        return int(s)
    # Всё остальное (channel..., chat..., bot...) — игнорируем
    return None


def _estimate_xp(message_count: int) -> int:
    """
    Оценка XP на основе количества сообщений.

    Бот даёт XP_PER_MESSAGE XP за каждое сообщение, но не чаще
    одного раза в XP_COOLDOWN секунд (кулдаун). Если сообщение пришло
    раньше чем через XP_COOLDOWN секунд — XP не начисляется.

    Поскольку мы не знаем временны́е метки сообщений из экспорта,
    возвращаем МАКСИМАЛЬНО возможный XP (как если бы каждое сообщение
    было отправлено с достаточным интервалом). Реальный XP может быть меньше.
    """
    return message_count * XP_PER_MESSAGE


def _estimate_mora(message_count: int) -> int:
    """
    Оценка Моры на основе количества сообщений.

    Бот с шансом MORA_MSG_CHANCE (17%) начисляет случайное количество
    Моры (от MORA_MSG_MIN до MORA_MSG_MAX) за каждое сообщение,
    но не чаще раза в MORA_MSG_COOLDOWN секунд.

    Оценка: message_count * шанс * средний_дроп.
    Это ожидаемое (математическое ожидание) значение Моры.
    """
    return math.floor(message_count * MORA_MSG_CHANCE * _MORA_AVG_DROP)


def load_result_json(path: Path) -> list[dict]:
    """Читает result.json и возвращает список сообщений."""
    if not path.exists():
        print(f"❌ Файл не найден: {path}", file=sys.stderr)
        sys.exit(1)

    with path.open(encoding="utf-8") as f:
        try:
            data = json.load(f)
        except json.JSONDecodeError as e:
            print(f"❌ Ошибка разбора JSON: {e}", file=sys.stderr)
            sys.exit(1)

    # Telegram Desktop кладёт сообщения в data["messages"]
    messages = data.get("messages") if isinstance(data, dict) else data
    if not isinstance(messages, list):
        print("❌ Не найден массив messages. Проверь, что файл — экспорт Telegram Desktop.", file=sys.stderr)
        sys.exit(1)

    return messages


def count_messages(messages: list[dict]) -> tuple[dict[int, int], dict[int, str]]:
    """
    Считает количество сообщений на пользователя.

    Возвращает:
      counts    — {user_id: message_count}
      names     — {user_id: full_name}
    """
    counts: dict[int, int] = defaultdict(int)
    names:  dict[int, str] = {}
    skipped_channels = 0

    for msg in messages:
        # Обрабатываем только обычные сообщения
        if msg.get("type") != "message":
            continue

        from_id_raw = msg.get("from_id")
        if not from_id_raw:
            continue

        user_id = _parse_user_id(str(from_id_raw))
        if user_id is None:
            # Канал, группа или бот — пропускаем
            skipped_channels += 1
            continue

        counts[user_id] += 1

        # Запоминаем имя (поле "from" — отображаемое имя пользователя)
        if user_id not in names:
            display_name = msg.get("from") or ""
            if display_name:
                names[user_id] = str(display_name).strip()

    if skipped_channels:
        print(f"ℹ️  Пропущено сообщений от каналов/групп/ботов: {skipped_channels}")

    return dict(counts), names


def build_import_records(
    counts: dict[int, int],
    names:  dict[int, str],
    min_messages: int = 1,
) -> tuple[list[dict], list[dict]]:
    """
    Формирует записи для import_data.json (формат бота «бот загрузить данные»).

    Возвращает:
      import_records  — список для записи в import_data.json
      report_rows     — расширенные данные для консольного отчёта (с XP и Морой)
    """
    import_records = []
    report_rows    = []

    for user_id, msg_count in sorted(counts.items(), key=lambda x: x[1], reverse=True):
        if msg_count < min_messages:
            continue

        full_name = names.get(user_id, "")
        xp_est    = _estimate_xp(msg_count)
        mora_est  = _estimate_mora(msg_count)

        # Формат, который ожидает «бот загрузить данные»
        record: dict = {"user_id": user_id, "messages": msg_count}
        if full_name:
            record["full_name"] = full_name

        import_records.append(record)
        report_rows.append({
            "user_id":  user_id,
            "name":     full_name or f"id{user_id}",
            "messages": msg_count,
            "xp_est":   xp_est,
            "mora_est": mora_est,
        })

    return import_records, report_rows


def print_report(report_rows: list[dict], total_messages: int, output_path: Path) -> None:
    """Красивый отчёт в консоль."""
    total_users = len(report_rows)
    total_xp    = sum(r["xp_est"]   for r in report_rows)
    total_mora  = sum(r["mora_est"] for r in report_rows)

    sep = "─" * 70
    print()
    print("═" * 70)
    print("  РЕЗУЛЬТАТ КОНВЕРТАЦИИ — Предвестник Import")
    print("═" * 70)
    print(f"  Уникальных пользователей : {total_users:,}")
    print(f"  Всего сообщений          : {total_messages:,}")
    print(f"  Суммарный XP (оценка)    : {total_xp:,}  ({XP_PER_MESSAGE} XP за сообщение)")
    print(f"  Суммарная Мора (оценка)  : {total_mora:,}  ({MORA_MSG_CHANCE*100:.0f}% шанс, ср. {_MORA_AVG_DROP} за выпадение)")
    print()
    print(f"  Файл импорта сохранён:   {output_path}")
    print(sep)
    print(f"  {'#':>4}  {'Имя':<28}  {'ID':>12}  {'Сообщ':>7}  {'XP':>7}  {'Мора':>6}")
    print(sep)

    for i, row in enumerate(report_rows[:50], 1):  # показываем топ-50
        name = row["name"][:27] + "…" if len(row["name"]) > 28 else row["name"]
        print(
            f"  {i:>4}  {name:<28}  {row['user_id']:>12}  "
            f"{row['messages']:>7,}  {row['xp_est']:>7,}  {row['mora_est']:>6,}"
        )

    if total_users > 50:
        print(f"  ... и ещё {total_users - 50} пользователей (смотри {output_path.name})")

    print(sep)
    print()
    print("  📌 Примечания:")
    print(f"     XP рассчитан как максимально возможный ({XP_PER_MESSAGE} XP × сообщения).")
    print(f"     Реальный XP может быть меньше из-за кулдауна {XP_COOLDOWN}с между начислениями.")
    print(f"     Мора — математическое ожидание. Реальная сумма зависела бы от случайности.")
    print()
    print("  📥 Как использовать import_data.json:")
    print("     В чате с ботом отправь команду:")
    print("     бот загрузить данные")
    print("     → Бот попросит файл/JSON. Скопируй содержимое import_data.json и отправь.")
    print("     Или сразу:")
    print("     бот загрузить данные [вставь содержимое файла]")
    print()
    print("═" * 70)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Конвертация Telegram-экспорта в import_data.json для бота Предвестник",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--input", "-i",
        default="result.json",
        help="Путь к result.json из экспорта Telegram (по умолчанию: result.json)",
    )
    parser.add_argument(
        "--output", "-o",
        default="import_data.json",
        help="Имя выходного файла (по умолчанию: import_data.json)",
    )
    parser.add_argument(
        "--min-messages", "-m",
        type=int,
        default=1,
        help="Минимум сообщений для включения пользователя (по умолчанию: 1)",
    )
    args = parser.parse_args()

    input_path  = Path(args.input)
    output_path = Path(args.output)

    print(f"📂 Читаю {input_path} …")
    messages = load_result_json(input_path)
    print(f"   Загружено записей: {len(messages):,}")

    print("📊 Подсчёт сообщений по пользователям …")
    counts, names = count_messages(messages)

    total_messages = sum(counts.values())

    import_records, report_rows = build_import_records(
        counts, names, min_messages=args.min_messages
    )

    if not import_records:
        print("⚠️  Нет пользователей, удовлетворяющих критериям. Файл не создан.")
        sys.exit(0)

    # Сохраняем import_data.json
    with output_path.open("w", encoding="utf-8") as f:
        json.dump(import_records, f, ensure_ascii=False, indent=2)

    print_report(report_rows, total_messages, output_path)


if __name__ == "__main__":
    main()
