import { useEffect, useMemo, useRef, useState, useSyncExternalStore } from "react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { AuthSession } from "./auth";
import { DEFAULT_API_BASE } from "./transport";
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
        <SignedIn user={user} onLogout={() => void auth.logout()} />
      ) : (
        <Login auth={auth} clientId={googleClientId} />
      )}
    </QueryClientProvider>
  );
}

function Login({
  auth,
  clientId,
}: {
  auth: AuthSession;
  clientId: string;
}) {
  const button = useRef<HTMLDivElement>(null);
  const [error, setError] = useState("");
  useEffect(() => {
    let active = true;
    const initialize = () => {
      if (
        !active ||
        !clientId ||
        !button.current ||
        typeof google === "undefined"
      )
        return;
      google.accounts.id.initialize({
        client_id: clientId,
        callback: ({ credential }) => {
          void auth.loginWithGoogle(credential).catch((reason: unknown) => {
            if (active)
              setError(
                reason instanceof Error ? reason.message : "Sign-in failed.",
              );
          });
        },
      });
      google.accounts.id.renderButton(button.current, {
        type: "standard",
        theme: "outline",
        size: "large",
        text: "signin_with",
      });
    };
    const script = document.getElementById("google-identity");
    const failed = () => setError("Could not load Google sign-in.");
    script?.addEventListener("load", initialize);
    script?.addEventListener("error", failed);
    initialize();
    return () => {
      active = false;
      script?.removeEventListener("load", initialize);
      script?.removeEventListener("error", failed);
    };
  }, [auth, clientId]);
  return (
    <main>
      <h1>SOT</h1>
      <div ref={button} />
      <button
        type="button"
        onClick={() => {
          void auth.loginWithoutGoogle().catch((reason: unknown) =>
            setError(
              reason instanceof Error ? reason.message : "Sign-in failed.",
            ),
          );
        }}
      >
        Continue without Google
      </button>
      {error && <p role="alert">{error}</p>}
    </main>
  );
}

function SignedIn({
  user,
  onLogout,
}: {
  user: User;
  onLogout: () => void;
}) {
  return (
    <main>
      <p>{user.display_name}</p>
      <button type="button" onClick={onLogout}>
        Sign out
      </button>
    </main>
  );
}
