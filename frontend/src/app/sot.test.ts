import { expect, it } from "vitest";
import { can, type Permission } from "./sot";
import type { CurrentMember } from "../types";

const member = (permissions: Permission[]): CurrentMember => ({
  workspace_id: "w1",
  user_id: "user-1",
  role: "member",
  permissions,
});

it("gates workspace.manage off a member role", () => {
  expect(can(member(["document.read", "session.read"]), "workspace.manage")).toBe(
    false,
  );
  expect(
    can(member(["workspace.manage", "document.read"]), "workspace.manage"),
  ).toBe(true);
});

it("treats a missing membership as no permissions", () => {
  expect(can(null, "session.create")).toBe(false);
});
