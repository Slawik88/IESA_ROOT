# Predvestnik V2 — Release Backlog (fresh start)

**Created:** 2026-08-29
**Scope:** current code only. Historical specifications, plans, audits and visual evidence were intentionally removed at the owner's request.

## Stop-ship

> **Scope correction — 2026-09-06.** GAME-004 records the retirement of the
> *legacy* pet/zoo and quest systems. It does not prohibit the later approved
> `pets-v1` and `quests-v1` surfaces: those are separate server-authoritative
> contracts, available through the current Mini App/chat, with no legacy
> rewards or old routes restored. Their verified limits remain: pet expedition
> route completion grants no value, and quest variety is constrained until new
> authoritative activity writers exist.

> **QUALITY-2026-09-07 — owner-requested whole-product audit is active.**
> This is not a cosmetic pass. The current authenticated loopback run captured
> the profile, quest log, fitting room, activity hub and Rhythm leaderboard.
> The findings below are therefore evidence-based current-state work, not a
> promise that an older test or a green static check represents release quality.
> No production URL/menu has been changed: the workspace contains only the
> stale DigitalOcean endpoint and disposable preprod tunnel configuration, not
> the owner-mentioned current production domain.

| ID | Priority | Player-facing gap / confirmed cause | Completion bar and order |
| --- | --- | --- | --- |
| **SOCIAL-001** | **Resolved locally** | Public profiles use a durable opaque `profile_ref`; the API exposes an explicit player projection rather than Telegram/database identifiers. Rhythm and Minesweeper leaderboard clients render the projected display name as a tappable public-profile link. The unauthenticated legacy `GET /profile/{user_id}` bypass discovered during QA was removed rather than wrapped. | 2026-09-13 live loopback proof now returns 404 for a real, small and maximum numeric ID while the opaque profile opens without rendering the raw Telegram ID. The route contract locks all three negative cases. Remaining external evidence belongs to QA-001: populated ranking order, 320/390/430 screenshots and a real Telegram tap test. |
| **SOCIAL-002** | **P1 · core tracker resolved locally** | The private **Chat Tracker** now has a compact summary, literal-title search, recent/week/all-time/rank sorting, stable paging and per-chat cards for the current player's level, rank, message counters, activity streak and current/recent moderation actions. Left chats and every other player's rows are excluded; chat/admin IDs, membership lists and moderator notes are never projected. | PostgreSQL proof covers isolation, left-chat exclusion, stable ties/pages, literal wildcard search, streaks and stripped moderation history. Live 320/390/430 and 1280 px proof covers zero overflow, 44–46 px controls, 12→14 paging/focus return, an 88-character title, expanded moderation history, empty/search states and zero console errors. Remaining source gap: the current achievement model has no chat-scoped receipt, so the UI does not fabricate “achievement progress”; define that durable source before adding it. |
| **UI-001** | **Resolved locally** | The shared renderer now has one identity/avatar anchor, a 168 px fitting/store stage, readable data rail and five-resource rail. Background, surface tone, edge, name/title typography and restrained card effect are composed from the saved look. The fitting room renders one card with a public/saved switch instead of duplicating the full layout. | 2026-09-09 visible loopback proof covered profile, fitting and the storefront at 320/390/430 widths. Exact whole-product screenshot evidence remains in QA-001, not a blocker to further local art refinement. |
| **UI-002** | **Resolved locally** | The owner screenshot was reproduced and measured: `.profile-showcase-main` had been reduced to 220 px, while the older 270 px `min-height` still forced its direct `.character-showcase-area` child beyond the stage. The bottom-anchored «Личный профиль» plate therefore overlapped the following resource rail by 39 px. | Direct stage children now inherit the 220 px stage height and reset the stale minimum without hiding or moving the caption. Live 320/390/430 px measurements show stage = character area = 220 px, caption/resource overlap = 0, an 11 px gap and no horizontal overflow; all five resource cells remain visible. The later, more specific store-preview rule still preserves its 168 px compact stage. Static delivery locks the cascade and the exact isolated preprod gate is **89/89**. |
| **COS-002** | **Resolved locally** | The delivered **Образы** page is now a mobile-first Zarniki storefront: collection/catalog/owned navigation, stable collection totals, item and whole-set checkout, live collection-context preview, durable whole-app skins and a server-backed Zarniki top-up route. The supplied Atlas art is a 1600✨ item in the Void collection and one shared skin applicator carries it through the shell, Rhythm and Minesweeper. Paid cosmetics are permanent entitlements and never hide behind a second VIP gate. | 2026-09-09 PostgreSQL negatives cover atomic item/set/skin debit, retry, insufficient balance rollback and grant provenance. Runtime invariant proves zero priced `vip_required` SKUs. Live 320/390/430 checks cover no horizontal overflow, 168 px stage, 44 px actions, dialog focus/Escape/return, Back hierarchy, single preview skin and the fail-closed Stars top-up message. Independent review drove three correction rounds. Exact final isolated gate: **89/89**. Production Stars invoice confirmation remains part of REL-001 and was not triggered in QA. |
| **QUEST-002** | **Resolved locally** | The old random set could fill four/five slots with only two/three metrics. It is now source-aware and lane-balanced: flexible play, Rhythm mode/verified-score goals, Minesweeper completion/win/difficulty goals and experienced-player-only Mafia completion/win. Reroll explicitly excludes the target and occupied metrics/lanes; pristine historical sets migrate collision-safely while any started period remains byte-for-byte intact. The mobile screen removes duplicate summaries and the overlapping floating Back, connects each set to its exact Mora reward, exposes paths from Rewards, and adds headings, named progressbars, retry and dialog focus return. No quest/page background asset exists; backgrounds remain cosmetics-only. | PostgreSQL proofs cover exact terminal receipt sets for normal/augments/500-score Rhythm, Minesweeper loss/easy/hard win, Mafia participants/winning faction, replay, unavailable-source empty state and both pristine/started migration paths. Visible isolated preprod shows 4 varied daily and 5 round-robin weekly goals, compact reward context, accessible dialog and focus return. Independent review found and then accepted fixes for the hard-win rollback, target-equivalent reroll, partial-period migration and missing augments E2E. Final isolated gate: **90/90**. |
| **CONTENT-001** | **Resolved locally · compensation deferred** | The chest store now uses one versioned mixed catalogue for free and paid keys: 12 stable pet species, five food items, pet-card packs, Mora, Diamonds, Jokers, Zarniki and the pinned VIP reward pool. A key costs 10 Zarniki, with two purchases per UTC day and exactly the same odds as free keys. Purchase, entitlement, prepare, typed delivery, reveal and unused-paid-key refund are idempotent and transaction-bound. The UI discloses star odds, every conditional reward weight, exact amounts/ranges, rarity tables, species/VIP pools and owned-pool fallback before purchase; a confirmation sheet repeats price/quota/refund terms. Daily/weekly set completion and completed pet activities mint typed keys, but a chest quest is eligible only when a key already exists and random card drops never gate set completion. Pet activities atomically spend 25/40/55 endurance, respect the chest flag/readiness guard and preserve completed runs for later settlement when disabled. Existing canonical pet ownership is reconciled instead of creating a duplicate. | One-million seeded simulation gives conservative EV 9.52 per 10-Zarniki key; transactional tests cover purchase races, replay, stale catalogue, every delivery type, unused-key refund, legacy pet ownership, disabled feature settlement, exhausted pets and no duplicate compensation call. Live isolated preprod at 320/390/430 px covered confirmation/cancel, exact 10★ disclosure, sealed prepare/reveal, quest progress and 38→13 endurance debit. Final isolated preprod gate: **96/96**. Duplicate/max-level compensation remains intentionally last before production, per owner instruction. |
| **ACH-002** | **Resolved locally** | The durable 1–40 model now has five server-terminal families: Rhythm, Minesweeper, Mafia, chests and pet activities. The mobile collection is browsable by **All / Games / Adventures**, shows two independent meters to the exact next level, explains which condition still blocks progress, and exposes levels 1/5/10/20/30/40 without turning the page into a reward wall. Rewards remain Mora-only. | Immutable terminal and reward receipts reject replay or altered facts; the received-Mora summary uses the amount actually stored in historical receipts rather than recalculating history through the current policy. Level 40 still requires the family event cap and 156 active weeks, and excess lifetime events do not rewrite the displayed cap. Live 320/390/430 px evidence shows zero horizontal overflow, one Back, 44 px actions, focus-preserving filters and readable partial progress. Independent review accepted all corrections. Final isolated gate: **97/97**. |
| **GAME-001** | **Resolved locally** | The shipped client now uses a one-use REST ticket and server-timed WebSocket with stable tap IDs and reconnect continuity; it no longer requests the exposed offline packet. Every terminal live run becomes `review_required`, so script-echoed runes cannot directly write the leaderboard, quests or achievements. | A developer-only review API records one append-only clear/quarantine decision. Transaction-scoped locking linearizes concurrent reuse of the global review ID; only `clear` writes trusted ranking/progression, idempotently. PostgreSQL counterexamples cover pre-review zero writes, clear, quarantine, replay and altered decision; live 390 px shows the pending-review result and a populated opaque-profile leaderboard. Independent re-review found a concurrency race, then returned ACCEPT after the lock fix. Real Telegram transport/reconnect remains in QA-001. |
| **REL-001** | **Stop-ship** | A preprod Quick Tunnel works only while its local process lives. The only discoverable stable DigitalOcean URL serves a stale legacy client. The owner says a production domain exists, but its exact hostname/deployment configuration is not present in this workspace. | Obtain the exact domain/deployment location, deploy only through the owner-approved release path (never a GitHub push), set the bot menu to the verified HTTPS `/predvestnik/` URL, and run authenticated Telegram, payment, route and rollback gates. No endpoint is to be guessed or repointed. |
| **QA-001** | **P1 · local matrix active** | The maintained matrix below now separates automated, fresh browser and external production evidence. Its adversarial passes disproved `97/97 = release-ready`: they found a raw-ID profile leak, overlapping browser Back controls and retry IDs that changed after uncertain responses. | The leak/navigation defects are fixed. Feed, reroll, chest prepare/purchase and pet activation/activity/decision now retain an operation ID until confirmed success; failed pet mutations refetch server authority. Independent review selected lost-response pet activity as the highest-risk residual and the full isolated gate is **103/103**. Continue remaining responsive/browser cases, then run the real Telegram Mini App, Stars and rollback gates. |
| **LCB-002** | **Ready to apply after target DB initialization** | Value-preserving v4 carries current Zarniki once, refunds 13,852 Zarniki proven spent by six users in the retired exchange, converts retired paid rights to Zarniki, caps liquid progression and converts every remaining score point continuously into diminishing VIP time. Existing VIP is preserved; no universal 21-day grant or randomized-key settlement. | Frozen snapshot: 253 users; 164,489 Zarniki, 131,449 Mora, 1,139 Diamonds and 25,007,699 score → 2,057.41 aggregate VIP days (median 3.32d, p99 64.11d, max 97.87d). Hash-confirmed v4 importer: 253 applied, then 253 replayed. Production has not been written. |
| **CHAT-001** | **Active · wave 1 implemented** | Rebuild Telegram as a coherent chat product: one home/help concept, message-only rankings, separated activity/admin rank/game/VIP concepts, sectional settings, complete social settlement and dependency-proven legacy removal. | Bare `бот` now opens structured help; discoverable archive/event tabs are gone. Tops support local players / globally aggregated players / chats × today / week / month / all time, with local timezone and canonical UTC global periods. Settings entry now checks live Telegram authority and UI is sectional. Broken unregistered event handler plus retired dev exchange/deal writers removed. Focused auth/route/compile checks pass; snapshot aggregate SQL returns all four new boards. Remaining: module registry/audit, placement/trends/privacy, divorce workflow, deeper legacy deletion and real Telegram UX. |

**Execution order:** `SOCIAL-001`, `UI-001`, `UI-002`, `COS-002`, `QUEST-002`,
`CONTENT-001`, `ACH-002` and `GAME-001` are complete locally. Continue with final
`QA-001` / `REL-001`; duplicate compensation is explicitly the final economy
wave immediately before production. `SOCIAL-002` retains only its explicit
chat-scoped achievement source decision.

### QA-001 current release evidence matrix — 2026-09-13

| Surface | Automated / authoritative evidence | Fresh browser evidence | Negative or counterexample | Residual gate |
| --- | --- | --- | --- | --- |
| Profile | PostgreSQL projection/privacy tests; static showcase/wrap contracts | 390 px: five resources, settings grid, no overlap or horizontal overflow | Green suite coexisted with anonymous raw-ID disclosure; legacy route now absent and live 404 | 320/430/desktop, long data, keyboard; Telegram tap |
| Fitting and cosmetics | Ownership, atomic item/set debit, replay, insufficient funds and skin application | 390 px: collection/catalog/owned navigation, 168 px preview, 44 px controls, Escape returns focus | Stars top-up is visibly fail-closed before the production payment gate | Real Stars paid/cancelled/lost-response recovery |
| Quests | Assignment variety, terminal receipts, reroll/reward replay and ARIA contract | 390 px: three tabs, four varied daily goals, one Back, no overflow | Lost reroll response formerly created a new action ID; client now retains it until success | Live failed-response replay; 320/430; Telegram entry |
| Pets | Ownership, endurance/activity/reward/replay PostgreSQL tests | 390 px: 11/100 state, disabled unaffordable activities, one local Back, no overflow | Feed, active slot, activity start and route choice retain one ID after an uncertain response; failures refetch the authoritative timer/state | Empty/many pets, live lost-response mock, timers, 320/430 |
| Chests | Mixed-catalogue, odds, typed delivery, replay and unused-key refund tests | 390 px: 1 key, disclosure, 54 px main action, one Back | Prepare/purchase now retain one action ID until success; reveal is recovered by immutable `open_id`; compensation remains deliberately deferred | Pending reload, 0-key/quota/error, 320/430 |
| Achievements | Immutable event/reward receipts and five-family projection | 390 px: filters, exact dual progress, milestones, 44 px actions, one Back | Static contract alone did not detect unrelated page navigation regressions | 320/430 re-run in final whole-product pass |
| Activities hub | Pure server view plus navigation contract | 390 px: three approved cards, CTA 44 px, no floating Back or overflow | A passing gate allowed Back to overlap the Sapper CTA before this audit | 320/430; reconcile UI with `/hub/me` |
| Rhythm | Ticket/WS/reconnect/stable-replay tests; pending-review/clear/quarantine/progression PG proofs; developer gate | 390 px: HTTP→ticket→WS, pending-review finish, populated trusted leaderboard and opaque profile link | Independent critic found concurrent review-ID race; transaction advisory lock fixed it and re-review returned ACCEPT | Real Telegram disconnect/reconnect and developer review smoke; 320/430 |
| Minesweeper | Server-owned state, revision, ownership, replay, ranking and terminal GET-loss proof | 390 px: all difficulties, readable 9×9 grid, no overflow | Uncertain action now keeps one ID, disables conflicting input and refetches authority; terminal GET reveals the same mines | Live forced lost-response replay; 320/430 |
| Mafia history | Full fake-Telegram match plus history projection | 390 px: empty modal, focus on Close, clear group instruction | Fake delivery does not prove Telegram DM/edit/callback behaviour | Controlled real group test and `/mafia-v1/me` adapter test |
| Public profile | Opaque reference resolver and safe DTO projection | 390 px: full card, five resources, no raw ID or overflow | Real numeric `/profile/990000001` returned private raw DTO while 97/97 passed; now 404 | Unknown ref and populated leaderboard click at 320/430/desktop |
| Chat Tracker | PostgreSQL isolation/search/sort/paging/streak/moderation projection proof | 320/390/430 and 1280 px: sticky tools, 44–46 px targets, long populated cards, expanded history, stable paging/focus, no overflow or console errors | Wildcards are escaped literally; left/foreign chat rows and raw chat/admin IDs are excluded | Chat-scoped achievement source decision only |
| Payment/support | Invoice/delivery/recovery and reconciliation/refund-review tests | 390 px store top-up boundary is fail-closed; dialog focus/Escape verified | Local success cannot prove Telegram Stars delivery or support routing | Production-like paid/cancelled/pending/lost-webhook and support smoke |
| Bot routes | Handler allowlist and focused middleware/callback contracts | Not representable by browser evidence | Imports/names do not prove Dispatcher ordering or Telegram delivery | Real private/group command, stale callback and permission smoke |

| ID | User path | Confirmed root cause | Safe resolution | Evidence / residual risk |
| --- | --- | --- | --- | --- |
| BOT-001 | Moderator creates `бот привязать админ чат`; reports should reach the trusted admin group. | The former bearer token could be redeemed by anyone in any group; it had no TTL and was consumed by non-atomic SELECT then DELETE. | Implemented: creator-bound 10-minute request; live rights check for the same user in both groups; destination bot-admin check; PostgreSQL one-to-one destination constraint; atomic consume → route → append-only bind audit. A rebind is rejected during an active purge because dossiers preserve their destination. | 2026-08-30 isolated-preprod test rejects foreign owner, replay, expired token, duplicate destination and active-purge rebind; concurrent delivery yields exactly one route. Schema startup, compile, diff check and external authenticated HTTPS smoke passed on the restarted test bot. Residual stop-ship gate: manually test source→destination bind and non-owner rejection in two real Telegram test groups before production. |
| FAM-001 | Player creates/accepts a marriage, views a family wallet, attempts a transfer or divorce. | Legacy `marriages` had no global membership constraint; the old direct-column writer accepted a supplied marriage id, had no idempotency and stored `FLOAT8`; hard deletion also conflicted with immutable family history. | Only the new server-resolved membership transfer may move value: personal + family append-only legs share one transaction, Zarники are whole-number, and client data never chooses a family. HTTP requires an idempotency key; Telegram uses a persisted owner-bound 10-minute one-shot intent. Divorce is a soft close after all family property is zero. The approved Stars policy has no automatic/user-facing refund; `/paysupport` is manually reviewed and a return is normally considered only before linked Zarники leave buyer personal custody. | 2026-08-30 isolated-preprod proof: schema migration; four-currency transfer retry/foreign-member/fractional/insufficient cases; HTTP rejects supplied marriage id and a missing idempotency key; Telegram rejects a foreign or expired intent and concurrent delivery yields exactly one operation. The former scheduler family-column mutation was removed; the obsolete direct writer remains fail-closed. Updated test bot and external authenticated HTTPS smoke passed. Residual production gate: owner-approved read-only migration audit plus a manual end-to-end transfer in a disposable married test account before any production migration. Payer-origin lots stay deferred unless a future policy permits refunds after transfer. |
| GAME-SCOPE | Development is directed at legacy Reconstruction campaign mechanics. | The old release backlog treated Chapters, Memories, Scar Map and other retired surfaces as active game bugs, conflicting with the owner-approved 2026-08-30 scope. | Retire those rows from the active queue. Do not extend legacy game code. New work begins only from the approved Rune Rhythm, Mini App Minesweeper and chat Mafia contracts; their detailed economies remain deferred. | Authority: `docs/PROJECT_RECONSTRUCTION_MASTER_PLAN.md`, priority blocks dated 2026-08-30. |
| GAME-001 | Player starts an endless Rune Rhythm run, chooses augmentations, taps runes and later reads a per-mode leaderboard. | The legacy Rhythm is coupled to retired Reconstruction campaign state and trusts a client-facing combat flow. The first live-WebSocket version also put transport latency between every tap and its feedback. | The approved play path is local-first: an authenticated start receives a server-derived buffered rune packet, then the Mini App resolves runes, health, timer, chunks and feedback locally. An offline terminal journal is deterministically replayed server-side for the player's own result, but it is not proof of human timing. Issuing that packet marks the run `offline_exposed`; terminal offline runs become `quarantined` and systemically cannot write leaderboard, quest metrics, achievement receipts or their downstream Mora. Only a server-timed transport run can be a future `clear` candidate; old pre-boundary rows are `legacy_unverified` and excluded. | 2026-09-07 independent review found that the former implementation allowed a forged perfect offline journal into the global table and terminal quest/achievement writers — a P0, so the prior statement that Rhythm had no progression effect was wrong. The new PostgreSQL negative proof submits a positive-score forged local journal and verifies `quarantined`, no leaderboard row, no quest receipt and no achievement receipt; it also rejects switching an offline-exposed run into trusted transport. Leaderboard DTO no longer returns raw user IDs. Integrity-review evidence is append-only, but no admin/public approval writer exists yet. JS/Python/ASGI and full isolated preprod **86/86** pass. Remaining release gate: migrate the Mini App to the existing server-timed transport and design/manual-test the separate reviewer workflow before presenting a non-empty public leaderboard as trusted. |
| GAME-002 | Player opens Mini App Minesweeper, chooses a difficulty, opens/flags cells and reads a difficulty-specific global table. | The retired wager Sapper exposed a different product contract: stake, cashout and a server session that cannot be reused. A wholly local replacement would make a leaderboard trivially forgeable. | Implemented a separate server-owned `/minesweeper` surface: Easy 6×6/6, Normal 9×9/10, Hard 9×9/18; safe first open + halo; touch-to-open, hold-to-flag plus explicit flag mode; every action is revisioned and server-resolved. Only confirmed wins rank by server elapsed time then open actions; no reward/economy/quest writer is attached. | 2026-08-31: pure rules and isolated PostgreSQL proof cover layout counts, safe first cell, flags, owner isolation, idempotent retry, payload conflict, terminal state and ranking. Live 390px test covered first-open cascade, flag, difficulty switch and loss revealing mines without console errors; 320px has no horizontal overflow. Residual release gate: owner must enable `game_minesweeper_v2` intentionally in production after the controlled test rollout. |
| GAME-003 | A group starts chat-native Mafia: lobby, private roles, night, discussion, voting and a persistent phase card. | There was no approved chat-game lifecycle; reusing global chat locks would block bystanders and could overwrite moderator settings. | Implemented a feature-gated (`game_mafia_v1`, production off) server-owned match state with row-locked deadlines, phase-aware deletion gate, explicit DM readiness, private roles/actions, one active game per chat/topic and a 5-second editable card. Discussion allows only living players; night/voting allow only nonplayers. The lobby reappears after ten human messages, settings stay server-side, and purge/delete-right failures pause instead of silently changing group permissions. All primary player actions are visible buttons; settings are host-only compact controls, choice buttons use player numbers, completed night/vote phases state their outcome, and open voting displays live selections while secret voting does not. The host can resume a safety-paused match with its stored phase/time once purge is inactive. The Mini App has read-only personal history/statistics. No rewards or economy writer is attached. | 2026-09-01 isolated PostgreSQL/fake-Telegram integration simulates four players through lobby, roles, card delivery/edit, phase gate, stale start, vote change, cancellation, settings/topic rejection, pause/resume, purge rejection and open/secret vote visibility. A live loopback Mini App test reached the history modal and exposed/fixed a broken post-onboarding route to the game hub. Rules, static delivery and compile/diff checks are green. Residual release gate: conduct a controlled real Telegram group check for bot deletion rights, callback rendering and private-message delivery before enabling the flag in production. |
| GAME-004 | Player opens the profile, help or the default Mini App and reads a retired game promise. | The active product surface still contained a Reconstruction client, a `/reconstruction/*` router, a pet tab and bot writers for old care/expeditions. | Resolved for the public runtime: removed the Reconstruction router/client, the old `/zoo` router and their tests; `/game` is a compatibility redirect to the activities hub; former routes are absent; the pet tab and old chat writers are closed. The scheduler module itself now contains only operational maintenance and Mafia phase advancement, so bot import no longer loads retired expedition, shop, auction/duel, Battle Pass, crypto-alert, Smart Pulse, chest-event or shadow-merchant jobs. The obsolete no-op streak middleware is physically absent. Chat settings and the Mini App expose only the approved surfaces; archival database rows remain for the future compensation audit. | Route, navigation and surface-parity contracts pass. The corrected full isolated-preprod gate is **103/103**. Remaining gates are external production evidence and the owner-approved archival compensation audit, not another runtime writer cleanup. |

## P1

| ID | User path | Confirmed root cause | Safe resolution | Evidence / residual risk |
| --- | --- | --- | --- | --- |
| BOT-003 | Globally banned user sends an update. | The database middleware used to refresh profile/activity before the later sanction gate suppressed the handler. | Implemented: one shared-connection sanction evaluation now runs before every automatic writer and records its result for the later middleware. An allowed appeal/help command reaches its handler without refreshing profile, chat settings, counters or hint state; any sanction-check failure stops the update. | 2026-08-30 contract proof covers blocked text, allowed appeal, one-shot evaluation and zero automatic writer calls; compile, preprod gate and external HTTPS smoke passed after test-bot restart. Residual: a message whose evaluation began before a concurrently committed new ban can still finish its automatic writes; absolute cross-transaction ordering needs a separate shared lock/change to sanction issuance. |
| BOT-004 | Former moderator taps a retained chat-settings button. | Callbacks previously validated only the historical menu owner; rank, destination context and live Telegram authority were not re-checked (except one special toggle). | Implemented one shared callback gate for menu, rank picker and every toggle: same owner, group context, current local rank ≥5 and live Telegram creator/manage-chat authority are required; settings keys remain allowlisted. | 2026-08-30 contract proof rejects local-rank demotion and lost Telegram authority before any database writer, while accepting a current authorized moderator. Compile, test-bot restart and external HTTPS smoke passed. Residual: a callback already inside the helper can race a later demotion; Telegram has no transactional role lock, so each new callback is revalidated immediately before it writes. |
| BOT-005 | Telegram `successful_payment` update is lost during a long outage/backlog. | A capped, stateless recovery could overlap between bot processes and silently treat an offset scan as complete even while new history rows shift its head. | Implemented: one durable lease coordinates scanners; every scan starts from Telegram history head, reaches a terminal short page, then re-reads that head. A changed head, page cap, invalid/failed relevant row or API failure creates a durable critical alert and resets the run; failed/invalid rows receive an immutable per-charge journal record. Ledger credits remain idempotent by Telegram charge id. | 2026-08-31 isolated PostgreSQL proof covers competing workers, lease release, failed Telegram-history call, critical alert, and immutable observation conflict; existing invoice/delivery/replay contract stays green. Residual release gate: execute one real production-like Telegram history recovery only after owner-approved production migration/audit; Stars remain disabled on preprod. |
| BOT-006 | Smart Pulse cannot DM a player due to a transient Telegram error. | The task marked every queued notice sent before attempting delivery, so a network error silently lost the notification. | Implemented: atomically lease one event for 10 minutes; mark it delivered and close the remainder only after Telegram accepts its DM. Transient errors release the lease for the next run; forbidden/bad-request DM routes are permanently classified with retained reason. Opted-out/expired events close without consuming the DM cooldown. | 2026-08-31 real isolated PostgreSQL proof covers concurrent lease rejection, transient release/retry, post-success batch close and permanent failure classification. Residual: Telegram can accept a DM then lose its HTTP response, so at-least-once retry can duplicate a non-economic notice; it never loses it silently. |
| BOT-007 | Moderator double-clicks or later uses an old rank-confirmation button. | Rank confirmation trusted target/rank/initiator embedded in callback data and had no expiry or one-time consume. | Implemented: callback contains only an opaque server token. The persisted request binds chat, initiator, target's source rank and desired rank for 10 minutes; the approver is checked before atomic consume, then initiator authority and target state are revalidated before the writer. | 2026-08-31 real isolated PostgreSQL proof rejects wrong-chat use and replay after first consume. Residual: a request whose source rank changes after atomic consume is safely rejected but must be recreated. |

## P2

| ID | User path | Confirmed root cause | Safe resolution | Evidence / residual risk |
| --- | --- | --- | --- | --- |
| BOT-008 | FastAPI co-host or a detached scheduler task crashes. | Startup used untracked `create_task`/`ensure_future`, so polling could remain alive after Mini App or a scheduler silently died. | Implemented a shared supervisor: every co-host/scheduler task has a named handle, completion/crash log and shutdown cancellation. Any unexpected exit signals the polling owner to terminate fail-fast, letting the process supervisor restart a coherent instance. | 2026-08-31 injected failing coroutine proves critical log + fail-fast signal; compile/diff checks pass. Residual: deployment must retain a process restart policy; the bot intentionally does not hot-restart individual stateful tasks in-process. |
| DOC-001 | CI runs the retained document-contract tests. | Removed historical documents were still read by `tools/test_current_game_docs.py` and `tools/test_currency_exchange_retirement.py`. | Resolved: the current-game test now reads only `docs/PROJECT_RECONSTRUCTION_MASTER_PLAN.md`; the unapproved legacy-economy test is excluded from the approved-scope runner. Historical documents were not restored. | 2026-09-01 approved-scope isolated preprod suite passes 78/78. Deferred economy design remains outside this test gate. |
| TEST-001 | Developer runs the isolated preprod suite before a release. | The runner did not set its own module `PYTHONPATH` or pass the owned isolated DSN to tests that require it; it also mixed retired Reconstruction/Chronicle and unapproved-economy contracts with the approved game surface. | Implemented: the runner supplies its disposable DSN, discovers imports from the module root, and explicitly excludes only tests whose assumptions contradict the owner-approved master-plan scope. The current game-document check reads that one plan and verifies that deleted historical game documents are not restored. | 2026-09-01 full isolated preprod run: 78/78 passed. This is not evidence that deferred economy/pet design is approved or ready; those decisions remain owner-led. |
| TEST-URL-001 | Test player opens the Mini App through the actual Telegram test bot after a Quick Tunnel expires. | `.env.test` still referenced a dead account-less Cloudflare hostname. The prescribed automation did not overwrite that stale menu while its replacement URL lacked a confirmed external 200, but Quick Tunnel edge publication can occur after its initial probe window. | A new Quick Tunnel was externally checked at `/predvestnik/` before changing `.env.test` or the test bot menu. The restarted isolated preprod bot reads the same URL and its Telegram API call confirms the menu button update. | 2026-09-07 external HTTP returned 200; startup log confirms `Кнопка меню → <new tunnel>`, loopback auth and bot ready state. It is intentionally a disposable testing URL; it dies with the local cloudflared process and is not a production deployment. |
| ECON-001 | Player converts already-delivered Zarinki to Mora or Diamonds without buying a direct Stars progression product or bypassing a cap by mixing targets. | Legacy exchange was deliberately closed and its obsolete 150 Mora/✨ quote had no quota, payment-review gate or shared HTTP/chat authority. | Added `zarniki_exchange_v1`: 1✨→10🪙 or 0.01💎, whole inputs only and one shared 50✨ UTC-day cap. The one service locks the player, replays before cap checks, freezes payment-review accounts, appends `-✨/+target` through the canonical ledger and records quota in the same outer transaction. Mini App and bot are adapters only. | 2026-09-05 pure simulation proves the 2,200✨ 200-Star package cannot convert in fewer than 44 days; real PostgreSQL proof covers atomic legs, replay, altered action key, cap/split-route bypass and review hold. Full isolated preprod gate: 83/83 green. Residual production gate: use a named tunnel/custom domain or deployment; Quick Tunnel availability ends with its local process. |
| ECON-002 | A capped pet/cosmetic duplicate must compensate the owner without becoming Stars, a generic wallet loophole or an accidental public product. | The approved currency had no name or durable receipt boundary; expanding the four-currency ledger would also widen every existing wallet writer and payment/history projection. | Named **Осколки Эха** (`echo_shards`). A separate internal account, immutable compensation receipt and append-only positive ledger remain isolated from API, chat, shop, exchange, transfer, invoice and payment paths. The internal pet terminal writer progresses 1→16, then emits exactly one shard at level 16 in the same transaction as append-only source and progression receipts; it refuses an arbitrary source string. | 2026-09-07 independent read-only economy review selected this isolated architecture. PostgreSQL proofs cover all fifteen level-ups, the terminal one-shard compensation, exact replay, changed source/pet conflict, snapshot tampering, numeric-coercion rejection, missing-source rejection and all receipt/ledger append-only triggers. There is still no public writer or client-supplied award. Residual: connect it only to a future verified chest/loot source; cosmetic duplicate writer, shard catalogue and spending remain intentionally absent. |

## Next safe wave

The authorization/payment/background waves above are implemented but still require
their listed manual production gates. For gameplay, use only the current owner
scope in `PROJECT_RECONSTRUCTION_MASTER_PLAN.md`: Rune Rhythm, Minesweeper and
Mafia. Do not restore or extend retired campaign mechanics while the new game
contracts and economy are intentionally deferred.

## Owner decisions — activity and pet direction (2026-09-05)

- Games are approved as activities, not as the sole or central product loop.
  Rune Rhythm, Minesweeper and Mafia remain isolated from pet power, currency,
  keys and paid advantages. Their tested preprod implementations require only
  their stated real-Telegram and production-flag gates.
- Pet progression is approved as a separate long-term activity: a level 1–16
  pet grows in expedition-only statistics and effects, and has visual milestones.
  It must not alter competitive results in Rhythm, Minesweeper or Mafia.
- The approved care direction is a 0–100 endurance model whose active pet loses
  endurance gradually (target: 10 per 24 hours); food restores it. Slot swaps
  must be server-authoritative and consume endurance to prevent temporary-slot
  abuse. Exact costs, thresholds, food sources and stat numbers remain pending
  the economy/balance wave.
- A trek is timer-only. An expedition has a 3/6/9-hour server timer followed by
  an interactive route, shared safely between Mini App and Telegram with one
  authoritative state/revision. The requested single shared active-slot rule
  still needs explicit confirmation because "one timer" may mean one total slot
  or one slot of each type.
- The owner permits two Zarniki-bought keys per account per day and limited
  paid expedition help that provides information or risk mitigation but never a
  guaranteed win. No exact SKU, price, reward table, odds, reset boundary or
  paid-item effect is approved yet; these are Wave 3 decisions.
- Refunds remain a manual owner review through `/paysupport`; no automatic
  refund button. The public policy must nevertheless preserve timely handling
  of legitimate non-delivery, payment-error and other valid disputes under
  Telegram rules. It must not promise unconditional denial or unbounded owner
  discretion. Direct Stars commerce remains disabled until the payment/review
  contract and real Telegram test gate are complete.
- Owner policy clarification: a manual Stars refund is normally denied when the
  precisely described digital service was delivered and used; a confirmed
  project-side payment or delivery failure is refunded to the original payer.
  Product descriptions, receipts and delivery evidence must be specific enough
  to make that distinction auditable.
- Zarniki are approved for one-way conversion to Mora and Diamonds, subject to
  a conservative rate, server-side limits and a balance simulation that prevents
  a small Stars purchase from creating disproportionate pet power. No rate or
  limit is approved yet. Conversion to Dark Mora remains undecided.
- A future cross-surface overflow/compensation currency is approved in
  principle: it is minted when a player receives an already-maxed collectible
  (including a level-16 pet duplicate). Its name, supported overflow sources,
  catalogue and any power limits are not yet approved; it must be append-only
  and cannot be exchanged back into Stars.
- Resource sources will include quests and achievements in addition to treks,
  expeditions, training and chests. Quest/achievement writers must be designed
  as versioned server definitions plus immutable event and reward receipts; no
  memory-only completion counter is allowed.
- Quest design is delegated: definitions must be concrete, non-grindy and
  understandable without guessing. Do not create objectives requiring a
  particular augmentation combination or vague conditions such as "find a rare
  reward". Each quest may expose a concise explanation of where and how it can
  be completed. Players receive two server-authoritative rerolls per week; a
  reroll replaces an unfinished eligible quest with a random eligible quest.
  VIP receives five server-authoritative rerolls per week instead of the
  standard two. The implementation must still prevent rerolling completed or
  ineligible quests and must remain auditable.
- Quests and achievement rewards must not grant cosmetics. Economy/catalogue,
  rates and balance simulations are delegated to the agent, subject to explicit
  owner decisions only for real-money boundaries, paid advantage and refund
  policy.

## Implemented release slice — cosmetics visibility and fitting room (2026-09-05)

- Public profile and cross-surface cosmetic projections now fail closed when
  VIP is inactive. Ownership and the selected loadout remain durable; renewing
  VIP restores the same look without a new equip action.
- The Mini App has a separate owner-only `/appearance` wardrobe route and a
  fitting room. It contains no checkout, direct-Stars invoice, gifting or
  transfer writer. It displays the same profile-card structure used by the
  player profile and explicitly tells a non-VIP owner that the saved look is
  visible only in the fitting room. Transfer is labelled "in development".
- Verified with unit projection tests, Python/JS compilation and an isolated
  preprod browser smoke as `@codex_test`. Visual item-by-item art revision,
  the shared Zarniki shop, and the full public-profile renderer unification
  are still open; do not describe this slice as a complete cosmetic release.

Continuation (2026-09-07): the public-profile renderer and the fitting-room
renderer are now one shared Mini App structure rather than two approximations.
The fitting room deliberately renders the actual public projection alongside
the owner-only saved look, so inactive VIP cannot leak cosmetics to the public
card. Independent review found stale-after-equip preview state and missing
release-wardrobe CSS; both were corrected, with refresh-after-write and a
single-client-operation guard. A catalogue audit confirms 134 cosmetics across
six slots and ten lineups: every item has one unique CSS token, with no absent
token. The 2026-09-09 production DOM audit additionally found no actual card,
swatch or name overflow across all 134 entries. A second independent review
found and closed mixed frame+halo loss and five pseudo-element reduced-motion
escapes; visible saved-look DOM contains both `frame-artifact` and `halo-dust`.

Continuation (2026-09-09): **Образы** is now the shared Zarniki store,
not an owner-only wardrobe. A paid SKU can no longer carry an effective VIP
display gate; non-purchasable service entitlements retain that capability.
Item/set/whole-app-skin purchases use authoritative prices and idempotent ledger
mutations. Insufficient balance opens the existing server package/invoice flow;
preprod correctly presents its fail-closed payment state and no invoice was
confirmed during QA. The preview is a modal, focus-managed collection look and
Back/Escape close the nearest layer before leaving the collection or store.
Browser smoke used visible loopback `@codex_test`; exact-code full preprod
regression completed **89/89 passed**. Manual art-direction review across the
narrow-screen/motion matrix remains open. The catalogue has ten lineups, but only
Hanami, Moon Lotus and Ryujin Tide currently have server-curated six-slot
looks; define the other seven together with the separate shared Zarniki shop
rather than exposing a partial store through the fitting room. Stable external
hosting and real Telegram release verification remain open.

## PET-001 — replacement pet foundation (2026-09-05, in progress)

| Field | Evidence |
|---|---|
| User path | Choose an active pet → its endurance drains slowly; switch it out without a free temporary buff exploit. |
| Root cause | The archived companion implementation still uses lore, 2/6/12-hour routes and retired game/economy effects, so it cannot be re-enabled for the approved product. |
| Implemented | `core/pets_v1.py` defines level 1–16, 0–100 endurance, 10 points/day drain, server-side five-point active-slot switch cost, and only 3/6/9-hour trek/expedition duration validation. Effects are explicitly expedition-only. |
| Negative proof | `tools/test_pets_v1_rules.py` rejects levels outside 1–16, old durations, clock rollback, underfunded slot switches and verifies same-slot idempotence. |
| Remaining stop-ship work | Add durable PostgreSQL state/action receipts and Mini App/chat adapters; design the duplicate-to-level-up and overflow-compensation writer; do not enable a route or economic reward until those contracts and tests exist. |

Continuation: durable `pet_v1_*` state and action receipts plus the authenticated
`/pets-v1/active` adapter are implemented. `tools/test_pets_v1_pg.py` proves
owner isolation, exact slot debit, replay and conflicting idempotency payloads
against isolated PostgreSQL. The Mini App and the read-only `бот питомцы` /
`бот питомец` renderer share one projection; its `startapp=pets` route is
visible-tested. One shared 3/6/9-hour `pet_v1_runs` timer now accepts either a
timer-only trek or an expedition and fail-closes a second active/ready run; it
can only become `ready`, never credit loot. A ready expedition accepts one
server-authoritative, idempotent `careful` / `steady` / `bold` route choice;
it does not resolve an outcome, award a reward or allow a second choice.
PostgreSQL proof covers no-active rejection, replay, cross-kind double-start
rejection and one-choice-only. The internal duplicate writer now raises a
specific owned pet from level 1 through 16 and turns further duplicates into
exactly one Echo Shard with an immutable progression receipt; it is not exposed
to clients and awaits a future verified loot source. Care/food and expedition
outcome/rewards remain unimplemented.

The same timer is also available in chat through `бот поход, 3|6|9` and
`бот экспедиция, 3|6|9`; its ready-expedition choice is likewise shared through
`бот маршрут, осторожный|ровный|рискованный`. Strict parsing rejects legacy or
ambiguous durations and routes.

## QUEST-001 / QUEST-002 — quest foundation and varied mobile log (resolved locally 2026-09-10)

| Field | Evidence |
|---|---|
| User path | Player opens clear daily/weekly tasks, replaces an unfinished task, then finishes an eligible activity. |
| Root cause | The historical quest surface was retired and its implicit assignments/rewards cannot safely be reopened. |
| Implemented | `quest_v1_*` keeps immutable definition snapshots, action and terminal-metric receipts. `/quests-v1` assigns 4 daily/5 weekly objectives from unique lanes and round-robin available sources; 2 weekly rerolls are enforced server-side (5 only after server VIP check) and cannot return an occupied metric/lane. Rhythm records completion, mode and verified 500-score events; Minesweeper records completion plus win/difficulty only after a win; Mafia records completion for each participant and a win only for the winning faction. Mafia assignments additionally require prior player participation. The Mini App can claim transparent free-Mora rewards of 20/100/75; no cosmetic, Stars, Zarniki or random drop is minted. |
| Negative proof | `tools/test_quests_v1_pg.py` proves unique lanes/metrics, source balancing, reroll/replay/conflict/limits, collision-safe zero-progress policy migration and atomic 195-Mora claims. Rhythm/Minesweeper/Mafia PostgreSQL proofs assert the exact metric set for each terminal outcome and no duplicate on retry. Visible preprod confirms 4 varied daily plus 5 balanced weekly goals, explicit 20/100/75 reward progress, accessible modal naming/focus return and no overlapping floating Back. |
| Remaining stop-ship work | Pet-care and chest objectives are intentionally absent from the active rotation until their terminal receipts exist. The read-only chat renderer (`бот квесты` / `бот задания`) opens the same Mini App `questlog` and deliberately has no writer. The current quest expansion passed an independent read-only implementation review; the next financial/content expansion still requires its own economic review before release. |
