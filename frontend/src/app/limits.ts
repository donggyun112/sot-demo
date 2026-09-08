/**
 * Mirrors `PROPOSAL_CONTENT_LIMIT` in backend/src/sot/consensus/domain.py, which
 * the OpenAPI schema carries as `CreateProposalRequest.content.maxLength`.
 * `limits.test.ts` fails if the two drift apart.
 */
export const PROPOSAL_CONTENT_LIMIT = 4000;
