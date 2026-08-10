# Design QA — IESA member cabinet strict redesign

## Comparison target

- Source visual truth: `docs/audits/2026-08-10-iesa-ux/full-site-pass-04-member/source-style/`
  - `home-390.png`, `login-390.png`, `register-1440.png`
- Browser-rendered implementation: `docs/audits/2026-08-10-iesa-ux/full-site-pass-04-member/strict-final/`
  - `profile-390-final.png`, `edit-390-unified.png`, `profile-390-spacing-fix.png`, `profile-1440-final.png`
- Full-view comparison evidence: `docs/audits/2026-08-10-iesa-ux/full-site-pass-04-member/strict-final/comparisons/`
  - `home-profile-390-normalized.png`
  - `login-edit-390-normalized.png`
  - `register-profile-1440.png`
- Focused region evidence:
  - `profile-390-spacing-fix.png` — shared left/right grid and PIN separation.
  - `edit-390-unified.png` — unified settings surface, tabs and form fields.
  - `strict-final/profile-390-pin-open.png` and `strict-v1/profile-390-qr-v2.png` — disclosure and QR overlay states.

The source and implementation are different product screens, so this is a design-system comparison rather than a pixel-identical clone. It verifies the IESA palette, typography, controls, surface treatment and density while allowing the cabinet's information architecture to differ.

## Viewport and normalization

- Mobile source captures: 390 × 900 px, CSS viewport 390 × 900, device scale factor 1.
- Mobile implementation captures: 390 × 844 px, CSS viewport 390 × 844, device scale factor 1.
- For equal-size comparison, the source was top-cropped to 390 × 844 without resampling. No density scaling was used.
- Desktop source and implementation: 1440 × 900 px, CSS viewport 1440 × 900, device scale factor 1.
- Responsive browser checks also covered widths 320, 768 and 1920 px.
- State: authenticated ordinary IESA member with verified e-mail, active membership, realistic posts, visits and unread notifications.

## Required fidelity surfaces

- Fonts and typography: the existing IESA sans/mono pairing, strong heading weight and compact utility labels are preserved. Cabinet section headings were reduced to a restrained scale so generic mobile `h2` rules cannot inflate them.
- Spacing and layout rhythm: all mobile top-level surfaces now share a 16 px content edge. The profile completion panel, stat group and PIN card use consistent 16 px vertical separation. Notification rows and stat cells intentionally share one enclosing surface.
- Colors and tokens: near-black canvas, white hierarchy and one red brand accent match IESA. Green, amber and red are limited to semantic states. Decorative multi-color glows and purple calendar accents were removed.
- Image quality and assets: the existing IESA logo, user avatar, generated QR endpoint and Font Awesome icon set are reused. No emoji, fake SVG, CSS drawing or placeholder visual was introduced.
- Copy and content: labels are task-oriented and concise. Security copy explains that changing a confirmed e-mail requires confirmation again. Empty calendar and notification states include clear next actions.

## Findings

No actionable P0, P1 or P2 findings remain in the final pass.

- [P3] Some icon shapes have small optical-weight differences because the existing Font Awesome set mixes solid and brand icons.
  - Location: profile quick navigation and Telegram status.
  - Impact: minor polish only; icons remain aligned, recognizable and accessible.
  - Follow-up: normalize icon family/weight during the later site-wide design-system pass.

## Comparison history

### Pass 1 — blocked

- Earlier evidence: `full-site-pass-04-member/after-valid/profile-390-top.png`, `profile-1440-top.png`, `edit-390-top.png`.
- P1 findings: visually fragmented dashboard, excessive nested cards, glow-heavy accents, oversized PIN treatment and inconsistent density compared with IESA auth/home surfaces.
- Fixes: rebuilt the visual hierarchy around one restrained canvas, thin dividers, grouped stat cells, compact semantic badges, quieter PIN/QR treatments, and a unified settings form.
- Post-fix evidence: `strict-v1/profile-390-top-v2.png`, `strict-v1/edit-390-top.png`.

### Pass 2 — blocked

- P2 findings: Bootstrap negative row gutter cancelled the intended gap between the stats group and PIN card; member cards extended 10 px beyond the shared mobile grid; an unclosed `#stats-section` wrapper nested the partner application container; the edit form had an unnecessary second inset.
- Fixes: closed the structural wrapper, reset mobile row gutters, standardized 16 px edges/gaps, removed per-card bottom margins inside the ordered mobile grid, and made the edit header/tabs/form one continuous surface.
- Post-fix evidence: `strict-final/profile-390-spacing-fix.png`, `strict-final/edit-390-unified.png`.

### Pass 3 — passed

- Side-by-side evidence: `strict-final/comparisons/home-profile-390-normalized.png`, `login-edit-390-normalized.png`, `register-profile-1440.png`.
- No horizontal overflow at 320, 390, 768, 1440 or 1920 px on profile, edit profile, calendar or notifications.
- Primary interactions tested: QR open/close, PIN disclosure, edit tabs/scroll, dirty-form save dock.
- Browser console and page errors checked: none.
- Django system check: passed.
- Django tests: 58 passed.

## Open questions

- None blocking. The home page is intentionally not treated as a final design target; its own redesign remains a separate site-wide task.

## Implementation checklist

- [x] Strict visual system applied across the ordinary member cabinet routes.
- [x] Mobile/desktop responsive geometry verified.
- [x] Key states and interactions verified.
- [x] Structural wrapper and Bootstrap gutter defects fixed.
- [x] Functional/security improvements retained.

final result: passed
