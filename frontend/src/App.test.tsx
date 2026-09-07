import { act, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, expect, it, vi } from "vitest";
import { App } from "./App";
import { AuthSession } from "./auth";
import { createServer, member } from "./test/server";

afterEach(() => vi.unstubAllGlobals());

it("lets a user continue without Google", async () => {
  const server = createServer();
  const requests: Request[] = [];
  const auth = new AuthSession(async (request) => {
    requests.push(request.clone());
    if (request.url.endsWith("/auth/refresh"))
      return Response.json({}, { status: 401 });
    if (request.url.endsWith("/auth/local"))
      return Response.json({
        access_token: "local-access",
        token_type: "bearer",
        user: member,
      });
    return server.network(request);
  }, "https://sot.test/api/v1");
  render(<App auth={auth} apiBase="https://sot.test/api/v1" />);
  await userEvent.click(
    await screen.findByRole("button", { name: "Continue without Google" }),
  );
  expect(await screen.findByText("Member")).toBeVisible();
  expect(
    requests.some((request) => request.url.endsWith("/auth/local")),
  ).toBe(true);
});

it("uses GIS credential login and exposes no actor switcher", async () => {
  let callback:
    | ((value: google.accounts.id.CredentialResponse) => void)
    | undefined;
  const requests: Request[] = [];
  const auth = new AuthSession(async (request) => {
    requests.push(request.clone());
    if (request.url.endsWith("/refresh"))
      return Response.json({}, { status: 401 });
    if (request.url.endsWith("/google"))
      return Response.json({
        access_token: "real-access",
        token_type: "bearer",
        user: member,
      });
    if (request.url.endsWith("/me")) return Response.json(member);
    return Response.json([]);
  }, "https://sot.test/api/v1");
  vi.stubGlobal("google", {
    accounts: {
      id: {
        initialize: (options: google.accounts.id.IdConfiguration) => {
          callback = options.callback;
        },
        renderButton: (element: HTMLElement) => {
          element.textContent = "Sign in with Google";
        },
      },
    },
  });
  render(
    <App
      auth={auth}
      googleClientId="google-client-id"
      apiBase="https://sot.test/api/v1"
    />,
  );
  expect(await screen.findByText("Sign in with Google")).toBeVisible();
  await act(async () =>
    callback?.({ credential: "gis-credential", select_by: "btn" }),
  );
  expect(await screen.findByText("Member")).toBeVisible();
  const login = requests.find((request) => request.url.endsWith("/google"));
  expect(await login?.json()).toEqual({ credential: "gis-credential" });
  expect(screen.queryByLabelText("작업자")).not.toBeInTheDocument();
});
