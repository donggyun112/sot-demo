import type { components } from "./generated/api";
import { createTransport, DEFAULT_API_BASE, type Network } from "./transport";

export class AuthSession {
  #accessToken: string | null = null;
  #user: components["schemas"]["UserResponse"] | null = null;
  #listeners = new Set<() => void>();
  #refreshing: Promise<void> | null = null;
  #cookieOperations: Promise<void> = Promise.resolve();
  #generation = 0;
  private readonly client;

  constructor(
    private readonly network: Network = (request) => fetch(request),
    apiBase = DEFAULT_API_BASE,
  ) {
    this.client = createTransport(network, apiBase);
  }
  get accessToken() {
    return this.#accessToken;
  }
  get user() {
    return this.#user;
  }
  subscribe = (listener: () => void) => {
    this.#listeners.add(listener);
    return () => {
      this.#listeners.delete(listener);
    };
  };
  private accept(data: components["schemas"]["AuthResponse"] | null) {
    this.#accessToken = data?.access_token ?? null;
    this.#user = data?.user ?? null;
    this.#listeners.forEach((listener) => listener());
  }
  // Order actual response headers, not just in-memory token updates. Only auth
  // endpoints enter this queue, so protected-request recovery can safely await it.
  private changeCookie(operation: () => Promise<void>): Promise<void> {
    const pending = this.#cookieOperations.then(operation);
    this.#cookieOperations = pending.catch(() => {});
    return pending;
  }
  async loginWithGoogle(credential: string) {
    const generation = ++this.#generation;
    this.#refreshing = null;
    await this.changeCookie(async () => {
      const { data } = await this.client.POST("/api/v1/auth/google", {
        body: { credential },
      });
      if (data && generation === this.#generation) {
        // Requests started while login was pending used the previous token.
        ++this.#generation;
        this.accept(data);
      }
    });
  }
  refresh = (): Promise<void> => {
    if (!this.#refreshing) {
      const pending = this.changeCookie(async () => {
        const generation = this.#generation;
        try {
          const { data } = await this.client.POST("/api/v1/auth/refresh");
          if (generation === this.#generation) this.accept(data ?? null);
        } catch (error) {
          if (generation === this.#generation) this.accept(null);
          throw error;
        }
      }).finally(() => {
        if (this.#refreshing === pending) this.#refreshing = null;
      });
      this.#refreshing = pending;
    }
    return this.#refreshing;
  };
  async logout() {
    const generation = ++this.#generation;
    this.#refreshing = null;
    await this.changeCookie(async () => {
      try {
        await this.client.POST("/api/v1/auth/logout");
      } finally {
        if (generation === this.#generation) {
          ++this.#generation;
          this.accept(null);
        }
      }
    });
  }
  fetch = async (request: Request): Promise<Response> => {
    const generation = this.#generation;
    const ensureCurrentSession = () => {
      if (generation !== this.#generation)
        throw new DOMException("Authentication session changed", "AbortError");
    };
    const send = () => {
      ensureCurrentSession();
      request.signal.throwIfAborted();
      const authorized = new Request(request.clone(), {
        credentials: "include",
      });
      if (this.#accessToken)
        authorized.headers.set("Authorization", `Bearer ${this.#accessToken}`);
      else authorized.headers.delete("Authorization");
      return this.network(authorized);
    };
    const response = await send();
    if (response.status !== 401) return response;
    ensureCurrentSession();
    await this.refresh();
    return send();
  };
}
