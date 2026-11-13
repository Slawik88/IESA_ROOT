"""
services/reports.py — человекочитаемые тексты отчётов.

Здесь только сборка текста из данных сервисов; правила считают money/cleaning.
"""
from core.money import format_amount
from services import cleaning, money, settings as settings_service


async def month_report_text(house, month: str) -> str:
    """Месячный итог: баланс котла, взносы, траты по категориям, долги возврата."""
    house_settings = await settings_service.house_settings(house["id"])
    currency = house_settings["currency"]
    report = await money.month_report(house["id"], month)

    balance = report["balance"]["balance"]
    lines = [f"📊 Отчёт за {month} — дом «{house['name']}»", ""]
    lines.append(f"Текущий баланс котла: {format_amount(balance, currency)}")
    lines.append(
        f"  подтверждённые взносы: {format_amount(report['balance']['confirmed_total'], currency)}"
    )
    lines.append(
        f"  потрачено из котла: {format_amount(report['balance']['house_spent'], currency)}"
    )
    if report["balance"]["reimbursed"]:
        lines.append(
            f"  возвращено из котла: {format_amount(report['balance']['reimbursed'], currency)}"
        )
    lines.append("")

    confirmed = [c for c in report["contributions"] if c["status"] == money.STATUS_CONFIRMED]
    declared = [c for c in report["contributions"] if c["status"] == money.STATUS_DECLARED]
    if confirmed:
        lines.append("Взносы:")
        for row in confirmed:
            lines.append(f"  {row['display_name']}: {format_amount(row['amount_kop'], currency)}")
        lines.append("")
    if declared:
        lines.append(f"Ожидают подтверждения взносы: {len(declared)}")
        lines.append("")

    if report["by_category"]:
        lines.append("Траты по категориям:")
        for name, kop in sorted(report["by_category"].items(), key=lambda item: -item[1]):
            lines.append(f"  {name}: {format_amount(kop, currency)}")
        lines.append("")

    if report["outstanding"]:
        lines.append("Ждут возврата из котла:")
        for row in report["outstanding"]:
            lines.append(f"  {row['display_name']}: {format_amount(row['amount_kop'], currency)}")
        lines.append("")

    history = await cleaning.month_history(house["id"], month)
    stats = cleaning.member_stats(history)
    if stats:
        lines.append("Уборка за месяц:")
        for entry in stats.values():
            parts = [f"убрался {entry['done']} раз"]
            if entry["open"]:
                parts.append(f"не закрыто дней: {entry['open']}")
            if entry["canceled"]:
                parts.append(f"отменено: {entry['canceled']}")
            lines.append(f"  {entry['name']}: {', '.join(parts)}")
    return "\n".join(lines)
