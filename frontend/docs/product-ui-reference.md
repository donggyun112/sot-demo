# SOT product UI reference

Global English-first interface for a consensus workspace. Root `index.html` is the IA draft (document canvas, session thread, evidence rail, toss, proposal). This document is the visual and locale contract the React app must follow. It is not a pixel clone of the HTML demo and not the beige/teal cutover chrome.

## Product

SOT is a place where people toss a curated session, not a finished sentence. The UI should feel like Linear (density, quiet chrome) meeting a document canvas (Notion/GitHub docs): a readable main column, a persistent outline, and an evidence rail. Copy is direct. No “Shared Source of Truth” masthead. Brand mark is **SOT**; tagline is **Sessions as evidence**.

## Tokens

| Token | Value | Use |
| --- | --- | --- |
| `--bg` | `#F7F7F5` | App canvas |
| `--surface` | `#FFFFFF` | Header, cards, rails |
| `--ink` | `#111113` | Primary text |
| `--muted` | `#6B6B70` | Meta, labels |
| `--line` | `#E6E6E3` | Borders |
| `--accent` | `#5E6AD2` | Primary actions (Linear indigo, not Toss blue) |
| `--accent-weak` | `#EEF0FB` | Selected block, chips |
| `--danger` | `#C63B3B` | Naked / missing evidence |
| `--ok` | `#1F8A5B` | Merged / published |
| `--radius` | `10px` | Controls and cards |
| `--header` | `56px` | App header height |
| `--font` | `"Inter", "Pretendard Variable", "Noto Sans KR", system-ui, sans-serif` | UI + Korean fallback |

Do not use Newsreader, DM Sans as the product face, coral/teal cutover colors, or a dark navy top bar.

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

Reuse the existing React + generated OpenAPI + TanStack Query + AG-UI stack. i18n uses `i18next` + `react-i18next`. Do not add a second API client. Do not ship `index.html` as the app.
