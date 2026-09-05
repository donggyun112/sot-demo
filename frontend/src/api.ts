import type {
  ActorId,
  ApprovalResponse,
  BootstrapResponse,
  Branch,
  Cite,
  DocumentResponse,
  NewTurn,
  Proposal,
  Session,
  SessionResponse,
  Toss,
  TossViewResponse,
  Turn,
} from "./types";

interface ProblemBody {
  error?: { code?: string; message?: string };
}

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

async function decode<T>(response: Response): Promise<T> {
  if (!response.ok) {
    let problem: ProblemBody = {};
    try {
      problem = (await response.json()) as ProblemBody;
    } catch {
      // A non-JSON upstream error still receives a stable client-side code.
    }
    throw new ApiError(
      response.status,
      problem.error?.code ?? "request_failed",
      problem.error?.message ?? `Request failed with ${response.status}`,
    );
  }
  return (await response.json()) as T;
}

export class SOTApi {
  constructor(
    private readonly baseUrl: string,
    readonly actor: ActorId,
  ) {}

  private request<T>(path: string, init: RequestInit = {}): Promise<T> {
    const headers = new Headers(init.headers);
    headers.set("X-SOT-User", this.actor);
    if (init.body !== undefined) headers.set("Content-Type", "application/json");
    return fetch(`${this.baseUrl}${path}`, { ...init, headers }).then(decode<T>);
  }

  bootstrap(): Promise<BootstrapResponse> {
    return this.request("/bootstrap");
  }

  getDocument(documentId: string): Promise<DocumentResponse> {
    return this.request(`/documents/${documentId}`);
  }

  getSession(sessionId: string): Promise<SessionResponse> {
    return this.request(`/sessions/${sessionId}`);
  }

  createSession(
    documentId: string,
    title: string,
  ): Promise<{ session: Session; branch: Branch }> {
    return this.request(`/documents/${documentId}/sessions`, {
      method: "POST",
      body: JSON.stringify({ title }),
    });
  }

  appendTurns(branchId: string, turns: NewTurn[]): Promise<{ turns: Turn[] }> {
    return this.request(`/branches/${branchId}/turns`, {
      method: "POST",
      body: JSON.stringify({ turns }),
    });
  }

  createCite(
    branchId: string,
    turnIds: string[],
    summary: string,
  ): Promise<{ cite: Cite }> {
    return this.request(`/branches/${branchId}/cites`, {
      method: "POST",
      body: JSON.stringify({ turn_ids: turnIds, summary }),
    });
  }

  createToss(citeId: string): Promise<{ toss: Toss }> {
    return this.request(`/cites/${citeId}/tosses`, { method: "POST" });
  }

  getToss(token: string): Promise<TossViewResponse> {
    return fetch(`${this.baseUrl}/tosses/${token}`).then(decode<TossViewResponse>);
  }

  forkToss(token: string): Promise<{ branch: Branch }> {
    return this.request(`/tosses/${token}/fork`, { method: "POST" });
  }

  createProposal(branchId: string, content: string): Promise<{ proposal: Proposal }> {
    return this.request(`/branches/${branchId}/proposals`, {
      method: "POST",
      body: JSON.stringify({ content }),
    });
  }

  approveProposal(proposalId: string): Promise<ApprovalResponse> {
    return this.request(`/proposals/${proposalId}/approve`, { method: "POST" });
  }
}
