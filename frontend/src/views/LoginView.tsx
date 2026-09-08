import { useEffect, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import type { AuthSession } from "../auth";
import styles from "./product.module.css";

export function LoginView({
  auth,
  clientId,
}: {
  auth: AuthSession;
  clientId: string;
}) {
  const { t } = useTranslation();
  const button = useRef<HTMLDivElement>(null);
  const [error, setError] = useState("");
  useEffect(() => {
    let active = true;
    const initialize = () => {
      if (!active || !clientId || !button.current || typeof google === "undefined")
        return;
      google.accounts.id.initialize({
        client_id: clientId,
        callback: ({ credential }) => {
          void auth.loginWithGoogle(credential).catch((reason: unknown) => {
            if (active)
              setError(reason instanceof Error ? reason.message : t("login.failed"));
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
    const failed = () => setError(t("login.gis"));
    script?.addEventListener("load", initialize);
    script?.addEventListener("error", failed);
    initialize();
    return () => {
      active = false;
      script?.removeEventListener("load", initialize);
      script?.removeEventListener("error", failed);
    };
  }, [auth, clientId, t]);
  return (
    <div className={styles.login}>
      <header className={styles.loginMasthead}>
        <a className={styles.loginBrand} href="/" aria-label={t("brand.name")}>
          {t("brand.name")}
        </a>
        <span>{t("login.edition")}</span>
      </header>

      <main className={styles.loginLayout}>
        <section className={styles.loginIntro} aria-labelledby="login-intro">
          <p className={styles.eyebrow}>{t("brand.tagline")}</p>
          <h1 id="login-intro">{t("login.headline")}</h1>
          <p className={styles.loginDeck}>{t("login.deck")}</p>
          <p className={styles.loginIndex}>{t("login.index")}</p>
        </section>

        <section className={styles.loginPanel} aria-labelledby="login-title">
          <p className={styles.eyebrow}>{t("login.access")}</p>
          <h2 id="login-title">{t("login.title")}</h2>
          <p className={styles.loginHint}>{t("login.hint")}</p>
          <div className={styles.googleButton} ref={button} />
          <div className={styles.loginRule} aria-hidden="true">
            <span>{t("login.or")}</span>
          </div>
          <button
            type="button"
            className={styles.primary}
            onClick={() => {
              void auth.loginWithoutGoogle().catch((reason: unknown) =>
                setError(reason instanceof Error ? reason.message : t("login.failed")),
              );
            }}
          >
            {t("login.continue")}
          </button>
          {error && (
            <p className={styles.alert} role="alert">
              {error}
            </p>
          )}
        </section>
      </main>

      <footer className={styles.loginFooter}>
        <span>{t("login.footerLeft")}</span>
        <span>{t("login.footerRight")}</span>
      </footer>
    </div>
  );
}
