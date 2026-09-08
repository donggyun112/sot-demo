import { useEffect, useRef, useState, type ReactNode } from "react";
import { useTranslation } from "react-i18next";
import {
  Link,
  NavLink,
  Outlet,
  useLocation,
  useNavigate,
  useParams,
  useSearchParams,
} from "react-router";
import { can, rememberWorkspace, useSot, useWorkspaceUi } from "../app/sot";
import { useOpenProposals } from "../app/inbox";
import { headingsFrom } from "../views/outline";
import { editSummary } from "../views/patch";
import styles from "./AppShell.module.css";

/**
 * The workspace shell. Navigation lives in one column so a screen's own header
 * carries only that screen's identity and actions.
 */
export function AppShell() {
  const { t } = useTranslation();
  const { workspaceId = "" } = useParams();
  const { api } = useSot();
  const { member } = useWorkspaceUi();
  const documents = api.useQuery(
    "get",
    "/api/v1/workspaces/{workspace_id}/documents",
    { params: { path: { workspace_id: workspaceId } } },
  );
  const waiting = useOpenProposals().waitingOnMe.length;
  const [navOpen, setNavOpen] = useState(false);
  const { pathname } = useLocation();
  /* Following a link is what dismisses the mobile drawer, not any click in it:
     the workspace menu lives inside and must be able to open. */
  useEffect(() => setNavOpen(false), [pathname]);

  return (
    <div className={styles.shell} data-nav={navOpen ? "open" : "closed"}>
      {/* Below 960px the sidebar becomes an overlay; without this bar the app
          would have no navigation at all on a phone. */}
      <div className={styles.navBar}>
        <button
          type="button"
          className={styles.navToggle}
          aria-expanded={navOpen}
          onClick={() => setNavOpen((open) => !open)}
        >
          {navOpen ? t("nav.close") : t("nav.open")}
        </button>
        <span className={styles.navBrand}>{t("brand.name")}</span>
      </div>
      {navOpen && (
        <button
          type="button"
          className={styles.scrim}
          aria-label={t("nav.close")}
          onClick={() => setNavOpen(false)}
        />
      )}
      <nav
        className={styles.sidebar}
        aria-label={t("nav.sidebar")}
        /* Close on anything that navigates — including re-picking the
           workspace you are already in, which changes no path. */
        onClick={(event) => {
          const target = event.target as HTMLElement;
          if (target.closest("a[href], [role='menuitem']")) setNavOpen(false);
        }}
      >
        {/* Labelled by the mark alone: the tagline is copy, not an address. */}
        <Link
          className={styles.brand}
          to={`/w/${workspaceId}`}
          aria-label={t("brand.name")}
        >
          <strong>{t("brand.name")}</strong>
          <span>{t("brand.tagline")}</span>
        </Link>
        <WorkspaceSwitcher />

        <div className={styles.group}>
          <NavLink
            to={`/w/${workspaceId}/inbox`}
            className={({ isActive }) =>
              isActive ? `${styles.item} ${styles.itemOn}` : styles.item
            }
          >
            <span className={styles.itemLabel}>{t("nav.inbox")}</span>
            {waiting > 0 && <span className={styles.badge}>{waiting}</span>}
          </NavLink>
        </div>

        <div className={styles.group}>
          <div className={styles.groupHead}>{t("nav.documents")}</div>
          {documents.data?.length === 0 && (
            <p className={styles.groupEmpty}>{t("docs.emptyTitle")}</p>
          )}
          {documents.data?.map((doc) => (
            <DocumentBranch
              key={doc.id}
              workspaceId={workspaceId}
              id={doc.id}
              title={doc.title || t("docs.untitled")}
            />
          ))}
        </div>

        <div className={styles.footer}>
          {can(member, "workspace.manage") && (
            <Link className={styles.item} to={`/w/${workspaceId}/members`}>
              <span className={styles.itemLabel}>{t("header.members")}</span>
            </Link>
          )}
          <Identity />
        </div>
      </nav>

      <main className={styles.main}>
        <Outlet />
      </main>
    </div>
  );
}

/** A document and, nested under it, the changes waiting on it. */
function DocumentBranch({
  workspaceId,
  id,
  title,
}: {
  workspaceId: string;
  id: string;
  title: string;
}) {
  const { api } = useSot();
  const { documentId } = useParams();
  const [params, setParams] = useSearchParams();
  const open = documentId === id;
  const proposals = api.useQuery(
    "get",
    "/api/v1/workspaces/{workspace_id}/documents/{document_id}/proposals",
    { params: { path: { workspace_id: workspaceId, document_id: id } } },
  );
  /* Same query key as the document screen, so this costs nothing extra. */
  const document = api.useQuery(
    "get",
    "/api/v1/workspaces/{workspace_id}/documents/{document_id}",
    { params: { path: { workspace_id: workspaceId, document_id: id } } },
    { enabled: open },
  );
  const headings = open
    ? headingsFrom(document.data?.current_revision.content ?? "").filter(
        (item) => item.id !== "body",
      )
    : [];
  const selected = params.get("block") ?? headings[0]?.id;
  const pending = (proposals.data ?? []).filter(
    (item) => item.status === "open" || item.status === "approved",
  );
  return (
    <>
      <NavLink
        end
        to={`/w/${workspaceId}/documents/${id}`}
        className={({ isActive }) =>
          isActive ? `${styles.item} ${styles.itemOn}` : styles.item
        }
      >
        <span className={styles.itemLabel}>{title}</span>
        {pending.length > 0 && (
          <span className={styles.count}>{pending.length}</span>
        )}
      </NavLink>
      {/* The open document's own structure, then what is pending against it. */}
      {headings.map((item) => (
        <button
          key={item.id}
          type="button"
          className={
            item.id === selected ? `${styles.child} ${styles.childOn}` : styles.child
          }
          data-depth={item.depth >= 3 ? "3" : String(item.depth)}
          onClick={() => {
            const next = new URLSearchParams(params);
            next.set("block", item.id);
            setParams(next, { replace: true });
          }}
        >
          <span className={styles.itemLabel}>{item.title}</span>
        </button>
      ))}
      {open &&
        pending.map((item) => (
          <NavLink
            key={item.id}
            to={`/w/${workspaceId}/proposals/${item.id}`}
            className={({ isActive }) =>
              isActive ? `${styles.child} ${styles.childOn}` : styles.child
            }
          >
            <span
              className={styles.dot}
              data-status={item.status}
              aria-hidden="true"
            />
            <span className={styles.itemLabel}>
              {editSummary(item.current_version.edits).slice(0, 40)}
            </span>
          </NavLink>
        ))}
    </>
  );
}

function WorkspaceSwitcher() {
  const { t } = useTranslation();
  const { workspaceId } = useParams();
  const navigate = useNavigate();
  const { workspaces } = useWorkspaceUi();
  const current = workspaces.find((item) => item.id === workspaceId);
  const [open, setOpen] = useState(false);
  const root = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) return;
    const onPointer = (event: PointerEvent) => {
      if (root.current && !root.current.contains(event.target as Node))
        setOpen(false);
    };
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") setOpen(false);
    };
    document.addEventListener("pointerdown", onPointer);
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("pointerdown", onPointer);
      document.removeEventListener("keydown", onKey);
    };
  }, [open]);

  return (
    <div className={styles.switcher} ref={root}>
      <button
        type="button"
        className={styles.switcherButton}
        aria-label={t("workspace.switch")}
        aria-expanded={open}
        aria-haspopup="menu"
        onClick={() => setOpen((value) => !value)}
      >
        <span className={styles.switcherName}>
          {current?.name ?? t("workspace.switch")}
        </span>
        <span aria-hidden="true">▾</span>
      </button>
      {open && (
        <div className={styles.menu} role="menu">
          {workspaces.map((item) => (
            <button
              key={item.id}
              type="button"
              role="menuitem"
              data-on={item.id === workspaceId ? "true" : "false"}
              onClick={() => {
                rememberWorkspace(item.id);
                setOpen(false);
                void navigate(`/w/${item.id}`);
              }}
            >
              {item.name}
            </button>
          ))}
          <span className={styles.menuDivider} />
          <Link role="menuitem" to="/workspaces/new" onClick={() => setOpen(false)}>
            {t("workspace.new")}
          </Link>
        </div>
      )}
    </div>
  );
}

function Identity() {
  const { t, i18n } = useTranslation();
  const { user, onLogout } = useSot();
  return (
    <div className={styles.identity}>
      {user && (
        <Link className={styles.item} to="/me">
          <span className={styles.itemLabel}>{user.display_name}</span>
        </Link>
      )}
      <div className={styles.identityActions}>
        <button
          type="button"
          className={styles.quiet}
          onClick={() =>
            void i18n.changeLanguage(i18n.language === "ko" ? "en" : "ko")
          }
        >
          {i18n.language === "ko" ? "EN" : "KO"}
        </button>
        <button type="button" className={styles.quiet} onClick={onLogout}>
          {t("header.signOut")}
        </button>
      </div>
    </div>
  );
}

/** A screen's own header: what this object is, and what it offers. */
export function TopBar({
  title,
  status,
  actions,
}: {
  title: ReactNode;
  status?: ReactNode;
  actions?: ReactNode;
}) {
  return (
    <header className={styles.topBar}>
      <span className={styles.topTitle}>{title}</span>
      {status}
      {actions && <div className={styles.topActions}>{actions}</div>}
    </header>
  );
}
