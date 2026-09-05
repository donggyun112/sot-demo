export type ActorId = "alice" | "bob";

export interface DocumentRecord {
  id: string;
  title: string;
  current_revision_id: string;
  created_by: ActorId;
  created_at: string;
}

export interface Revision {
  id: string;
  document_id: string;
  number: number;
  content: string;
  proposal_id: string | null;
  created_by: ActorId;
  created_at: string;
}

export interface Session {
  id: string;
  document_id: string;
  owner_id: ActorId;
  title: string;
  created_at: string;
}

export interface Branch {
  id: string;
  session_id: string;
  owner_id: ActorId;
  parent_branch_id: string | null;
  source_toss_id: string | null;
  created_at: string;
}

export interface Turn {
  id: string;
  branch_id: string;
  ordinal: number;
  role: "user" | "assistant";
  content: string;
  created_at: string;
}

export interface Cite {
  id: string;
  branch_id: string;
  created_by: ActorId;
  turn_ids: string[];
  summary: string;
  created_at: string;
}

export interface Toss {
  id: string;
  cite_id: string;
  token: string;
  created_by: ActorId;
  created_at: string;
}

export interface Proposal {
  id: string;
  document_id: string;
  branch_id: string;
  created_by: ActorId;
  content: string;
  status: "open" | "published";
  created_at: string;
}

export interface BootstrapResponse {
  users: ActorId[];
  current_user: ActorId;
  documents: DocumentRecord[];
}

export interface DocumentResponse {
  document: DocumentRecord;
  current_revision: Revision;
  revisions: Revision[];
  sessions: Session[];
}

export interface SessionResponse {
  session: Session;
  branches: Branch[];
  turns: Turn[];
  cites: Cite[];
  proposals: Proposal[];
}

export interface TossViewResponse {
  toss: Toss;
  cite: Cite;
  turns: Turn[];
}

export interface NewTurn {
  role: "user" | "assistant";
  content: string;
}

export interface ApprovalResponse {
  proposal: Proposal;
  approver_ids: ActorId[];
  revision: Revision | null;
}
