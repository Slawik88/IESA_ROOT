# HataNatata — отдельный личный бот поиска аренды

Прочитай README.md. Не импортируй Предвестника, Домового или Django. Не меняй их
окружения, базы и unit-файлы. Корневые зависимости сайта этому боту не нужны.

- `models.py` — личный фильтр и нормализованное объявление.
- `sources.py` — адаптеры публичных страниц, `network.py` — HTTP и robots.
- `scanner.py` — общий сбор с ограничениями и первой тихой синхронизацией.
- `store.py` — отдельный SQLite, история доставки, кэш и очередь.
- `bot.py`, `telegram.py` — меню в личке и Telegram Bot API.
- `backup.py` — root-only зашифрованная копия в личный R2.

Проверки из корня: `python -m pytest hatanatata/tests -q`,
`python -m ruff check hatanatata`. Live smoke:
`python -m hatanatata.check_sources` (временная тестовая SQLite, без токенов).

Никогда не печатай токен, Telegram URL с токеном, production env или содержимое
бэкапа. Не обходи защиту сайтов, CAPTCHA, платный доступ, robots.txt.
Ошибки разбора не равны пустой выдаче. В статусе отражай частичный охват.
Сначала проверяй на реальном Linux runtime с тестовой БД, затем выпускай отдельную
службу с проверенным SHA. Не запускай второй getUpdates для production-токена.
