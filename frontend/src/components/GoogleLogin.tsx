import { useEffect, useRef, useState } from "react";
import type { AuthSession } from "../auth";

export function GoogleLogin({
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
                reason instanceof Error
                  ? reason.message
                  : "로그인에 실패했습니다.",
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
    const failed = () =>
      setError("Google 로그인 연결을 불러오지 못했습니다. 새로고침해 주세요.");
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
    <main className="empty-state">
      <div className="eyebrow">SOT</div>
      <h1>Google로 로그인</h1>
      <div ref={button} />
      {!clientId && <p>Google 로그인 설정이 필요합니다.</p>}
      {error && <p role="alert">{error}</p>}
    </main>
  );
}
