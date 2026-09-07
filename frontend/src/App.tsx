import { useEffect, useMemo, useState, useSyncExternalStore } from "react";
import {
  QueryClient,
  QueryClientProvider,
  useQueryClient,
} from "@tanstack/react-query";
import { createAPI, type API } from "./api";
import { AuthSession } from "./auth";
import { DEFAULT_API_BASE } from "./transport";
import { AppShell } from "./components/AppShell";
import { DocumentView } from "./components/DocumentView";
import { GoogleLogin } from "./components/GoogleLogin";
import { SessionWorkspace } from "./components/SessionWorkspace";
import { TossView } from "./components/TossView";
import type { User } from "./types";

interface AppProps {
  apiBase?: string;
  auth?: AuthSession;
  googleClientId?: string;
  queryClient?: QueryClient;
}

export function App({
  apiBase = DEFAULT_API_BASE,
  auth: suppliedAuth,
  googleClientId = import.meta.env.VITE_GOOGLE_CLIENT_ID ?? "",
  queryClient: suppliedQueryClient,
}: AppProps) {
  const auth = useMemo(
    () => suppliedAuth ?? new AuthSession(undefined, apiBase),
    [suppliedAuth, apiBase],
  );
  const api = useMemo(() => createAPI(auth, apiBase), [auth, apiBase]);
  const [queryClient] = useState(
    () =>
      suppliedQueryClient ??
      new QueryClient({
        defaultOptions: {
          queries: {
            retry: false,
            staleTime: 30_000,
            refetchOnWindowFocus: false,
          },
          mutations: { retry: false },
        },
      }),
  );
  const user = useSyncExternalStore(auth.subscribe, () => auth.user);
  useEffect(() => {
    if (!auth.user) void auth.refresh().catch(() => {});
  }, [auth]);
  useEffect(
    () => () => {
      queryClient.clear();
    },
    [queryClient, user?.id],
  );
  return (
    <QueryClientProvider client={queryClient}>
      {user ? (
        <WorkspaceApp
          key={user.id}
          user={user}
          api={api}
          auth={auth}
          apiBase={apiBase}
        />
      ) : (
        <GoogleLogin auth={auth} clientId={googleClientId} />
      )}
    </QueryClientProvider>
  );
}

function WorkspaceApp({
  user,
  api,
  auth,
  apiBase,
}: {
  user: User;
  api: API;
  auth: AuthSession;
  apiBase: string;
}) {
  const cache = useQueryClient();
  const workspaces = api.useQuery("get", "/api/v1/workspaces");
  const me = api.useQuery("get", "/api/v1/me");
  const [selectedWorkspaceId, setWorkspaceId] = useState<string | null>(null);
  const workspaceId = selectedWorkspaceId ?? workspaces.data?.[0]?.id ?? "";
  const [selectedDocumentId, setDocumentId] = useState<string | null>(null);
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [tossToken, setTossToken] = useState<string | null>(null);
  const [publishedBundle, setPublishedBundle] = useState<{
    branchId: string;
    bundleId: string;
  } | null>(null);
  const [error, setError] = useState("");
  const documents = api.useQuery(
    "get",
    "/api/v1/workspaces/{workspace_id}/documents",
    { params: { path: { workspace_id: workspaceId } } },
    { enabled: Boolean(workspaceId) },
  );
  const documentId = selectedDocumentId ?? documents.data?.[0]?.id ?? "";
  const member = api.useQuery(
    "get",
    "/api/v1/workspaces/{workspace_id}/members/me",
    { params: { path: { workspace_id: workspaceId } } },
    { enabled: Boolean(workspaceId) },
  );
  const documentParams = {
    params: { path: { workspace_id: workspaceId, document_id: documentId } },
  };
  const document = api.useQuery(
    "get",
    "/api/v1/workspaces/{workspace_id}/documents/{document_id}",
    documentParams,
    { enabled: Boolean(workspaceId && documentId) },
  );
  const sessions = api.useQuery(
    "get",
    "/api/v1/workspaces/{workspace_id}/documents/{document_id}/sessions",
    documentParams,
    { enabled: Boolean(workspaceId && documentId) },
  );
  const createSession = api.useMutation(
    "post",
    "/api/v1/workspaces/{workspace_id}/documents/{document_id}/sessions",
  );
  const changeWorkspace = (id: string) => {
    setWorkspaceId(id);
    setDocumentId(null);
    setSessionId(null);
    setTossToken(null);
    setPublishedBundle(null);
    setError("");
  };
  const openSession = (id: string) => {
    setSessionId(id);
    setTossToken(null);
  };
  const queryError =
    workspaces.error ||
    me.error ||
    documents.error ||
    member.error ||
    document.error ||
    sessions.error;
  const message =
    error ||
    (queryError instanceof Error
      ? queryError.message
      : queryError
        ? "요청을 완료하지 못했습니다."
        : "");
  return (
    <AppShell
      user={me.data ?? user}
      workspaces={workspaces.data ?? []}
      selectedWorkspaceId={workspaceId}
      onWorkspaceChange={changeWorkspace}
      documents={documents.data ?? []}
      sessions={sessions.data ?? []}
      selectedDocumentId={documentId}
      onDocumentSelect={(id) => {
        setDocumentId(id);
        setSessionId(null);
        setTossToken(null);
      }}
      onSessionSelect={openSession}
      onTossOpen={setTossToken}
      onLogout={() => {
        void auth
          .logout()
          .catch((reason: unknown) =>
            setError(
              reason instanceof Error
                ? reason.message
                : "로그아웃에 실패했습니다.",
            ),
          );
      }}
    >
      {message && (
        <div className="error-panel" role="alert">
          <p>{message}</p>
          <button
            className="button"
            onClick={() => {
              setError("");
              void cache.refetchQueries({ type: "active", stale: true });
            }}
          >
            다시 시도
          </button>
        </div>
      )}
      {workspaces.isLoading && (
        <div className="loading" role="status">
          동기화 중…
        </div>
      )}
      {!workspaces.isLoading && !workspaces.data?.length && (
        <main className="empty-state">
          <h1>아직 Workspace가 없습니다</h1>
        </main>
      )}
      {workspaceId &&
        !tossToken &&
        !sessionId &&
        documents.data?.length === 0 && (
          <main className="empty-state">
            <h1>아직 공유 문서가 없습니다</h1>
          </main>
        )}
      {tossToken ? (
        <TossView
          key={tossToken}
          api={api}
          token={tossToken}
          workspaces={workspaces.data ?? []}
          selectedWorkspaceId={workspaceId}
          onForked={(destination, id) => {
            changeWorkspace(destination);
            openSession(id);
          }}
        />
      ) : sessionId ? (
        <SessionWorkspace
          key={`${workspaceId}:${sessionId}`}
          auth={auth}
          api={api}
          apiBase={apiBase}
          workspaceId={workspaceId}
          sessionId={sessionId}
          member={member.data}
          publishedBundle={publishedBundle}
          onPublishedBundleChange={setPublishedBundle}
          onOpenToss={setTossToken}
        />
      ) : (
        document.data && (
          <DocumentView
            api={api}
            member={member.data}
            data={document.data}
            sessions={sessions.data ?? []}
            canCreate={
              member.data?.permissions.includes("session.create") ?? false
            }
            onOpenSession={openSession}
            onCreateSession={async () => {
              const created = await createSession.mutateAsync({
                ...documentParams,
                body: {},
              });
              await cache.invalidateQueries({
                queryKey: api.queryOptions(
                  "get",
                  "/api/v1/workspaces/{workspace_id}/documents/{document_id}/sessions",
                  documentParams,
                ).queryKey,
                exact: true,
              });
              openSession(created.session_id);
            }}
          />
        )
      )}
    </AppShell>
  );
}
