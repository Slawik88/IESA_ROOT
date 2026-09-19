# Cosmetics storefront design QA

- Reference: owner-supplied dark celestial atlas and the existing Predvestnik profile-card language.
- Viewports checked: 320, 390 and 430 px; no horizontal overflow observed.
- Store hierarchy: collections, catalogue and owned items remain reachable from one persistent bottom-nav destination; collection Back restores the collection list and item Back/Escape closes the nearest preview first.
- Commerce: every offer has an authoritative Zarniki price, individual and missing-set purchase paths, current balance, deficit copy and a server-backed top-up route. Preprod's disabled Stars issuance is surfaced without creating an invoice.
- Preview: the selected item is shown inside a complete collection look; whole-app skin preview replaces rather than stacks the active `skin-*` class and reverts on close/page leave.
- Accessibility: 44 px actions, keyboard tabs, modal labels, focus entry, focus trap, Escape close and trigger-focus return are implemented.
- Visual fit: the supplied Atlas is used as a real WebP asset; Void profile surfaces and card lines inherit the same restrained indigo palette. The fitting/store preview stage is 168 px.
- Automated evidence: JS/Python syntax, targeted lineage/static/price/atomic purchase tests and exact final preprod suite 89/89.

## UI-002 profile caption regression

- Reproduced cause: a 270 px child minimum overflowed the 220 px profile stage and placed the bottom-anchored caption 39 px into the resource rail.
- Resolution: both direct stage children inherit the stage height and reset the stale minimum; the caption remains visible with its original padding and type scale.
- Responsive evidence: at 320, 390 and 430 px the stage and character area are both 220 px, caption/resource overlap is 0, the gap is 11 px and horizontal overflow is 0.
- Scope check: five resource cells remain visible; the later store-preview rule remains 168 px and therefore is not enlarged by the profile fix.
- Independent review: Accepted; no mandatory changes. Its P2 test-hardening note was also applied by binding the regression assertion to the complete selector block.
- Regression evidence: direct and rooted static-delivery contracts, Python compile, scoped diff check and exact isolated preprod suite 89/89.

## QUEST-002 mobile quest log

- Hierarchy: sticky Today/Week/Rewards tabs expose one task group at a time; the summary preserves completion and remaining-reroll context without a nine-card wall.
- Actionability: every quest shows progress, authoritative help and a 44 px action; Rhythm and Minesweeper launch directly, while Mafia correctly opens its Telegram-oriented explanation.
- Safety: reward total is derived from server values; reroll confirmation shows the remaining allowance and a shared in-flight guard prevents duplicate reroll or claim requests.
- Accessibility: 10 px minimum supporting copy, semantic progress bars, tablist/tabpanel state, roving tabindex, arrow/Home/End navigation and focus restoration.
- Responsive evidence: all three panels checked at 320/390/430 px with zero horizontal overflow and 44 px minimum controls; sticky top is 49 px after scroll and cancel preserves 2/2 rerolls.
- Independent review: Changes requested on four material issues, all corrected; final verdict Accepted.
- Regression evidence: quest rules, bot and PostgreSQL negative paths plus exact final isolated preprod suite 90/90.

final result: passed
