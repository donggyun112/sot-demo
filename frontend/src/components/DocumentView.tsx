import { useState } from "react";

import type { DocumentResponse } from "../types";

interface DocumentViewProps {
  data: DocumentResponse;
  onCreateSession: (title: string) => Promise<void>;
  onOpenSession: (sessionId: string) => void;
}

export function DocumentView({ data, onCreateSession, onOpenSession }: DocumentViewProps) {
  const [creating, setCreating] = useState(false);
  const [title, setTitle] = useState("");
  const [busy, setBusy] = useState(false);

  const submit = async (event: React.FormEvent) => {
    event.preventDefault();
    if (!title.trim()) return;
    setBusy(true);
    try {
      await onCreateSession(title.trim());
      setTitle("");
      setCreating(false);
    } finally {
      setBusy(false);
    }
  };

  return (
    <main className="document-view" tabIndex={-1}>
      <header className="document-header">
        <div>
          <div className="eyebrow">MAIN · REVISION {data.current_revision.number}</div>
          <h1>{data.document.title}</h1>
        </div>
        <button className="button" type="button" onClick={() => setCreating(true)}>
          새 세션
        </button>
      </header>
      {creating && (
        <form className="inline-form" onSubmit={(event) => void submit(event)}>
          <label>
            세션 제목
            <input value={title} onChange={(event) => setTitle(event.target.value)} autoFocus />
          </label>
          <button className="button" disabled={busy} type="submit">
            세션 만들기
          </button>
        </form>
      )}
      <article className="main-revision">
        <p>{data.current_revision.content}</p>
        {data.provenance && (
          <aside className="provenance" aria-label="Main revision provenance">
            <div className="eyebrow">PROVENANCE · TOSS</div>
            <strong>{data.provenance.cite.summary}</strong>
            <span>제안자 {data.provenance.proposal.created_by}</span>
          </aside>
        )}
      </article>
      <section>
        <div className="section-heading">
          <h2>검토 세션</h2>
          <span>{data.sessions.length}</span>
        </div>
        {data.sessions.length === 0 ? (
          <p className="muted">아직 초안 세션이 없습니다.</p>
        ) : (
          <ul className="session-list">
            {data.sessions.map((session) => (
              <li key={session.id}>
                <button type="button" onClick={() => onOpenSession(session.id)}>
                  <strong>{session.title}</strong>
                  <span>{session.owner_id}</span>
                </button>
              </li>
            ))}
          </ul>
        )}
      </section>
    </main>
  );
}
