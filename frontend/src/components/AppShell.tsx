import { useState } from "react";

import type { DocumentRecord, Session, User, Workspace } from "../types";

interface AppShellProps {
  user: User;
  workspaces: Workspace[];
  selectedWorkspaceId: string;
  onWorkspaceChange: (workspaceId: string) => void;
  onLogout: () => void;
  documents: DocumentRecord[];
  sessions: Session[];
  selectedDocumentId: string | null;
  children: React.ReactNode;
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
        <button
          className="brand"
          type="button"
          onClick={() =>
            props.selectedDocumentId &&
            props.onDocumentSelect(props.selectedDocumentId)
          }
        >
          <span>SOT</span>
          Shared Source of Truth
        </button>
        <div className="actor-switcher">
          <span>{props.user.display_name}</span>
          <button type="button" onClick={props.onLogout}>
            로그아웃
          </button>
        </div>
      </header>
      <div className="shell-body">
        <nav
          id="primary-navigation"
          className={navOpen ? "side-nav open" : "side-nav"}
        >
          <label>
            Workspace
            <select
              value={props.selectedWorkspaceId}
              onChange={(event) => props.onWorkspaceChange(event.target.value)}
            >
              {props.workspaces.map((workspace) => (
                <option key={workspace.id} value={workspace.id}>
                  {workspace.name}
                </option>
              ))}
            </select>
          </label>
          <div className="nav-label">DOCUMENTS</div>
          {props.documents.map((document) => (
            <button
              className={
                document.id === props.selectedDocumentId
                  ? "nav-item active"
                  : "nav-item"
              }
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
          {props.sessions.length > 0 && (
            <div className="nav-label">SESSIONS</div>
          )}
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
              세션 {session.id.slice(0, 8)}
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
              <input
                value={token}
                onChange={(event) => setToken(event.target.value)}
              />
            </label>
            <button type="submit">열기</button>
          </form>
        </nav>
        <div className="page-content">{props.children}</div>
      </div>
    </div>
  );
}
