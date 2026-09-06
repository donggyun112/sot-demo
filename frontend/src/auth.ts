import type { components } from "./generated/api";
import { createTransport, DEFAULT_API_BASE, type Network } from "./transport";

export class AuthSession {
  #accessToken: string | null = null;
  #user: components["schemas"]["UserResponse"] | null = null;
  #listeners = new Set<() => void>();
  #refreshing: Promise<void> | null = null;
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
  async loginWithGoogle(credential: string) {
    const generation = ++this.#generation;
    const { data } = await this.client.POST("/api/v1/auth/google", {
      body: { credential },
    });
    if (data && generation === this.#generation) this.accept(data);
  }
  refresh = (): Promise<void> => {
    if (!this.#refreshing) {
      const generation = this.#generation;
      this.#refreshing = this.client
        .POST("/api/v1/auth/refresh")
        .then(({ data }) => {
          if (generation === this.#generation) this.accept(data ?? null);
        })
        .catch((error: unknown) => {
          if (generation === this.#generation) this.accept(null);
          throw error;
        })
        .finally(() => {
          this.#refreshing = null;
        });
    }
    return this.#refreshing;
  };
  async logout() {
    ++this.#generation;
    try {
      await this.client.POST("/api/v1/auth/logout");
    } finally {
      this.accept(null);
    }
  }
  fetch = async (request: Request): Promise<Response> => {
    const send = () => {
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
    await this.refresh();
    return send();
  };
}
