# Валидация и жёсткая самокритика проекта экономики

**Дата проверки:** 2026-08-15
**Post-revision verdict:** `PAPER DESIGN READY FOR OWNER REVIEW`.
**Implementation/cutover verdict:** `NO-GO`, пока владелец не утвердил решения, не собраны machine-readable manifests и не пройдены runtime/release gates.
**Что уже можно использовать:** каноническую экономическую конституцию, 40 событий, конкретные settlement-правила и production-снимок как ориентир масштаба.
**Что пока нельзя утверждать:** что provisional-цены подтверждены поведением людей, runtime физически соблюдает канон, миграционный manifest охватывает 100% строк, а repeatability доказана 28-дневным пилотом.

Это не косметическая рецензия. Ниже перечислены места, где текущий проект может потерять права игроков, создать двойную выдачу, сохранить legacy-faucet, сломать сезонный бюджет или лишь **изобразить** десятилетнюю устойчивость.

## Post-revision resolution ledger

Исходная критика C1–C19 ниже сохранена как audit trail. Статус `DESIGN-RESOLVED` означает: в `GAME_ECONOMY_MASTER_SPEC.md` уже записано однозначное каноническое правило. Это **не** означает, что правило реализовано, протестировано или одобрено владельцем.

| ID | Статус после ревизии | Каноническое решение | Что ещё обязательно |
|---|---|---|---|
| C1 | `DESIGN-RESOLVED` | один terminal action → одна atomic Mora delta/`operation_id`; overlays не печатают Мору; Reserve lock `(user_id, period_id)` | machine-readable source registry, concurrency/fault tests |
| C2 | `DESIGN-RESOLVED` | Алмазы `6 free season + 2 mastery + 2 event + 2 new-account`, все внутри hard cap 12/season | owner approval provisional budget, manifest validator, live calibration |
| C3 | `DESIGN-RESOLVED` | походы исправлены на `50/145/285` Моры за `2/6/12h`, pet channel ≤600 | pilot по выбору длительности и net efficiency |
| C4 | `DESIGN-RESOLVED` | meaningful loss: первая развилка, ≥40% обязательных сигналов correct, no abort-pattern/quarantine; после 3 поражений exact seed reward=0 | server predicate и adversarial replay tests |
| C5 | `DESIGN-RESOLVED` | при нулевом denominator accuracy=`—`; decision accuracy и input purity — разные метрики | server recompute/UI contract tests |
| C6 | `DESIGN-RESOLVED` | `constitution-v2` удалил неподтверждённые 1 000 Моры; учитывает только Chronicle cap 3 000, onboarding 300 вынесен отдельно | catalog-driven model после owner approval |
| C7 | `DESIGN-RESOLVED` | каждый paid consumable/buff получает per-row `consume/refund/service-cosmetic convert/archive`; old power не действует в новом core; referral premium commission закрывается | SKU/item manifest, dependency graph=0, scheduler/static writer evidence |
| C8 | `DESIGN-RESOLVED` | Alliance доступен сразу; `active clan`=≥4 eligible ×≥2 meaningful days ×4 weeks; projects≥3 clans; competition≥8 clans с ≥5 eligible; functional solo-equivalence | owner approval thresholds и telemetry gates |
| C9 | `DESIGN-RESOLVED` | active lot отменяется: item продавцу, bid500 и подтверждённый listing fee назад, commission=0; все reserve/duel/bid/item holds обязаны сойтись | final freeze reconciliation; любой ambiguous hold блокирует cutover |
| C10 | `DESIGN-RESOLVED` | token 1:1 → bound Legacy Archive Reveal; frozen non-premium pool, bulk resolve; после exhaustion каждый остаток → `Legacy Archive Prestige +1`, без dust/Mora/power | точный pool/ownership manifest и UI bulk receipt |
| C11 | `DESIGN-RESOLVED` | deposits закрыты; legacy access сохраняется, withdrawal atomic с уведомлением; split только двумя совпадающими подписями; спор → freeze | escrow row reconciliation и support rehearsal |
| C12 | `DESIGN-RESOLVED` | `T0` + 72h server-side TWAP непосредственно до freeze; неполное/невоспроизводимое окно блокирует cutover, fallback нет; old sell formula с fee 5%; `ROUND_HALF_UP` до 0,01 Моры; appeal 14 дней; book cost только P/L reference | immutable price observations/hash и dry-run всех 6 positions |
| C13 | `DESIGN-RESOLVED` | VIP remaining service term сохраняется; каждый scheduled weekly spin 1:1 → bound `Legacy Archive Reveal`; `ceil(remaining/50d)` → cosmetic-only tracks; old extra slots 1:1 с clamp 0..2 → permanent showcase slots; gameplay power выключается | 100% original SKU/term/scheduled-promises mapping и per-account receipts |
| C14 | `DESIGN-RESOLVED` | Preparations cap 3/вид, 6 total; ranked/Tower/Ghost используют normalized values и пустой external preparation set; Intel off in rated | loadout dependency/fairness tests |
| C15 | `DESIGN-RESOLVED` | первая pet-role выбирается сразу; затем direct choice unopened role на 5-й, 10-й, …, 45-й meaningful gameplay day; все 10 открыты не позднее дня 45 | role usability/balance pilot |
| C16 | `DESIGN-RESOLVED` | рынок закрыт до четырёх недель одновременно: ≥30 buyers, ≥20 sellers, ≥100 arms-length deals/week, related top-2 <25% GMV, top 10% buyers ≤45% GMV, single buyer и single seller каждый ≤10% GMV; только gameplay-crafted decorative whitelist с non-paid provenance | четыре недели реальных данных и wash/provenance checks |
| C17 | `DESIGN-RESOLVED` | до Season 1 готовы Season 1–3 и emergency evergreen; при buffer<2 новый paid season не продаётся | фактически готовый content buffer и automated season QA |
| C18 | `OPEN RELEASE EVIDENCE GATE` | permanent economy/pass запрещены до ≥30 независимых людей, ≥500 valid runs и 28 дней repeatability на `DEV_MVP` без real-wallet rewards | собрать реальные данные; бумажный документ не может закрыть этот пункт |
| C19 | `DESIGN-RESOLVED` | baseline counts не используются как scope; maintenance строит immutable freeze manifest всех eligible rows, включая soft-deleted payment/refund rights | 100% runtime coverage, три идентичных dry-run и rollback rehearsal |

**Сводка:** C1–C17 и C19 закрыты на уровне дизайна; C18 принципиально остаётся открытым evidence gate. Для всех строк ещё остаются owner approval и/или manifest/runtime доказательства.

## 1. Что именно проверено

Основные артефакты:

- `PRODUCTION_SNAPSHOT.md` — агрегированный снимок production на `2026-08-15 09:48:14 UTC`;
- `EVENT_ECONOMY_CATALOG.md` — 40 проектных контрактов событий;
- `economy_model.mjs` — детерминированный недельный stress test на 520 недель;
- `GAMEPLAY_ECONOMY_REBUILD_AUDIT.md` и текущий код — контроль полноты legacy-механик.

Метод:

1. Проверены структура и обязательные поля всех событий.
2. Карточки сопоставлены с текущими кошельками, реестрами, таблицами, scheduler-задачами и активными обязательствами.
3. Источники, sinks, transfer и прогресс-метры сведены отдельно, чтобы обнаружить двойной учёт.
4. Пересчитаны лимиты, сроки накопления и эффективность походов.
5. Модель запущена два раза; результаты побайтово совпали.
6. Проверены syntax, конечность коэффициентов и отсутствие отрицательного медианного баланса.

Навигационный knowledge graph помог найти контуры `gacha`, `auction`, `family`, `clans`, `crypto`, `expeditions`, `payments` и прямые writers. Его связи использовались только как карта: выводы ниже перепроверены по файлам и снимку.

## 2. Что сделано хорошо и должно сохраниться

- В каталоге действительно присутствуют **40 из 40** карточек, и у каждой есть все 10 обязательных полей: цель, вход, решение, source, sink, transfer, cap/catch-up, anti-abuse, telemetry и end-state.
- Мора, Алмазы и Зарники получили разные задачи. Тёмная Мора больше не предлагается как ещё один бесконечный кошелёк.
- `Attunement`, `Bond`, `Season XP`, `Night Reputation` и клановый вклад объявлены метрами, а не торгуемыми валютами.
- Прогресс не продаётся за Stars/Зарники; paid gacha и платные rated attempts запрещены.
- Старые питомцы, юниты, косметика, темы, VIP-сроки, семейные средства и escrow не предлагается стирать молча.
- Повторяемая Мора объединена общим недельным Reserve, а каналы названы альтернативами, а не дополнительными faucet.
- Аукцион закрыт до реальной ликвидности; клановые системы имеют gate по фактической аудитории.
- Проект не притворяется прогнозом: численные цены и выдачи обозначены provisional.

Это уже согласованный бумажный фундамент, достаточный для owner review. Он всё ещё не является реализованной и доказанной runtime-экономикой.

## 3. Валидация production-снимка

### 3.1. Уровень доверия

| Область | Оценка | Почему |
|---|---|---|
| Время и режим запроса | хорошо | указаны UTC, `REPEATABLE READ READ ONLY`, отсутствие PII |
| Масштаб аудитории и кошельков | пригодно с оговорками | квантили и охват полезны, но несколько окон смешаны |
| Мора за 30 дней | только направление | `wallet_log` неполон, переводы и системные операции смешаны |
| Остальные валютные потоки | недостаточно | полного source/sink для Алмазов, Зарников и Тёмной Моры нет |
| Миграционный baseline | неполон | перечислена часть stock, но не все активные права и состояния |
| Воспроизводимость | частичная | основной SQL назван, дополнительные запросы не сохранены как единый versioned bundle |
| Retention | нельзя использовать для game retention | D1/D7/D30 построены по сообщениям и без показанных denominators |

### 3.2. Что требуется добавить до любой миграции

Снимок должен стать не текстовой сводкой, а checksum-манифестом. Сейчас в нём отсутствуют или не доказаны:

- суммы всех кошельков, а не только квантили; отдельно paid, promotional, admin и legacy provenance;
- opening balance + все ledger delta + closing balance по каждой валюте;
- количество и сумма всех строк `user_reserve`, а не только один активный bid;
- четыре активных похода и их prepaid cost/таймер/использованные ускорители;
- pending/active duels, minigame sessions и gameplay runs;
- `claimed_free_levels`, `claimed_paid_levels`, заслуженные, но не полученные BP-награды;
- все ненулевые `gacha_pity`, включая доказательство counterfactual-компенсации;
- активные `player_buffs`, особенно купленные за Алмазы/Зарники и partner gifts;
- family pets (`pets.marriage_id`) и их активные походы;
- все `user_reserve`-строки, которые могли остаться от дуэлей и аукциона;
- текущие daily deal / weekly showcase reveals и покупки;
- активные promocodes, незавершённые referral promises и purchase commissions;
- payment/refund/chargeback reconciliation по Telegram charge id;
- косметические loadouts/presets и не только ownership rows;
- обычные и shadow relics, включая явное `0` как проверенный результат;
- clan treasury Mora, pending requests, buildings, shards и coins по одной миграционной формуле;
- exact inventory по **каждому** `item_id`, включая купленные donate-consumables;
- account level/XP, achievements, streak state и старые рекорды, которые уходят в Legacy Hall;
- список 38 прямых balance-write с владельцем решения `remove / route to ledger / migration-only`;
- список scheduler jobs с доказательством, что после cutover они не печатают legacy rewards.

### 3.3. Аналитические оговорки

- `5 512 046,78 in − 4 426 848,02 out = +1 085 198,76` арифметически верно, но это **не инфляция**: в поток входят transfers, auction, crypto, exchange и неполный ledger.
- Проценты D1/D7/D30 без числителей, знаменателей и cohort dates нельзя проверять и нельзя использовать как release target.
- Охваты смешивают all-time и 30-day окна. Каждая строка должна иметь `population`, `window`, `timezone`, `eligibility`.
- Утверждение каталога о `3 435,73` Алмазов и данные о четырёх активных походах не видны в самом snapshot. Они должны либо появиться в нём, либо иметь отдельный воспроизводимый query/result hash.
- Старый `cached CP` непригоден для миграции — это верно отмечено. Ни одна компенсация не должна опираться на него.

**Вывод:** snapshot достаточен, чтобы запретить вайп и увидеть концентрацию. Он недостаточен, чтобы выполнить cutover.

## 4. Полнота текущих mechanics и assets

| Домен production | Post-revision design | Что ещё требует manifest/runtime evidence |
|---|---|---|
| Мора, Алмазы, Зарники, Тёмная Мора, Кристаллы | exact 1:1 visible wallets; Dark→Legacy Claim; new emission0; Crystal retired | final totals, minor-unit precision и provenance reconciliation |
| Account level/XP, social rank/top | →Social Legacy Level; gameplay access только Chronicle | per-account receipt и отсутствие скрытого gate в runtime |
| 10 видов питомцев, 288 copies, имена, placement | ownership сохраняется; первая роль сразу, затем direct choice на 5-й, 10-й, …, 45-й meaningful gameplay day; deterministic 10-role path≤45 active days | per-pet/family-placement freeze rows и role pilot |
| Уровни и 5 360 duplicates | exact Legacy Care Rank/history; 0 Bond/power seed | checksum всех duplicate totals и receipts |
| Fatigue, food, boosters, paid time-skips | per-row consume/refund/service-cosmetic convert/archive; no new-core effect | item/SKU manifest и dependency graph=0 |
| Четыре active expeditions baseline | old result один раз вне Reserve; observed prepaid cost297 | final freeze count, timers и atomic settlement replay |
| 16 юнитов, levels, 43 shards, squad | ownership/Legacy Mastery/Research Claim; 0 Attunement/power seed | exact unit/shard/squad rows и owed-unlock audit |
| Старые grid battles, Gates, Abyss, raids, wars, CP duels | новые sessions запрещены; terminal once, incomplete escrow refunded; history archived | API/scheduler kill-switch и pending-session reconciliation |
| Achievements, quests, BP | earned auto-claim; paid earned rights preserved; old XP не переносится | per-account claimed/unclaimed/SKU manifest |
| Gacha, 991+7 tokens, pity, history | 1:1 legacy choices; counterfactual pity replay; exhaustion→prestige | frozen pools, ordered history replay и bulk receipts |
| Inventory и единственный craft recipe | category-specific claims, no universal currency/power | отдельное правило каждому nonzero item ID; wildcard запрещён |
| Shop, daily deal, weekly showcase, dark market | rotation не создаёт право; confirmed purchase сохраняется/settles | revealed/purchased/unconsumed entitlement manifest |
| 6 relics и 4 shadow relic types | named ownership; old power off; schematic/cosmetic claim; zero-hold check | exact ownership/checksum и safe visual fallback |
| Один клан, 8 участников, buildings/shards/coins | Alliance/solo path; active-clan gates; Foundation/history claims без power | treasury/holds/requests freeze manifest и live gate data |
| 11 браков, family vault, family pets, gifts | atomic legacy withdrawal; joint split; dispute freeze; no new vault | principals/balances/buffs reconciliation и support rehearsal |
| Аукцион и shared `user_reserve` | cancel lot; item+bid500+verified fee refund; no commission | reconcile 100% holds/stale states; ambiguous row blocks cutover |
| Crypto holdings | fixed `T0` + 72h server-side TWAP; no fallback; old-close fee 5%; half-up до 0,01 Моры; appeal14d | immutable observations/hash и dry-run всех final positions |
| Minigames | free, Reserve≤400, one Intel, no rated Intel/stakes | active-session closeout и solver/replay evidence |
| Cosmetics, themes, loadouts, presets | exact ownership preserved; orphan gets owner-only renderer/fallback | ID checksums и paid/gift/refund provenance |
| VIP, Stars payments, referrals, promos, admin grants | exact term preserved; old power off; scheduled spins 1:1 reveals; `ceil(remaining/50d)` tracks; old slots→0/1/2 showcase slots; referral cutoff | 100% SKU/term/promise mapping, charge reconciliation и receipts |
| Chat chests, anniversaries, cult/contraband | future faucets закрыты; earned right settles once | active eligibility/cooldown claims и scheduler evidence |
| Новый autoclicker MVP stats/runs/actions | test history preserved; `DEV_MVP`, real-wallet reward=0 | C18 evidence и separation from production analytics |

**Главная проблема полноты:** E40 называет классы активов, но пока нет исчерпывающего `asset_type × source_table × row_count × action × target × checksum` манифеста. Без него фраза «100% mapping» непроверяема.

## 5. Реестр источников, sinks и статусов новой системы

| Ресурс/право | Источники | Sinks/применение | Статус и пробел |
|---|---|---|---|
| Мора | E01, E02, E03, E05, E15, E17, E20, E22, E23, E36, E37 | E08, E15, E18, E19, E24, позже E28 | atomic one-action rule и prices заданы; machine manifest/live calibration pending |
| Алмазы | E05, E09, E10 | E21/E25 direct cosmetic/service | exact `6+2+2+2`, hard cap12, sinks4/8/12/20; owner/pilot pending |
| Зарники | E38 purchase/refund; versioned promo/admin correction | E10 premium track, E26, E27, E33 | provenance/recovery state задан; Stars package rate и runtime reconciliation pending |
| Тёмная Мора legacy | emission=0 | category-specific Legacy Night Archive Claim | no power/universal conversion; exact freeze catalog/checksum pending |
| Attunement | E02/E03 | немедленно в выбранный Memory/Imprint | 10 win/4 loss, 12×100%+12×50%, thresholds/costs заданы provisional |
| Season XP | E10/E11/E12/E16/E22/E23 | 50 milestones | exact 5 000 required/6 500 available, unique milestone keys; season manifest pending |
| Bond | E14 | pet story/cosmetic milestones | 48h opportunity, bank7, exact 12 milestones; usability calibration pending |
| Night Reputation | E06 | direct milestones | meter/end-state определены; final season reward table pending manifest |
| Community Reputation | E30/E34 | social status/cosmetics | no money/power; exact cap/anti-spam values pending pilot manifest |
| Clan/project progress | E16–E18 | direct project completion | active-clan, contribution cap и solo-equivalence заданы; live audience gate pending |
| Archive Reveal | E10/E11/E21, legacy tokens | выбрать 1 из 3 unowned/direct legacy resolution | new bank cap12; legacy 1:1, bulk и prestige fallback заданы; pools pending manifest |
| Schematics | E02/E15/E24 | открыть recipe/right | permanent/category-bound; exact content graph pending season/recipe manifest |
| Preparations | E12/E15/E20/E24 | одно bounded utility | cap3/type, 6 total, no ranked; runtime dependency tests pending |
| Practice credits | E29 | только paper crypto | seasonal/nonconvertible; legacy TWAP settlement задан, execution pending |
| Cosmetics/decor | milestones, Archive, stores | equip/gift/future market whitelist | relative SKU matrix и provenance rules заданы; exact catalog manifest pending |

Ни одна строка ещё не имеет полного machine-readable registry: `resource_code`, `source_code`, `sink_code`, `amount_formula`, `budget_scope`, `idempotency_key`, `transferability`, `expiry`, `balance_precision`, `version`. Следовательно, каталог пока является GDD, а не исполнимым экономическим контрактом.

## 6. Скрытые противоречия и конкретные исправления

> Этот раздел сохраняет формулировки находок **до ревизии**. Канонические исправления уже внесены в master specification; их актуальный статус находится в Post-revision resolution ledger выше. Раздел остаётся как доказуемая история «что было найдено → почему правило появилось».

### C1. Один run может получить Мору несколько раз

Один terminal run одновременно может быть E03, целью E11, вкладом E16/E17, фестивалем E22 и мировым событием E23. Фразы «Мора берётся из Reserve» не запрещают пяти отдельным handlers выдать пять наград до cap.

**Исправление:** один `economic_operation_id` и ровно одна Mora-операция на terminal action. Overlays пишут ссылки на неё и выдают только XP/stamp/status. Если несколько правил предлагают Мору, manifest заранее определяет одну композицию; суммы не складываются неявно.

Season XP может одновременно продвинуть несколько **заранее опубликованных** целей, но каждая milestone имеет собственный unique key, а сумма всех достижимых milestones всё равно обязана оставаться в сезонных 6 250–6 500 XP.

Atomic formula на `period_id`:

```text
available = 2400 + min(1200, floor(previous_period_unused * 0.50))
remaining = max(0, available - already_granted)
actual_grant = min(server_proposed_grant, remaining)
```

`previous_period_unused` переносится только один раз. Операция блокирует строку `(user_id, period_id)` и имеет unique idempotency key. После исчерпания Reserve игра, mastery и история продолжаются, но Mora grant равен нулю.

### C2. Сезонный бюджет Алмазов не сводится

E05, E09 и E10 умеют выпускать Алмазы, а E25 обещает typical 8–10 и absolute 12/season. Сейчас нельзя доказать, что источники суммарно не дадут 14–20.

**Исправление:** публиковать в season manifest максимум 12:

| Source bucket | Max/season |
|---|---:|
| Free Season Path | 6 |
| Mastery milestone | 2 |
| Festival/world path | 2 |
| Early achievement или нейтральная альтернатива | 2 |
| **Итого hard mint cap** | **12** |

Любая account milestone в конкретном сезоне потребляет тот же bucket, а не создаёт 13-й Алмаз. Refund/incident compensation учитывается отдельным финансовым source и не маскируется под gameplay mint.

### C3. Эффективность походов противоречит заявленному пределу

`50/145/280` за `2/6/12ч` дают `25,00 / 24,17 / 23,33` Моры в час. Разница крайних значений — около **6,7%**, а каталог заявляет не более 5%.

**Исправление:** минимум `50/145/285` либо новая таблица после моделирования active interaction. В manifest должны храниться и gross, и net efficiency после preparation cost.

### C4. Награда за поражение фармится намеренно

35 Моры за «meaningful loss» выгодно автоматизировать, если meaningful не определено.

**Исправление:** серверный eligibility predicate: минимальная доля корректно обработанных сигналов, минимальная длительность только как нижний anti-abuse guard, отсутствие повторяющегося abort-pattern, diminishing после повторов одного seed. Нельзя награждать просто за прошедшее время.

### C5. Accuracy имеет нулевой denominator

Формула E03 `correct/(correct+wrong+missed)` не определена при нуле событий. Клиентское `100%` в таком случае будет ложью.

**Исправление:** `accuracy = null` и UI `—`, пока denominator = 0. Отдельно считать signal recall, tap precision, rejected taps и missed; server result — единственный источник истины.

### C6. Модель содержит 1 000 Моры early milestones, каталог — нет

`economy_model.mjs` автоматически выдаёт до 1 000 Моры в первые десять active weeks. В E09 нет этого числового бюджета.

**Исправление:** либо добавить в master specification единый lifetime cap `1 000 Mora` с конкретными milestone IDs, либо убрать grant из модели. До решения эта часть результата модели является предположением.

### C7. Paid advantage может пережить cutover через старые предметы и scheduler

Текущий код содержит paid fatigue reset/cooldown skip, Diamond food, VIP weekly items, referral Zarniki commission и gameplay buffs от partner gifts. Новый каталог запрещает их влияние, но одного текста недостаточно.

**Исправление:** до запуска новой игры каждый остаток и активный buff получает одно из действий: `consume under old contract before cutoff`, `refund`, `convert to cosmetic/service entitlement`, `archive history`. Никакой старый paid item не должен применяться к новой competitive run. Referral commission после cutoff запрещена; сохранённое ранее premium ownership остаётся.

### C8. Кланы всё ещё могут стать обязательным gate

E17 доступен текущему единственному клану, E18 ждёт три активных клана, а «эквивалент соло» пока не имеет формулы.

**Исправление:** gameplay information/schematic всегда имеет Alliance/solo path с тем же временем и expected utility. Клан даёт coordination, hall, story и cosmetic expression, но не эксклюзивную силу. `Active clan` определить до аналитики, например: ≥4 eligible members, ≥2 meaningful days у каждого за 7 дней, четыре недели подряд. Полноценные проекты — при ≥3 таких кланах; соревнование — только при ≥8 кланах с ≥5 eligible members. Пороги изменяются только новой manifest-version.

### C9. Старый Reserve — не только одна ставка на 500

`user_reserve` используется аукционом и дуэлями. Один active lot не доказывает, что остальные reserve rows свободны.

**Исправление:** перед cutover reconcile `reserved = active auction escrow + pending duel escrow` по каждому игроку. Разница блокирует миграцию. Settle/refund делается compensating entry; `UPDATE reserved=0` запрещён.

### C10. 991 legacy reveals могут разрушить cosmetic catalog

1:1 сохранение токенов справедливо по количеству, но max 124 у одного игрока может исчерпать весь pool, превратить reveal в непонятный fallback и уничтожить будущий спрос.

**Исправление:** права остаются 1:1 и bound, но нужен отдельный `Legacy Archive` с опубликованным pool и value floor. После полного владения игрок выбирает из evergreen legacy finishes/status, а не получает новую premium-линейку или универсальную валюту. Никакого expiry.

### C11. Family escrow не имеет конечного dispute policy

Оба супруга исторически имеют права вывода, provenance вкладов нет. Совместный split не решает развод, удалённый аккаунт, многолетнюю неактивность и concurrent withdrawal.

**Исправление:** atomic balance lock; self-service withdrawals по старому правилу до нуля; mutual split как более безопасная опция; при споре — freeze и ручная компенсирующая операция. Никакого административного «справедливого» split без доказательств.

### C12. Crypto settlement предлагает два несовместимых исхода

Snapshot/TWAP и «старые правила» могут дать разную Мору. Пока игрок может выбрать выгодное толкование.

**Исправление:** до объявления миграции выбрать одну формулу, timestamp, oracle, spread/fee, rounding и appeal window. Сделать dry-run по всем 6 позициям и опубликовать receipt. Book cost не является payout.

### C13. VIP-компенсация не оценена

Верное решение — не переносить gameplay advantage. Но «равноценный пакет» без таблицы снова становится субъективным.

**Исправление:** inventory всех обещанных benefits × remaining term, публичная replacement table, минимум исходной paid utility в сервисе/косметике, индивидуальный receipt и owner approval. В новой боёвке старый benefit не действует ни одного дня.

### C14. Preparations/Intel могут попасть в ranked

E20 запрещает Intel в ranked, но общее правило для E12/E15/E24 preparations отсутствует.

**Исправление:** все ranked/Tower/Ghost runs используют нормализованный loadout и `external_preparations=[]`. Любой informational advantage должен быть одинаковым для всех участников seed.

### C15. Десять functional pet roles обещаны, но путь получения не описан

Первый питомец гарантирован; способы детерминированно открыть остальные девять ролей, cadence и catch-up отсутствуют.

**Исправление:** evergreen Chronicle contracts с прямым выбором роли, опубликованный максимум времени до каждой роли и отсутствие duplicate/RNG gate. Cosmetic rarity не меняет функцию.

### C16. Рынок откроется в экономике с огромной концентрацией Mora

Верхний дециль уже держит 61,2% Моры, max/median ≈89,7×. Ликвидность сама по себе не защищает новые декоративные товары от доминирования старых кошельков.

**Исправление:** сохранить Мору 1:1, но добавить market concentration guard, holding period, arms-length price bands и желанные escalating prestige sinks. Не открывать рынок, пока концентрация и wash-trading не проходят четыре недели подряд.

### C17. Fifty-day season не имеет производственного контракта

За 3 650 дней помещается **73 сезона**. Каждый требует XP manifest, цели, mastery/night rules, festival, Archive pool, тексты, QA и косметические награды. Каталог описывает продукт, но не способность команды выпускать его.

**Исправление:** до Season 1 полностью готовы Season 1–3 и emergency evergreen season. Должен существовать data-driven season compiler с автоматическими проверками:

- доступно 6 250–6 500 XP и требуется 5 000;
- Diamond mint ≤12;
- ни одна цель не требует покупки, клана, PvP, гачи, аукциона или сообщений;
- все reward IDs существуют и имеют end-state;
- ни один paid SKU не ведёт к gameplay value;
- все временные права auto-resolve;
- feasibility проходит P75 целевой когорты.

Если запас готового контента меньше двух сезонов, запускается честный evergreen/archive interval без новой валюты, а не сырой сезон.

### C18. Тридцатидневная увлекательность не доказана

Наличие 40 карточек не доказывает, что core run не надоест через месяц.

**Исправление:** до постоянной экономики — минимум 28 дней, ≥30 независимых тестировщиков, ≥500 valid runs, повторный запуск на 2-й и 4-й неделе, diversity используемых Memories/Imprints и qualitative exit reasons. Rewards в тесте остаются нулевыми/stand-only.

### C19. Snapshot-counts ошибочно звучат как фиксированный migration scope

`183 аккаунта`, `4 похода`, `1 lot`, `8 VIP` и другие числа верны только на время read-only snapshot. К моменту maintenance они изменятся. Миграция, написанная под эти числа, оставит новые строки без mapping либо применит неправильный assertion.

**Исправление:** baseline используется для проектирования и dry-run, но окончательный scope берётся из immutable freeze snapshot внутри maintenance. Assertions проверяют `100% eligible rows`, а не `row_count = 183`. Отдельно задаётся политика soft-deleted/recoverable accounts и прав, связанных с реальными платежами.

## 7. P0 exploit и legacy obligations

После ревизии таблица ниже является **обязательным runtime/release gate**, а не списком оставшихся бумажных дыр: каноническое поведение задано, но реализация ещё должна доказать его тестами и reconciliation.

| P0 | Почему блокирует | Обязательный gate |
|---|---|---|
| Любой старый direct balance writer или scheduler остаётся активен | обходит Reserve и новый ledger | 0 unauthorized writers, 0 legacy reward jobs |
| Несколько events платят за один terminal action | двойная/пятерная выдача | один operation ID, atomic Reserve row |
| Старый paid consumable/VIP buff влияет на новый run | прямой paid advantage | полная replacement/refund table до cutover |
| Auction/duel reserve не сходится | потеря или разблокировка чужой Моры | per-user escrow reconciliation = 100% |
| Family vault меняется конкурентно | двойной вывод | row lock + immutable compensating ledger |
| Crypto formula не выбрана до snapshot | выбор выгодной цены задним числом | immutable oracle/time/formula before freeze |
| BP/unclaimed/pity не перечислены по account | потеря earned/paid right | exact entitlement manifest + auto-claim/compensation |
| Legacy reveal исчерпывает pool без fallback | мёртвые права или premium cannibalization | отдельный legacy pool + permanent value floor |
| Refund/chargeback после расходования Зарников не определён | отрицательный/необеспеченный premium stock | linked financial state machine |
| Client или retry может повторить terminal reward | дюп | unique event key, conflict-payload reject, fault injection |
| Float/rounding меняет legacy balance | скрытая потеря | integer minor units + before/after receipt |
| Shared economy запускается по cohort | арбитраж между версиями | один maintenance cutover всех shared systems |
| Код ожидает старые snapshot-counts | новые аккаунты/escrow остаются вне migration | финальный freeze manifest, coverage=100%, без hardcoded counts |

## 8. Проверка математической модели

### 8.1. Исправленные отчётные ошибки

Текущая модель — `constitution-v2`. В ней исправлены отчётные ошибки и удалено неподтверждённое предположение:

- horizon теперь честно равен `520 недель = 3 640 дней`, а не 3 650;
- week 8 называется `56d`, а не `50d`;
- P50 sink/source считается как медиана per-run ratio, а не ratio двух отдельных медиан;
- добавлены P50 total source/sink;
- active-income days отделены от calendar days при modeled activity;
- право на newcomer grants задаётся cohort-флагом, а не ошибочно выводится из ненулевого кошелька;
- удалены неподтверждённые `1 000 Mora early milestones`;
- из one-time Моры внутри stress test остался только опубликованный Chronicle cap `3 000`; onboarding `300` явно находится вне десятилетнего recurring stress;
- явно записано `stress_test_not_prediction=true` и перечислены ограничения.

Проверки: `node --check` — success; два запуска — byte-identical; все ratios конечны; отрицательных медианных balances нет; main и payer совпадают при одинаковых gameplay inputs.

### 8.2. Результаты stress test

Это **не прогноз поведения игроков**. Это ответ на вопрос: «что произойдёт при заданных вручную activity/earn/spend assumptions?»

| Persona | Active weeks P50 | Source P50 | Sink P50 | Mora P50, 520w | Mora P90, 520w | Sink/source P50 |
|---|---:|---:|---:|---:|---:|---:|
| Короткий | 323 | 277 588 | 252 545 | 24 851 | 27 129 | 0,910 |
| Основной | 447 | 919 244 | 861 346 | 57 760 | 64 052 | 0,937 |
| Увлечённый | 505 | 1 168 579 | 1 141 968 | 26 235 | 34 049 | 0,978 |
| Возвращающийся | 250 | 287 415 | 258 475 | 32 243 | 35 291 | 0,900 |
| Ветеран P100 | 468 | 1 056 782 | 1 179 706 | 192 713 | 199 674 | 1,117 |
| Плательщик без силы | 447 | 919 244 | 861 346 | 57 760 | 64 052 | 0,937 |
| Рациональный накопитель | 520 | 1 201 242 | 156 179 | **1 360 614** | **1 363 664** | 0,130 |

Жёсткий теоретический максимум повторяемой Моры за 520 недель — `2 400 × 520 = 1 248 000` до carry и one-time grants. Модельный hoarder заканчивает примерно с 1,36 млн, потому что начинает с production max `315 568,25`, получает усечённый jittered income и почти не тратит.

Главный вывод модели не «баланс готов», а обратное: добровольный каталог должен переживать миллионные кошельки, а marketplace нельзя открывать только по liquidity gate.

### 8.3. Проверка affordability

| Цена | Main: active income days | Main: calendar days | Short: active income days | Short: calendar days |
|---:|---:|---:|---:|---:|
| 100 | 0,3 | 0,4 | 0,8 | 1,3 |
| 800 | 2,7 | 3,2 | 6,6 | 10,6 |
| 3 200 | 10,9 | 12,7 | 26,4 | 42,5 |
| 12 000 | 41,0 | 47,6 | 98,8 | 159,4 |

12 000 — это не универсальная «обычная» цена: для short-persona она соответствует примерно пяти месяцам календаря при modeled activity. Она допустима только как явно необязательный prestige sink.

### 8.4. Почему модель пока не валидирует десять лет

1. Spending ratio задан автором. Модель предполагает наличие sinks вместо проверки, что реальные SKU захотят покупать.
2. Нет catalog saturation: один cosmetic нельзя покупать бесконечно.
3. Нет churn, resurrection, cohort aging, сезонности, релизов и изменения поведения.
4. Нет carry 50% Reserve, хотя это правило конституции.
5. Нет Алмазов, Зарников, entitlements, Archive backlog, refunds, gifts и admin grants.
6. Нет market transfers, wealth concentration dynamics и price formation.
7. Нет clan/family escrow и multi-account abuse.
8. Нет прогресс-метров, времени до cap, build diversity и content consumption.
9. Нет 73 season manifests и стоимости/скорости производства контента.
10. Main=payer совпадают по конструкции: им даны одинаковые параметры и seed. Это unit test запрета, не аудит всех product paths.
11. One-time campaign grants начисляются по active week, а не по реальному завершению milestones.
12. Onboarding 300 намеренно не входит в десятилетний recurring stress; это нужно учитывать при сравнении с first-30-day economy, но больше нет скрытого extra-1 000 assumption.

Следующая модель должна быть discrete-event simulation с реальным catalog: cohorts, SKU ownership, finite demand, season manifests, exact sources/sinks, legacy stock, returners, market и adversarial personas. До live calibration нельзя называть её forecast.

## 9. Что владелец должен утвердить до кода

После ревизии у каждого пункта уже есть рекомендуемое правило. Владельцу не предлагают придумать решение с нуля — нужно принять его, изменить или явно отклонить:

1. Diamond split `6+2+2+2`, cap12 и direct prices `4/8/12/20`.
2. Dark Mora → category-specific Legacy Night Archive Claim, new emission=0.
3. Category policies для каждого inventory/relic/unit/pet/clan asset; exact per-row manifest строится после approval.
4. Broken pity replay: qualifying premium result закрывает текущий блок; только каждый недополученный full35 → direct choice; финальный residual ≥18 → один bound legacy reveal; appeal 14 дней.
5. Legacy-token pool: 1:1, frozen non-premium catalog, bulk resolve, exhaustion → archive prestige only.
6. Crypto: `T0 + 72h server-side TWAP` непосредственно до freeze; при неполном/невоспроизводимом окне cutover block без fallback; old sell formula, fee 5%, `ROUND_HALF_UP` до 0,01 Моры, appeal 14 дней; book cost только P/L reference.
7. VIP: сохранить exact remaining service term; scheduled weekly spins 1:1 → bound reveals; `ceil(remaining/50d)` → cosmetic-only tracks; old extra slots 1:1 с clamp 0..2 → permanent showcase slots; gameplay power выключить.
8. Family escrow: legacy withdrawal с atomic lock/уведомлением, split только jointly signed, спор → freeze.
9. Premium refund state machine: provenance reversal; irreducible remainder → premium-only recovery case без gameplay block.
10. Clan gates/solo-equivalence: Alliance сразу, projects после 3 active clans, competition после 8.
11. Reward Reserve: rolling 7d от server epoch, carry≤1 200 один раз, один terminal operation.
12. Pilot price bands и affordability guardrails; они не становятся production-final до telemetry.
13. Content contract: current+2 complete seasons и emergency evergreen; при buffer<2 paid season не продаётся.

Пока решения D01–D27 не подписаны, product implementation остаётся `NO-GO`, даже несмотря на готовность бумажного проекта к review.

## 10. Финальный checklist

### Бумажный проект — состояние после ревизии

- [x] Письменный runtime source/sink registry задаёт caps, transfer и end-state.
- [x] Сезонные Diamond/XP sources сходятся с hard caps.
- [x] Один terminal action не может дать несколько Mora grants.
- [x] Pilot prices проверены stress-моделью для newcomer/main/short/veteran/hoarder.
- [x] Для каждого legacy asset **класса** задано preserve/convert/settle/archive правило.
- [x] Paid promises имеют non-power replacement/refund contract.
- [x] Выбраны recommended family, crypto, auction, pity, VIP и BP settlement rules.
- [x] Определены content buffer, emergency evergreen и stop-sale rule.
- [ ] Владелец утвердил D01–D27.
- [ ] Письменные правила скомпилированы в machine-readable manifests с exact per-row coverage.

### До реализации shared economy

- [ ] Создан versioned `economy/resource/event/price/season` manifest.
- [ ] Все balance/entitlement mutations идут через один ledger API.
- [ ] Есть atomic Reserve row и per-terminal idempotency.
- [ ] Legacy endpoints и scheduler jobs fail closed под одним cutover flag.
- [ ] Precision переведена в integer minor units.
- [ ] Migration dry-run воспроизводится три раза с одинаковыми checksums.

### До production cutover

- [ ] 100% asset rows mapped; 0 unknown IDs; 0 orphan rights.
- [ ] 100% auction/duel/family/crypto/payment escrow reconciled.
- [ ] 0 unauthorized direct writers и 0 legacy reward jobs.
- [ ] 30 дней shadow ledger reconciliation без необъяснённых deltas.
- [ ] ≥99,5% terminal events complete; retry/fault injection не удваивает reward.
- [ ] Paid-to-gameplay dependency graph пуст.
- [ ] Core проверен ≥28 дней, ≥30 людьми и ≥500 valid runs без economy rewards.
- [ ] Season 1–3 content-complete; automated manifest validators зелёные.
- [ ] Персональный migration receipt понятен на мобильном экране.
- [ ] Backup, rollback rehearsal и maintenance cutover пройдены.

## Итог

Проект стал существенно честнее старой экономики: он убирает paid power, лишние wallets, обязательную гачу и бесконечные независимые faucet. После ревизии это уже не просто каталог намерений: C1–C17 и C19 имеют конкретные канонические решения, согласованные между master specification, event catalog и `constitution-v2`.

| Слой готовности | Финальный статус |
|---|---|
| Бумажный дизайн | **READY FOR OWNER REVIEW** |
| Owner approval D01–D27 | **PENDING** |
| Machine-readable economy/season/migration manifests | **PENDING** |
| Product implementation | **NO-GO до approval + manifests** |
| C18: 30 people / 500 runs / 28 days | **OPEN RELEASE EVIDENCE GATE** |
| Production cutover | **NO-GO до runtime, migration и release evidence** |

Следующий правильный шаг — review владельца. После утверждения: machine-readable manifests, ledger shadow, dev-only core pilot, затем C18. Ни stress-модель, ни хороший документ не заменяют эти доказательства.
