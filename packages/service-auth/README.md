# service-auth

`service-auth` is a reusable Python library for authenticating short-lived JWT access tokens
against one configured issuer, audience and JWKS endpoint. It retrieves and caches public signing
keys, verifies compact JWS signatures and strict claims, and returns an immutable, domain-neutral
`Principal`.

The package issues no tokens, owns no login or user session, and contains no Platform or Agent
authorization policy. A consuming service must independently decide which verified clients and
scopes may perform each operation.

## Security profile

- Algorithms are limited to a configured non-empty subset of `RS256`, `PS256` and `ES256`.
- JWKS retrieval is HTTPS-only, does not follow redirects, and limits responses to 256 KiB and 64
  keys.
- Tokens are limited to 16 KiB and require `typ=at+jwt`, a bounded `kid`, one issuer, one audience,
  and explicit `iat`, `nbf` and `exp` claims.
- Tokens may live for at most 300 seconds with 30 seconds of clock skew.
- JWKS state is process-local: fresh through 300 seconds, stale-usable through 900 seconds, then
  expired.
- Token-provided key locations and key material are never trusted.

`AsyncJwksProvider.start()` performs credential maintenance only. It is not an application job
worker. Call `close()` during service shutdown to stop maintenance and close provider-owned HTTP
resources.

## Verification

From the repository root:

```bash
UV_CACHE_DIR=/tmp/service-auth-uv-cache uv run --project packages/service-auth \
  pytest packages/service-auth/tests -q
UV_CACHE_DIR=/tmp/service-auth-uv-cache uv run --project packages/service-auth \
  ruff check packages/service-auth/src packages/service-auth/tests
UV_CACHE_DIR=/tmp/service-auth-uv-cache uv run --project packages/service-auth \
  mypy packages/service-auth/src
```
