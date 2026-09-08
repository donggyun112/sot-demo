---
version: alpha
name: SOT
description: "A dark product surface for a consensus document tool. The ground is a soft near-black — oklch(0.18) with a faint cool cast, never pure black — and surfaces climb a five-step ladder above it so a sidebar, a panel and a card separate by lightness rather than by lines. Borders are white at 8–14% alpha, so they read the same on every step. Type runs Inter at exactly two weights, 400 and 500: hierarchy comes from size and ink level, never from bold. Three ink levels only. The single chromatic accent is a blue at oklch(0.65 0.16 255), reserved for the brand mark, focus and one primary action per screen; success green and destructive red are the only other colors, and large areas of either use the same hue at 14% alpha. Derived from the Multica dark token set."

colors:
  canvas: "oklch(0.18 0.005 285.823)"
  surface: "oklch(0.21 0.006 285.885)"
  surface-raised: "oklch(0.235 0.007 285.885)"
  surface-hover: "oklch(0.274 0.006 286.033)"
  surface-selected: "oklch(0.3 0.006 286.033)"
  surface-strong: "oklch(0.35 0.006 286.033)"
  divider: "oklch(1 0 0 / 8%)"
  border: "oklch(1 0 0 / 14%)"
  ink: "oklch(0.985 0 0)"
  ink-muted: "oklch(0.705 0.015 286.067)"
  ink-dim: "oklch(0.552 0.016 285.938)"
  brand: "oklch(0.65 0.16 255)"
  brand-hover: "oklch(0.72 0.16 255)"
  focus-ring: "oklch(0.65 0.16 255 / 40%)"
  on-brand: "oklch(0.985 0 0)"
  success: "oklch(0.65 0.15 145)"
  success-tint: "oklch(0.65 0.15 145 / 14%)"
  danger: "oklch(0.704 0.191 22.216)"
  danger-tint: "oklch(0.704 0.191 22.216 / 14%)"

typography:
  title:
    fontFamily: Inter
    fontSize: 28px
    fontWeight: 500
    lineHeight: 1.2
    letterSpacing: -0.6px
  heading:
    fontFamily: Inter
    fontSize: 22px
    fontWeight: 500
    lineHeight: 1.25
    letterSpacing: -0.4px
  body:
    fontFamily: Inter
    fontSize: 16px
    fontWeight: 400
    lineHeight: 1.5
    letterSpacing: -0.05px
  body-emphasis:
    fontFamily: Inter
    fontSize: 16px
    fontWeight: 500
    lineHeight: 1.5
    letterSpacing: -0.2px
  label:
    fontFamily: Inter
    fontSize: 14px
    fontWeight: 400
    lineHeight: 1.5
    letterSpacing: 0
  button:
    fontFamily: Inter
    fontSize: 14px
    fontWeight: 500
    lineHeight: 1.2
    letterSpacing: 0
  caption:
    fontFamily: Inter
    fontSize: 12px
    fontWeight: 400
    lineHeight: 1.4
    letterSpacing: 0
  eyebrow:
    fontFamily: Inter
    fontSize: 12px
    fontWeight: 500
    lineHeight: 1.3
    letterSpacing: 0.4px
  mono:
    fontFamily: JetBrains Mono
    fontSize: 12px
    fontWeight: 400
    lineHeight: 1.5
    letterSpacing: 0

rounded:
  sm: 6px
  md: 8px
  lg: 10px
  xl: 14px
  pill: 9999px

spacing:
  xs: 4px
  sm: 8px
  md: 12px
  lg: 16px
  xl: 24px
  xxl: 32px
  section: 48px

components:
  button-primary:
    backgroundColor: "{colors.brand}"
    textColor: "{colors.on-brand}"
    typography: "{typography.button}"
    rounded: "{rounded.md}"
    padding: 0 16px
    height: 32px
  button-secondary:
    backgroundColor: "{colors.surface}"
    textColor: "{colors.ink}"
    borderColor: "{colors.border}"
    typography: "{typography.button}"
    rounded: "{rounded.md}"
    padding: 0 16px
    height: 32px
  button-quiet:
    backgroundColor: transparent
    textColor: "{colors.ink-muted}"
    typography: "{typography.button}"
    rounded: "{rounded.sm}"
    padding: 0 8px
    height: 30px
  chip:
    backgroundColor: "{colors.surface-selected}"
    textColor: "{colors.ink-muted}"
    borderColor: "{colors.border}"
    typography: "{typography.caption}"
    rounded: "{rounded.pill}"
    padding: 0 8px
    height: 22px
  chip-success:
    backgroundColor: "{colors.success-tint}"
    textColor: "{colors.success}"
    borderColor: "{colors.success}"
    typography: "{typography.caption}"
    rounded: "{rounded.pill}"
    padding: 0 8px
    height: 22px
  panel:
    backgroundColor: "{colors.surface}"
    borderColor: "{colors.divider}"
    textColor: "{colors.ink}"
    padding: 16px
  card:
    backgroundColor: "{colors.surface-raised}"
    borderColor: "{colors.divider}"
    textColor: "{colors.ink}"
    typography: "{typography.label}"
    rounded: "{rounded.lg}"
    padding: 12px
  row:
    backgroundColor: "{colors.surface}"
    borderColor: "{colors.divider}"
    textColor: "{colors.ink}"
    typography: "{typography.label}"
    rounded: "{rounded.lg}"
    padding: 12px 16px
  nav-item:
    backgroundColor: transparent
    textColor: "{colors.ink-muted}"
    typography: "{typography.label}"
    rounded: "{rounded.sm}"
    padding: 0 8px
    height: 30px
  nav-item-selected:
    backgroundColor: "{colors.surface-selected}"
    textColor: "{colors.ink}"
    typography: "{typography.label}"
    rounded: "{rounded.sm}"
    padding: 0 8px
    height: 30px
  text-input:
    backgroundColor: "{colors.surface-raised}"
    textColor: "{colors.ink}"
    borderColor: "{colors.divider}"
    typography: "{typography.label}"
    rounded: "{rounded.md}"
    padding: 0 12px
    height: 36px
  composer:
    backgroundColor: "{colors.surface}"
    textColor: "{colors.ink}"
    borderColor: "{colors.border}"
    typography: "{typography.body}"
    rounded: "{rounded.lg}"
    padding: 12px 16px
  diff-added:
    backgroundColor: "{colors.success-tint}"
    textColor: "{colors.success}"
    typography: "{typography.mono}"
  diff-removed:
    backgroundColor: "{colors.danger-tint}"
    textColor: "{colors.danger}"
    typography: "{typography.mono}"
  avatar:
    backgroundColor: "{colors.surface-strong}"
    textColor: "{colors.ink}"
    typography: "{typography.caption}"
    rounded: "{rounded.pill}"
  quote:
    backgroundColor: "{colors.surface-selected}"
    borderColor: "{colors.brand}"
    textColor: "{colors.ink}"
    typography: "{typography.label}"
---

## Overview

SOT is a place a team keeps one canonical design document and changes it by
argument. People read for long stretches and act in short bursts, so the
surface is quiet by default and speaks only where a decision is waiting.

The ground is `{colors.canvas}` — `oklch(0.18)`, a soft near-black with a faint
cool cast at hue 286. **Not pure black.** Pure black is harsh on an LCD and
leaves no room below the ground for anything to recede into. Above it, five
surface steps climb to `{colors.surface-selected}`; a sidebar, a panel, a card
and a selected row separate by *lightness*, not by drawing more lines.

Borders are white at low alpha — `{colors.divider}` at 8% and
`{colors.border}` at 14% — so the same border token reads correctly on every
step of the ladder. A fixed grey would be invisible on one step and heavy on
the next.

Type is Inter at **two weights only, 400 and 500**. There is no semibold and no
bold anywhere. Hierarchy comes from size and from which of the three ink levels
a run of text uses. Adding weight to make something important is the failure
mode this rule exists to prevent.

**Key characteristics:**
- Soft near-black ground; five-step surface ladder carries all hierarchy.
- Alpha borders, never fixed grey lines.
- Two font weights, three ink levels, five type sizes.
- One chromatic accent (`{colors.brand}`), one primary action per screen.
- Only two other colors exist: success and danger. Large areas of either use
  the same hue at 14% alpha, never a separate mixed tone.
- No shadows on in-page surfaces. Depth is lightness.

Derived from the Multica dark token set (`packages/ui/styles/tokens.css`, the
`.dark` block). What was taken: the surface ladder, the alpha borders, the
oklch neutral cast, the weight discipline, the radius scale. What was added: a
document title step, because a design document needs one and a task tool does
not.

## Colors

### Surface

The ladder is the whole hierarchy system. Each step is a *relationship*, not a
decoration.

- **Canvas** ({colors.canvas}): The document reading area — the quietest thing
  on screen, because it is what people look at longest.
- **Surface** ({colors.surface}): Sidebar and side panels. Deliberately
  *lighter* than the canvas: tools sit above the page, not behind it.
- **Surface Raised** ({colors.surface-raised}): A bounded card inside a panel.
- **Surface Hover** ({colors.surface-hover}): Pointer is over a target.
- **Surface Selected** ({colors.surface-selected}): A lasting selection — the
  open document in the sidebar, the paragraph a discussion is attached to.
- **Surface Strong** ({colors.surface-strong}): Avatar grounds and other small
  filled shapes that must read against a raised card.

**Selection is neutral.** A selected nav item, a chosen row and a status chip
all use `{colors.surface-selected}` with `{colors.ink}` — never a tinted
accent. Hover must never override selection: a selected item under the pointer
keeps its selected background.

### Border

- **Divider** ({colors.divider}): Structural separation — panel edges, header
  rules, the line under a card's meta row.
- **Border** ({colors.border}): A bounded control or an emphasised card.

### Text

Three levels. If a screen needs a fourth, the hierarchy is wrong.

- **Ink** ({colors.ink}): Everything a person is meant to read — headings,
  body, message text, row titles.
- **Ink Muted** ({colors.ink-muted}): Supporting text that answers "what is
  this" — metadata, descriptions, secondary labels.
- **Ink Dim** ({colors.ink-dim}): Text a reader may skip entirely —
  timestamps, counts, section eyebrows, placeholders.

### Semantic

- **Brand** ({colors.brand}): Brand mark, focus ring, links, and the single
  primary action on a screen. Never a background for selection, never an
  avatar, never a badge that isn't calling for action.
- **Brand Hover** ({colors.brand-hover}): The primary action under the pointer
  — one step lighter, same hue and chroma. Secondary and quiet buttons hover on
  the surface ladder instead, never on the brand.
- **Focus Ring** ({colors.focus-ring}): `:focus-visible` on every interactive
  element, as a 3px ring outside the control's own border. Keyboard focus is
  the one place the accent appears without being asked for.
- **Success** ({colors.success}): Approved, merged, adopted as evidence.
- **Danger** ({colors.danger}): Removed lines in a diff, form errors,
  destructive confirmation.

Large areas of success or danger use `{colors.success-tint}` /
`{colors.danger-tint}` — the same hue at 14% alpha over whatever surface is
underneath. Do not mix a separate opaque tone for a tint; it will be wrong on
one step of the ladder.

## Typography

### Font family

- **Inter** — the whole interface. CJK falls back to `Pretendard Variable`,
  then `Noto Sans KR`, then the system stack.
- **JetBrains Mono** — diffs, identifiers, counts, tool names, file names.
  Nowhere else.

### Scale

| Token | Size | Weight | Use |
|---|---|---|---|
| `{typography.title}` | 28px | 500 | Document title, issue title |
| `{typography.heading}` | 22px | 500 | Section heading inside a document |
| `{typography.body}` | 16px | 400 | Document body, chat messages |
| `{typography.body-emphasis}` | 16px | 500 | A card's own title |
| `{typography.label}` | 14px | 400 | Rows, panel content, form fields |
| `{typography.button}` | 14px | 500 | Every button |
| `{typography.caption}` | 12px | 400 | Metadata, timestamps, hints |
| `{typography.eyebrow}` | 12px | 500 | Uppercase section header, +0.4px |
| `{typography.mono}` | 12px | 400 | Diffs, ids, counts |

Five sizes carry the product: 28, 22, 16, 14, 12. There is no 18, no 20, no 32
and no 40. If two things in one block need to differ, change the ink level
before reaching for a size.

### Principles

- **Two weights.** 400 for reading, 500 for anything that labels or acts.
  `font-weight: 600` and above do not appear in this system.
- **Negative tracking on the two display steps only.** Body and below sit at
  −0.05px or 0.
- **The eyebrow is the one positive-tracking style** (+0.4px, uppercase). That
  contrast is what marks it as a taxonomy label rather than content.
- **Mono only where a value is meant to be copied or compared.**

## Layout

### Spacing

Base unit **4px**. Named steps: `{spacing.xs}` 4 · `{spacing.sm}` 8 ·
`{spacing.md}` 12 · `{spacing.lg}` 16 · `{spacing.xl}` 24 · `{spacing.xxl}` 32
· `{spacing.section}` 48. Intermediate multiples of 4 are allowed; anything not
a multiple of 4 is a bug.

Spacing carries meaning: 4px binds an icon to its label, 8px groups a row's
parts, 16px separates blocks, 24px separates named sections inside a panel.

### Frame

| Region | Width | Notes |
|---|---|---|
| Sidebar | 220–240px | Workspace, inbox, documents, sessions |
| Header | 52–56px | Identity and state of the current object only |
| Document column | max 680px | Centred in the canvas |
| Side panel | 300–340px | What you can do here |
| Conversation column | max 720px | Left-aligned, not centred |

### Containers, in order of preference

1. Spacing alone.
2. A single divider.
3. A change of surface step.
4. A bordered card.

Reach for the last only when a group can be acted on as a unit.

## Elevation

There are no shadows on in-page surfaces. Depth is the surface ladder.

Shadow appears only under something that genuinely floats above the page and
can be dismissed — a dialog, a dropdown, a popover. Those use a large soft
shadow with `{colors.surface-raised}` as the fill.

## Shapes

| Token | Value | Use |
|---|---|---|
| `{rounded.sm}` | 6px | Nav items, small chips, icon buttons |
| `{rounded.md}` | 8px | Buttons, inputs, selects |
| `{rounded.lg}` | 10px | Cards, rows, code blocks |
| `{rounded.xl}` | 14px | A panel-sized container |
| `{rounded.pill}` | 9999px | Status chips, avatars, counters |

No other radii. `12px` and `16px` in particular are not part of this scale.

## Components

### Buttons

One `{components.button-primary}` per screen — the single thing the screen is
for. Everything else is `{components.button-secondary}` or
`{components.button-quiet}`. Two primaries on one screen means the screen has
two purposes and should be split.

An action that cannot run yet stays visible, disabled, with a line of
`{typography.caption}` beneath it saying why. Hiding it teaches the reader that
the capability does not exist.

### Chips

`{components.chip}` for state that is merely informational. `{components.chip-success}`
for a state that closes something — approved, merged, adopted. There is no
brand-coloured chip.

### Diff

`{components.diff-added}` and `{components.diff-removed}` in
`{typography.mono}`, full-bleed to the container's padding so the tint reads as
a band rather than a floating label.

## Do's and don'ts

### Do

- Separate regions by climbing the surface ladder.
- Keep the canvas quieter than the panels around it.
- Use alpha borders so one token works on every step.
- Let size and ink level carry hierarchy.
- State why a disabled action is disabled.
- Keep the accent for the brand mark, focus, links, and one action.

### Don't

- Use pure black, or a sixth surface step.
- Use `font-weight: 600` or above.
- Introduce a fourth ink level.
- Tint selection with the accent.
- Colour an avatar or a decorative badge with the accent.
- Add a shadow to something that does not float.
- Write the product's own model into the interface as explanatory prose. Copy
  states consequences ("anyone with the link can read this"), never doctrine.

## Known gaps

- **Light mode is not defined.** The Multica source has one; it was not carried
  over because SOT has no light surface yet.
- **Charts are not defined.** The source has a five-step brand-hue ramp if one
  is ever needed.
- **Warning and info** exist in the source (`oklch(0.70 0.16 85)`,
  `oklch(0.65 0.18 250)`) and were deliberately left out. Add them only when a
  screen genuinely has a third and fourth state, not for variety.
