# Общие правила для всех ИИ-агентов (любой вендор)

До первой правки кода в Предвестнике прочитай `predvestnik_v2/AGENTS.md` (точка входа:
слои, маршрутизация по документам) и `predvestnik_v2/CLEAN_CODE.md` (обязательный
стандарт кода: анти-мусор, git-гигиена, Definition of Done). Для инструментов,
понимающих импорты, они подтянутся ниже; для остальных — это явное указание прочитать.

@predvestnik_v2/AGENTS.md
@predvestnik_v2/CLEAN_CODE.md
@predvestnik_v2/AUTONOMOUS_MODE.md
@predvestnik_v2/AUTONOMOUS_AGENT_POLICY.md
@predvestnik_v2/docs/PLAYER_COPY.md

## Предвестник: патч-ноуты в официальный канал (обязательно)

Каждое обновление Предвестника, которое заметит игрок, выпускается вместе с пунктом в патч-ноуте дня:
`predvestnik_v2/FastAPI/static/patch-notes/<ГГГГ-ММ-ДД>.json` и скриншот в `patch-notes/img/` (или `"image": "cover"`).
Пишем для обычного игрока: польза, где найти, без технических слов; картинка — реальный экран без личных данных.
Отправляет создатель кнопкой в админке («Патч-ноуты»), сам бот ничего не публикует.
Полные правила и формат: `predvestnik_v2/docs/PATCH_NOTES.md`. Проверка: `python predvestnik_v2/tools/test_patch_notes_contract.py`.
