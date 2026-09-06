import { useState } from "react";

import type { DocumentResponse, Session } from "../types";

interface DocumentViewProps {
  data: DocumentResponse;
  sessions: Session[];
  canCreate: boolean;
  onCreateSession: () => Promise<void>;
  onOpenSession: (sessionId: string) => void;
}

export function DocumentView({
  data,
  sessions,
  canCreate,
  onCreateSession,
  onOpenSession,
}: DocumentViewProps) {
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  const submit = async () => {
    setBusy(true);
    try {
      await onCreateSession();
    } catch (reason) {
      setError(
        reason instanceof Error ? reason.message : "세션 생성에 실패했습니다.",
      );
    } finally {
      setBusy(false);
    }
  };

  return (
    <main className="document-view" tabIndex={-1}>
      <header className="document-header">
        <div>
          <div className="eyebrow">
            MAIN · REVISION {data.current_revision.number}
          </div>
          <h1>{data.document.title}</h1>
        </div>
        <button
          className="button"
          disabled={busy || !canCreate}
          type="button"
          onClick={() => void submit()}
        >
          새 세션
        </button>
      </header>
      {error && <p role="alert">{error}</p>}
      <article className="main-revision">
        <p>{data.current_revision.content}</p>
        {data.current_revision.citations.length > 0 && (
          <aside className="provenance" aria-label="Main revision provenance">
            <div className="eyebrow">PROVENANCE · TOSS</div>
            {data.current_revision.citations.map((citation, index) => (
              <strong key={index}>{citation.claim_anchor}</strong>
            ))}
            <span>제안 {data.current_revision.proposal_id}</span>
          </aside>
        )}
      </article>
      <section>
        <div className="section-heading">
          <h2>검토 세션</h2>
          <span>{sessions.length}</span>
        </div>
        {sessions.length === 0 ? (
          <p className="muted">아직 초안 세션이 없습니다.</p>
        ) : (
          <ul className="session-list">
            {sessions.map((session) => (
              <li key={session.id}>
                <button type="button" onClick={() => onOpenSession(session.id)}>
                  <strong>세션 {session.id.slice(0, 8)}</strong>
                  <span>{session.created_by}</span>
                </button>
              </li>
            ))}
          </ul>
        )}
      </section>
    </main>
  );
}
