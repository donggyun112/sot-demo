import { useEffect, useMemo, useState, useSyncExternalStore } from "react";
import "./i18n";
import { useTranslation } from "react-i18next";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { Navigate, Outlet, Route, Routes, useLocation, useParams } from "react-router";
import { AuthSession } from "./auth";
import { createAPI } from "./api";
import {
  lastWorkspace,
  rememberWorkspace,
  SotContext,
  useSot,
  useWorkspaceUi,
  WorkspaceUiProvider,
} from "./app/sot";
import { AppShell } from "./components/AppShell";
import { InboxView } from "./views/InboxView";
import { LoginView } from "./views/LoginView";
import { CreateWorkspaceView } from "./views/CreateWorkspaceView";
import { DocumentListView } from "./views/DocumentListView";
import { DocumentView } from "./views/DocumentView";
import { SessionListView } from "./views/SessionListView";
import { SessionView } from "./views/SessionView";
import { ProfileView } from "./views/ProfileView";
import { MembersView } from "./views/MembersView";
import { ProposalView } from "./views/ProposalView";
import { DEFAULT_API_BASE } from "./transport";
import styles from "./views/product.module.css";
import type { User, Workspace } from "./types";

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
      <AppRoutes
        auth={auth}
        apiBase={apiBase}
        googleClientId={googleClientId}
        user={user}
      />
    </QueryClientProvider>
  );
}

function AppRoutes({
  auth,
  apiBase,
  googleClientId,
  user,
}: {
  auth: AuthSession;
  apiBase: string;
  googleClientId: string;
  user: User | null;
}) {
  const location = useLocation();
  const api = useMemo(() => createAPI(auth, apiBase), [auth, apiBase]);
  if (!user) {
    return <LoginView auth={auth} clientId={googleClientId} />;
  }
  return (
    <SotContext.Provider
      value={{
        api,
        auth,
        apiBase,
        user,
        onLogout: () => void auth.logout(),
      }}
    >
      {user ? (
        <SignedInRoutes api={api} />
      ) : (
        <Routes>
        </Routes>
      )}
    </SotContext.Provider>
  );
}

function SignedInRoutes({ api }: { api: ReturnType<typeof createAPI> }) {
  const workspaces = api.useQuery("get", "/api/v1/workspaces");
  const list = workspaces.data ?? [];
  if (workspaces.isLoading) return <Splash />;
  return (
    <WorkspaceUiProvider workspaces={list} member={null}>
      <Routes>
        <Route path="/me" element={<ProfileView />} />
        <Route path="/workspaces/new" element={<CreateWorkspaceView />} />
        <Route path="/w/:workspaceId" element={<WorkspaceLayout />}>
          <Route element={<AppShell />}>
            <Route index element={<DocumentListView />} />
            <Route path="inbox" element={<InboxView />} />
            <Route path="members" element={<MembersView />} />
            <Route path="documents/:documentId" element={<DocumentView />} />
            <Route
              path="documents/:documentId/sessions"
              element={<SessionListView />}
            />
            <Route
              path="sessions/:sessionId/branches/:branchId"
              element={<SessionView />}
            />
            <Route path="sessions/:sessionId" element={<SessionView />} />
            <Route path="proposals/:proposalId" element={<ProposalView />} />
          </Route>
        </Route>
        <Route path="*" element={<HomeRedirect workspaces={list} />} />
      </Routes>
    </WorkspaceUiProvider>
  );
}

function WorkspaceLayout() {
  const { workspaceId = "" } = useParams();
  const { api } = useSot();
  const { workspaces } = useWorkspaceUi();
  const known = workspaces.some((item) => item.id === workspaceId);
  const me = api.useQuery(
    "get",
    "/api/v1/workspaces/{workspace_id}/members/me",
    { params: { path: { workspace_id: workspaceId } } },
    { enabled: known },
  );
  if (!known) {
    return (
      <Navigate
        to={workspaces[0] ? `/w/${workspaces[0].id}` : "/workspaces/new"}
        replace
      />
    );
  }
  rememberWorkspace(workspaceId);
  if (me.isError) {
    return <Navigate to="/workspaces/new" replace />;
  }
  if (!me.data) return <Splash />;
  return (
    <WorkspaceUiProvider workspaces={workspaces} member={me.data}>
      <Outlet />
    </WorkspaceUiProvider>
  );
}

function Splash() {
  const { t } = useTranslation();
  return (
    <div className={styles.login}>
      <main>
        <h1>{t("brand.name")}</h1>
        <p>{t("common.loading")}</p>
      </main>
    </div>
  );
}

function HomeRedirect({ workspaces }: { workspaces: Workspace[] }) {
  if (workspaces.length === 0) return <Navigate to="/workspaces/new" replace />;
  const remembered = lastWorkspace();
  const id = workspaces.some((item) => item.id === remembered)
    ? remembered
    : workspaces[0].id;
  return <Navigate to={`/w/${id}`} replace />;
}
