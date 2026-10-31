# D · Косметика: образы, тиры, стенд (исследование 2026-10-27)

Пути: `R` = `predvestnik_v2/`, `S` = `predvestnik_v2/FastAPI/static/`. Номера строк на 27.10.2026: сверять с текущим кодом.
Рендеры исследователя лежали во временной папке той сессии и **не сохранились**; воспроизводить заготовкой `../seed/nodb-render/` (см. её README).

## Базовая линия S16 (31.10.2026)

Закреплённый код образов: `aec31c33c0d1ab6a5a7551adcc4f3f931855d01a`.
До снимается из отдельного worktree этой ревизии. Новый воспроизводимый стенд и
перепроверенные 42 концепта — [D2-cosmetics-audit.md](D2-cosmetics-audit.md).
Исследование ниже сохраняет исходную дату 27.10; актуализации S06/S14 отмечены явно.

## Что считается косметикой

**Актуальная система — Skins V3.** 42 образа в `R/core/skins_v3_catalog.py`: 28 постоянных (включая «Тайное Знание»), 12 сезонных, 2 личных. Каждый образ — комплект из 6 «предметов-названий» (ник-эффект,
титул, рамка, ореол, фон, частицы); отдельно они не продаются. Тиры **D→SSS** (не F→SSS из старого плана владельца), шаг SSS только с VIP. Цены покупки: D 400, C 650, B 900, A 1250, S 1850, SS 2700,
SSS 3800 ✨. Шаги Эссенции: C 60, B 140, A 560, S 1000, SS 1600, SSS 2600 (`R/core/skins_v3.py`). Регалии (23 шт., `R/core/marks_v1.py`, `S/app.29.js`, `marks-v3.css`) и 3 supporter-печати
за Stars (`R/core/supporter_cosmetics_v1.py`) — отдельные косметические типы.

**Легаси (закрыто, код остался):** `R/core/cosmetics.py` (134 предмета по 6 слотам и 10 линейкам; `services/cosmetics.py` и роутер `/cosmetics` отвечают 410); `R/core/themes.py` (61 текстовая «тема профиля»
бота, не тема интерфейса); `R/core/global_skins_v1.py`. Остаются для компенсаций, Telegram-профиля и батл-пасса.

Доки частично устарели: `SKINS_V3.md` пишет «25 постоянных» и «сезонных 3», `SKINS_CHAT_DESIGN_HANDOFF.md` — «39 скинов». В коде 28+12+2 и 3 сезона (halloween, new_year, valentine).

## Как отрисовано и где применяется

В `S/` нет ни PNG, ни WebP, ни Lottie для косметики. Всё процедурное.
- **Рамка, ореол, фон, частицы, ник** — CSS по «виду» (`kinds`), общий для всех образов: `S/appearance-v3.css`, `appearance-ring-v3.css`, `appearance-stage-v3.css`. Градиенты, маски и DOM `<i>`/`<b>`.
  Разметка: `S/app.20.js` (`apFromLook`, `apStage`, `apHalo`, `apFrame`).
- **Фирменная деталь (`sig`)** — DOM `<u>` + CSS (`S/app.22.js:29-48`, `skin-signatures*.css`), либо вектор SVG из бежеров (`S/app.32/33/34/53.js`, `skin-sig-a..d`).
- **Сцена вокруг аватара** — слои `_scAdd('id', [[тир,'форма движение',{…}]])` в `S/app.35–38,48,53.js`. Картинки — SVG, запечённые в `data-URI` CSS `S/skin-scene-{a..g}-v3.css`. Генерируют
  `R/tools/scene_art_{a..g}.py` + `scene_kit.py`; запуск `python tools/scene_art.py` (`--check`).
- **Ник** — `S/nickname-v3.js` + `nickname-v3.css`. Два SVG-мотива на образ.
- **Telegram-карточка «бот я»** — Pillow, `R/bot/chat/skin_card_draw.py`. Тексты: `R/core/skins_v3_chat*.py`. SSS — MP4 через PyAV (`skin_motion.py`).
- **Где видно:** профиль, витрина «Образы», публичная карточка, топы и таблицы игр (только если у владельца VIP, `R/services/appearance_public_v3.py`); тосты и подарочная карточка, VIP-превью, семейное дерево;
  **чат Telegram** — видят все, без VIP; **Мафия онлайн:** S14 уже отдаёт VIP-only look/avatar и публичные регалии; рисовать стол будет S15.

## Тиры: что меняется, что нет

**Меняется по тиру (универсально, по виду):**
- Рамка: D–B тонкая, C–B градиент, A+ conic-градиент из 3 цветов, S+ свечение, ряд вращается с B.
- Ореол: ripple 1→2→3 кольца, orbit 1→2→3 спутника, flame 1→3 языка на B, rays тоньше с A.
- Частицы: 6/8/11/15/20/26/34 (`S/app.20.js:8`). `.ap-lite` оставляет половину. Сила `--ap-i` растёт .4→1.
- Ник: C градиент, B эмблема, A рельс и блик по буквам, S свечение, SS ромб, SSS корона.
- Приложение: `fx-1…7` (`S/fx-tiers-v3.css`) — зерно, блики, параллакс, ленты света.
- Сцена: C земля/вода, B небо/свет, A предметы по бокам, S живое, SS редкие события, SSS всё.
- Фирменная деталь: для S/SS/SSS-редкости со своего тира, остальные на SSS.
- Telegram-карточка: частицы 0/0/10/18/28/38/52, вторая линия рамки с S, свечение с SS, звёзды по углам и видео на SSS.

**Не меняется:** палитра, набор видов, геометрия и размеры, названия и титулы, привязка к сету.

**Следствие:** на D все образы кроме двух личных — шаблон: цветное пятно, кольцо, 6 частиц, ник. Отличие только цветом и комбинацией видов.

## Два конкретных случая

**Сакура** (Ханами, Бутон, Лепестковый Вихрь, Лунный Лотос, Письмо с Розой). Многоугольники и круги в трёх местах:
- **Telegram-карточка, самый грубый.** `R/bot/chat/skin_card_draw.py:87-91`: лепесток `petal`/`leaf` = `d.polygon` из 4 точек, ромб с чередованием радиуса 1 и .4. Искры `spark`/`glint`/`star` — 8-конечный полигон (:97-99).
- **Ханами в Mini App.** Цветки на дереве — круги случайного цвета: `R/tools/scene_art_b.py:126-146` (`blossoms` → `circ`), на рендере это розовое «конфетти». Падающие «лепестки» сцены — точки-круги
  `dot rise` (`S/app.36.js:42-49`). Частица `petal` — прямоугольник с `border-radius:100% 0 100% 0` и градиентом (`S/appearance-stage-v3.css:72,75`). Искры — маска-восьмиугольник `--m-spark` (:58, :81).
  Силуэты фона — полигоны `d_poly`/`poly` (`R/tools/scene_kit.py:31-37`).
- **Лучше нарисовано** (ориентир): лепесток с выемкой и 5-лепестковый цветок `R/tools/scene_art_c.py:264-270` (`PETAL`, `#f`), ветви `sakura_branch` :311-341; цветок кроны Ханами `#ornCBlossom` в `S/app.34.js:10`.

**Бездна** (`void`, редкость S). Каталог `core/skins_v3_catalog.py:89-92`, описание «Свет падает в воронку…». По тирам:
- **D–C — почти палитра.** Только общий фон `.ap-bg-vortex` (размытый conic-градиент 150vmin + чёрный круг, `appearance-stage-v3.css:34-36`), ореол eclipse, штриховая рамка.
- **B — «воронка».** Слой `i-spiral` (`S/app.37.js:12`): 5 рукавов-полигонов `ribbon`, opacity .3, вращение 260 с. Рисует `R/tools/scene_art_c.py:23-39`.
- **A — обломки** (`rubble`, `shredded`). **S (`sig_from=S`) — чёрная дыра:** тень горизонта, диск, дуги линзы (`S/app.22.js:32`, `skin-signatures-v3.css:11-29`), `lensArcs`. **SS/SSS** — струя, свет, кольца.
- В Telegram-карточке: 8 дуг шириной 2 px и 8-конечные звёзды (`skin_card_draw.py:76-79`): почти палитра.
- Чтобы увидеть дыру, нужно купить за 1850✨ и вложить 1760 Эссенции (~705✨). Тир превью в «Образах» выбирается без покупки.

## Тема интерфейса от косметики

**Уже есть.** `core/themes.py` тут ни при чём. Токены образа (`app_tokens`) уходят в `body` через `v3ApplyLook` (`S/app.22.js:12-27`). Регулярка `_V3_TOKEN` разрешает только `--v3-*` и `--acc-rgb`.
Меняются bg/ink/dim/faint/track/acc/on-acc/sheet/dock/wash. Игровые страницы получают токены через `S/skin-runtime-v3.js`. По тиру добавляются `fx-N`: фон-холст (акварель, свет, зерно), блики,
параллакс. Тосты и подарки берут форму и цвет от образа. Шрифт, геометрия, порядок информации по гейтам остаются прежними.

**Точки расширения:** (1) ключи `spec` в `app_tokens` (новый токен нужно пропустить через `_V3_TOKEN`); (2) `body[data-skin="id"]` — хук для CSS на образ; (3) событие `skinchange`, `View Transition` при смене
образа (`v3Morph`); (4) `--v3-dur` и `--v3-ease` — образ может менять темп; (5) реестры `_AP_DECOR`, `_ORN`, `_scAdd`; (6) каталог `SKINS`, сеты `SETS`, сезоны `SEASONS`.

**Ограничения.** Гейты запрещают менять геометрию и порядок. `R/docs/COSMETICS_REDESIGN_MIGRATION_PLAN_2026-09-27.md` («направление утверждено, массовое исполнение не разрешено»): визуальная перерисовка
под теми же id миграции не требует. Смена id, цен, обладания — требует (закрытие покупок на сервере, снимок, отображение старый→новый).

## Таблица всех образов

Формат сцены: «слоёв (C·B·A·S·SS·SSS)». Оценка — детализация на SSS по рендеру, 1–5. «D–C» везде ≈1–2: шаблон, исключение — два личных образа.
Виды: рамка/ореол/частицы/ник/фон. Сеты: Л — Сад Лотоса, С — Сад Сакуры, А — Тайное Знание, Т — Ночь Тыкв, Н — Новогодняя Ночь, Б — Бал Полуночи, З — Зимние Истории, В — Два Сердца.

| id (название) | ред. | сет | виды | сцена | деталь (с тира) | оц. | что улучшить |
|---|---|---|---|---|---|---|---|
| forest (Лесной Странник) | D | | ring/soft/leaf/grad/wash | 11 (2·3·2·3·1·0) | canopy (SSS) | 3 | самый скромный сюжет: 2 картинки, на C–B почти пусто |
| dune (Песчаная Тропа) | D | | dash/soft/dot/grad/wash | 16 (4·3·3·4·1·1) | dunes (SSS) | 3 | добавить живое (ветер, следы), не только дюны |
| harbor (Тихая Гавань) | D | | double/ripple/dot/grad/mesh | 18 (3·4·4·5·1·1) | lighthouse (SSS) | 4 | — |
| lotus_pond (Пруд Лотосов) | D | Л | ring/ripple/leaf/grad/wash | 16 (3·4·3·4·1·1) | lilypads (SSS) | 3 | круги шаблонные, `leaf` — «линза» |
| threshold (Порог) | C | | seg/orbit/spark/shimmer/mesh | 14 (2·3·3·3·3·0) | gateway (SSS) | 3 | две картинки, нет SSS-слоя сцены |
| frost (Изморозь) | C | | dash/rays/snow/shimmer/mesh | 16 (3·3·5·3·1·1) | rime (SSS) | 4 | — |
| copper (Медные Сумерки) | C | | double/ripple/spark/foil/grid | 18 (3·4·4·5·2·0) | cogs (SSS) | 4 | нет SSS-слоя |
| sakura_bud (Бутон Сакуры) | C | С | dash/soft/petal/shimmer/mesh | 13 (3·3·2·3·2·0) | budbloom (SSS) | 3 | лепестки частиц «линзой», ветка редкая |
| inferno (Инферно) | B | | seg/flame/ember/glow/mesh | 24 (3·5·5·4·5·2) | blaze (SSS) | 4 | — |
| hanami (Ханами) | B | С | dash/soft/petal/ink/mesh | 21 (3·4·4·4·3·3) | hanamitree (SSS) | 3 | **цветки дерева — круги, «лепестки» — точки** |
| jade (Нефритовый Двор) | B | | double/rays/dot/foil/grid | 22 (3·4·4·6·2·3) | jadecourt (SSS) | 4 | — |
| celestial (Небесное Сияние) | A | | seg/rays/glint/foil/rays | 20 (3·3·3·5·4·2) | seraph (SSS) | 5 | — |
| ruby (Рубиновый Собор) | A | | double/eclipse/spark/foil/vortex | 24 (3·6·4·6·2·3) | facets (SSS) | 5 | — |
| observatory (Лазурная Обсерватория) | A | | seg/orbit/glint/shimmer/stars | 21 (3·5·2·5·3·3) | telescope (SSS) | 4 | — |
| lotus_gold (Золотой Лотос) | A | Л | double/rays/glint/foil/rays | 24 (3·6·4·6·3·2) | goldlotus (SSS) | 4 | — |
| void (Бездна) | S | | dash/eclipse/glint/lens/vortex | 18 (3·3·3·3·3·3) | void (S) | 5 на S+ / 1–2 на D–A | **дыра видна только с тира S**; на D–C переносить часть детали вниз |
| aurora (Северное Сияние) | S | | double/ripple/glint/shimmer/aurora | 17 (4·4·3·2·2·2) | aurora (S) | 4 | — |
| solar (Расплавленное Солнце) | S | | seg/flame/ember/foil/rays | 17 (3·4·2·3·3·2) | solar (S) | 4 | — |
| sakura_storm (Лепестковый Вихрь) | S | С | seg/orbit/petal/lens/vortex | 17 (2·3·2·3·4·3) | petalstorm (S) | 4 | сцена хорошая (`PETAL`), частицы и деталь — «линза» |
| artifact (Артефакт) | SS | | seg/orbit/spark/glitch/grid | 20 (2·4·3·2·6·3) | artifact (SS) | 4 | — |
| moon_lotus (Лунный Лотос) | SS | Л | dash/ripple/petal/ink/aurora | 22 (3·4·6·4·2·3) | lotus (SS) | 4 | — |
| ryujin_tide (Прилив Рюдзина) | SS | | double/ripple/ring/ink/vortex | 19 (2·6·2·3·2·4) | tide (SS) | 4 | — |
| midnight_comet (Полуночная Комета) | SSS | | dash/orbit/glint/comet/stars | 15 (2·3·3·3·2·2) | comet (SSS) | 3 | разрежено: комета и звёзды |
| chrono (Хроно-ткач) | SSS | | seg/orbit/sand/foil/grid | 19 (2·3·4·3·4·3) | chrono (SSS) | 5 | — |
| starheart (Сердце Звезды) | SSS | | double/rays/spark/foil/rays | 18 (2·3·2·4·4·3) | heart (SSS) | 4 | — |
| pumpkin_lantern (Тыквенный Фонарь) | C | Т | dash/flame/ember/glow/wash | 22 (3·5·5·3·2·4) | jacklight (SSS) | 4 | — |
| cobweb (Паутина Полуночи) | B | Т | seg/eclipse/glint/shimmer/grid | 22 (4·6·4·2·3·3) | cobwebs (SSS) | 4 | — |
| witch_hour (Час Ведьм) | A | Т | double/orbit/spark/foil/vortex | 23 (3·4·4·6·3·3) | witchmoon (SSS) | 4 | — |
| snow_globe (Снежный Шар) | C | Н | ring/soft/snow/grad/wash | 20 (4·3·4·4·2·3) | snowdome (SSS) | 4 | — |
| garland (Огни Гирлянды) | B | Н | dash/ripple/glint/shimmer/mesh | 24 (4·4·3·7·3·3) | fairylights (SSS) | 4 | — |
| midnight_chimes (Бой Курантов) | A | Н | double/rays/spark/foil/rays | 21 (4·2·3·5·3·4) | bellchimes (SSS) | 4 | — |
| raven_masquerade (Вороний Маскарад) | S | Б | double/eclipse/glint/foil/vortex | 15 (3·2·4·3·1·2) | ravenmask (S) | 3 | арт ~3 КБ, центр пуст |
| phantom_carriage (Призрачный Экипаж) | SS | Б | seg/orbit/spark/lens/mesh | 15 (2·3·6·2·1·1) | ghostcoach (SS) | 2 | сцена едва читается, экипаж почти не виден |
| gingerbread_house (Пряничная Мастерская) | B | З | double/soft/snow/foil/wash | 11 (2·3·1·2·1·2) | sugarhouse (SSS) | 3 | мало слоёв |
| polar_express (Полярный Экспресс) | S | З | seg/rays/snow/shimmer/stars | 11 (2·2·2·2·1·2) | northtrain (S) | 2 | поезд и виадук еле видны |
| rose_letter (Письмо с Розой) | A | В | double/soft/petal/ink/wash | 12 (2·1·3·3·1·2) | rosequill (SSS) | 3 | арт ~2 КБ, роза — один угол |
| glass_heart (Хрустальное Сердце) | SS | В | dash/orbit/glint/lens/stars | 13 (1·4·3·2·1·2) | crystalheart (SS) | 3 | арт ~1 КБ |
| quiet_library (Тихая Библиотека) | B | А | double/rays/dot/ink/wash | 11 (2·2·2·2·1·2) | candlelit (SSS) | 4 | — |
| alchemist (Лаборатория Алхимика) | A | А | seg/ripple/spark/foil/grid | 12 (2·2·2·2·2·2) | ouroboros (SSS) | 4 | — |
| grimoire (Живой Гримуар) | S | А | dash/orbit/glint/ink/vortex | 11 (2·1·2·2·2·2) | grimoire (S) | 4 | — |
| scarlet_star (Алая Звезда) | SSS | личный | double/neon/star/glow/bow | 16 (4·3·2·2·2·3) | bowstar (SSS) | 5 | с тира D уникальна |
| crimson_dark (Багровый Мрак) | SSS | личный | drip/eclipse/drop/ink/grunge | 16 (4·2·1·5·3·1) | bloodmoon (SSS) | 5 | с тира D уникальна |

Окна сезонов (UTC, `R/core/skins_v3_catalog.py:248`): на 27.10 открыт Хэллоуин (17.10–4.11): pumpkin_lantern, cobweb, witch_hour, raven_masquerade, phantom_carriage. Новый год: 15.12–11.01. Валентин: 7.02–21.02.

## Стенд и скриншоты

**Что есть** (`R/docs/UI_STAND_AND_SMOKE.md`):
- `python tools/ui_stand.py --skin X --tier T --rich` поднимает приложение «как прод» на :8403.
- `python tools/ui_skin_lab.py --only void,hanami --ladder --out DIR` собирает лестницу D…SSS одной картинкой на образ, `ladder-<id>.png`. Ключи: `--tiers`, `--frames N` (кадры движения), `--device mid|low`,
  `--phase` (редкие события), `--view profile`, `--scale 2`.
- В самом приложении: витрина «Образы» (`S/app.23.js`, `_lkPick`/`lkTier`) показывает любой тир без покупки.
- «До/после» по тирам внутри одной ревизии уже есть как `--ladder`. Для сравнения двух ревизий кода нужно прогнать лабораторию в две папки и сравнить `PIL.ImageChops`. Скрипта в репозитории нет
  (`pdiff`/`stagecap` из `DESIGN_SESSION_BRIEF.md` лежали в `/tmp`).
- Admin-превью только мини-арт карточки (`S/bot-admin/admin.js:1747`).

**Среда.** Chromium `/opt/pw-browsers/chromium-1243/chrome-linux/chrome`. Playwright под Node: `/opt/node-tools/node_modules/playwright` (1.63). PIL, `psql` есть. Для `ui_stand` и `ui_smoke` нужны зависимости
проекта (см. `../ENV.md`).

**Рабочий вариант без БД.** Статичная страница из CSS и JS самого проекта плюс JSON каталога рендерит профильную сцену любого образа и тира на Node-Playwright за секунды (проверено исследователем).
Заготовка — `../seed/nodb-render/`.

## Технические ограничения

- **Анимации.** `ap-anim` на `body` включается только при полном режиме. Классы устройства: `.ap-lite` (частицы вдвое, без слоёв `w2`), `.ap-low` (всё статично). `_v3StartWatchdog` понижает ступень, если
  медиана кадра >26 мс. Вне экрана пауза `.ap-off`. Бюджет в `ui_smoke_checks.py`: BUDGET anims ≤95, passes ≤14, area ≤24, bmf ≤24. Замер `--perf --device mid|low`. Тест: до 24 слоёв, до 15 движущихся без `w2`.
- **reduced-motion** покрыт в `appearance-ring-v3`, `appearance-stage-v3`, `shell-v3`, `motion-v3`, Мафии. Плюс настройка «Спокойный режим» `pv_no_fx` (`body.no-fx`).
- **Размер.** Образы: ~989 КБ CSS (173 КБ gzip). Сцены 7 файлов `skin-scene-*` ≈ 830 КБ, 211 картинок. JS одним файлом ~1.15 МБ (343 КБ gzip). `index.html` грузит 55 `<link rel=stylesheet>`.
  **С S06 сцены загружаются по требованию** через `_scArt`/`_scene_art`, по буквенным CSS; образ по умолчанию их не скачивает. Числа веса выше — опись на 27.10, не холодная загрузка текущего приложения.
- **Кэш.** `?v=<хэш всего пакета>` → `Cache-Control: immutable, 1 год`, GZip (`R/FastAPI/main.py:309-325`). **С S06** каждый файл имеет собственный хэш и ETag/304; выпуск больше не заставляет заново скачивать весь набор CSS/JS.
- **Шрифты.** Onest и Sora с Google Fonts (`S/index.html:21-23`). В карточке чата шрифт локальный (`R/bot/chat/assets/fonts/`).
- **Telegram-карточка.** ≤0.9 с на картинку, декор кэшируется на пару образ+тир. SSS-видео за ≤3 с, иначе уходит картинка.

## Риски

- Любое улучшение образов упрётся в бюджеты: нельзя `filter` на предке движущегося, polygon `clip-path`, `mix-blend-mode`. Мерить `--perf --device mid` и сверять попиксельно.
- Рост ассетов: после S06 загружается нужный буквенный файл сцен; добавленная картинка увеличивает вес всей этой группы. В D2 отдельно измерен вес уникальных правил и групп.
- Смена id, цен, обладания образов требует миграционного плана; перерисовка под теми же id безопасна.
- Правило видимости: чужой образ в Mini App виден только при VIP владельца (`appearance_public_v3.py`). Образы в Мафии онлайн охватят только VIP-игроков, если не менять правило.
- Два агента правят общие файлы (`app.css`, `shell-v3.css`, `index.html`, `main.py`) в разных стилях кода.
