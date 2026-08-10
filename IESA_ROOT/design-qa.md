# Design QA — IESA partner cabinet strict redesign

## Comparison target

- Product-language target: the accepted strict ordinary-member cabinet:
  - `docs/audits/2026-08-10-iesa-ux/full-site-pass-04-member/strict-final/profile-390-top.png`
  - `docs/audits/2026-08-10-iesa-ux/full-site-pass-04-member/strict-final/profile-1440-top.png`
- Same-screen partner baseline:
  - `docs/audits/2026-08-10-iesa-ux/full-site-pass-05-partner/baseline-viewport/`
- Browser-rendered final implementation:
  - `docs/audits/2026-08-10-iesa-ux/full-site-pass-05-partner/strict-final/`
- Side-by-side evidence:
  - `strict-final/comparisons/dashboard-before-after-390.png`
  - `strict-final/comparisons/dashboard-before-after-1440-normalized.png`
  - `strict-final/comparisons/member-target-partner-390.png`
  - `strict-final/comparisons/member-target-partner-1440-normalized.png`
  - `strict-final/comparisons/dashboard-focus-390.png`

This is a design-system and task-flow comparison, not a pixel-identical clone. The partner cabinet has different operational content, but it must share the accepted IESA cabinet language: strict near-black canvas, thin dividers, restrained radii, clear typography, one red brand accent, and semantic color only where status requires it.

## Viewports and state

- Mobile: 320 × 760 and 390 × 844 CSS pixels, device scale factor 1.
- Tablet: 768 × 900 CSS pixels, device scale factor 1.
- Desktop: 1440 × 1000 and 1920 × 1080 CSS pixels, device scale factor 1.
- Authenticated partner with a linked member, five historical visits, unconfirmed e-mail banner, calendar access, analytics and company profile.
- Final comparison captures use the completed-tour state so onboarding dimming does not contaminate visual evidence.

## Audited flow steps

1. Partner dashboard and verification banner — healthy.
   - Primary task is visually dominant; e-mail status and resend action are clear but secondary.
2. Member search and keyboard autocomplete — healthy.
   - One matching result, `aria-expanded=true`, ArrowDown focus and Enter-ready selection verified.
3. Visit entry and PIN validation — healthy.
   - Member identity, service, amount and six-digit PIN are presented in one ordered form; invalid PIN state is visible and specific.
4. Member visit history — healthy.
   - Summary, totals, status and visit records remain readable as desktop rows and mobile data cards.
5. Partner-wide history, filters and CSV action — healthy.
   - HTMX history content, date/status filters and export action retain a stable layout.
6. Analytics — healthy.
   - KPI hierarchy, chart containers, empty states and table density match the strict system.
7. Meeting calendar, date picker and scheduling drawer — healthy.
   - Mobile date control, add action, date overlay and stable drawer were exercised at 320, 390 and 768 px.
8. Company profile and validation — healthy.
   - Business identity fields are grouped logically; required-field error remains adjacent to the field.
9. Edit/cancel visit templates — healthy.
   - Strict forms, destructive-action hierarchy and cancellation context were reviewed and covered by Django tests. Browser capture was not forced because the preview records were outside the editable time window.

## Required fidelity surfaces

- Typography: existing IESA sans/mono pairing retained. Page titles, utility labels and values use one predictable hierarchy; decorative all-caps is limited to short labels.
- Spacing: top-level mobile content uses 16 px edges; desktop content uses a bounded 1320 px workspace; nested surfaces use a consistent 14–20 px rhythm.
- Color: near-black canvas, white hierarchy and IESA red. Green, amber and red are reserved for verified/success, attention and destructive/error states.
- Shape: compact 7–12 px radii and one-pixel dividers. No glow-heavy cards, floating decorative bubbles or gratuitous gradients.
- Assets: existing IESA logo and Font Awesome icons only. Emoji and approximate CSS/SVG art were removed from partner empty states and calendar controls.
- Copy: actions use verbs and explain consequences. PIN copy states why the current member code is required; e-mail copy explains its security role.
- Accessibility: visible focus styles, semantic buttons, labels, `aria` state on autocomplete, touch-sized mobile controls and `prefers-reduced-motion` support.

## Comparison history

### Pass 1 — blocked

- Evidence: `full-site-pass-05-partner/baseline-viewport/`.
- P1/P2 findings:
  - two visually competing dashboard systems and excessive independent cards;
  - operational search did not read as the main action;
  - inconsistent page shells, form density and mobile table behavior;
  - calendar relied on a hard-to-discover floating action and emoji-like glyphs;
  - tablet layout kept a desktop sidebar and compressed the actual work area.
- Fixes:
  - created one partner portal system shared by all routes;
  - rebuilt dashboard information architecture around member search and visit logging;
  - standardized cards, tables, forms, alerts, actions and responsive navigation;
  - replaced floating/ambiguous calendar controls with an explicit mobile toolbar.
- Post-fix evidence: `full-site-pass-05-partner/strict-v1/`.

### Pass 2 — blocked

- P2 findings:
  - at 768 px the vertical sidebar left too little width for the main task and wrapped business identity text;
  - calendar drawer screenshots initially caught the 350 ms transition before the panel reached its stable position;
  - at 320–390 px inline `grid-column: span 2` created a hidden implicit form column and clipped date/time/address fields;
  - global mobile navigation belonged to a higher ancestor stacking context and covered drawer actions.
- Fixes:
  - switched the partner shell to a horizontal, scrollable section bar through 991.98 px;
  - validated drawer geometry after 500 ms stable state;
  - forced a true one-column calendar form at widths up to 640 px;
  - lifted the main stacking context only while a partner calendar modal is open.
- Post-fix evidence:
  - `strict-final/dashboard-768.png`
  - `strict-final/calendar-drawer-320.png`
  - `strict-final/calendar-drawer-390.png`
  - `strict-final/calendar-drawer-768.png`

### Pass 3 — passed

- Six routes × five widths: HTTP 200 and 0 px horizontal overflow in every case.
- Search results: one result; ARIA expanded state and keyboard focus verified at every width.
- Mobile Today/Recent Clients panel switching verified at 320, 390 and 768 px.
- Calendar overlays: z-index and bottom-edge ownership verified at 320, 390 and 768 px; drawer owns the bottom interaction area.
- JavaScript console errors: 0.
- Django system check: passed.
- Full Django suite: 58/58 passed.
- `git diff --check`: passed.

## Remaining findings

No actionable P0, P1 or P2 finding remains in this partner-cabinet scope.

- [P3] Some Font Awesome glyphs have slightly different optical weight.
  - Location: section navigation and compact utility actions.
  - Impact: cosmetic only; alignment and recognition remain clear.
  - Follow-up: normalize icon family weight in the later global design-system pass.

## Implementation checklist

- [x] Dashboard rebuilt around the partner's primary task.
- [x] Shared strict system applied to every partner route.
- [x] Mobile, tablet and desktop navigation verified.
- [x] Forms, validation, tables, filters, empty states and semantic alerts verified.
- [x] Calendar overlay/drawer interaction and stacking defects fixed.
- [x] E-mail verification/security banner preserved.
- [x] Existing server behavior and authorization boundaries preserved.

final result: passed
