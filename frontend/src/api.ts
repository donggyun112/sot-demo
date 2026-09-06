import createQueryClient from "openapi-react-query";
import type { AuthSession } from "./auth";
import { createTransport, DEFAULT_API_BASE } from "./transport";

export { ApiError } from "./transport";
export const createAPI = (auth: AuthSession, apiBase = DEFAULT_API_BASE) =>
  createQueryClient(createTransport(auth.fetch, apiBase));
export type API = ReturnType<typeof createAPI>;
