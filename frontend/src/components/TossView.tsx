import { useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import type { API } from "../api";
import type { Workspace } from "../types";

interface TossViewProps {
  api: API;
  token: string;
  workspaces: Workspace[];
  selectedWorkspaceId: string;
  onForked: (workspaceId: string, sessionId: string, bundleId: string) => void;
}

export function TossView({
  api,
  token,
  workspaces,
  selectedWorkspaceId,
  onForked,
}: TossViewProps) {
  const cache = useQueryClient();
  const view = api.useQuery("get", "/api/v1/tosses/{token}", {
    params: { path: { token } },
  });
  const fork = api.useMutation(
    "post",
    "/api/v1/workspaces/{workspace_id}/tosses/{token}/fork",
  );
  const [destination, setDestination] = useState(selectedWorkspaceId);
  const [error, setError] = useState("");
  if (view.error)
    return (
      <p role="alert">
        {view.error instanceof Error
          ? view.error.message
          : "Toss를 불러오지 못했습니다."}
      </p>
    );
  if (!view.data) return <p role="status">Toss 동기화 중…</p>;
  return (
    <main className="toss-view" tabIndex={-1}>
      <div className="eyebrow">TOSS · SHARED EVIDENCE</div>
      <h1>{view.data.title}</h1>
      <p className="muted">
        {view.data.attribution.author_display_name} ·{" "}
        {view.data.attribution.published_at}
      </p>
      <ol className="evidence-list">
        {view.data.items.map((item, index) => (
          <li key={index}>
            <span>
              {item.role} · {item.provenance}
            </span>
            <p>{item.content}</p>
          </li>
        ))}
      </ol>
      <label>
        Destination Workspace
        <select
          value={destination}
          onChange={(event) => setDestination(event.target.value)}
        >
          {workspaces.map((workspace) => (
            <option value={workspace.id} key={workspace.id}>
              {workspace.name}
            </option>
          ))}
        </select>
      </label>
      <button
        className="button"
        disabled={!destination || fork.isPending}
        type="button"
        onClick={() => {
          void fork
            .mutateAsync({
              params: { path: { workspace_id: destination, token } },
              body: {},
            })
            .then(async (created) => {
              await cache.invalidateQueries({
                queryKey: api.queryOptions(
                  "get",
                  "/api/v1/workspaces/{workspace_id}/sessions/{session_id}",
                  {
                    params: {
                      path: {
                        workspace_id: destination,
                        session_id: created.session_id,
                      },
                    },
                  },
                ).queryKey,
                exact: true,
              });
              onForked(destination, created.session_id, view.data!.bundle_id);
            })
            .catch((reason: unknown) =>
              setError(
                reason instanceof Error
                  ? reason.message
                  : "Fork에 실패했습니다.",
              ),
            );
        }}
      >
        Fork
      </button>
      {error && <p role="alert">{error}</p>}
    </main>
  );
}
