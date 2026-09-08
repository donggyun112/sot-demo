# SOT frontend UI

- Status: implementation source for the product React app
- Date: 2026-09-08
- Visual tokens: [`frontend/docs/product-ui-reference.md`](../../../frontend/docs/product-ui-reference.md)
- IA draft: repo-root `index.html` (filled document / session / list) and `msbd-real.html` (empty document / new session / fork)
- Backend contract: [`2026-08-30-sot-v1-design.md`](./2026-08-30-sot-v1-design.md) §17
- Do not ship `index.html` as the app. Do not clone Toss-blue demo chrome.

## 1. Product

SOT is a consensus workspace. People toss a curated session, not a finished sentence. Brand mark **SOT**. Tagline **Sessions as evidence**. Copy is English-first; Korean is a locale, not the default.

After login the user enters a **workspace** (Linear / Notion / Jira). They never land on a filled document canvas with zero workspaces.

## 2. Routes

```text
/login
/workspaces/new
/w/:workspaceId
/w/:workspaceId/documents/:documentId
/w/:workspaceId/documents/:documentId/sessions
/w/:workspaceId/sessions/:sessionId
/s/:shareToken
/w/:workspaceId/proposals/:proposalId
```

Search params (preserve across refresh): `block`, `turn`, `panel`.

Entry:

1. Unauthenticated → `/login`.
2. Authenticated and zero workspaces → `/workspaces/new`.
3. Authenticated with workspaces → last used `/w/:workspaceId`, else the first workspace.
4. Workspace home is the **document list**, not a document body.

`POST /api/v1/workspaces/{id}/documents` wraps existing `CreateDocument` (`document.create`). Empty title **Untitled**, empty content. Then the user starts a session on that document. Session create remains `POST .../documents/{id}/sessions`.

## 3. Screens

### 3.1 Login

Google Identity Services button plus **Continue without Google** (`POST /api/v1/auth/local`). No actor/role switcher.

### 3.2 Create workspace

Centered form: workspace name, primary submit. Same first-run as Linear/Notion. Success → `/w/:id`. Header already shows the signed-in user.

### 3.3 Header (all signed-in screens)

56px white bar, left to right:

- Workspace switcher (top-left). Current name. Menu: other workspaces, Create workspace.
- Brand **SOT** + tagline.
- Breadcrumb for the current screen.
- Members, if `workspace.manage`.
- Language `en` | `ko` (`i18n.changeLanguage`, no shell reload).
- User display name links to `/me`. Sign out.

Demo-bar from the HTML prototype is not product chrome.

### 3.4 Document list (`/w/:workspaceId`)

Centered stack (HTML `branches` / `docs` layout, max 640px).

- Empty: heading + copy from the empty-document draft: the canvas is not a typing surface; a session decision arrives with evidence. No fake create-document button.
- Rows: title, path/meta, session chips, status (published / empty). Click opens the document.

### 3.5 Document (`/w/:workspaceId/documents/:id`)

Three columns: outline 220px · document card max 720px · evidence rail 320px.

- Body is `revision.content` rendered as Markdown.
- Outline is ATX headings in that Markdown. Selecting a heading sets `?block=`.
- Rail: citations whose `claim_anchor` matches the selected heading. If none: naked empty copy + “Start a session from this section” which creates a session on **this document** (not a new document).
- Header chip for published/current revision. Action: session list.

Mobile ≤960px: one column; outline/rail become a right sheet when `panel` is set.

### 3.6 Session list

Centered rows for `GET .../documents/{id}/sessions`. Status chips: original / unmerged / private / shared as the API provides. Click opens the session. Document row at the top returns to the document.

### 3.7 Session

Two columns: thread 1fr · side 340px.

- Thread: curated turns with Drop / Edit / Join (`POST .../curation-ops`), then AG-UI `AgentChat` Markdown. Tool calls stay cards.
- Branches in `?branch=` / `?compare=`. New branch opens a compare pane with agree/conflict counts (shared-session chrome).
- Side: bundle preview, publish, toss, proposal — `session.participate`.

### 3.8 Toss (`/s/:shareToken`)

Public bundle card. No private session chrome. Logged-in Fork posts to a destination workspace (`session.participate` implied by being able to write a session). Anonymous users see sign-in.

### 3.9 Proposal (`/w/:workspaceId/proposals/:proposalId`)

Patch against current document revision (`linePatch`), citations, required approvers, version decisions. **Approve** / **Reject** = `session.participate` on `open`. **Merge** = `document.publish` on `approved`.

### 3.10 Profile (`/me`)

`GET /api/v1/me`: display name, email, user id. Current workspace role and permission chips from `GET .../members/me`. Workspace list.

### 3.11 Members (`/w/:workspaceId/members`)

`workspace.manage` only. Shows the current membership and `POST .../members` to add a user id with role `member`.

### 3.12 Permission gating

| Permission | UI |
| --- | --- |
| `workspace.manage` | Members |
| `document.create` | New document on the empty list |
| `document.read` | Document list and body |
| `document.publish` | Proposal merge |
| `session.create` | Start / new session |
| `session.read` | Session list, preview |
| `session.participate` | Agent composer, publish, toss, propose, approve |

## 4. Empty states (from the HTML drafts)

| State | Copy / action |
| --- | --- |
| Zero workspaces | Create workspace form |
| Zero documents | List empty; do not POST a document |
| Document with no headings | Single untitled block |
| Heading with no citation | Naked rail; start session on this document |
| Session with no cite | Side: no document link |
| Toss inbox empty | Empty card (when toss UI ships) |

## 5. Libraries

Reuse: React 19, Vite, TanStack Query, `openapi-fetch` + `openapi-react-query`, `@ag-ui/client` + `@ag-ui/pydantic-ai`, zod, GIS script.

Add:

| Package | Why |
| --- | --- |
| `react-router` | Routes above |
| `i18next` + `react-i18next` | Chrome / empty / buttons. Server-owned title, turn, proposal body stay raw |
| `streamdown` | Markdown for streaming chat and static document/proposal |
| `@streamdown/code` + `shiki` | Fenced code |
| `@streamdown/cjk` | Korean text |

Do not add: Tailwind, a second API client, assistant-ui / CopilotKit chrome, Tiptap, Zustand, `react-markdown` beside Streamdown, KaTeX, Mermaid (until a document actually stores diagrams).

Style Streamdown through `components` mapped to CSS Modules. Tokens stay CSS variables from the product-ui-reference table (`--bg #F7F7F5`, `--accent #5E6AD2`, Inter then Pretendard Variable then Noto Sans KR).

## 6. State

- Auth identity: `AuthSession` + `useSyncExternalStore` (already).
- Server: TanStack Query via `createAPI`.
- Selection: URL search params only.
- i18n language: `localStorage` key `sot.locale`.
- Last workspace: `localStorage` key `sot.workspace`.

No global store.

## 7. Tests

Existing login tests must keep passing (Continue without Google, GIS credential, no actor switcher). Add coverage for: zero workspaces → create form; workspace with documents → list; opening a document renders revision markdown; empty document list copy.

## 8. Out of scope this slice

- Pixel clone of `index.html`
- Document-create HTTP
- Curation tool UI beyond AgentChat tool cards
- Proposal approve/merge polish (route + card shell only if the list/document path is done)
- Shipping the HTML files as routes
