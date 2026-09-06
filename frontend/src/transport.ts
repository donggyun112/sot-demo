import createFetchClient from "openapi-fetch";
import { z } from "zod";
import type { paths } from "./generated/api";

export const DEFAULT_API_BASE = import.meta.env.VITE_API_BASE ?? "/api/v1";
export const serviceRoot = (apiBase: string) =>
  new URL(
    apiBase.replace(/\/api\/v1\/?$/, "") || "/",
    window.location.origin,
  ).href.replace(/\/$/, "");
export type Network = (request: Request) => Promise<Response>;

export class ApiError extends Error {
  readonly name = "ApiError";
  constructor(
    readonly status: number,
    readonly code: string,
    message: string,
  ) {
    super(message);
  }
}

// FastAPI's exception-handler envelope is not represented in its OpenAPI responses.
// Validate this untrusted envelope only; REST DTOs come from generated types.
const problem = z.object({
  error: z.object({ code: z.string(), message: z.string() }),
});

export function createTransport(network: Network, apiBase = DEFAULT_API_BASE) {
  const client = createFetchClient<paths>({
    baseUrl: serviceRoot(apiBase),
    fetch: network,
    credentials: "include",
  });
  client.use({
    async onResponse({ response }) {
      if (response.ok) return;
      const parsed = problem.safeParse(
        await response
          .clone()
          .json()
          .catch(() => null),
      );
      throw new ApiError(
        response.status,
        parsed.success ? parsed.data.error.code : "request_failed",
        parsed.success
          ? parsed.data.error.message
          : `Request failed with ${response.status}`,
      );
    },
  });
  return client;
}
