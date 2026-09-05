import { useEffect, useMemo, useState } from "react";

import type { SOTApi } from "../api";
import type { ActorId, Cite, SessionResponse } from "../types";
import { AgentChat } from "./AgentChat";
import { ProposalView } from "./ProposalView";

interface SessionWorkspaceProps {
  actor: ActorId;
  api: SOTApi;
  apiBase: string;
  detail: SessionResponse;
  onChanged: () => void;
  onOpenToss: (token: string) => void;
  onPublished: () => void;
}

export function SessionWorkspace({
  actor,
  api,
  apiBase,
  detail,
  onChanged,
  onOpenToss,
  onPublished,
}: SessionWorkspaceProps) {
  const ownedBranch = detail.branches.find((branch) => branch.owner_id === actor);
  const [branchId, setBranchId] = useState(ownedBranch?.id ?? detail.branches[0]?.id ?? "");
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [summary, setSummary] = useState("");
  const [proposalText, setProposalText] = useState("");
  const [newCite, setNewCite] = useState<Cite | null>(null);
  const [busy, setBusy] = useState(false);
  const [status, setStatus] = useState("");

  useEffect(() => {
    setBranchId(ownedBranch?.id ?? detail.branches[0]?.id ?? "");
    setSelected(new Set());
  }, [actor, detail.branches, ownedBranch?.id]);

  const branch = detail.branches.find((item) => item.id === branchId);
  const turns = useMemo(
    () => detail.turns.filter((turn) => turn.branch_id === branchId),
    [branchId, detail.turns],
  );
  const proposals = detail.proposals.filter((proposal) => proposal.branch_id === branchId);

  const createCite = async (event: React.FormEvent) => {
    event.preventDefault();
    if (!branchId || selected.size === 0 || !summary.trim()) return;
    setBusy(true);
    try {
      const { cite } = await api.createCite(branchId, [...selected], summary.trim());
      setNewCite(cite);
      setStatus("Cite를 만들었습니다. 이제 공유 가능한 Toss로 발행할 수 있습니다.");
    } catch (reason) {
      setStatus(reason instanceof Error ? reason.message : "Cite 생성에 실패했습니다.");
    } finally {
      setBusy(false);
    }
  };

  const createToss = async () => {
    if (!newCite) return;
    setBusy(true);
    try {
      const { toss } = await api.createToss(newCite.id);
      setStatus("Toss 링크를 만들었습니다.");
      onOpenToss(toss.token);
    } catch (reason) {
      setStatus(reason instanceof Error ? reason.message : "Toss 생성에 실패했습니다.");
    } finally {
      setBusy(false);
    }
  };

  const createProposal = async (event: React.FormEvent) => {
    event.preventDefault();
    if (!branchId || !proposalText.trim()) return;
    setBusy(true);
    try {
      await api.createProposal(branchId, proposalText.trim());
      setProposalText("");
      setStatus("Main 변경 제안을 만들었습니다.");
      onChanged();
    } catch (reason) {
      setStatus(reason instanceof Error ? reason.message : "제안 생성에 실패했습니다.");
    } finally {
      setBusy(false);
    }
  };

  const approve = async (proposalId: string) => {
    setBusy(true);
    try {
      const result = await api.approveProposal(proposalId);
      if (result.revision) {
        setStatus(`revision ${result.revision.number}가 main에 반영됐습니다.`);
        onPublished();
      } else {
        setStatus(`${result.approver_ids.length}/2 승인 · 다른 구성원의 승인이 필요합니다.`);
      }
    } catch (reason) {
      setStatus(reason instanceof Error ? reason.message : "승인에 실패했습니다.");
    } finally {
      setBusy(false);
    }
  };

  if (!branch) {
    return <main className="empty-state">이 세션에는 아직 branch가 없습니다.</main>;
  }

  return (
    <main className="workspace" tabIndex={-1}>
      <header className="workspace-header">
        <div>
          <div className="eyebrow">SESSION · {branch.owner_id.toUpperCase()} BRANCH</div>
          <h1>세션 · {detail.session.title}</h1>
        </div>
        <label>
          Branch
          <select value={branchId} onChange={(event) => setBranchId(event.target.value)}>
            {detail.branches.map((item) => (
              <option key={item.id} value={item.id}>
                {item.owner_id} · {item.id.slice(0, 8)}
              </option>
            ))}
          </select>
        </label>
      </header>

      <div className="workspace-grid">
        <section className="chat-panel" aria-label="Agent conversation">
          {branch.owner_id === actor ? (
            <AgentChat
              actor={actor}
              api={api}
              apiBase={apiBase}
              branchId={branch.id}
              sessionId={detail.session.id}
              turns={turns}
              onSaved={onChanged}
            />
          ) : (
            <p className="muted">이 branch는 {branch.owner_id} 소유라 읽기만 가능합니다.</p>
          )}
        </section>

        <aside className="curation-panel">
          <section>
            <div className="section-heading">
              <h2>근거 선별</h2>
              <span>{selected.size}</span>
            </div>
            {turns.length === 0 ? (
              <p className="muted">완료된 대화가 저장되면 Cite로 고를 수 있습니다.</p>
            ) : (
              <form onSubmit={(event) => void createCite(event)}>
                <ul className="turn-list">
                  {turns.map((turn) => (
                    <li key={turn.id}>
                      <label>
                        <input
                          type="checkbox"
                          checked={selected.has(turn.id)}
                          aria-label={`${turn.content} 선택`}
                          onChange={() =>
                            setSelected((current) => {
                              const next = new Set(current);
                              if (next.has(turn.id)) next.delete(turn.id);
                              else next.add(turn.id);
                              return next;
                            })
                          }
                        />
                        <span>
                          <small>{turn.role}</small>
                          {turn.content}
                        </span>
                      </label>
                    </li>
                  ))}
                </ul>
                <label>
                  인용 요약
                  <input value={summary} onChange={(event) => setSummary(event.target.value)} />
                </label>
                <button className="button" disabled={busy} type="submit">
                  Cite 만들기
                </button>
              </form>
            )}
            {newCite && (
              <button className="button accent" disabled={busy} type="button" onClick={() => void createToss()}>
                Toss 만들기
              </button>
            )}
          </section>

          <section>
            <h2>Main 변경 제안</h2>
            <form onSubmit={(event) => void createProposal(event)}>
              <label>
                제안 본문
                <textarea
                  value={proposalText}
                  onChange={(event) => setProposalText(event.target.value)}
                  rows={4}
                />
              </label>
              <button className="button secondary" disabled={busy} type="submit">
                Proposal 만들기
              </button>
            </form>
            <div className="proposal-list">
              {proposals.map((proposal) => (
                <ProposalView
                  key={proposal.id}
                  proposal={proposal}
                  busy={busy}
                  onApprove={(id) => void approve(id)}
                />
              ))}
            </div>
          </section>
        </aside>
      </div>
      <p role="status" aria-live="polite" className="status-bar">
        {status}
      </p>
    </main>
  );
}
