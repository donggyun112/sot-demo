# Shared Service Authentication Design

**Date:** 2026-09-02
**Status:** Approved
**Scope:** reusable JWT access-token verification package and Agent-specific authorization adapter

## 1. Purpose

Platform Server and Agent Server are separate services, but both need the same security-sensitive
JWT verification behavior. The shared component is a Python library, not a shared authentication
service and not a place for either service's domain policy.

The library verifies a caller credential and returns a domain-neutral principal. Each consuming
service then decides what that principal may do. Agent Server remains a resource server that
independently validates every Agent-audience credential; it never trusts a caller-supplied subject
header or Platform-internal session state.

## 2. Approved decisions

- Create an independently installable `service-auth` package under `packages/service-auth`.
- Use `joserfc` for JOSE/JWT/JWK primitives.
- Own the asynchronous JWKS fetch and cache policy instead of inheriting a library HTTP client's
  cache semantics.
- Keep authentication generic and authorization service-specific.
- Configure one trusted issuer, one logical audience and one explicit `jwks_uri` per verifier in
  V1.
- Never resolve a network location from an untrusted token header or claim.
- Keep each process's JWKS cache local; do not put authentication keys in Redis or PostgreSQL.
- Do not implement token issuance, Platform login, AG-UI execution, persistence, streaming or the
  Agent loop in this slice.

## 3. Dependency and ownership boundaries

```text
packages/service-auth
├── JWT/JWS verification
├── claim validation
├── JWKS fetch/cache
├── Principal
└── typed authentication errors

platform-server (future consumer)
├── depends on service-auth
├── owns login/session integration
├── owns Platform API authorization
└── obtains or exchanges Agent-audience access tokens

agent-server
├── depends on service-auth
├── owns allowed Platform client IDs
├── owns agent:run / agent:abort policy
├── derives request owner and Semora subject
└── maps authentication/authorization failures to Agent HTTP responses
```

`service-auth` must not import FastAPI, Platform code, Agent code, Semora, Redis or database code.
It depends on `joserfc` for cryptography and `httpx` for asynchronous HTTPS. It owns no global
configuration and opens no network connection at import time. A service constructs and owns the
verifier and closes it through its application lifecycle.

## 4. Package shape and public contracts

Target package shape:

```text
packages/service-auth/
├── pyproject.toml
├── src/service_auth/
│   ├── __init__.py
│   ├── errors.py
│   ├── jwks.py
│   ├── models.py
│   └── verifier.py
└── tests/
```

### 4.1 Principal

Successful verification returns an immutable value containing only normalized fields needed by a
consumer:

```text
Principal
├── issuer: str
├── subject: str
├── client_id: str
└── scopes: frozenset[str]
```

The common verifier briefly holds the raw `subject` because Agent Server needs `(issuer, subject)`
to derive its opaque owner. Agent Server consumes it at the authentication boundary and must not
pass it to request admission, storage or Semora.

### 4.2 Verification profile

Every verifier receives an immutable profile:

```text
VerificationProfile
├── issuer
├── audience
├── jwks_uri
├── allowed_algorithms
├── maximum_token_lifetime = 300 seconds
├── clock_skew = 30 seconds
├── jwks_freshness = 300 seconds
├── jwks_maximum_age = 900 seconds
├── refresh_failure_backoff = 5 seconds
└── unknown_kid_refresh_cooldown = 5 seconds
```

`allowed_algorithms` is required deployment configuration and has no permissive default. V1
supports exactly `RS256`, `PS256` and `ES256`; a deployment selects the non-empty subset matching
its issuer. `none`, all `HS*` algorithms and every other value are rejected during configuration.
Unit and integration tests use `RS256` as the primary fixture.

`issuer`, `audience` and `jwks_uri` must be non-empty. Production `jwks_uri` must use HTTPS. Tests
inject a fake key fetcher and therefore do not require a real network URL.

### 4.3 Core operations

The public behavior is equivalent to:

```text
await AccessTokenVerifier.verify(token) -> Principal
await AsyncJwksProvider.start()         -> None
await AsyncJwksProvider.close()         -> None
AsyncJwksProvider.readiness()           -> JwksReadiness
```

The clock, key fetcher and asynchronous sleep strategy are injected when constructing the provider
so callers cannot choose the verification time per request and lifecycle tests never wait in real
time. The production implementation uses a UTC/monotonic clock, `asyncio.sleep`, and a shared
`httpx.AsyncClient` owned by the provider.

## 5. Token verification profile

The accepted credential is an RFC 9068-style JWT access token sent as
`Authorization: Bearer <token>` over TLS. Token extraction belongs to the service's HTTP adapter;
cryptographic and claim verification belongs to `service-auth`.

Validation order:

1. Reject an empty token, a token larger than 16 KiB, or anything other than compact JWS with
   three segments.
2. Parse the protected header only to select validation rules; do not treat it as trusted data.
3. Require a non-empty `kid` of at most 256 UTF-8 bytes, exact case-sensitive `typ=at+jwt`, and an
   `alg` in the configured allow-list.
4. Reject `jku`, `jwk`, `x5u`, `x5c`, `x5t`, `x5t#S256` and any unsupported `crit` header. V1
   supports no critical extension and never selects a verification key from token-carried key or
   certificate material.
5. Resolve `kid` only from the configured issuer's cached JWKS.
6. Verify the signature with `joserfc` and the same fixed algorithm allow-list.
7. Validate and normalize the claims.
8. Return `Principal`; do not return the original claims or token.

Claims contract:

- `iss` must be a string exactly equal to the configured issuer.
- `aud` must be either the configured audience string or a one-element array containing exactly
  that string. Multi-resource audience tokens are rejected.
- `sub` must be a non-empty string.
- `iat`, `nbf` and `exp` are required NumericDate values. Booleans are not valid numbers.
- `exp` must be later than `iat`, and `exp - iat` must not exceed 300 seconds.
- `iat` and `nbf` may be at most 30 seconds ahead of the verifier clock.
- `exp` may be at most 30 seconds behind the verifier clock.
- At least one of `client_id` or `azp` must be a non-empty string. If both exist, they must match.
- Missing `scope` normalizes to an empty set so service authorization returns `403`. If present,
  it must be an OAuth space-delimited string; empty entries and duplicates are normalized.
- Extra claims are ignored and are not returned to consumers.

An OIDC ID token does not satisfy this profile. A `jti` claim may exist but is ignored, not stored
and not used to reject replay in V1.

## 6. JWKS fetch and cache

### 6.1 Trust and transport

The provider fetches only its configured `jwks_uri`. It never follows a token-provided URL. The
production fetcher:

- uses HTTPS with certificate verification;
- does not follow redirects;
- applies a 2-second connect timeout and a 3-second read timeout;
- accepts at most 256 KiB of response data;
- requires a JSON object with a `keys` array;
- accepts at most 64 keys;
- imports only public signing keys compatible with configured asymmetric algorithms;
- requires a unique, non-empty `kid` of at most 256 UTF-8 bytes on every candidate signing key;
- honors compatible JWK `use`, `key_ops` and `alg` restrictions when those members are present.

Malformed or oversized JWKS responses count as key-source failures and never replace the last
valid key set.

### 6.2 Cache states

Age is measured from the monotonic time of the last successful fetch:

```text
EMPTY          no successful fetch
FRESH          age <= 5 minutes
STALE_USABLE   5 minutes < age <= 15 minutes
EXPIRED        age > 15 minutes
```

- `FRESH`: resolve known `kid` without network access.
- `STALE_USABLE`: attempt refresh. If it fails, a key already present for that `kid` remains usable.
- `EXPIRED` or `EMPTY`: a failed refresh produces `KeySourceUnavailable`; old keys are unusable.
- Unknown `kid`: request one immediate refresh. If the refreshed set still lacks the key, reject
  the token. If refresh fails while another usable set exists, reject that token rather than
  report the whole authentication system unavailable.

All refresh causes share one per-process single-flight operation. A failed fetch starts a
five-second backoff; requests inside that window reuse a still-usable known key or fail without
opening another connection. Unknown-`kid` refreshes also have a global five-second cooldown,
including when the preceding fetch succeeded but did not contain the requested key, so random
key IDs cannot force one issuer request each. A successful fetch atomically replaces the whole key
set, updates the success timestamp and clears only the failure backoff.

`start()` is idempotent. It performs one immediate refresh attempt, records a failure without
turning a transient issuer outage into a configuration error, and then starts a small in-process
periodic key-refresh task. The task refreshes at the five-minute freshness boundary and retries a
failed refresh after the bounded backoff. This is credential maintenance, not an Agent execution
worker and not a job queue. `close()` is idempotent; it cancels and awaits both the maintenance task
and any provider-owned in-flight refresh, then closes only HTTP resources the provider owns.

Redis and PostgreSQL are deliberately absent from this flow. Replicas converge by independently
fetching the issuer's public key set.

## 7. Agent-specific authorization

Agent Server turns a verified `Principal` into an immutable authenticated caller:

```text
AuthenticatedAgentCaller
├── owner_issuer: str
├── owner_subject_hash: 32 bytes
└── semora_subject: str
```

The original principal and raw subject do not cross this boundary. `owner_issuer` is copied from
the already verified principal so persistence can store the trusted issuer beside the hash. The
derivation is:

```text
owner_subject_hash = SHA-256(UTF8(issuer) || 0x00 || UTF8(subject))
semora_subject = "agtsub:v1:" || base64url_no_padding(owner_subject_hash)
```

Before deriving the caller, Agent Server requires `client_id` to be in its deployment allow-list.
The run policy requires `agent:run`; the explicit abort policy requires `agent:abort`. Scope checks
remain Agent code because the common package cannot know Agent operations.

When persistence and public routes are implemented later:

- creation stores `owner_issuer` and `owner_subject_hash`, never raw `sub`;
- attach, resume and abort authenticate a new token and recompute the owner;
- owner mismatch and absent run return the same `404` response;
- authorization does not participate in the AG-UI payload hash;
- an established SSE connection is not cancelled solely because its initial token later expires;
- reconnect and abort always authenticate again.

## 8. Error contract

The common package exposes HTTP-neutral typed errors:

```text
CredentialMissing       service adapter could not supply a credential
InvalidToken(reason)    token, header, signature or claims are invalid
KeySourceUnavailable    no usable cached key and trusted JWKS cannot be fetched
```

`InvalidToken.reason` is a bounded internal enum, not attacker-provided text. Agent's HTTP adapter
maps failures as follows:

| Condition | Status | Public code |
|---|---:|---|
| Missing or malformed Bearer credential | 401 | `invalid_token` |
| Invalid signature/header/claims or unresolved `kid` | 401 | `invalid_token` |
| Valid principal, disallowed `client_id` | 403 | `forbidden` |
| Required Agent scope absent | 403 | `insufficient_scope` |
| Run absent or owner mismatch | 404 | `run_not_found` |
| Cache unusable and trusted JWKS unavailable | 503 | `auth_keys_unavailable` |

`401` returns `WWW-Authenticate: Bearer error="invalid_token"`. Missing scope returns
`WWW-Authenticate: Bearer error="insufficient_scope", scope="<required-scope>"`. `503` returns
`Retry-After: 5` and must not carry a Bearer challenge.

The response body shape is always `{"error":{"code":"...","message":"..."}}`. Public messages are
fixed per public code: `Authentication failed`, `Caller is not allowed`, `Required scope is
missing`, `Run not found`, and `Authentication keys are temporarily unavailable`. Exception text
and internal reason values never enter the public body.

Public responses do not disclose whether issuer, audience, signature or time validation failed.
`InvalidToken` uses exactly these internal reasons: `token_malformed`, `token_too_large`,
`header_invalid`, `algorithm_rejected`, `kid_missing`, `kid_unknown`, `signature_invalid`,
`issuer_mismatch`, `audience_mismatch`, `subject_invalid`, `time_claim_invalid`,
`token_not_yet_valid`, `token_expired`, `token_lifetime_exceeded`, `client_identity_invalid`, and
`scope_invalid`. Agent authorization separately records `scope_missing`, `client_forbidden` and
`owner_mismatch`.

## 9. Readiness, logging and metrics

`/healthz` remains process liveness and never depends on the issuer. A future Agent `/readyz`
aggregates `JwksReadiness` with its other mandatory dependencies. Reading readiness never performs
network I/O.

- Before the first successful JWKS load: not ready.
- Last successful load no older than 15 minutes: ready, including stale-but-usable state.
- Last successful load older than 15 minutes: not ready.
- Invalid verification configuration: fail when constructing the verifier, before serving traffic.

The library and adapters never log the token, raw subject, full owner hash or raw attacker-provided
`kid`. They expose only bounded reason/state values so a service adapter can produce safe logs and
metrics without parsing exception text. Service-level metrics may include a configured issuer
alias and a verified allow-listed client ID, but no user identity. When production route wiring is
added, the adapter will count verification outcome, refresh outcome, forced unknown-key refresh,
`jwks_stale_used`, and key-source-unavailable, and observe cache age and refresh duration. A metrics
backend dependency is outside this first package slice.

## 10. Test strategy

### 10.1 Common unit tests

- valid RSA-signed token;
- wrong signature and key;
- `none`, `HS*` and non-allow-listed algorithms;
- malicious `jku`, `jwk`, `x5u`, `x5c`, `x5t`, `x5t#S256` and unsupported `crit`;
- malformed, oversized and non-compact tokens;
- missing/invalid `typ` and `kid`;
- issuer and audience mismatch, including multi-audience rejection;
- missing or mistyped time claims, expiration, future issue/not-before and 300-second lifetime;
- exact 30-second skew boundaries;
- `client_id`/`azp` normalization and conflict;
- missing, malformed and duplicated scope values.

### 10.2 JWKS state tests

Use fake time and a deterministic fake fetcher:

- fresh hit without fetch;
- refresh after five minutes;
- successful key rotation;
- unknown `kid` forced refresh once;
- stale known key during outage;
- failure after maximum age;
- concurrent lookups collapse into one fetch;
- failure backoff prevents connection storms;
- invalid/oversized JWKS never replaces a valid set;
- background maintenance closes cleanly;
- readiness is a pure state read with no network call.

### 10.3 Agent policy and adapter tests

- allow-listed and denied client IDs;
- `agent:run` and `agent:abort` independence;
- fixed owner-hash and Semora-subject vectors;
- no raw token or raw subject in the resulting Agent caller;
- exact `401`, `403`, `404`, `503` mappings and Bearer headers;
- owner mismatch and missing run have indistinguishable public responses.

HTTP mapping is tested through a small test-only FastAPI application. This slice does not create
the real `/ag-ui` or abort route and does not change the running Agent application's route surface.
No test contacts a public issuer.

### 10.4 Boundary and regression tests

- `service-auth` builds and imports independently.
- The shared package contains no Platform, Agent, FastAPI, Semora, Redis or database import.
- Agent Server depends on the package without importing Platform code.
- Existing Agent admission, distribution, HTTP health and boundary tests continue to pass.

## 11. First implementation slice

The first implementation slice ends when:

1. `packages/service-auth` contains the contracts, verifier and JWKS provider described here;
2. its isolated unit tests pass;
3. Agent Server contains its authorization/owner adapter and HTTP error mapping;
4. Agent-specific authentication tests pass;
5. the existing Agent Server suite remains green.

The slice does not wire authentication into the production FastAPI app. Public route wiring,
Agent PostgreSQL ownership checks, SSE behavior and Semora execution each require their own later
design/implementation checkpoint.

## 12. References

- [RFC 9068: JWT Profile for OAuth 2.0 Access Tokens](https://www.rfc-editor.org/rfc/rfc9068)
- [RFC 8725: JSON Web Token Best Current Practices](https://www.rfc-editor.org/rfc/rfc8725)
- [joserfc JWT guide](https://jose.authlib.org/en/guide/jwt/)
- [joserfc JWK guide](https://jose.authlib.org/en/guide/jwk/)
- [Agent Server / AG-UI Boundary Design](../plans/2026-08-30-agui-agent-boundary.md)
