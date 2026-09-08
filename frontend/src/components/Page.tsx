import type { ReactNode } from "react";
import { useTranslation } from "react-i18next";
import styles from "./Page.module.css";

/**
 * Page pattern layer. Screens pick a pattern instead of composing a bare div,
 * so titles, counts, actions and empty/error states sit in the same place on
 * every screen.
 */

export function PageHeader({
  title,
  count,
  description,
  actions,
}: {
  title: ReactNode;
  count?: number;
  description?: ReactNode;
  actions?: ReactNode;
}) {
  return (
    <header className={styles.header}>
      <div className={styles.heading}>
        <h1>{title}</h1>
        {typeof count === "number" && (
          <span className={styles.count}>{count}</span>
        )}
      </div>
      {actions && <div className={styles.headerActions}>{actions}</div>}
      {description && <p className={styles.description}>{description}</p>}
    </header>
  );
}

/** Loading, empty, error and permission all render here, never ad hoc. */
export function PageState({
  tone = "muted",
  title,
  description,
  actions,
}: {
  tone?: "muted" | "danger";
  title: ReactNode;
  description?: ReactNode;
  actions?: ReactNode;
}) {
  return (
    <div
      className={styles.state}
      data-tone={tone}
      role={tone === "danger" ? "alert" : "status"}
    >
      <p className={styles.stateTitle}>{title}</p>
      {description && <p className={styles.stateDescription}>{description}</p>}
      {actions && <div className={styles.stateActions}>{actions}</div>}
    </div>
  );
}

/** A named group inside a rail or side panel. */
export function Section({
  title,
  count,
  aside,
  children,
}: {
  title: ReactNode;
  count?: number;
  aside?: ReactNode;
  children: ReactNode;
}) {
  return (
    <section className={styles.section}>
      <div className={styles.sectionHead}>
        <h3>{title}</h3>
        {typeof count === "number" && (
          <span className={styles.count}>{count}</span>
        )}
        {aside && <div className={styles.sectionAside}>{aside}</div>}
      </div>
      {children}
    </section>
  );
}

/**
 * An action stays on screen even when it cannot run yet, and says why. Hiding
 * it until its prerequisite is met is what makes a screen unreadable: the user
 * cannot see what the screen is for.
 */
export function Action({
  label,
  hint,
  blockedBy,
  variant = "ghost",
  pending = false,
  onClick,
  type = "button",
}: {
  label: ReactNode;
  hint?: ReactNode;
  /** Reason the action cannot run yet. Present means disabled. */
  blockedBy?: ReactNode;
  variant?: "primary" | "ghost";
  pending?: boolean;
  onClick?: () => void;
  type?: "button" | "submit";
}) {
  const { t } = useTranslation();
  const blocked = Boolean(blockedBy);
  return (
    <div className={styles.action}>
      <button
        className={variant === "primary" ? styles.primary : styles.ghost}
        type={type}
        disabled={blocked || pending}
        onClick={onClick}
      >
        {pending ? t("common.working") : label}
      </button>
      <span className={styles.actionHint}>{blockedBy ?? hint}</span>
    </div>
  );
}
