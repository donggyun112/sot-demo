import type { components } from "./generated/api";

export type User = components["schemas"]["UserResponse"];
export type Workspace = components["schemas"]["WorkspaceResponse"];
export type CurrentMember =
  components["schemas"]["CurrentWorkspaceMemberResponse"];
export type DocumentRecord = components["schemas"]["DocumentSummaryResponse"];
export type DocumentResponse = components["schemas"]["DocumentResponse"];
export type Session = components["schemas"]["SessionResponse"];
export type Branch = components["schemas"]["BranchResponse"];
export type Turn = components["schemas"]["TurnResponse"];
export type Proposal = components["schemas"]["ProposalResponse"];
export type PublicBundle = components["schemas"]["PublicBundleResponse"];
