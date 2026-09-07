import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { expect, it } from "vitest";
import { App } from "../App";
import { AuthSession } from "../auth";
import type { components } from "../generated/api";
import { createServer, session, turns } from "../test/server";

type Item = components["schemas"]["BundleItemResponse"];
type Curation = components["schemas"]["CurationRequest"];
const privateTurn = { ...turns[0], id: "private", role: "user" as const, content: "private prompt" };
const initial: Item[] = [
  { source_ids: ["private"], role: "user", content: "private prompt", provenance: "copied" },
  { source_ids: [turns[0].id], role: "assistant", content: turns[0].content, provenance: "copied" },
];

it("excludes unchecked private Turns before joining, chains versions and safely retries after a partial failure", async () => {
  const server = createServer();
  server.state.sessions = [session];
  server.state.turns = [privateTurn, ...turns];
  let projection = initial;
  const writes: Curation[] = [];
  let failed = false;
  const auth = new AuthSession(async (request) => {
    if (request.url.endsWith("/bundle-preview")) return Response.json(projection);
    if (request.url.endsWith("/curation-ops")) {
      const body = await request.json() as Curation;
      writes.push(body);
      if (body.operation.kind === "drop") {
        projection = [initial[1]];
      } else if (!failed) {
        failed = true;
        server.state.branchVersion++;
        return Response.json({ error: { code: "version_conflict", message: "changed concurrently" } }, { status: 409 });
      } else {
        projection = [{ ...initial[1], content: "public summary", provenance: "edited" }];
      }
      return Response.json({ resource_id: "operation", branch_version: ++server.state.branchVersion });
    }
    return server.network(request);
  }, "https://sot.test/api/v1");
  await auth.loginWithGoogle("credential");
  render(<App auth={auth} apiBase="https://sot.test/api/v1" />);
  await userEvent.click((await screen.findAllByRole("button", { name: /세션 session-/ }))[0]);
  await userEvent.click(await screen.findByRole("checkbox", { name: /B로 결정/ }));
  expect(screen.getByRole("checkbox", { name: /private prompt/ })).not.toBeChecked();
  await userEvent.type(screen.getByLabelText("인용 요약"), "public summary");
  await userEvent.click(screen.getByRole("button", { name: "선별 적용" }));
  expect(await screen.findByText("changed concurrently")).toBeVisible();
  expect(screen.queryByRole("button", { name: "Bundle 발행" })).not.toBeInTheDocument();
  await userEvent.click(screen.getByRole("button", { name: "선별 적용" }));
  await waitFor(() => expect(screen.getByRole("status")).toHaveTextContent("선별을 적용했습니다"));
  expect(writes).toEqual([
    { expected_version: 2, operation: { kind: "drop", turn_id: "private" } },
    { expected_version: 3, operation: { kind: "join", turn_ids: [turns[0].id], content: "public summary" } },
    { expected_version: 4, operation: { kind: "join", turn_ids: [turns[0].id], content: "public summary" } },
  ]);
  await userEvent.click(screen.getByRole("button", { name: "Bundle 미리보기" }));
  const preview = await screen.findByRole("region", { name: "Bundle preview" });
  expect(preview).toHaveTextContent("public summary");
  expect(preview).not.toHaveTextContent("private prompt");
});

it.each(["excluded", "partial join"])("rejects a stale %s selection before any write", async (kind) => {
  const server = createServer();
  server.state.sessions = [session];
  server.state.turns = [privateTurn, ...turns];
  let writes = 0;
  const auth = new AuthSession(async (request) => {
    if (request.url.endsWith("/bundle-preview")) return Response.json(kind === "excluded"
      ? [initial[1]] : [{ ...initial[1], source_ids: ["private", turns[0].id] }]);
    if (request.url.endsWith("/curation-ops")) writes++;
    return server.network(request);
  }, "https://sot.test/api/v1");
  await auth.loginWithGoogle("credential");
  render(<App auth={auth} apiBase="https://sot.test/api/v1" />);
  await userEvent.click((await screen.findAllByRole("button", { name: /세션 session-/ }))[0]);
  await userEvent.click(await screen.findByRole("checkbox", { name: /private prompt/ }));
  await userEvent.type(screen.getByLabelText("인용 요약"), "summary");
  await userEvent.click(screen.getByRole("button", { name: "선별 적용" }));
  await waitFor(() => expect(screen.getByRole("status")).toHaveTextContent(kind === "excluded"
    ? "이미 제외된 Turn은 다시 선택할 수 없습니다" : "이미 합친 Turn은 묶음 전체를 선택하거나 제외하세요"));
  expect(writes).toBe(0);
  expect(screen.queryByRole("button", { name: "Bundle 발행" })).not.toBeInTheDocument();
  if (kind === "excluded") {
    expect(screen.getByRole("checkbox", { name: /private prompt/ })).toBeDisabled();
    expect(screen.getByRole("checkbox", { name: /private prompt/ })).not.toBeChecked();
  }
});

it("keeps existing joins indivisible, drops a deselected group once, and cannot restore excluded sources", async () => {
  const server = createServer();
  server.state.sessions = [session];
  const second = { ...turns[0], id: "second", content: "second joined source" };
  const fresh = { ...turns[0], id: "fresh", content: "new source" };
  server.state.turns = [...turns, second, fresh];
  const joined: Item = { ...initial[1], source_ids: [turns[0].id, second.id], content: "previous join" };
  const freshItem: Item = { ...initial[1], source_ids: [fresh.id], content: fresh.content };
  let projection = [joined, freshItem];
  const writes: Curation[] = [];
  const auth = new AuthSession(async (request) => {
    if (request.url.endsWith("/bundle-preview")) return Response.json(projection);
    if (request.url.endsWith("/curation-ops")) {
      const body = await request.json() as Curation;
      writes.push(body);
      projection = body.operation.kind === "drop" ? [freshItem]
        : [{ ...freshItem, content: "replacement summary", provenance: "edited" }];
      return Response.json({ resource_id: "operation", branch_version: ++server.state.branchVersion });
    }
    return server.network(request);
  }, "https://sot.test/api/v1");
  await auth.loginWithGoogle("credential");
  render(<App auth={auth} apiBase="https://sot.test/api/v1" />);
  await userEvent.click((await screen.findAllByRole("button", { name: /세션 session-/ }))[0]);
  await userEvent.type(await screen.findByLabelText("인용 요약"), "replacement summary");
  await userEvent.click(await screen.findByRole("button", { name: "Bundle 미리보기" }));
  expect(await screen.findByRole("button", { name: "Bundle 발행" })).toBeDisabled();
  await userEvent.click(screen.getByRole("checkbox", { name: /B로 결정/ }));
  expect(screen.getByRole("checkbox", { name: /second joined source/ })).toBeChecked();
  await userEvent.click(screen.getByRole("checkbox", { name: /second joined source/ }));
  expect(screen.getByRole("checkbox", { name: /B로 결정/ })).not.toBeChecked();
  await userEvent.click(screen.getByRole("checkbox", { name: /new source/ }));
  await userEvent.click(screen.getByRole("button", { name: "선별 적용" }));
  await waitFor(() => expect(screen.getByRole("status")).toHaveTextContent("선별을 적용했습니다"));
  expect(writes).toEqual([
    { expected_version: 2, operation: { kind: "drop", turn_id: turns[0].id } },
    { expected_version: 3, operation: { kind: "join", turn_ids: [fresh.id], content: "replacement summary" } },
  ]);
  expect(screen.getByRole("checkbox", { name: /B로 결정/ })).toBeDisabled();
  expect(screen.getByRole("checkbox", { name: /second joined source/ })).toBeDisabled();
  await userEvent.click(screen.getByRole("button", { name: "Bundle 미리보기" }));
  expect(await screen.findByRole("button", { name: "Bundle 발행" })).toBeEnabled();
});
