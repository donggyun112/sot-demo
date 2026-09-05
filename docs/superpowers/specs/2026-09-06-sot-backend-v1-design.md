# SOT Backend v1 정본 설계

- 상태: 사용자 문서 검토 대기
- 작성일: 2026-09-06
- 제품 기준: [`README.md`](../../../README.md)
- 이전 제품 설계: [`2026-08-30-sot-v1-design.md`](2026-08-30-sot-v1-design.md)
- 현재 실행 결정: [`2026-09-06-pydantic-ai-direct-vertical-slice-design.md`](2026-09-06-pydantic-ai-direct-vertical-slice-design.md)

## 1. 문서의 지위

이 문서는 SOT v1 백엔드의 정본이다. 기존 `2026-08-30-sot-v1-design.md`에서 제품 의미,
도메인 상태, 공개 범위, 합의 정책을 계승하고, 이후 확정된 단일 FastAPI·PostgreSQL·Pydantic
AI 실행 구조를 반영한다.

다음 이전 결정은 폐기한다.

- Platform Server와 Agent Server의 분리 배포
- Semora 또는 LangGraph 기반 실행 계층
- Agent 전용 데이터베이스와 서비스 간 JWT
- 실행 journal, lease, replay cursor, recovery scanner
- Redis 기반 live event 복제
- 브라우저 연결과 독립적으로 계속되는 agent run
- OpenRouter 전용 model abstraction

`2026-08-30-sot-v1-design.md`의 UX와 제품 정책은 여전히 유효하다. 다만 백엔드 구조,
agent 실행 수명, 저장소와 실시간 전송에 관해서는 이 문서가 우선한다. 현재 E2E vertical
slice는 이 설계의 동작을 검증하는 프로토타입이며 최종 모듈 구조의 정본이 아니다.

## 2. 목표

1. 사적 draft session과 공개 가능한 합의 상태를 명확히 분리한다.
2. session, branch, curation, bundle, toss, proposal, approval, main revision을 제품 도메인으로
   구현한다.
3. FastAPI route, application use case, domain policy, PostgreSQL adapter의 책임을 분리한다.
4. 실제 OIDC 사용자와 workspace/session 권한을 모든 명령과 조회에서 일관되게 적용한다.
5. Pydantic AI를 request-scoped 단일 비동기 agent로 실행한다.
6. model provider를 특정 사업자에 종속시키지 않고 순서가 있는 fallback을 지원한다.
7. 테스트에서 LLM이나 PostgreSQL 없이 핵심 도메인 정책을 검증할 수 있게 한다.

## 3. 비목표

- microservice 분리
- worker, queue 또는 background agent executor
- DBOS, workflow engine 또는 event sourcing
- agent 실행 checkpoint와 장애 후 재개
- partial model output 영속화
- SSE event replay와 `Last-Event-ID`
- Redis
- CQRS read database
- 여러 agent가 협업하는 runtime orchestration
- 조직별 승인 규칙 DSL
- 사실 판정 또는 AI 생성 탐지

LLM 실행 내구성은 목표가 아니지만, 사용자가 만든 제품 데이터와 승인된 main revision의
트랜잭션 무결성은 목표다.

## 4. 아키텍처 결정

SOT Backend는 **모듈러 모놀리스**다. 배포 단위는 FastAPI 애플리케이션 하나이며 제품 데이터는
PostgreSQL 하나가 소유한다. 각 제품 모듈 내부는 Ports and Adapters 형태로 구성한다.

```text
Browser
  ├─ REST/JSON ─────────────────────────────────────┐
  └─ AG-UI/SSE ─────────────────────────────────────┤
                                                     ▼
                                            FastAPI application
                          ┌──────────────────────────┼───────────────────────┐
                          ▼                          ▼                       ▼
                    REST adapters              AG-UI adapter          auth adapter
                          │                          │                       │
                          └──────────────┬───────────┴───────────────────────┘
                                         ▼
                               application use cases
                                         │
                                domain models/policies
                                         │ ports
                          ┌──────────────┴──────────────┐
                          ▼                             ▼
                 PostgreSQL adapters             Pydantic AI adapter
                          │                             │
                     PostgreSQL                  model providers
```

### 4.1 허용하는 의존 방향

```text
presentation/infrastructure -> application -> domain
```

- Domain은 FastAPI, Pydantic, psycopg, Pydantic AI 타입을 import하지 않는다.
- Application은 use case와 transaction 경계를 소유하고 port만 의존한다.
- REST와 AG-UI는 application command/query를 호출하는 inbound adapter다.
- PostgreSQL과 Pydantic AI는 application/domain port를 구현하는 outbound adapter다.
- Agent tool은 route나 SQL을 직접 호출하지 않고 같은 application use case를 호출한다.
- 한 모듈은 다른 모듈의 PostgreSQL adapter나 table을 직접 사용하지 않는다.

## 5. 제품 모듈

### 5.1 `identity`

- OIDC subject와 SOT user 매핑
- workspace와 membership
- workspace role 정책
- local/test 전용 development identity

### 5.2 `documents`

- Document와 immutable DocumentRevision
- current main pointer
- revision provenance와 citation 조회
- main 변경의 optimistic concurrency

### 5.3 `sessions`

- Session, SessionMember, Branch
- 완료된 user/assistant/tool Turn
- draft 접근 정책과 branch 상태
- curation op, bundle preview와 immutable Bundle

### 5.4 `sharing`

- bundle share link, 제품 용어로서의 toss
- token hashing, 만료, revoke와 rotate
- 인증 없는 공개 bundle 조회
- 공개된 bundle만 사용하는 sanitized fork

### 5.5 `consensus`

- versioned Proposal
- source session의 owner/editor를 기준으로 고정한 required approver와 Approval
- reject, stale, approved, merged 상태 전이
- 승인 완료 시 새 DocumentRevision publication

Proposal creator와 source session의 owner/editor는 required approver에 자동 포함된다. creator는
approver를 추가할 수 있지만 자동 포함된 사용자를 제거할 수 없다.

### 5.6 `agent`

- server-owned instruction과 tool registry
- branch context assembly
- Pydantic AI model/fallback 구성
- AG-UI request와 event 변환
- application use case를 호출하는 tool adapter

`agent`는 제품 aggregate를 소유하지 않는다. agent가 만든 cite나 proposal도 각각 sessions 또는
consensus application use case를 통해 저장한다.

## 6. 코드 구조

```text
backend/src/sot/
├── bootstrap/
│   ├── app.py                 # composition root와 FastAPI factory
│   └── settings.py
├── shared/
│   ├── errors.py              # 안정적인 application/domain error
│   ├── ids.py                 # UUID와 token 생성
│   ├── clock.py
│   └── unit_of_work.py        # transaction port
├── identity/
├── documents/
├── sessions/
├── sharing/
├── consensus/
│   ├── api.py                 # inbound HTTP adapter
│   ├── application.py         # command/query handlers
│   ├── domain.py              # entities, value objects, policy
│   ├── ports.py               # repository/query ports
│   └── postgres.py            # outbound persistence adapter
└── agent/
    ├── api.py                 # AG-UI endpoint
    ├── application.py         # context assembly와 run 요청
    ├── models.py              # provider-neutral model construction
    ├── prompts.py
    └── tools.py               # application command adapters
```

각 모듈은 같은 내부 형태를 사용하되 파일이 작을 때 불필요한 하위 디렉터리를 만들지 않는다.
공유 코드는 기술적으로 중립적인 primitive로 제한한다. 제품 정책을 `shared`에 넣지 않는다.

## 7. Application 경계

하나의 거대한 `SOTService`를 두지 않는다. 외부에서 관찰 가능한 유스케이스마다 command 또는
query handler를 둔다.

대표 command는 다음과 같다.

- `CreateWorkspace`
- `AddWorkspaceMember`
- `CreateDocument`
- `CreateSession`
- `AppendCompletedTurns`
- `ApplyCuration`
- `PublishBundle`
- `CreateShareLink`
- `RevokeShareLink`
- `ForkSharedBundle`
- `CreateProposal`
- `ReviseProposal`
- `DecideProposal`
- `MergeProposal`

각 mutation은 actor, aggregate ID, 입력 payload, expected version, idempotency key를 명시적으로
받는다. handler 하나가 transaction 하나를 연다. transaction 안에서 권한 확인, aggregate 로드,
domain transition, 저장이 완료된다.

조회는 transaction을 길게 유지하지 않는다. 조회 전용 port가 응답 projection을 만들 수 있지만
권한 필터를 우회할 수는 없다.

## 8. Domain 정책

### 8.1 핵심 불변 조건

1. draft turn은 branch에 append-only로 저장한다.
2. 완료되지 않은 assistant output은 Turn이 아니다.
3. curation은 원본 turn을 변경하지 않고 공개 projection만 만든다.
4. Bundle은 publish 후 immutable이며 새 정리는 새 version이다.
5. 공개 toss로 선택되지 않은 draft turn을 조회할 수 없다.
6. sanitized fork는 공개 BundleItem만 seed history로 사용한다.
7. Proposal approval은 proposal version에 귀속된다.
8. proposal body나 version이 바뀌면 이전 approval은 효력을 잃는다.
9. required approver가 모두 같은 version을 승인해야 merge할 수 있다.
10. Proposal의 base revision이 current main과 다르면 merge하지 않고 stale로 전환한다.
11. merge는 새 immutable revision 생성, citation 생성, main pointer 이동을 한 transaction에서 한다.
12. 동일한 idempotency key와 동일 payload는 같은 결과를 반환하고 다른 payload는 conflict다.

### 8.2 상태

```text
Session:  draft -> shared -> closed
Bundle:   published -> revoked
Proposal: open -> approved -> merged
               ├-> rejected
               └-> stale
```

main은 Session 상태가 아니다. main은 Document가 가리키는 최신 승인 revision이다.

## 9. PostgreSQL

### 9.1 소유 데이터

PostgreSQL은 다음 제품 데이터만 저장한다.

- `sot_user`, `sot_workspace`, `sot_workspace_member`
- `sot_document`, `sot_document_revision`, `sot_revision_citation`
- `sot_session`, `sot_session_member`, `sot_branch`, `sot_turn`
- `sot_curation_op`, `sot_bundle`, `sot_bundle_item`
- `sot_share_link`
- `sot_proposal`, `sot_proposal_bundle`, `sot_proposal_approver`, `sot_approval`
- `sot_idempotency_record`: actor, scope, key, canonical payload hash, response reference

다음 데이터는 저장하지 않는다.

- provider streaming chunk
- AG-UI event
- partial assistant message
- agent run, lease, checkpoint 또는 replay cursor
- model provider 내부 상태

### 9.2 저장 방식

- PostgreSQL 16과 `psycopg` async pool을 사용한다.
- ORM을 도입하지 않고 명시적 SQL adapter를 유지한다.
- migration은 순방향 SQL 파일이며 애플리케이션 시작과 별도의 명령으로 실행할 수 있어야 한다.
- repository는 aggregate 저장과 조회를 담당하고 transaction을 스스로 commit하지 않는다.
- Unit of Work가 connection/transaction과 repository instance를 묶는다.
- 외래 키, unique, check constraint로 표현 가능한 불변 조건은 DB에도 둔다.

### 9.3 동시성

- versioned aggregate mutation은 `expected_version`을 검사한다.
- turn ordinal은 `(branch_id, ordinal)` unique와 transaction 안의 순번 할당으로 보호한다.
- 마지막 approval과 publication은 proposal/document row lock 안에서 처리한다.
- `(document_id, revision_number)`와 approval identity는 unique constraint로 중복을 막는다.
- 위험한 POST 재시도는 `Idempotency-Key`와 canonical payload hash로 구분한다.

Agent 실행 자체는 재개하거나 exactly-once로 만들지 않는다. 다만 이미 성공한 agent tool의 제품
mutation은 idempotency key와 domain constraint로 중복되지 않아야 한다.

## 10. 인증과 권한

### 10.1 인증

운영 환경은 OIDC Authorization Code + PKCE를 사용한다. Backend는 bearer token의 signature,
issuer, audience, expiry를 검증하고 `(issuer, subject)`로 SOT user를 찾는다. provider credential과
OIDC token은 제품 테이블 또는 브라우저 로그에 기록하지 않는다.

`X-SOT-User: alice|bob` 방식은 local/test profile에서만 활성화하며 운영 설정에서는 애플리케이션
시작 단계에 거부한다.

### 10.2 권한

Workspace role:

- `owner`: workspace 관리와 문서 publication 관리
- `member`: session, bundle, proposal 생성과 참여
- `viewer`: 허용된 문서와 session 읽기

Session role:

- `owner`: member, bundle, toss 관리
- `editor`: turn, curation, proposal 생성
- `viewer`: 읽기

공개 toss token은 정확히 하나의 immutable bundle을 읽는 capability다. workspace나 draft 접근권한을
부여하지 않는다. raw token은 생성 응답과 URL에서만 사용하며 DB에는 SHA-256 hash만 저장한다.
공개 응답에는 `Cache-Control: private, no-store`를 설정하고 access log에서 token path를 가린다.

## 11. HTTP API

모든 제품 API는 `/api/v1` 아래에 둔다. command route는 인증, schema validation, handler 호출,
응답 변환만 담당한다.

상태를 만드는 `POST` command는 `Idempotency-Key`를 받는다. 같은 actor와 command scope에서 같은
key와 payload를 다시 보내면 기존 결과를 반환하고, payload가 다르면 `409 idempotency_conflict`를
반환한다. versioned aggregate 변경은 body의 `expected_version`을 함께 검사한다.

### 11.1 Identity와 workspace

| Method | Path | 목적 |
| --- | --- | --- |
| `GET` | `/me` | 현재 사용자 |
| `GET` | `/workspaces` | 접근 가능한 workspace |
| `POST` | `/workspaces` | workspace 생성 |
| `POST` | `/workspaces/{id}/members` | member 추가 |

### 11.2 Documents와 sessions

| Method | Path | 목적 |
| --- | --- | --- |
| `GET` | `/documents/{id}` | current main과 provenance |
| `GET` | `/documents/{id}/revisions/{number}` | 과거 revision |
| `POST` | `/documents/{id}/sessions` | draft session 생성 |
| `GET` | `/sessions/{id}` | session, branch, turn snapshot |
| `POST` | `/sessions/{id}/branches` | 권한 내 draft branch |
| `POST` | `/branches/{id}/turns` | 완료된 turn append |
| `POST` | `/branches/{id}/curation-ops` | 공개 projection 편집 |
| `GET` | `/branches/{id}/bundle-preview` | 현재 preview |
| `POST` | `/branches/{id}/bundles` | immutable bundle publish |

### 11.3 Toss와 consensus

| Method | Path | 목적 |
| --- | --- | --- |
| `POST` | `/bundles/{id}/tosses` | share capability 생성 |
| `DELETE` | `/tosses/{id}` | revoke |
| `GET` | `/tosses/{token}` | 인증 없는 공개 bundle 조회 |
| `POST` | `/tosses/{token}/fork` | 로그인 후 sanitized fork |
| `POST` | `/documents/{id}/proposals` | proposal 생성 |
| `GET` | `/proposals/{id}` | proposal과 approval 조회 |
| `PUT` | `/proposals/{id}` | 새 proposal version |
| `POST` | `/proposals/{id}/decisions` | approve 또는 reject |
| `POST` | `/proposals/{id}/merge` | 조건 충족 시 publication |

### 11.4 Agent

| Method | Path | 목적 |
| --- | --- | --- |
| `POST` | `/branches/{id}/agent` | 권한 확인 후 AG-UI run 실행 |

별도 Agent Server API, run attach API, replay API와 cancel API는 두지 않는다. 브라우저의 Stop은
현재 HTTP request를 취소한다.

### 11.5 오류 계약

```json
{
  "error": {
    "code": "version_conflict",
    "message": "The resource changed after it was loaded"
  }
}
```

- 인증 실패: `401`
- 권한 실패: `403`
- 리소스 없음: `404`
- state/version/idempotency 충돌: `409`
- 입력 검증 실패: `422`
- provider 또는 agent 오류: AG-UI `RUN_ERROR`

외부 응답은 내부 예외, SQL, provider credential을 포함하지 않는다.

## 12. Agent 실행

### 12.1 수명

한 `POST /branches/{id}/agent` 요청은 하나의 asyncio task와 Pydantic AI run을 소유한다. 브라우저가
연결을 끊거나 Stop을 누르면 run 취소를 허용한다. 서버는 연결이 없는 run을 계속 실행하거나
나중에 복구하지 않는다.

```text
authenticate -> authorize branch -> assemble context -> run Pydantic AI
             -> AG-UI events -> RUN_FINISHED | RUN_ERROR
```

partial assistant output은 화면에만 존재한다. `RUN_FINISHED` 뒤 frontend가 완성된 user/assistant
turn을 `/branches/{id}/turns`에 저장한다. 저장이 실패하면 같은 완성 turn을 재시도하고 model을 다시
실행하지 않는다.

### 12.2 Model

- `SOT_MODELS`는 Pydantic AI model reference의 순서 있는 목록이다.
- 하나면 그대로 사용하고 둘 이상이면 Pydantic AI `FallbackModel`을 만든다.
- provider key는 각 provider의 표준 환경 변수로 주입한다.
- 요청이 임의 model이나 provider credential을 지정할 수 없다.
- test는 `TestModel` 또는 `FunctionModel`을 사용한다.

### 12.3 Context와 tools

서버가 base instruction, 현재 main, 공개 가능한 branch context와 actor 권한을 조립한다. client가
보낸 system prompt나 server tool 구현을 신뢰하지 않는다.

초기 server tool은 다음 두 개다.

- `session_cite`: 선택 turn을 curation/bundle 후보로 만든다.
- `sot_update`: main을 직접 수정하지 않고 proposal을 만든다.

tool은 application command를 호출하며 route나 repository를 우회하지 않는다. tool 성공은 독립된
제품 transaction으로 확정된다. 이후 model run이 실패해도 이미 성공한 제품 mutation을 rollback한
것처럼 표시하지 않는다.

## 13. 조회와 화면 동기화

v1은 REST snapshot과 mutation 후 refetch를 사용한다. 제품용 SSE journal이나 durable projection은
두지 않는다.

- agent text와 tool event만 AG-UI stream으로 즉시 표시한다.
- 완료된 turn 저장 후 session snapshot을 다시 조회한다.
- proposal decision 후 proposal/document snapshot을 다시 조회한다.
- 여러 탭의 즉시 동기화가 제품 요구사항이 되면 PostgreSQL `LISTEN/NOTIFY` 또는 비내구성 SSE를
  별도 설계한다. 이를 위해 event-sourced write model은 도입하지 않는다.

## 14. 오류와 실패 의미

- 입력 오류는 domain command 실행 전에 거부한다.
- 예상된 domain 오류는 안정적인 code와 HTTP status로 변환한다.
- transaction 실패는 command 전체를 rollback한다.
- provider 실패와 연결 취소는 완료 turn을 만들지 않는다.
- transcript 저장 실패는 완성 text를 client에 남기고 저장만 재시도한다.
- tool mutation 성공 후 stream이 끊기면 mutation은 유지되며 동일 idempotency key 재시도는 기존
  결과를 반환한다.
- main publication 중 어떤 단계라도 실패하면 revision, citation, main pointer가 모두 rollback된다.

## 15. 관측성과 운영

- JSON structured log에 request ID, actor ID, route, resource ID, latency와 result code를 기록한다.
- AG-UI run에는 request ID를 연결하되 prompt와 model output은 기본 로그에 남기지 않는다.
- health endpoint는 process liveness와 database readiness를 구분한다.
- migration은 배포 단계에서 한 번 실행하고 web replica 시작마다 경쟁 실행하지 않는다.
- metric은 HTTP latency/error, DB pool, model latency/error, tool success/error를 포함한다.
- 공개 toss token, bearer token, provider key는 모든 log와 trace에서 제거한다.

## 16. 테스트 전략

### 16.1 Domain

- 상태 전이와 불변 조건을 순수 unit test로 검증한다.
- PostgreSQL, FastAPI, Pydantic AI가 없어도 실행돼야 한다.

### 16.2 Application

- in-memory port와 fake Unit of Work로 권한, idempotency, transaction orchestration을 검증한다.
- 각 command의 success, forbidden, conflict, retry를 검증한다.

### 16.3 Infrastructure

- PostgreSQL 16에서 SQL adapter와 migration을 integration test한다.
- FK, unique, version conflict, rollback과 concurrent approval publication을 검증한다.

### 16.4 API와 Agent

- FastAPI contract test로 auth, validation, error envelope와 response schema를 고정한다.
- Pydantic AI test model로 instruction, context, tool 권한을 검증한다.
- AG-UI contract test로 event ordering과 `RUN_FINISHED`/`RUN_ERROR`를 검증한다.
- 실제 provider smoke test는 opt-in이다.

### 16.5 E2E

현재 Alice/Bob 흐름을 characterization test로 유지한다. 실제 인증을 붙인 뒤에는 test OIDC issuer로
로그인, toss 공개 읽기, sanitized fork, 두 사용자 승인, main publication을 검증한다.

## 17. 현재 vertical slice에서의 전환

현재 구현의 동작을 유지하면서 내부를 단계적으로 교체한다.

1. 기존 backend/API/E2E를 characterization baseline으로 고정한다.
2. composition root와 Unit of Work를 도입한다.
3. `SOTService`를 identity/documents/sessions/sharing/consensus command와 query로 분리한다.
4. 하나의 `ports.py`와 `store/postgres.py`를 모듈별 port/adapter로 이동한다.
5. development identity 뒤에 OIDC adapter와 workspace/session membership을 연결한다.
6. 현재 cite/toss 축약 모델을 curation, immutable bundle, share link 모델로 확장한다.
7. agent tool을 application command adapter로 교체한다.
8. 기존 API compatibility가 불필요해지는 시점에 축약 endpoint와 schema를 제거한다.

각 단계가 끝날 때 기존 vertical E2E는 계속 통과해야 한다. schema 변경은 새 migration으로 추가하며
이미 생성된 local 데이터의 파괴를 전제로 하지 않는다.

## 18. 수용 기준

- FastAPI 애플리케이션 하나와 PostgreSQL 하나로 실행된다.
- Domain이 framework와 persistence package를 import하지 않는다.
- Route와 agent tool이 같은 application policy를 사용한다.
- 제품 mutation 하나가 transaction 하나에 대응한다.
- 실제 OIDC identity와 workspace/session authorization이 적용된다.
- 공개 toss로 draft 원문이나 비선택 turn에 접근할 수 없다.
- concurrent approval에서도 main revision이 한 번만 생성된다.
- provider-neutral fallback model이 동작한다.
- browser disconnect 후 agent run을 복구하거나 replay하려 하지 않는다.
- unit, integration, contract, E2E 검증이 모두 통과한다.
