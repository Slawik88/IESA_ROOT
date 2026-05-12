"""
Сервис построения календарной сетки (Block 4b).

Извлечён из partner_calendar() для соблюдения SRP.
"""
from __future__ import annotations

import calendar as _cal_mod
from datetime import date, timedelta
from typing import Any


def build_month_grid(year: int, month: int, meetings_by_date: dict) -> list[list[dict | None]]:
    """Строит двумерный массив ячеек для отображения месячной сетки.

    Args:
        year, month: целевой год и месяц
        meetings_by_date: dict {date: [Meeting, ...]}

    Returns:
        Список недель (7 дней каждая). None = пустая ячейка (день вне месяца).
        Ячейка-словарь: date, num, is_today, is_selected, meetings, count.
    """
    today = date.today()
    cal_weeks = _cal_mod.monthcalendar(year, month)

    grid = []
    for week in cal_weeks:
        row = []
        for day_num in week:
            if day_num == 0:
                row.append(None)
            else:
                d = date(year, month, day_num)
                meets = meetings_by_date.get(d, [])
                row.append({
                    'date':        d,
                    'num':         day_num,
                    'is_today':    d == today,
                    'is_selected': False,   # caller may patch this
                    'meetings':    meets,
                    'count':       len(meets),
                })
        grid.append(row)
    return grid


def mark_selected(grid: list[list[dict | None]], selected_day: date) -> None:
    """Помечает выбранный день в уже построенной сетке (мутирует in-place)."""
    for week in grid:
        for cell in week:
            if cell and cell['date'] == selected_day:
                cell['is_selected'] = True
                return


def get_jump_options(current_year: int, current_month: int) -> list[dict]:
    """Список вариантов для быстрого прыжка: текущий год ± 2."""
    _MONTH_ABBR = ['', 'Янв', 'Фев', 'Мар', 'Апр', 'Май', 'Июн',
                   'Июл', 'Авг', 'Сен', 'Окт', 'Ноя', 'Дек']
    today = date.today()
    options = []
    for y in range(today.year - 2, today.year + 4):
        for m in range(1, 13):
            options.append({
                'value':    f'{y}-{m:02d}',
                'label':    f'{_MONTH_ABBR[m]} {y}',
                'selected': (y == current_year and m == current_month),
            })
    return options


def serialize_day_meetings(meetings) -> list[dict[str, Any]]:
    """Сериализует встречи дня в JSON-совместимый список для JS-рендеринга."""
    result = []
    for m in meetings:
        result.append({
            'id':          m.pk,
            'title':       m.title,
            'member':      m.member.get_full_name() or m.member.username,
            'start':       m.start_time.strftime('%H:%M') if m.start_time else None,
            'end':         m.end_time.strftime('%H:%M')   if m.end_time   else None,
            'start_h':     m.start_time.hour + m.start_time.minute / 60 if m.start_time else None,
            'end_h':       m.end_time.hour   + m.end_time.minute   / 60 if m.end_time   else None,
            'status':      m.status,
            'address':     m.address,
            'is_recurring': m.is_recurring,
            'series_label': m.series_label,
            'cancel_url':  f'/auth/partner/meeting/{m.pk}/cancel/',
        })
    return result
