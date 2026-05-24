# i18n Grammar Audit Plan — IESA Sport (2026-05-24)

> 66 шаблонов · 1278 `{% trans %}` · 23 `{% blocktrans %}` · 3 языка (uk/fr/de)
> Цель: 0 грамматических, падежных, согласовательных ошибок на всех страницах.

---

## ✅ ИСПРАВЛЕНО в этой сессии (2026-05-24)

### Опечатки и грамматика (uk/fr/de)
- [x] **UK** `Відкрйте` → `Відкрийте` (опечатка, msgid `Discover a world of`)
- [x] **UK** `Відданий керівництво` → `Віддане керівництво` (рассогласование рода прилагательного, msgid `Dedicated`)
- [x] **UK** `співпрацюємо з` → `співпрацюємо` (повтор предлога "з... з", msgid `collaborate with`)
- [x] **UK** `Приєднатися до нашої наступної зустрічі` → `Приєднайтеся до наших наступних зустрічей` (число+форма глагола, msgid `Join our next` + `gatherings`)
- [x] **UK** `Прив'язати акаунт … або надішліть` → `Прив'яжіть акаунт … або надішліть` (согласование наклонений)
- [x] **FR** `Rejoignez notre prochain rencontres` → `Rejoignez nos prochaines rencontres` (род+число)
- [x] **DE** `an unserer nächsten Treffen` → `an unseren nächsten Treffen` (число)
- [x] **DE** `Warum beitreten IESA?` → `Warum sollten Sie IESA beitreten?` (порядок слов)

### Архитектурные правки (split-trans → blocktrans)
- [x] `core/index.html:783` `The people behind / our mission` → blocktrans
  - UK: `Люди, що стоять за нашою місією` (творительный падеж)
  - FR: `Les personnes derrière notre mission`
  - DE: `Die Menschen hinter unserer Mission`
- [x] `core/index.html:931` `Why join / IESA?` → blocktrans
  - UK: `Чому варто приєднатися до IESA?`
  - FR: `Pourquoi rejoindre l'IESA ?`
  - DE: `Warum sollten Sie IESA beitreten?`

### Инструменты
- [x] `scripts/spellcheck_translations.py` — pyspellchecker для FR/DE + UK русизмы
- [x] `scripts/find_split_trans.py` — поиск split-trans конструкций
- [x] `scripts/audit_translations.py` — case-mismatch, дубли, HTML/placeholder
- [x] `scripts/fix_case_duplicates.py` + `scripts/fix_known_translations.py`

---

## 🔴 ПРИОРИТЕТ 1 — критичные страницы (видны всем)

| Шаблон | trans | Что проверить |
|---|---|---|
| - [ ] `core/index.html` | 117 | главная — все блоки секций, hero, CTA |
| - [ ] `templates/base.html` | 56 | navbar, footer, мета-данные — видно везде |
| - [ ] `templates/partials/_navbar.html` | 32 | главная навигация, dropdowns |
| - [ ] `users/login.html` | 20 | форма входа, ошибки валидации |
| - [ ] `users/register.html` | 45 | форма регистрации, label'ы полей |
| - [ ] `users/how_it_works.html` | 39 | онбординг публичный |
| - [ ] `blog/post_list.html` | 36 | публичный блог — карточки постов |
| - [ ] `blog/post_detail.html` | 13 | детальная страница поста |
| - [ ] `blog/event_list.html` | 21 | список мероприятий |
| - [ ] `blog/event_detail.html` | 17 | детальная мероприятия |

## 🟡 ПРИОРИТЕТ 2 — личный кабинет

| Шаблон | trans | Что проверить |
|---|---|---|
| - [ ] `users/profile.html` | 113 | основная страница ЛК — самая большая |
| - [ ] `users/profile_edit.html` | 42 | форма редактирования профиля |
| - [ ] `users/profile_public.html` | 27 | публичный профиль |
| - [ ] `users/profile_deactivate_confirm.html` | 20 | подтверждение деактивации |
| - [ ] `users/partials/acr_form.html` | 78 | Account Change Request форма |
| - [ ] `users/activity_levels_info.html` | 42 | страница активностей и баллов |
| - [ ] `users/connect_telegram_code.html` | 23 | подключение Telegram |
| - [ ] `users/search_results.html` | 16 | поиск пользователей |
| - [ ] `users/member_scan_card.html` | ? | карта члена (для скана) |

## 🟡 ПРИОРИТЕТ 3 — партнёрский кабинет

| Шаблон | trans | Что проверить |
|---|---|---|
| - [ ] `users/partner_dashboard.html` | 31 | главная партнёра |
| - [ ] `users/partner_calendar.html` | 41 | календарь визитов |
| - [ ] `users/partner_analytics.html` | 29 | аналитика партнёра |
| - [ ] `users/partner_member_visits.html` | 22 | история визитов |
| - [ ] `users/partner_access_denied.html` | 18 | страница отказа доступа |
| - [ ] `users/partner_base.html` | 11 | базовый шаблон партнёра |
| - [ ] `users/log_visit.html` | 14 | форма логирования визита |
| - [ ] `users/insurance_agent.html` | 34 | страница страхового агента |

## 🟢 ПРИОРИТЕТ 4 — остальное

| Шаблон | trans | Что проверить |
|---|---|---|
| - [ ] `blog/post_create.html` | 27 | форма создания поста |
| - [ ] `blog/htmx/comments_section.html` | 12 | комментарии (HTMX) |
| - [ ] `blog/partials/post_list_items.html` | ? | элементы списка постов |
| - [ ] `blog/partials/event_list_items.html` | 14 | элементы списка событий |
| - [ ] `notifications/notification_list.html` | 22 | список уведомлений |
| - [ ] `gallery/gallery.html` | 16 | галерея |
| - [ ] `products/product_list.html` | 13 | список продуктов |
| - [ ] `core/benefits.html` | 14 | страница преимуществ |
| - [ ] `users/test_telegram.html` | 11 | dev-страница TG |
| - [ ] `templates/admin/accountchangerequest_change_form.html` | 12 | admin форма ACR |

---

## 🔍 Как проверять каждый шаблон

### 1. Открыть страницу в браузере во всех 3 языках
```
?lang=uk  →  ?lang=fr  →  ?lang=de
```

### 2. Прочитать визуально каждое предложение
Искать:
- **Опечатки** (одинарные/двойные буквы пропущены/добавлены)
- **Падежные ошибки** (особенно после предлогов «за», «з», «до», «у», «на»)
- **Согласование рода** прилагательного с существительным
- **Согласование числа** (ед/мн.ч.)
- **Согласование наклонений** (инфинитив vs повелительное)
- **Порядок слов** (особенно в немецком — глагол в конце придаточного)
- **Артикли** во французском/немецком

### 3. Особое внимание — split-trans и переменные
Если в шаблоне есть `{% trans "X" %} <span>{% trans "Y" %}</span>` или
`{% trans "X" %} {{ variable }}` — там часто грамматика ломается.
Решение: переписать на `{% blocktrans %} ... {{ var }} ... {% endblocktrans %}`.

### 4. Запустить автоматические проверки
```bash
cd IESA_ROOT
python scripts/audit_translations.py        # дубли, HTML mismatch
python scripts/spellcheck_translations.py    # орфография
python scripts/find_split_trans.py           # split-trans паттерны
```

### 5. Исправления через polib (Windows-friendly)
```python
import polib
po = polib.pofile('locale/uk/LC_MESSAGES/django.po')
e = po.find('msgid_text')
e.msgstr = 'правильный перевод'
po.save('locale/uk/LC_MESSAGES/django.po')
po.save_as_mofile('locale/uk/LC_MESSAGES/django.mo')
```

---

## 📋 Чеклист на следующие сессии

**Сессия 1 (этот документ)**: создан план + исправлены 11 ошибок ✅

**Сессия 2 (PRIORITY 1 — публичные страницы)**:
- [ ] `core/index.html` — пройти все 9 секций × 3 языка = 27 проходов
- [ ] `templates/base.html` + `_navbar.html` — навбар, футер
- [ ] `login.html` + `register.html` + `how_it_works.html`

**Сессия 3 (PRIORITY 1 — блог)**:
- [ ] `blog/post_list.html` + `blog/post_detail.html`
- [ ] `blog/event_list.html` + `blog/event_detail.html`

**Сессия 4 (PRIORITY 2 — личный кабинет)**:
- [ ] `users/profile.html` (113 trans — большая!)
- [ ] `users/profile_edit.html` + `profile_public.html`
- [ ] `users/partials/acr_form.html` (78 trans)

**Сессия 5 (PRIORITY 3 — партнёр)**:
- [ ] `partner_dashboard.html` + `partner_calendar.html`
- [ ] `partner_analytics.html` + `partner_member_visits.html`

**Сессия 6 (PRIORITY 4 — остальное)**:
- [ ] Все остальные шаблоны
- [ ] Финальный прогон автоматических проверок
- [ ] Скриншот-тест на 3 устройствах × 3 языка

---

## ⚙️ Известные ограничения автоматических проверок

1. **Pyspellchecker не знает** украинский — для UK работают только кастомные правила в `spellcheck_translations.py`
2. **Compound-слова в немецком** длиннее 10 символов автоматически пропускаются (слишком много false positives)
3. **Грамматические правила** (падежи, спряжения, согласование) автоматически не проверяются — нужна ручная вычитка носителем языка
4. **Split-trans** — скрипт находит, но решение требует переписывания шаблона

## 💡 Рекомендации

1. **Привлечь носителей языка** для финальной вычитки uk/fr/de — особенно французский (артикли, согласование рода) и немецкий (падежи, порядок слов в придаточных).
2. **После каждой правки** прогонять `audit_translations.py` чтобы не появились новые дубли.
3. **Не вводить новые `{% trans %}` с пунктуацией на конце**, склеенной с другим trans — это ломает грамматику в большинстве языков.
