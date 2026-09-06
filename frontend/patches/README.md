# AG-UI stream cleanup patch

`@ag-ui/client` is pinned to 0.0.59, the latest compatible release audited for this cutover. Its supported `fetch` option connects `PydanticAIAgent` to the shared authentication boundary.

Both 0.0.48 and 0.0.59 reproduce an unhandled rejection when a response stream errors: the primary error reaches the subscriber, then `reader.cancel()` rejects with that error again during teardown. [Upstream source](https://github.com/ag-ui-protocol/ag-ui/blob/main/sdks/typescript/packages/client/src/run/http-request.ts) rethrows the teardown rejection.

The pnpm patch changes only this redundant cancellation rejection handler in the distributed ESM and CommonJS files. The primary stream error, SDK event parsing, and application error reporting remain intact. The patch is large because upstream ships minified single-line bundles.

Remove the patch and its `patchedDependencies` entry after upgrading to an upstream release that handles cancellation cleanup. Run `pnpm test src/components/AgentChat.streaming.test.tsx` without suppressing unhandled rejections to verify the upstream fix, including the existing AbortError and post-event failure cases.
