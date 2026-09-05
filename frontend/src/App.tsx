import { useCallback, useEffect, useMemo, useState } from "react";

import { ApiError, SOTApi } from "./api";
import { AppShell } from "./components/AppShell";
import { DocumentView } from "./components/DocumentView";
import { SessionWorkspace } from "./components/SessionWorkspace";
import { TossView } from "./components/TossView";
import type {
  ActorId,
  BootstrapResponse,
  DocumentResponse,
  SessionResponse,
  TossViewResponse,
} from "./types";

const DEFAULT_API_BASE = import.meta.env.VITE_API_BASE ?? "/api/v1";

export function App({ apiBase = DEFAULT_API_BASE }: { apiBase?: string }) {
  const [actor, setActor] = useState<ActorId>("alice");
  const [bootstrap, setBootstrap] = useState<BootstrapResponse | null>(null);
  const [documentId, setDocumentId] = useState<string | null>(null);
  const [document, setDocument] = useState<DocumentResponse | null>(null);
  const [session, setSession] = useState<SessionResponse | null>(null);
  const [toss, setToss] = useState<TossViewResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const api = useMemo(() => new SOTApi(apiBase, actor), [actor, apiBase]);

  const describeError = (reason: unknown) => {
    if (reason instanceof ApiError) return `${reason.code}: ${reason.message}`;
    return reason instanceof Error ? reason.message : "요청을 완료하지 못했습니다.";
  };

  const loadBootstrap = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      const data = await api.bootstrap();
      setBootstrap(data);
      setDocumentId((current) => current ?? data.documents[0]?.id ?? null);
    } catch (reason) {
      setError(describeError(reason));
    } finally {
      setLoading(false);
    }
  }, [api]);

  const loadDocument = useCallback(
    async (id: string) => {
      setLoading(true);
      setError("");
      try {
        setDocument(await api.getDocument(id));
        setDocumentId(id);
        setSession(null);
        setToss(null);
      } catch (reason) {
        setError(describeError(reason));
      } finally {
        setLoading(false);
      }
    },
    [api],
  );

  const loadSession = useCallback(
    async (id: string) => {
      setLoading(true);
      setError("");
      try {
        setSession(await api.getSession(id));
        setToss(null);
      } catch (reason) {
        setError(describeError(reason));
      } finally {
        setLoading(false);
      }
    },
    [api],
  );

  const openToss = useCallback(
    async (token: string) => {
      setLoading(true);
      setError("");
      try {
        setToss(await api.getToss(token));
      } catch (reason) {
        setError(describeError(reason));
      } finally {
        setLoading(false);
      }
    },
    [api],
  );

  useEffect(() => {
    void loadBootstrap();
  }, [loadBootstrap]);

  useEffect(() => {
    if (documentId && !session && !toss) void loadDocument(documentId);
  }, [documentId, loadDocument, session, toss]);

  useEffect(() => {
    if (session && !toss) void loadSession(session.session.id);
  }, [actor]); // Re-resolve actor-scoped branch data after switching identity.

  const createSession = async (title: string) => {
    if (!documentId) return;
    const created = await api.createSession(documentId, title);
    setDocument((current) =>
      current ? { ...current, sessions: [...current.sessions, created.session] } : current,
    );
    await loadSession(created.session.id);
  };

  const users = bootstrap?.users ?? (["alice", "bob"] as ActorId[]);

  return (
    <AppShell
      actor={actor}
      users={users}
      documents={bootstrap?.documents ?? []}
      sessions={document?.sessions ?? []}
      selectedDocumentId={documentId}
      onActorChange={setActor}
      onDocumentSelect={(id) => void loadDocument(id)}
      onSessionSelect={(id) => void loadSession(id)}
      onTossOpen={(token) => void openToss(token)}
    >
      {loading && <div className="loading" role="status">동기화 중…</div>}
      {error && (
        <div className="error-panel" role="alert">
          <p>{error}</p>
          <button className="button" type="button" onClick={() => void loadBootstrap()}>
            다시 시도
          </button>
        </div>
      )}
      {!loading && !error && bootstrap?.documents.length === 0 && (
        <div className="empty-state">
          <div className="eyebrow">EMPTY WORKSPACE</div>
          <h1>아직 공유 문서가 없습니다</h1>
          <p>백엔드 seed가 생성되면 여기에 main revision이 표시됩니다.</p>
        </div>
      )}
      {!loading && !error && toss && (
        <TossView
          actor={actor}
          api={api}
          view={toss}
          onForked={(sessionId) => void loadSession(sessionId)}
        />
      )}
      {!loading && !error && !toss && session && (
        <SessionWorkspace
          actor={actor}
          api={api}
          apiBase={apiBase}
          detail={session}
          onChanged={() => void loadSession(session.session.id)}
          onOpenToss={(token) => void openToss(token)}
          onPublished={() => documentId && void api.getDocument(documentId).then(setDocument)}
        />
      )}
      {!loading && !error && !toss && !session && document && (
        <DocumentView
          data={document}
          onCreateSession={createSession}
          onOpenSession={(id) => void loadSession(id)}
        />
      )}
    </AppShell>
  );
}
