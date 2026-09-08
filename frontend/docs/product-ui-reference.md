# SOT product UI reference

Global English-first interface for a consensus workspace. Root `index.html` is the IA draft (document canvas, session thread, evidence rail, toss, proposal). This document is the **layout and locale** contract the React app must follow. It is not a pixel clone of the HTML demo and not the beige/teal cutover chrome.

**Color, type, radius, and spacing come from [`apple/DESIGN.md`](../../apple/DESIGN.md)** and are adapted to the product surfaces in `frontend/src/styles/tokens.css`. When this file and the Apple reference disagree, the Apple reference wins unless SOT needs an accessibility or data-density adjustment.

## Product

SOT is a place where people toss a curated session, not a finished sentence. The UI should feel like Linear (density, quiet chrome) meeting a document canvas (Notion/GitHub docs): a readable main column, a persistent outline, and an evidence rail. Copy is direct. No “Shared Source of Truth” masthead. Brand mark is **SOT**; tagline is **Sessions as evidence**.

## Tokens

| Token | Value | Use |
| --- | --- | --- |
| `--canvas` | `oklch(0.18 0.005 285.823)` | Document reading area — the quietest surface |
| `--surface` | `oklch(0.21 0.006 285.885)` | Header, rails, side panels. Lighter than the canvas |
| `--surface-raised` | `oklch(0.235 0.007 285.885)` | Cards inside a panel |
| `--surface-hover` | `oklch(0.274 0.006 286.033)` | Pointer over a target |
| `--surface-selected` | `oklch(0.3 0.006 286.033)` | Lasting selection. Neutral, never a tinted accent |
| `--surface-strong` | `oklch(0.35 0.006 286.033)` | Avatar grounds |
| `--divider` | `oklch(1 0 0 / 8%)` | Structural separation |
| `--border` | `oklch(1 0 0 / 14%)` | Bounded controls, emphasised cards |
| `--ink` | `oklch(0.985 0 0)` | Everything meant to be read |
| `--ink-muted` | `oklch(0.705 0.015 286.067)` | "What is this" — meta, descriptions |
| `--ink-dim` | `oklch(0.552 0.016 285.938)` | Skippable — timestamps, eyebrows, placeholders |
| `--brand` | `oklch(0.65 0.16 255)` | Links and the one primary action per screen |
| `--brand-hover` / `--focus-ring` | `oklch(0.72 0.16 255)` / `…/ 40%` | Primary hover, `:focus-visible` |
| `--success` / `--success-tint` | `oklch(0.65 0.15 145)` / `… / 14%` | Approved, merged, published |
| `--danger` / `--danger-tint` | `oklch(0.704 0.191 22.216)` / `… / 14%` | Removed diff lines, errors |
| `--radius-sm`…`--radius-xl` | `6/8/10/14px` + `pill` | Controls, cards, panels |
| `--space-xs`…`--space-section` | `4/8/12/16/24/32/48px` | 4px base unit |
| `--header` | `56px` | App header height |
| `--font` | `"Inter", "Pretendard Variable", "Noto Sans KR", system-ui, sans-serif` | UI + Korean fallback |
| `--font-mono` | `"JetBrains Mono", ui-monospace, …` | Patch diffs, ids, tool names |

Type scale: `28/-0.6` document and issue titles · `22/-0.4` section headings · `16/-0.05` body · `14` rows, panels and buttons · `12` meta, and `12/+0.4` uppercase eyebrow. Five sizes, and **two weights only — 400 and 500**. There is no 18, no 20, no 40, and no semibold anywhere.

There are no shadows on in-page surfaces; depth is the surface ladder. Shadow appears only under something that floats and can be dismissed.

Do not use Newsreader or DM Sans as the product face, coral/teal cutover colors, a light canvas, or pure black.

## Sharing a session

Tossing is link-based, not addressed to a person. `POST .../bundles/{id}/tosses` returns a token **once**; `GET /tosses/{token}` is unauthenticated, so anyone holding the link can read the bundle. A workspace member opens the link and forks it into a workspace with `POST .../tosses/{token}/fork`.

Because the usual case is sharing inside your own workspace:

- The session side offers **Copy share link** as the primary action, not just "open".
- The fork destination defaults to the workspace you came from (`sot.workspace`), not the first in the list.
- The card states that anyone with the link can read it, and offers **Revoke link** (`DELETE .../tosses/{toss_id}`) — the token is the only access control there is.
- The token and toss id live in `?toss=` / `?tossId=` so a reload does not strand a live share link.

## Proposal length

Every required approver reads a proposal as a diff before it can merge, so content is capped at `PROPOSAL_CONTENT_LIMIT` (4000 characters). The cap lives in `backend/src/sot/consensus/domain.py` on `ProposalVersion`, which every create/revise path builds — including the agent's `sot_update` tool, which is the path that actually runs long. The agent's instructions state the limit so it aims short instead of discovering the rejection.

The client mirrors the number in `src/app/limits.ts`, checked against the generated OpenAPI `maxLength` by `limits.test.ts`. The session side shows a live counter and refuses to submit over the cap; a blank body proposes the bundle preview, which counts the same.

## Identity in the UI

Raw UUIDs never appear as content.

- `GET /workspaces/{id}/members` returns the roster with `display_name`. Membership alone is the gate — every member sees who else is in the workspace — and only the name is exposed, never the profile. `useDisplayName` resolves ids through it: **You** for yourself, the person's name otherwise, **Another member** only when they are genuinely off the roster.
- A session has no title in the API, so it is titled by its first user turn, falling back to its creation timestamp.
- Bundles get ordinal labels (`Bundle 1`); the id goes in `title`.
- An id a user must actually hand to someone (their own) is behind a copy button, never printed inline. Adding a member still takes a raw id because `AddWorkspaceMemberRequest` accepts only `user_id`.

## Layout (elevated from the HTML draft)

1. **Header** — 56px white bar: brand, breadcrumb, workspace, language, user, sign out.
2. **Document** — three columns: outline (220px) · document card (fluid, max 720px) · evidence/proposal rail (320px).
3. **Session** — thread (fluid) · curation/proposal side (340px). Thread is the conversation, not a form dump.
4. **Session list** — centered stack of session rows (from the HTML “branches” view).
5. **Toss** — shared-evidence card, destination workspace, Fork. No private session chrome.
6. **Proposal** — lives in the document rail and as a compact card on the session side; Approve and Merge stay separate.

Mobile: collapse outline and rail; keep the document/thread as the only column.

## Locale

- Default `en`. Korean is `ko`.
- Chrome, buttons, labels, empty states, and status strings go through i18next (`react-i18next`).
- Server-owned content (document title, turn text, proposal body) is not translated by the client.
- Switching language calls `i18n.changeLanguage` and must not reload the app shell.

## Libraries

Reuse the existing React + generated OpenAPI + TanStack Query + AG-UI stack. i18n uses `i18next` + `react-i18next`. Markdown uses `streamdown` (chat + document). Routing uses `react-router`. Do not add a second API client. Do not ship `index.html` as the app.

Screen IA, empty states, and first-run workspace flow: [`docs/superpowers/specs/2026-09-08-sot-frontend-ui-design.md`](../../docs/superpowers/specs/2026-09-08-sot-frontend-ui-design.md).
