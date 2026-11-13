"""Даты денежных операций: ввод человека и проверка локального дня дома."""
from datetime import datetime, date

from services.households import DomainError


def parse_date(raw: str, today: str) -> str:
    for pattern in ("%Y-%m-%d", "%d.%m.%Y"):
        try:
            result = datetime.strptime(raw.strip(), pattern).date().isoformat()
            break
        except ValueError:
            continue
    else:
        raise DomainError("Введите дату как 25.10.2026 или 2026-10-25")
    if result > today:
        raise DomainError("Операцию можно записать за сегодня или прошедший день")
    return result


def parse_month(raw: str) -> str:
    for pattern in ("%Y-%m", "%m.%Y"):
        try:
            result = datetime.strptime(raw.strip(), pattern).date()
            return date(result.year, result.month, 1).isoformat()[:7]
        except ValueError:
            continue
    raise DomainError("Введите месяц как 2026-10 или 10.2026")
