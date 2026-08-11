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
