import { useState } from "react";

import type { ActorId, DocumentRecord, Session } from "../types";

interface AppShellProps {
  actor: ActorId;
  users: ActorId[];
  documents: DocumentRecord[];
  sessions: Session[];
  selectedDocumentId: string | null;
  children: React.ReactNode;
  onActorChange: (actor: ActorId) => void;
  onDocumentSelect: (documentId: string) => void;
  onSessionSelect: (sessionId: string) => void;
  onTossOpen: (token: string) => void;
}

export function AppShell(props: AppShellProps) {
  const [navOpen, setNavOpen] = useState(false);
  const [token, setToken] = useState("");

  return (
    <div className="app-shell">
      <header className="topbar">
        <button
          className="nav-toggle"
          type="button"
          aria-expanded={navOpen}
          aria-controls="primary-navigation"
          onClick={() => setNavOpen((open) => !open)}
        >
          메뉴
        </button>
        <button className="brand" type="button" onClick={() => props.selectedDocumentId && props.onDocumentSelect(props.selectedDocumentId)}>
          <span>SOT</span>
          Shared Source of Truth
        </button>
        <label className="actor-switcher">
          작업자
          <select value={props.actor} onChange={(event) => props.onActorChange(event.target.value as ActorId)}>
            {props.users.map((user) => (
              <option key={user} value={user}>
                {user === "alice" ? "Alice" : "Bob"}
              </option>
            ))}
          </select>
        </label>
      </header>
      <div className="shell-body">
        <nav id="primary-navigation" className={navOpen ? "side-nav open" : "side-nav"}>
          <div className="nav-label">DOCUMENTS</div>
          {props.documents.map((document) => (
            <button
              className={document.id === props.selectedDocumentId ? "nav-item active" : "nav-item"}
              key={document.id}
              type="button"
              onClick={() => {
                props.onDocumentSelect(document.id);
                setNavOpen(false);
              }}
            >
              {document.title}
            </button>
          ))}
          {props.sessions.length > 0 && <div className="nav-label">SESSIONS</div>}
          {props.sessions.map((session) => (
            <button
              className="nav-item session"
              key={session.id}
              type="button"
              onClick={() => {
                props.onSessionSelect(session.id);
                setNavOpen(false);
              }}
            >
              {session.title}
            </button>
          ))}
          <form
            className="toss-opener"
            onSubmit={(event) => {
              event.preventDefault();
              if (token.trim()) props.onTossOpen(token.trim());
            }}
          >
            <label>
              Toss token
              <input value={token} onChange={(event) => setToken(event.target.value)} />
            </label>
            <button type="submit">열기</button>
          </form>
        </nav>
        <div className="page-content">{props.children}</div>
      </div>
    </div>
  );
}
