# Predvestnik UI implementation gates

These are owner-approved acceptance criteria for the production redesign.

## Readability

- Secondary dates, hints, history timestamps and market-volume values must stay
  readable on a dim phone and outdoors; never use near-black text on black.
- Verify contrast on the VIP screen, chest explanation, history and exchange.

## Selected states

- Wallet amount cards need one unmistakable selected state with accent outline.
- Exchange Buy/Sell must be a real segmented control or equally explicit active
  state, not two visually identical labels.

## Mobile ergonomics

- Every interactive control has at least a 44×44 CSS-pixel hit area, including
  VIP weekday markers and appearance tabs such as Void/Ash.
- The visible glyph may be smaller; the tap target may not be.

## Visual hierarchy

- The “large update is not released” notice in More is supporting information,
  not the primary CTA. Use a restrained dark surface with accent border/text so
  Top up, What's new and Settings remain the first navigation targets.

## Reward moments

- Every chest, including one-star, must feel valuable: staged reveal, internal
  glow, particles, depth/shadow and restrained pulse motion.
- Respect `prefers-reduced-motion` and never delay delivery or hide the server
  result behind animation.

## Monolithic composition

- Screens must read as one continuous scene. Avoid a rounded container around
  every paragraph, statistic and row; use spacing, type scale, alignment and
  one or two deliberate surfaces to group content.
- Borders are separators of meaning, not default decoration. Hairlines must be
  low-contrast and may not outline every nested element.
- The bottom navigation belongs to the canvas: no floating capsule inside a
  second floating capsule. Its active item must remain obvious without becoming
  the loudest shape on screen.

## Hierarchy and consistency

- Reserve the theme accent for the primary action, current selection and short
  success feedback. Status copy, decorative particles and secondary actions
  must not compete with that accent.
- Navigation naming is canonical across every screen (`Профиль`, `Игры`,
  `Образы`, `Ещё`); singular/plural drift is a release defect.
- A screen has one primary heading and one primary action. Repeated oversized
  labels, duplicate balance summaries and multiple equally bright CTAs must be
  collapsed into one clear reading path.
- Empty and unavailable states explain the next useful action in one sentence;
  they must not leave large decorative dead zones or look like an error.

## Financial clarity

- The exchange chart must name its time range and expose enough scale/context
  to distinguish real market data from decoration.
- Buy/Sell state, amount, expected units, fee, slippage and final confirmation
  are visually separate. Destructive Sell styling may not reuse the positive
  Buy treatment.
- Wallet package selection has one source of truth: the summary and package
  grid may not appear to show two different selected amounts.

## Theme-ready structure

- Cosmetics may change semantic tokens (`canvas`, `surface`, `text`, `accent`,
  `glow`, `particles`, `motion`) but not information order, hit areas, contrast
  floor or component geometry.
- Decorative layers never sit between content and interaction. Every theme is
  checked at 320 px and 390 px with long names, four-digit balances and reduced
  motion.

These gates apply to both the current redesign implementation and the upcoming
player-exchange UI. Automated contrast, active-state, hit-target and reduced-
motion checks must accompany visual review at phone widths.
