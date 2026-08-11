# Design QA — «Тихая сцена»

## Comparison target

- Source visual truth:
  - `FastAPI/static/design-concepts/profile-card/01-open-central-stage.png` — 1068 × 1473 px.
  - `FastAPI/static/design-concepts/profile-card/02-stage-data-rail.png` — 1126 × 1397 px.
- Selected direction: central open showcase from option 1 combined with the vertical data rail from option 2.
- Implementation capture: `docs/audits/2026-08-11-site-redesign/after/profile-card-390.png` — 366 × 500 px.
- Normalized same-input comparison: `docs/audits/2026-08-11-site-redesign/after/profile-card-comparison.png` — 732 × 500 px.
- Full product captures:
  - `docs/audits/2026-08-11-site-redesign/after/`
  - `docs/audits/2026-08-11-site-redesign/secondary/`
- Browser viewport: 390 × 844 CSS px, `deviceScaleFactor: 1`.
- State: local dev profile with equipped avatar frame, name glow and title; profile overview at scroll position 0.
- Density normalization: option 2 was resized to 366 × 500 px only for the side-by-side comparison. The implementation element was captured at its native 366 × 500 CSS-pixel size.

## Full-view comparison evidence

The implementation keeps the same dominant regions as the selected hybrid: identity and fitting-room action in the header, a two-column central body with the open canvas taking roughly two thirds of the width, a narrow four-item information rail, and a low-emphasis resource row. The base card is deliberately neutral so equipped profile backgrounds and particles remain the atmospheric layer.

The complete 390 px captures show the same surface ladder, borders, radii, typography hierarchy and restrained gold state color across profile, pets, arena, market, appearance, battle pass, auction, help, admin and global moderation. The 320/390/430 px capture set has no horizontal page overflow.

## Focused-region comparison evidence

The focused card comparison confirms:

- Identity block, avatar, title and fitting-room entry remain readable and aligned.
- The showcase/data-rail proportion matches the source closely.
- Power, level/XP, streak and achievements remain immediately scannable.
- The resource row is secondary to the canvas and retains four existing values.
- Existing `frame-oak` and `glow-moon` cosmetic classes survive the layout refactor.
- The source's decorative stage orbit was intentionally omitted because the approved brief requested no added effects and a neutral future character canvas.

## Required fidelity surfaces

- Fonts and typography: system font stack retained; hierarchy uses weight, brightness and tabular figures. Rail labels and values fit without wrapping at 320/390/430 px.
- Spacing and layout rhythm: header, canvas, rail, resources and metadata use consistent 1 px separators and compact 9–12 px spacing. No heavy base shadow remains on the profile card.
- Colors and visual tokens: cold neutral surfaces and low-alpha borders follow the selected mock. Gold is reserved for state, value and primary actions.
- Image quality and asset fidelity: no visible source asset was approximated in CSS. Existing avatar and cosmetic assets/classes are reused. The empty canvas is product space, not a missing placeholder asset.
- Copy and content: only real profile values from the dev response are shown. The fitting room is explicitly named «Примерочная»; no invented play-time or achievement data was introduced.

## Comparison history

### Pass 1

- [P2] The fitting-room control used the shorter label «Образы», weakening the explicit easy-access requirement.
  - Fix: changed the visible action to «Примерочная» while retaining the compact mobile treatment.
- [P2] Primary section tabs were 40 px high, below the project's 44 px mobile target.
  - Fix: raised top-level tab targets to 44 px; dense nested tabs remain 40 px.

### Pass 2

- Post-fix evidence: `docs/audits/2026-08-11-site-redesign/after/profile-card-comparison.png` and the 320/390/430 verification run.
- No actionable P0, P1 or P2 visual mismatch remains.

## Interaction and runtime checks

- Opening the fitting room from the central showcase works at 320/390/430 px.
- Profile, pets, arena, market, more, auction, battle pass and help navigation activate the expected screen.
- Cosmetics cross-surface, fitting-room layout, collection navigation and collection-atmosphere checks pass.
- Browser console checked across the capture set: no application JavaScript exception. The local mock server still emits its known preview-only favicon/API 404 and unavailable WebSocket handshake messages.

## Follow-up polish

- [P3] When a real character-rendering system is introduced, place it inside `.character-showcase-area` without changing the surrounding layout or adding default decorative effects.

final result: passed

---

# Design QA addendum — bottom navigation containment

## Comparison target

- Source visual truth: the user's 611 × 755 px screenshot showing the fixed dock shifted beyond the left edge. The same pre-fix cascade was reproduced at `docs/audits/2026-08-11-bottom-nav/bottom-nav-source-reproduction-611.png`.
- Implementation: `docs/audits/2026-08-11-bottom-nav/bottom-nav-after-611.png`.
- Focused evidence: `docs/audits/2026-08-11-bottom-nav/bottom-nav-source-focused-611.png` and `docs/audits/2026-08-11-bottom-nav/bottom-nav-after-focused-611.png`.
- Viewport and pixels: both full captures are 611 × 755 px at a 611 × 755 CSS viewport and `deviceScaleFactor: 1`; both focused captures are 611 × 110 px from the same browser state. No density normalization was needed.
- State: local preview profile, bottom dock visible, profile item active, scroll position 0. The pre-fix capture injects only the former late `left: 9px; right: 9px; width: 482px` cascade so the user-reported defect can be compared at the same content and viewport.

## Full-view and focused comparison evidence

The source reproduction loses the profile and pets destinations beyond the left viewport edge and shows only part of the arena destination. The revised capture keeps all five destinations inside the centered 500 px application column. In the focused pair, the dock changes from approximately `-232..250px` to `64.5..546.5px`; its intended 482 px tablet width and 9 px bottom inset are preserved.

## Required fidelity surfaces

- Fonts and typography: unchanged; labels retain their existing size, weight, line height and single-line fit at 320/390/611/1024 px.
- Spacing and layout rhythm: the dock is centered with 9 px side clearance on mobile and capped at 482 px on wider screens. All five items retain equal tracks and a 50 px minimum height.
- Colors and visual tokens: unchanged; active gold, neutral surface, border and shadow tokens remain consistent with the approved redesign.
- Image quality and asset fidelity: no raster asset, icon or decorative layer was added or replaced; existing navigation symbols are unchanged.
- Copy and content: all five destination labels and their order are unchanged.

## Findings and comparison history

### Pass 1

- [P1] Persistent bottom navigation was clipped at widths of 520 px and above.
  - Cause: a late `.nav { left: 9px }` rule overrode the tablet centering rule while leaving `transform: translateX(-50%)` active.
  - Fix: made the final rule self-contained with `left: 50%`, `right: auto`, `transform: translateX(-50%)`, and `width: min(calc(100vw - 18px), 482px)`; removed the now-redundant media-query width override.

### Pass 2

- Post-fix browser verification passes at 320, 390, 611 and 1024 px: no dock clipping, no horizontal page overflow, exact center alignment, five practical touch targets, and a 9 px bottom inset.
- All five destinations (`profile`, `zoo`, `arena`, `market`, `more`) activate the expected dock item and page at every tested width.
- Browser runtime errors checked: none.
- No actionable P0, P1 or P2 mismatch remains. No focused-region issue remains for typography, spacing, color, imagery, icons, copy, interaction state or responsiveness.

## Follow-up polish

- No P3 visual follow-up is required for this scoped correction.

final result: passed
