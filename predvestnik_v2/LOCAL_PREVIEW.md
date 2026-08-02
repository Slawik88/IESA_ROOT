# Локальный сервер и предпроизводственная проверка

Локальный стенд — обязательный первый этап любой разработки `predvestnik_v2`.
Изменение сначала реализуется и проверяется здесь; production-деплой, рестарт и
операции с живой БД выполняются только отдельным явно разрешённым шагом.

## Быстрый запуск в текущем Linux/VS Code окружении

Из корня репозитория:

```bash
nix-shell -p nodejs_22 --run 'npm run preview --prefix predvestnik_v2'
```

Либо в VS Code: `Ctrl+Shift+P` → `Tasks: Run Task` →
`Predvestnik: local preview`.

Сервер слушает `http://localhost:8402/`. Порт можно изменить переменной `PORT`:

```bash
PORT=63768 nix-shell -p nodejs_22 --run 'npm run preview --prefix predvestnik_v2'
```

Если Node.js уже установлен системно, достаточно:

```bash
cd predvestnik_v2
npm run preview
```

## Как смотреть изменения в VS Code

1. Открыть нижнюю панель (`Ctrl+J`).
2. Выбрать вкладку `PORTS`. Если её нет: `Ctrl+Shift+P` →
   `Ports: Focus on Ports View`.
3. Нажать `Forward a Port`, ввести `8402`.
4. У строки порта нажать `Open in Browser` или `Open in Preview`.

Настройка `remote.restoreForwardedPorts` сохранена в `.vscode/settings.json`, поэтому
VS Code должен помнить проброшенный порт между подключениями.

Для просмотра сайта прямо во вкладке редактора дополнительное расширение не нужно:
`Ctrl+Shift+P` → `Simple Browser: Show` → `http://localhost:8402/`.

## Как смотреть изменения файлов

Если служебная вкладка `Codex Diff` показывает `Oops, an error has occurred`, diff
всё равно доступен штатными средствами VS Code: `Ctrl+Shift+G` → `Changes` → нажать
на файл. Список и открытый diff обновляются автоматически. Отдельное Git-расширение
не требуется. Для восстановления панели Codex сначала выполнить `Ctrl+Shift+P` →
`Developer: Reload Window`; затем, если ошибка сохраняется, обновить или
переустановить только официальное расширение `Codex — OpenAI`.

`FastAPI/static/index.html`, `app.css` и части `app.01.js`…`app.11.js` читаются с
диска на каждый HTTP-запрос. Сервер следит за изменениями в `FastAPI/static/` и
через локальный SSE-канал автоматически обновляет все открытые вкладки. Команда
`npm run preview` также перезапускает сервер после изменения самого
`tools/preview_server.mjs`; подключённые вкладки обновятся после восстановления
соединения. Ручной `F5` обычно не нужен.

## Что именно эмулирует стенд

`tools/preview_server.mjs` — Node.js HTTP-сервер без FastAPI, Telegram и БД. Он:

- отдаёт реальный `FastAPI/static/index.html` с пустым `BASE`;
- собирает `/static/app.js` из `app.01.js`…`app.11.js` в production-порядке;
- отдаёт реальный `app.css` и остальные статические файлы;
- заранее создаёт локальную сессию, чтобы не мешал экран логина;
- автоматически обновляет все открытые вкладки после изменений клиентских файлов;
- возвращает реалистичные моки для профиля, валют, питомцев, боёв, магазина,
  косметики, тем и админки;
- хранит покупку/экипировку тем в памяти процесса и сбрасывает её через
  `POST /__preview/reset`;
- записывает незамоканные запросы в `tools/unknown-api.log`.

Ограничения стенда:

- нет PostgreSQL, транзакций и настоящей серверной бизнес-логики;
- нет Telegram WebApp API и поведения реального мобильного клиента;
- WebSocket upgrade намеренно закрывается;
- большинство мутаций — статические успешные ответы, кроме stateful-сценария тем;
- данные мока могут устареть относительно реальных роутеров, поэтому новый или
  изменённый API-контракт нужно обновлять и проверять с обеих сторон.

Локальные предложения, явно помеченные как localhost-only (например, модель цен
косметики из `docs/superpowers/plans/2026-07-31-local-cosmetics-pricing.md`), нельзя
переносить в production-каталог без отдельного решения владельца.

## Проверки

Установка браузерной зависимости:

```bash
cd predvestnik_v2
nix-shell -p nodejs_22 chromium --run 'PUPPETEER_SKIP_DOWNLOAD=true npm install'
```

В Nix-окружении используется системный Chromium. Профильный Puppeteer-тест:

```bash
nix-shell -p nodejs_22 chromium --run \
  'PUPPETEER_EXECUTABLE_PATH=$(command -v chromium) node predvestnik_v2/tools/verify_fitting_room.mjs'
```

Быстрый smoke при уже запущенном сервере:

```bash
nix-shell -p nodejs_22 --run 'npm run check:preview --prefix predvestnik_v2'
```

UI-регрессии находятся в `tools/verify_*.mjs` и используют Puppeteer с адресом
`http://localhost:8402/`. Основная проверочная ширина — 390 px. Для затронутого
сценария нужно запустить профильный скрипт, затем связанные регрессии. Длинный
набор запускать последовательно: исторически параллельный прогон создавал ложные
гонки кадров; подозрительное падение перепроверяется изолированно.

Полный последовательный прогон:

```bash
nix-shell -p nodejs_22 chromium --run \
  'PUPPETEER_EXECUTABLE_PATH=$(command -v chromium) npm run test:ui --prefix predvestnik_v2'
```

Можно отфильтровать файлы подстрокой имени, например:

```bash
nix-shell -p nodejs_22 chromium --run \
  'PUPPETEER_EXECUTABLE_PATH=$(command -v chromium) npm run test:ui --prefix predvestnik_v2 -- fitting looks'
```

Для ревизии косметики скрипт ниже читает локальный `core.cosmetics`, собирает по
две полные комбинации каждой линейки и сохраняет карточки в `/tmp` без обращения к
production или пользовательским данным:

```bash
cd predvestnik_v2
nix-shell -p nodejs_22 chromium --run \
  'PUPPETEER_EXECUTABLE_PATH=$(command -v chromium) node tools/capture_all_cosmetic_lineups_audit.mjs'
```

Минимальный предпроизводственный шлюз:

1. синтаксис затронутых Python/JavaScript-файлов;
2. `npm run check:preview`;
3. профильные `verify_*.mjs`/`test_*.py`;
4. ручной просмотр на 390 px и проверка консоли;
5. `no-fx`/`prefers-reduced-motion` для затронутых эффектов;
6. проверка `tools/unknown-api.log` на новые незамоканные запросы;
7. отдельное ревью diff и только затем предложение о production-деплое.

Локальный стенд доказывает клиентский контракт и UX, но не заменяет сервисные тесты
для транзакций, гонок, прав доступа и расчётов. Такие изменения дополнительно
проверяются на реальном коде `services/`/`infrastructure/` с тестовой БД или фейковым
адаптером до любого разговора о production.
