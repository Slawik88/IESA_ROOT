@predvestnik_v2/BASE_PROMPT.md
@predvestnik_v2/AUTONOMOUS_MODE.md
@predvestnik_v2/AUTONOMOUS_AGENT_POLICY.md

## Предвестник: патч-ноуты в официальный канал (обязательно)

Каждое обновление Предвестника, которое заметит игрок, выпускается вместе с пунктом в патч-ноуте дня:
`predvestnik_v2/FastAPI/static/patch-notes/<ГГГГ-ММ-ДД>.json` и скриншот в `patch-notes/img/` (или `"image": "cover"`).
Пишем для обычного игрока: польза, где найти, без технических слов; картинка — реальный экран без личных данных.
Отправляет создатель кнопкой в админке («Патч-ноуты»), сам бот ничего не публикует.
Полные правила и формат: `predvestnik_v2/docs/PATCH_NOTES.md`. Проверка: `python predvestnik_v2/tools/test_patch_notes_contract.py`.
