# DEEP BUGS BACKLOG — IESA ROOT
> Глубокий аудит кодовой базы. Генерирован: 2026-05-06.
> **Не исправлять вручную** — этот файл является очередью для последовательного выполнения.
> Формат: `[ ]` — не сделано, `[x]` — выполнено.

---

## БЛОК 1: ЯДРО И ПОЛЬЗОВАТЕЛИ (`core/`, `users/`)

### 🔴 КРИТИЧЕСКИЕ

- [x] **B1-01** `users/signals_partner.py:64–75` — **Инвертированная логика сигнала**: при добавлении пользователя в группу Partners сигнал сначала создаёт Partner-профиль (строки 47–51), а затем УДАЛЯЕТ его и сбрасывает `is_partner=False` (строки 64–75). Результат: пользователь добавляется в группу, но доступа не получает. **Исправление**: удалить строки 64–75 целиком.

- [x] **B1-02** `users/views_verification.py:397–405` — **Race condition при инкременте `failed_pin_attempts`**: два параллельных запроса читают одно значение и оба инкрементируют → счётчик блокировки не достигает максимума корректно. **Исправление**: заменить на `User.objects.filter(pk=member.pk).update(failed_pin_attempts=F('failed_pin_attempts') + 1)`, затем `refresh_from_db()`.

- [x] **B1-03** `users/views_verification.py:356–360` — **Отсутствие `select_for_update` при сбросе счётчика PIN**: два одновременных успешных ввода могут перезаписать друг друга. **Исправление**: обернуть в `with transaction.atomic(): member = User.objects.select_for_update().get(pk=member.pk)`.

- [x] **B1-04** `users/views_verification.py:348–380` — **Отсутствие транзакции при создании Visit + уведомлении**: если уведомление падает после `visit.save()`, Visit сохранён но пользователь не оповещён. **Исправление**: Visit сохранять в `transaction.atomic()`, уведомление — снаружи блока с `try/except + logger`.

### 🟠 ВЫСОКИЙ ПРИОРИТЕТ

- [x] **B1-05** `users/cleverreach_client.py:92–125`, `users/email_service.py:196–217` — **Синхронные HTTP-запросы (timeout=15–30с) в request/response цикле**: при медленном CleverReach весь Django-воркер заморожен. **Исправление**: вынести `send_visit_confirmed` и аналогичные функции в Celery-задачи.

- [x] **B1-06** `users/signals.py:10–27` — **Bare `except: pass` в сигнале генерации QR**: ошибки при генерации QR-кода (например, недоступен MEDIA_ROOT) скрываются, пользователь создаётся без QR без алерта. **Исправление**: `except Exception as exc: logger.error(...)`, убрать `pass`.

- [x] **B1-07** `users/admin.py:240–273` — **Двойной `except: pass` при регенерации QR в адмике**: ошибки удаления старого файла и установки S3 ACL молча глотаются. **Исправление**: логировать + показывать `messages.warning(request, ...)`.

- [x] **B1-08** `users/views_verification.py:58–77` — **Двойной DB-запрос в `is_partner()` helper**: при каждом `@partner_required` вызове выполняется `bool(user.is_partner)` + `Partner.objects.filter(user=user).exists()` + `User.objects.filter(pk=...).update(...)`. **Исправление**: кэшировать результат на экземпляре `user._is_partner_cached`.

- [x] **B1-09** `users/views_verification.py:721–726` — **`asyncio.run()` в синхронной Django view**: блокирует поток на время выполнения `init_bot_commands()`. **Исправление**: запускать через `loop = asyncio.new_event_loop(); loop.run_until_complete(...); loop.close()` в отдельном потоке или через фоновую задачу.

### 🟡 СРЕДНИЙ ПРИОРИТЕТ

- [x] **B1-10** `core/views.py:93–132` — **Кэш без инвалидации**: `CoreProduct`, `President`, `Partner`, `Member` кэшируются на 1 час без сигналов инвалидации. После правки в адмике пользователи видят старые данные. **Исправление**: добавить `post_save`/`post_delete` сигналы с `cache.delete('idx:...')` в `core/signals.py`.

- [x] **B1-11** `users/views.py:282–301` — **QR-кэш без инвалидации при смене `permanent_id`**: если `permanent_id` переприсвоен другому пользователю, старый кэш отдаёт чужой QR 1 час. **Исправление**: в `User.save()` при изменении `permanent_id` вызывать `cache.delete(f'qr_image_{old.permanent_id}')`.

- [x] **B1-12** `users/models.py:418–427` — **Отсутствие DB CheckConstraint на `Visit.status`**: можно создать Visit с произвольным статусом. **Исправление**: добавить `CheckConstraint(check=Q(status__in=['ACTIVE','EDITED','CANCELLED']), name='valid_visit_status')`.

- [x] **B1-13** `users/models.py` — **Отсутствие валидатора размера аватара**: пользователь может загрузить 100 MB PNG. **Исправление**: добавить `validators=[validate_avatar_size]` (лимит 5 MB) на поле `avatar`.

- [x] **B1-14** `users/views_verification.py:244–255` — **Хрупкий парсинг UUID**: множественные вложенные `try/except` для парсинга UUID. **Исправление**: вынести в `try_parse_uuid(s)` утилиту.

- [x] **B1-15** `users/views_verification.py:633–656` — **`service_breakdown` без LIMIT**: агрегация по service_type без `[:20]` может вернуть тысячи строк. **Исправление**: добавить `[:20]`.

- [x] **B1-16** `users/models.py:462–467` — **Отсутствует составной индекс на `VisitAudit`**: часто запрашивается `visit.audits.all()`. **Исправление**: добавить `Index(fields=['visit', '-changed_at'], name='audit_visit_time_idx')`.

- [x] **B1-17** `core/views.py:103–132` — **Кэширование `list(QuerySet[:N])` вместо правильного подхода**: `list()` форсирует материализацию. Для маленьких `[:4]` некритично, но плохая практика при масштабировании. **Исправление**: хранить lazy QuerySet или документировать ограничение.

---

## БЛОК 2: КОНТЕНТ И БИЗНЕС-ЛОГИКА (`blog/`, `gallery/`, `products/`, `notifications/`)

### 🔴 КРИТИЧЕСКИЕ

- [x] **B2-01** `blog/views/comments.py:52` — **Опечатка в `redirect`: `'blog:blog:post_detail'`**: двойной namespace вызывает `NoReverseMatch` при non-HTMX запросах. **Исправление**: заменить на `'blog:post_detail'`.

- [x] **B2-02** `blog/models.py:136–139` — **Некорректная `unique_together` на `PostView`**: `unique_together = (('post', 'user'), ('post', 'ip_address'))` создаёт ДВА отдельных уникальных ограничения, а не логическое «либо-либо». Анонимный пользователь с тем же IP что и другой зарегистрированный пользователь сломает запись view. **Исправление**: заменить на `UniqueConstraint` с `condition=Q(user__isnull=False)` и `condition=Q(ip_address__isnull=False)` раздельно.

### 🟠 ВЫСОКИЙ ПРИОРИТЕТ

- [x] **B2-03** `blog/admin.py:114–156` — **N+1 в `PostAdmin.engagement_details()`**: `obj.likes.count()` + `obj.comments.count()` для каждого поста в списке (25 постов = 50 extra queries). **Исправление**: переопределить `get_queryset()` с `annotate(likes_count=Count('likes'), comments_count=Count('comments'))`.

- [x] **B2-04** `blog/admin.py:256` — **N+1 в `EventAdmin.participants_count()`**: `obj.registrations.filter(status='confirmed').count()` для каждого события. **Исправление**: аннотировать в `get_queryset()`.

- [x] **B2-05** `blog/signals.py:6–40` — **Отсутствие `try/except` в сигналах Like/Comment**: исключение в `author.update_statistics()` разбивает транзакцию сохранения лайка/комментария. **Исправление**: обернуть в `try/except Exception as e: logger.error(...)`.

- [x] **B2-06** `blog/views/events.py:139` — **Race condition в регистрации на событие**: два параллельных `get_or_create` без `select_for_update` → IntegrityError вместо graceful handling. **Исправление**: обернуть в `transaction.atomic()` + `try/except IntegrityError`.

- [x] **B2-07** `notifications/` — **Отсутствие дедупликации уведомлений**: 10 лайков от одного пользователя → 10 идентичных уведомлений. **Исправление**: в `notify_new_like()` проверять существование `Notification` за последний час с теми же `recipient`, `sender`, `notification_type`.

- [x] **B2-08** `notifications/` — **Нет механизма очистки старых уведомлений**: таблица растёт бесконечно. **Исправление**: создать `management/commands/cleanup_notifications.py` + crontab `0 2 * * *`.

- [x] **B2-09** `blog/views/posts.py:19` (infinite scroll) — **Отсутствие защиты от DDoS через infinite scroll**: страницы 1000+ возможны. **Исправление**: ограничить `page = min(page, 100)` или перейти на cursor-based pagination.

### 🟡 СРЕДНИЙ ПРИОРИТЕТ

- [x] **B2-10** `blog/views/comments.py:66–89` — **Отсутствие валидации глубины вложенности**: `reply` на `reply` разрешён, хотя шаблон этого не поддерживает. **Исправление**: в `comment_create` проверить `if parent.parent is not None: return HttpResponse(status=400)`.

- [x] **B2-11** `blog/models.py:31`, `blog/models.py:161` — **Поле `status` без `db_index`**: часто используется в `filter(status='published')`. **Исправление**: добавить `db_index=True` на `Post.status` и `Event.status`, добавить составной `Index(fields=['status', '-created_at'])`.

- [x] **B2-12** `blog/views/search.py:23–38` — **`post_search()` не нормализует запрос**: `global_search()` использует `normalize_search_query()`, а `post_search()` — нет. Несогласованные результаты. **Исправление**: добавить `normalized = normalize_search_query(query)` в `post_search`.

- [x] **B2-13** `blog/views/subscriptions.py:52–61` — **HTMX polling `follower_count` каждые N секунд без кэш-заголовков**: клиент игнорирует `cache.set(..., 60)` если нет `Cache-Control` в ответе. **Исправление**: добавить `response['Cache-Control'] = 'public, max-age=300'` и увеличить polling interval в шаблоне до `every 5m`.

- [x] **B2-14** `notifications/views.py:20–40` — **Неправильная пагинация**: `notifications = Notification.objects.filter(...).order_by(...)` материализует весь QuerySet до применения `Paginator`. **Исправление**: передать QuerySet напрямую в `Paginator(queryset, 20)` без промежуточного присваивания.

- [x] **B2-15** `blog/admin.py:40–46` — **`AuthorFilter.lookups()` без `try/except`**: если таблица Post недоступна при миграции, админка ломается. **Исправление**: обернуть в `try/except Exception: return []`.

- [x] **B2-16** `blog/models.py:45–69` — **`get_recommended_posts()`: двойной `N+1` pattern**: `same_author.count()` + перечисление queryset вызывает 2 SQL запроса. Уже частично исправлен ранее (`same_author_count`), но `list(same_author) + list(other_posts)` можно объединить в один запрос через `UNION`. **Исправление**: использовать `.union()` или единый annotated queryset.

- [x] **B2-17** `blog/admin.py:51–69` — **Отсутствие аудит-логирования в admin actions**: `publish_posts`, `reject_posts` не логируют, кто и когда выполнил действие. **Исправление**: добавить `logger.info(f"Admin {request.user.username} published posts: {list(queryset.values_list('id', flat=True))}")`.

- [x] **B2-18** `blog/views/search.py:66–109` — **Глобальный поиск без DB-таймаута**: при большой БД и коротком запросе (напр. "а") может тормозить секунды. **Исправление**: добавить `SET LOCAL statement_timeout = '3s'` через `connection.cursor()` или ограничить минимальную длину запроса до 3 символов.

---

## БЛОК 3: TELEGRAM-БОТ (`users/telegram/`)

### 🔴 КРИТИЧЕСКИЕ

- [x] **B3-01** `users/apps.py:26` — **`asyncio.run()` при потенциально уже работающем event loop (ASGI)**: при деплое на Daphne/Uvicorn вызов `asyncio.run()` внутри `ready()` падает с `RuntimeError`. **Исправление**: заменить на `try: loop = asyncio.get_running_loop(); loop.create_task(...) except RuntimeError: asyncio.run(...)`.

- [x] **B3-02** `users/views_verification.py:959–966` — **Webhook всегда возвращает 200 OK, даже при ошибке обработки**: Telegram считает update доставленным и не переотправит его. **Исправление**: при `except Exception` возвращать `JsonResponse({"ok": False}, status=500)`.

- [x] **B3-03** `users/views_verification.py:922–924` — **Webhook без rate limiting**: `@csrf_exempt` без `@ratelimit` — возможен DoS фейковыми update'ами. **Исправление**: добавить `@ratelimit(key='ip', rate='200/m', block=True)`.

### 🟠 ВЫСОКИЙ ПРИОРИТЕТ

- [x] **B3-04** `users/telegram/client.py:22–25` — **`asyncio.sleep(retry_after)` без максимума**: Telegram может вернуть `Retry-After: 3600`, бот зависнет на час. **Исправление**: `retry_after = min(int(resp.headers.get("Retry-After", 5)), 30)`.

- [x] **B3-05** `users/telegram/client.py:176–208` — **Синхронный `send_message` без retry**: async версия использует `_post_with_retry`, sync — нет. Синхронные уведомления из Django signals теряются при временном сбое. **Исправление**: реализовать retry-цикл в sync версии аналогично async.

- [x] **B3-06** `users/telegram/notify.py` — **Синхронный код (ORM запросы) вызывается из async контекста**: если `notify_visit_confirmed()` будет вызван из async handler, ORM-запросы заблокируют event loop. **Исправление**: создать `notify_visit_confirmed_async()` с `sync_to_async` обёрткой.

- [x] **B3-07** `users/telegram/client.py:34, 162, 201, 226, 241` — **`resp.json()` без обработки `JSONDecodeError`**: невалидный JSON от Telegram API (редкое, но возможное) ломает retry-логику. **Исправление**: обернуть в `try/except (json.JSONDecodeError, ValueError)` с retry.

- [x] **B3-08** `users/telegram/handlers.py:287–288` — **`except Exception: pass` ловит `asyncio.CancelledError`**: при graceful shutdown бот зависает вместо корректного завершения. **Исправление**: `except asyncio.CancelledError: raise` + `except (DatabaseError, OperationalError) as exc: logger.warning(...)`.

### 🟡 СРЕДНИЙ ПРИОРИТЕТ

- [x] **B3-09** `users/telegram/client.py:15–41` — **Новый `httpx.AsyncClient` на каждый запрос**: при высокой нагрузке это N открытых TCP-соединений. **Исправление**: создать глобальный `_client_pool = httpx.AsyncClient(limits=httpx.Limits(max_connections=10))` на уровне модуля с lifecycle-управлением.

- [x] **B3-10** `users/telegram/client.py:46–76` vs `176–208` — **Дублирование кода**: async и sync версии `send_message` почти идентичны, но с разной retry-логикой. **Исправление**: sync версия должна быть тонкой обёрткой через `async_to_sync(send_message_async)(...)`.

- [x] **B3-11** `users/telegram/dispatcher.py:43–52` — **Нет fallback-handler для неизвестных callback'ов**: пользователь получает generic "неизвестное действие" вместо контекстной подсказки. **Исправление**: добавить `_handle_unknown_callback` с инструкцией `/help`.

- [x] **B3-12** `users/telegram/handlers.py:45–46, 104, 143` — **`sync_to_async(lambda: ...)` без timeout**: медленная БД → бот зависает на неопределённое время. **Исправление**: обернуть в `asyncio.wait_for(..., timeout=3.0)` + fallback.

- [x] **B3-13** `users/views_verification.py:937–940` — **Пустой payload не валидируется**: `_json.loads(request.body or '{}')` пропустит пустой `{}` в `process_incoming_update({})` без ошибки. **Исправление**: добавить `if "update_id" not in payload: return JsonResponse({"ok": False}, status=400)`.

- [x] **B3-14** `users/views_verification.py:959–966` — **`asyncio.CancelledError` не пробрасывается из webhook**: при graceful shutdown `CancelledError` ловится как `Exception` и логируется, но не пробрасывается. **Исправление**: добавить `except asyncio.CancelledError: raise` первым.

---

## БЛОК 4: ФРОНТЕНД (`static/`, `templates/`)

### 🔴 КРИТИЧЕСКИЕ

- [x] **B4-01** `static/js/partner-card-effects.js:15–24` — **`addTiltEffect`/`addRippleEffect` без проверки повторной инициализации**: при каждом `htmx:afterSettle` (вызов `runAll()`) на уже инициализированные карточки добавляются новые listeners → экспоненциальный рост. **Исправление**: проверять `if (card.dataset.tiltInit) return; card.dataset.tiltInit = '1';` перед добавлением.

- [x] **B4-02** `static/js/page-effects.js:232–243` — **Tilt/mousemove listeners без cleanup при HTMX swap**: после каждого swap старые listeners остаются на удалённых DOM-элементах (detached DOM leak). **Исправление**: добавить `document.addEventListener('htmx:beforeSwap', cleanupListeners)` с сохранением ссылок через WeakMap.

- [x] **B4-03** `static/js/performance-optimization.js:96–109` — **`DOMCache` кэширует ссылки на элементы без инвалидации при HTMX swap**: после swap кэш содержит detached DOM-узлы. **Исправление**: добавить `document.addEventListener('htmx:afterSwap', () => DOMCache.elements = {})`.

- [x] **B4-04** CSS — **`@keyframes fadeInUp` определена в 4 разных файлах** (`components.css:70`, `pages.css:970`, `homepage.css:1041`, `responsive.css:1313`) **с разными значениями** (20px, 24px, 30px): браузер использует последнюю по порядку загрузки, поведение непредсказуемо. **Исправление**: оставить одно определение в `animations.css`, удалить из остальных.

- [x] **B4-05** CSS — **Аналогично `@keyframes` — дублирование `fadeIn` (3 файла)**, `slideInUp` (2), `pulse` (3 с разными значениями), `spin` (2), `skeleton-loading` (3). **Исправление**: консолидировать все в `animations.css`.

- [x] **B4-06** `templates/core/htmx/partner_modal.html:62–238` — **238 строк `<style>` внутри HTMX-партиала**: CSS перезагружается при каждом открытии модала, не кэшируется браузером. **Исправление**: вынести в `static/css/partner-modal.css`, подключить в `base.html`.

### 🟠 ВЫСОКИЙ ПРИОРИТЕТ

- [x] **B4-07** `static/js/mobile-optimization.js:96, 108` — **Два отдельных `window.scroll` listeners**: `closeDropdown` + `bottomNav shadow`. Плюс нет debounce на shadow-обновление (вызов `style.boxShadow` 60+ раз/сек). **Исправление**: объединить в один RAF-throttled listener.

- [x] **B4-08** `static/js/community-ui.js:32` — **Countdown-таймеры без надёжного cleanup**: `document.contains(el)` не перехватывает HTMX swap корректно при batch-замене. **Исправление**: использовать `htmx:beforeSwap` event с хранением timerId в WeakMap по элементу.

- [x] **B4-09** `static/js/sections-interactions.js`, `static/js/partner-card-effects.js` — **`DOMContentLoaded` + `htmx:afterSettle` без проверки повторной инициализации**: каждый HTMX swap вызывает `run()` заново на всех элементах страницы, а не только на новых. **Исправление**: добавить `data-initialized` атрибут как guard.

- [x] **B4-10** `static/js/premium-sections-interactions.js:32–39` — **Mousemove listener вычисляет `getBoundingClientRect()` и меняет `style.transform` без RAF**: 60+ DOM reflow/repaint в секунду при hover. **Исправление**: обернуть в `requestAnimationFrame` с `ticking` флагом.

- [x] **B4-11** `templates/partials/admin_appeal_form.html:8–77` — **12+ дублирующихся inline `style` атрибутов** с идентичными RGBA-значениями (~2 KB лишнего HTML). **Исправление**: создать CSS классы `.appeal-form-field`, `.appeal-form-label`, `.appeal-form-btn` в `components.css`.

- [x] **B4-12** `templates/blog/htmx/post_search_results.html:2–16` — **`<style>` блок в HTMX-партиале**: загружается при каждом нажатии клавиши в поиске. **Исправление**: вынести в `static/css/search.css`.

- [x] **B4-13** `templates/base.html:436–442` — **`htmx:responseError` обрабатывает только 403**: статусы 500, 503, сетевые ошибки — без feedback для пользователя. **Исправление**: добавить toast-уведомление для 500 (`"Ошибка сервера, попробуйте позже"`) и retry-кнопку для 503.

- [x] **B4-14** `static/js/page-effects.js:211–221` — **`PerformanceObserver` никогда не disconnect'сится**: накапливается при каждом HTMX swap. **Исправление**: добавить `document.addEventListener('htmx:beforeSwap', () => observer.disconnect())`.

### 🟡 СРЕДНИЙ ПРИОРИТЕТ

- [x] **B4-15** `static/js/header-hide-on-scroll.js:37–48` — **`setTimeout` для scroll вместо `requestAnimationFrame`**: может вызвать visual jank при быстром скролле. **Исправление**: заменить на RAF + `ticking` флаг.

- [x] **B4-16** `templates/base.html:257–264` — **Notifications dropdown: `hx-swap="innerHTML"` теряет scroll-позицию** при каждом открытии. **Исправление**: использовать `hx-swap="innerHTML show:no-scroll"` или сохранять позицию через JS перед swap.

- [x] **B4-17** `static/js/community-ui.js:21` — **`innerHTML` с хардкодом HTML-строки**: не критичный XSS (нет user-input), но плохая практика для будущих изменений. **Исправление**: использовать `document.createElement` + `textContent`.

- [x] **B4-18** `static/css/pages.css` — **Фиксированные `px`-отступы без media queries в ряде компонентов** (например, `.profile-edit-card { padding: 30px }`). На экранах <360px занимает 40%+ ширины. **Исправление**: добавить `@media (max-width: 575px) { padding: 12px }` в `responsive.css`.

- [x] **B4-19** `templates/blog/htmx/post_search_results.html:41, 44, 69, 117, 168` — **Повторяющиеся `style="color:#fff;"` вместо CSS-классов**. **Исправление**: заменить на `.search-result-title` класс в CSS.

- [x] **B4-20** `templates/base.html:229–237` — **Отсутствует `hx-indicator` атрибут на search input**: спиннер существует в DOM, но не привязан через `hx-indicator="#search-spinner"`. **Исправление**: добавить атрибут на `<input>`.

- [x] **B4-21** `static/css/components.css` — **15+ вариантов кнопок с одинаковыми `:hover/:active/:focus` блоками**: CSSOM bloat, 60+ правил вместо 15. **Исправление**: перевести на CSS-переменные уровня компонента `--btn-bg`, `--btn-hover-bg`.

- [x] **B4-22** `static/js/performance-optimization.js:8–10` — **`STATIC_BASE` и `_ownScript` на уровне модуля без IIFE**: загрязнение глобального namespace. **Исправление**: обернуть в `(function() { ... })()`.

---

## СВОДНАЯ ТАБЛИЦА ПРИОРИТЕТОВ

| Код | Файл | Критичность | Тип | Статус |
|-----|------|-------------|-----|--------|
| B1-01 | users/signals_partner.py | 🔴 КРИТ | Logic Bug | [x] |
| B1-02 | users/views_verification.py | 🔴 КРИТ | Race Condition | [x] |
| B1-03 | users/views_verification.py | 🔴 КРИТ | Race Condition | [x] |
| B1-04 | users/views_verification.py | 🔴 КРИТ | Consistency | [x] |
| B2-01 | blog/views/comments.py | 🔴 КРИТ | Bug (NoReverseMatch) | [ ] |
| B2-02 | blog/models.py | 🔴 КРИТ | Data Integrity | [ ] |
| B3-01 | users/apps.py | 🔴 КРИТ | RuntimeError | [x] |
| B3-02 | users/views_verification.py | 🔴 КРИТ | Idempotency | [x] |
| B3-03 | users/views_verification.py | 🔴 КРИТ | DoS | [x] |
| B4-01 | static/js/partner-card-effects.js | 🔴 КРИТ | Memory Leak | [ ] |
| B4-04 | static/css (multiple) | 🔴 КРИТ | CSS Conflict | [ ] |
| B1-05 | users/cleverreach_client.py | 🟠 ВЫСОК | Blocking HTTP | [x] |
| B1-06 | users/signals.py | 🟠 ВЫСОК | Silent Error | [x] |
| B2-03 | blog/admin.py | 🟠 ВЫСОК | N+1 | [x] |
| B2-05 | blog/signals.py | 🟠 ВЫСОК | Silent Error | [x] |
| B2-06 | blog/views/events.py | 🟠 ВЫСОК | Race Condition | [x] |
| B2-07 | notifications/ | 🟠 ВЫСОК | Spam | [x] |
| B3-04 | users/telegram/client.py | 🟠 ВЫСОК | DoS/Hang | [x] |
| B3-05 | users/telegram/client.py | 🟠 ВЫСОК | Reliability | [x] |
| B4-02 | static/js/page-effects.js | 🟠 ВЫСОК | Memory Leak | [ ] |
| B4-03 | static/js/performance-optimization.js | 🟠 ВЫСОК | Stale Cache | [ ] |
| B4-06 | templates/core/htmx/partner_modal.html | 🟠 ВЫСОК | Performance | [ ] |

> **Итого:** 9 критических, 13 высоких, 20 средних = **42 задачи**

---

## ПОРЯДОК ВЫПОЛНЕНИЯ (рекомендуемый)

### Спринт 1 — Критические баги (ломают функциональность прямо сейчас)
1. B1-01 — Исправить инвертированную логику `signals_partner.py`
2. B2-01 — Исправить опечатку `'blog:blog:post_detail'`
3. B3-01 — Исправить `asyncio.run()` в `apps.py`
4. B2-02 — Исправить `unique_together` на `PostView`

### Спринт 2 — Race conditions и транзакции
5. B1-02, B1-03 — Race conditions PIN counter
6. B1-04 — Transaction atomicity Visit + notification
7. B2-06 — Race condition event registration
8. B3-02, B3-03 — Webhook security + idempotency

### Спринт 3 — Производительность и надёжность
9. B1-05 — Вынести email в background tasks
10. B2-03, B2-04 — N+1 в admin
11. B2-07, B2-08 — Дедупликация и очистка уведомлений
12. B3-04, B3-05 — Retry логика в Telegram client

### Спринт 4 — Фронтенд (Memory leaks + CSS)
13. B4-01 — Guard повторной инициализации listeners
14. B4-02, B4-03 — HTMX cleanup для listeners и DOMCache
15. B4-04, B4-05 — Консолидация дублирующихся CSS анимаций
16. B4-06, B4-11, B4-12 — Вынос `<style>` из шаблонов

### Спринт 5 — Качество кода
17. Всё оставшееся из средних приоритетов
