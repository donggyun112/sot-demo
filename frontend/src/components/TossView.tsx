import { useState } from "react";

import type { SOTApi } from "../api";
import type { ActorId, TossViewResponse } from "../types";

interface TossViewProps {
  actor: ActorId;
  api: SOTApi;
  view: TossViewResponse;
  onForked: (sessionId: string) => void;
}

export function TossView({ actor, api, view, onForked }: TossViewProps) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  const fork = async () => {
    setBusy(true);
    setError("");
    try {
      const { branch } = await api.forkToss(view.toss.token);
      onForked(branch.session_id);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Fork에 실패했습니다.");
    } finally {
      setBusy(false);
    }
  };

  return (
    <main className="toss-view" tabIndex={-1}>
      <div className="eyebrow">PUBLIC TOSS</div>
      <h1>{view.cite.summary}</h1>
      <p className="muted">Alice가 선별한 근거 묶음 · 읽기는 로그인 없이 가능합니다.</p>
      <ol className="evidence-list">
        {view.turns.map((turn) => (
          <li key={turn.id}>
            <span>{turn.role}</span>
            <p>{turn.content}</p>
          </li>
        ))}
      </ol>
      <button className="button" disabled={busy} type="button" onClick={() => void fork()}>
        {actor === "bob" ? "Bob으로 fork" : "Alice로 fork"}
      </button>
      {error && <p role="alert">{error}</p>}
    </main>
  );
}
