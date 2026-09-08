import { expect, it } from "vitest";
import openapi from "../generated/openapi.json";
import { PROPOSAL_CONTENT_LIMIT } from "./limits";

it("keeps the proposal limit in step with the generated contract", () => {
  const schemas = (openapi as { components: { schemas: Record<string, unknown> } })
    .components.schemas;
  // The limit rides on what an edit ADDS, since a proposal is edits now.
  const replace = (
    schemas.DocumentEditRequest as {
      properties: { replace: { maxLength?: number } };
    }
  ).properties.replace;
  expect(replace.maxLength).toBe(PROPOSAL_CONTENT_LIMIT);
  for (const name of ["CreateProposalRequest", "ReviseProposalRequest"]) {
    expect(
      (schemas[name] as { properties: Record<string, unknown> }).properties.edits,
    ).toBeDefined();
  }
});
