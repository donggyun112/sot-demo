import { createContext, useContext, type ReactNode } from "react";
import type { API } from "../api";
import type { AuthSession } from "../auth";
import type { CurrentMember, User, Workspace } from "../types";

export const WORKSPACE_KEY = "sot.workspace";

export type Permission = CurrentMember["permissions"][number];

export type SotContextValue = {
  api: API;
  auth: AuthSession;
  apiBase: string;
  user: User | null;
  onLogout: () => void;
};

export const SotContext = createContext<SotContextValue | null>(null);

export function useSot() {
  const value = useContext(SotContext);
  if (!value) throw new Error("SotContext missing");
  return value;
}

type WorkspaceUi = {
  workspaces: Workspace[];
  member: CurrentMember | null;
};

const WorkspaceUiContext = createContext<WorkspaceUi | null>(null);

export function WorkspaceUiProvider({
  workspaces,
  member,
  children,
}: WorkspaceUi & { children: ReactNode }) {
  return (
    <WorkspaceUiContext.Provider value={{ workspaces, member }}>
      {children}
    </WorkspaceUiContext.Provider>
  );
}

export function useWorkspaceUi() {
  const value = useContext(WorkspaceUiContext);
  if (!value) throw new Error("WorkspaceUiContext missing");
  return value;
}

export function useWorkspaceUiOptional() {
  return useContext(WorkspaceUiContext);
}

export function can(member: CurrentMember | null | undefined, permission: Permission) {
  return member?.permissions.includes(permission) ?? false;
}

export function rememberWorkspace(id: string) {
  localStorage.setItem(WORKSPACE_KEY, id);
}

export function lastWorkspace() {
  return localStorage.getItem(WORKSPACE_KEY);
}
