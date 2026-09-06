# SOT Backend v1 정본 설계

- 상태: 최종 승인
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

### 1.1 설계 인터뷰에서 승인된 결정

1. Workspace가 최상위 tenant이자 권한 경계다.
2. 하나의 PostgreSQL에서 모든 tenant-owned row를 `workspace_id`로 논리 격리한다.
3. Workspace 기본 역할은 `owner`, `member`, `viewer`다.
4. draft session은 기본 비공개이며 session owner와 명시적으로 초대된 사용자만 접근한다.
5. Workspace owner도 초대 없이 private session 본문을 읽을 수 없다.
6. 공통 RBAC 계층이 `(actor, scope, role) -> permission` 평가를 담당한다.
7. role/permission catalog는 코드에 고정하고 scope별 role assignment만 DB에 저장한다.
8. 사용자 정의 role과 권한 편집 기능은 v1 범위에서 제외한다.
9. 인증 수단은 provider adapter로 확장할 수 있어야 하며 현재 확정된 provider는 Google SSO다.
10. 모든 인증 수단은 하나의 `AuthFacade`를 거쳐 동일한 사용자 연결과 token 발급 흐름을 사용한다.
11. Google token은 Google 신원 확인에만 사용하고 SOT API 인증에는 SOT 자체 Access/Refresh
    Token을 사용한다.
12. Access Token은 frontend memory에만 보관하고 `Authorization: Bearer`로 전송한다.
13. Refresh Token은 `HttpOnly`, `Secure`, `SameSite` cookie로 전달하고 refresh 때 rotation한다.
14. v1은 `GoogleAuthAdapter`만 구현하고 사용되지 않는 이메일 adapter나 빈 구현은 만들지 않는다.
15. `AuthProvider` 경계는 실제 provider 추가 시 `AuthFacade`의 token 흐름을 재사용할 수 있는 최소
    contract로 유지한다.
16. 한 사용자의 여러 브라우저·기기 동시 로그인을 허용하고 refresh-token family마다 독립된
    auth session을 둔다.
17. 전체 backend는 도메인 중심 모듈러 모놀리스로 구성한다. 최상위 제품 모듈은 `identity`,
    `workspace`, `document`, `session`, `sharing`, `consensus`, `agent`다.
18. 각 제품 모듈은 자기 API, application use case, domain policy, port와 infrastructure adapter를
    소유하며 다른 모듈의 DB adapter를 직접 참조하지 않는다.
19. 현재 요구사항에는 내부 event bus를 두지 않는다. 모듈 간 협업은 공개된 application port를
    통한 동기식 in-process 호출로 처리한다.
20. 현재 서비스 규모는 단일 FastAPI deployable과 7개 제품 모듈로 유지하며 더 작은 service로
    분리하지 않는다.
21. 외부 command의 최상위 application handler가 Unit of Work와 PostgreSQL transaction 하나를
    소유한다.
22. 여러 모듈이 참여하는 use case도 같은 UoW에 참여하며 repository와 하위 application port는
    직접 commit하지 않는다.
23. aggregate의 상태 전이와 자체 불변조건은 Domain 객체가 소유하고, 인증·RBAC·transaction과
    모듈 간 조율은 Application handler가 소유한다.
24. 하나의 거대한 service와 상태 없이 데이터만 담는 anemic domain model을 모두 피한다.
25. 범용 `BaseRepository[T]`를 만들지 않고 aggregate별 command repository port를 둔다.
26. 화면과 API 조회는 같은 PostgreSQL을 사용하는 query port가 projection DTO를 직접 만들며,
    별도 CQRS infrastructure나 read database는 두지 않는다.
27. FastAPI/Pydantic request·response DTO, Application command·result, Domain entity·value object를
    분리하고 경계에서 명시적으로 mapping한다.
28. Domain layer는 Pydantic model을 사용하지 않고 순수 Python 타입으로 유지한다.
29. 별도 DI framework와 service locator를 두지 않고 `build_app()` composition root에서 모든
    adapter와 application 객체를 명시적으로 조립한다.
30. Application 의존성은 constructor injection으로 연결하고 FastAPI `Depends`는 actor와
    request-scoped dependency 같은 inbound HTTP 경계에만 사용한다.
31. Agent의 canonical conversation history는 browser가 보낸 message 배열이 아니라 권한 확인 후
    PostgreSQL에서 조회한 branch의 완료 Turn이다.
32. AG-UI request에서는 현재 실행의 최신 사용자 입력만 실행 입력으로 받아들이고, 완료되지 않은
    client history를 제품 상태나 agent context로 신뢰하지 않는다.
33. Pydantic AI Agent 정의는 application lifetime에 한 번 조립해 재사용한다.
34. actor, workspace, branch, canonical history와 application port는 request-scoped `AgentDeps`로
    전달하며 Agent singleton에는 mutable conversation state를 두지 않는다.
35. PostgreSQL adapter는 ORM 없이 `psycopg` async와 명시적 SQL을 사용한다. Domain 객체와 row의
    mapping은 각 모듈의 persistence adapter가 소유한다.
36. v1은 PostgreSQL RLS를 사용하지 않는다. Application RBAC, workspace-scoped repository API,
    composite FK/unique constraint의 세 경계로 tenant 격리를 강제한다.
37. 제품 모듈 의존 관계는 `document -> workspace`, `session -> workspace/document`,
    `sharing -> workspace/session`, `consensus -> workspace/document/session/sharing`,
    `agent -> workspace/document/session/consensus`의 비순환 graph로 제한한다.
38. `shared`에는 ID, Clock, Error, Unit of Work 같은 기술 중립 primitive만 두고 제품 정책이나
    aggregate를 넣지 않는다.
39. 모듈 전체를 노출하는 범용 Facade 대신 소비자가 실제로 사용하는 capability 단위의 좁은
    application `Protocol`과 immutable result DTO를 공개한다. `SessionAuthorizer`도 불변
    `SessionView`만 반환하며 mutable aggregate, 내부 handler와 repository는 모듈 밖에서 import하지 않는다.
40. 각 table의 소유 모듈은 명확히 하되 PostgreSQL migration은 repository 전체의 단일 선형
    sequence로 관리하고 배포 단계의 별도 command로 실행한다.
41. 예상 가능한 Domain/Application 실패는 typed error와 안정적인 error code로 표현하고,
    FastAPI 전역 error mapper만 HTTP status와 response envelope로 변환한다.
42. 전역 idempotency middleware와 공통 deduplication table은 두지 않는다. 기본 무결성은
    transaction, unique constraint와 expected version으로 지키고 실제 중복 위험이 확인된
    use case에만 국소 idempotency를 설계한다.
43. Unit of Work는 transaction lifecycle만 소유한다. 같은 transaction에 참여하는 application
    port와 repository 호출은 opaque `TransactionContext`를 명시적으로 전달한다.
44. Transaction을 `contextvar`로 숨기거나 모든 module repository를 속성으로 가진 거대한 UoW를
    만들지 않는다.
45. CI architecture test가 layer dependency, module DAG, `contracts.py` 외 cross-module import와
    framework/persistence package의 Domain 유입을 자동으로 검사한다.
46. 읽기 adapter도 다른 모듈 소유 table을 직접 조회하거나 JOIN하지 않는다. 복합 화면은 최상위
    query handler가 각 모듈의 query port를 조합한다.
47. 실제 측정된 성능 문제가 생기기 전에는 cross-module denormalized projection을 만들지 않는다.
48. Access Token은 사용자 identity만 나타내며 현재 workspace를 token claim이나 server session에
    고정하지 않는다. 인증된 제품 API는 URL의 `/workspaces/{workspace_id}`로 tenant context를
    명시한다.
49. 인증 endpoint와 인증 전 공개 bundle을 읽는 `GET /tosses/{token}`은 workspace prefix 밖에 둔다.
    공개 toss를 fork할 때는 인증 후 destination workspace를 URL로 명시한다.
50. 공개 toss fork는 수신자가 접근 가능한 destination workspace에 새로운 private Session과 Branch를
    만든다. 공개 BundleItem만 seed history로 복사하며 source workspace membership, source session
    role, 비공개 draft 접근권한과 이후 변경의 실시간 연결은 승계하지 않는다. 생성된 fork는 원본
    toss가 나중에 revoke되어도 독립적으로 유지된다. 이 fork Session은 `document_id = None`인
    detached Session이다. Destination Document를 자동 생성하지 않고 source Document 링크도 저장하지
    않는다. 일반 `/documents/{document_id}/sessions` 생성은 같은 workspace의 Document를 필수로 검증한다.
51. Fork에는 내부 감사용 `source_bundle_id`와 공개 시점의 제한된 attribution snapshot을 provenance로
    저장한다. 이 값은 source workspace를 조회하거나 권한을 얻는 live reference가 아니며 DB foreign
    key나 cross-workspace JOIN에 사용하지 않는다. 외부 API에는 attribution snapshot만 노출한다.
52. Agent endpoint가 완성된 user/assistant/tool Turn을 서버에서 원자적으로 저장한 뒤
    `RUN_FINISHED`를 전송한다. Frontend는 transcript를 별도 append하지 않고 stream 표시 후 snapshot만
    다시 조회한다. Partial output과 취소된 run은 저장하지 않는다.
53. Agent run은 장시간 외부 I/O를 포함하는 orchestration이므로 model 호출 동안 PostgreSQL
    transaction을 유지하지 않는다. 권한/context 조회, 각 tool command, 완료 Turn append는 각각
    짧은 transaction을 사용한다.
54. 같은 Branch의 동시 Agent run은 lock이나 durable run record로 직렬화하지 않는다. 각 run이
    시작 시 `base_branch_version`을 고정하고 optimistic concurrency를 사용한다. 먼저 Branch를
    변경한 run이 lineage를 선점하며 뒤늦은 run은 `version_conflict`로 `RUN_ERROR`를 보낸다. 의도적인
    병렬 작업은 별도 Branch에서 실행한다.
55. Agent는 실행 중 `expected_branch_version`을 lineage token처럼 유지한다. Branch-scoped tool
    command와 완료 Turn append는 같은 transaction에서 현재 version을 검사하고 성공 시 증가된 version을
    반환한다. 경쟁 run은 첫 충돌에서 중단되므로 transcript 없이 proposal/citation 같은 tool 부작용만
    남지 않는다.
56. 공유 상태는 Session이나 Bundle이 아니라 ShareLink(toss)가 소유한다. Session lifecycle은
    `open -> closed`이고, Bundle은 발행 후 상태 전이 없이 영구 immutable이다. ShareLink만
    `active -> revoked` 또는 `expired`로 전이한다. Toss 생성은 private Session을 공개 상태로 바꾸지
    않는다.
57. Required approver 집합은 Proposal version 생성 시점의 immutable snapshot이다. 초기 version은
    creator와 당시 source Session의 owner/editor를 자동 포함한다. 이후 Session membership 변경은
    진행 중인 version의 승인 조건을 바꾸지 않으며, approver 구성을 바꾸려면 명시적으로 새 Proposal
    version을 만들어 이전 approval을 무효화한다.
58. 마지막 required approval은 Proposal을 `approved`로만 전이하고 main을 자동 변경하지 않는다.
    `document.publish` permission을 가진 actor가 별도 `MergeProposal` command를 호출해야 한다. Merge는
    base revision을 다시 검사하고 새 revision, citation과 main pointer를 한 transaction에서
    변경한다. Background publication이나 내부 event는 사용하지 않는다.
59. SessionMember는 항상 같은 Workspace의 WorkspaceMember여야 한다. 외부 사용자의 private Session
    초대는 Workspace membership을 먼저 만든 뒤 별도 Session role을 부여한다. Workspace membership만으로
    private Session 접근권한이 생기지 않으며, 인증 없는 공개 toss 조회만 이 membership 계층의
    예외다.
60. Private Session의 effective permission은 Workspace role과 Session role이 모두 허용하는
    교집합이다. Workspace role은 권한 상한이고 Session role은 해당 Session에 대한 명시적 grant다.
    따라서 Workspace owner도 Session role 없이는 본문에 접근할 수 없고, Workspace viewer는 Session
    editor를 받아도 편집할 수 없다.

### 1.2 아직 확정하지 않은 항목

- 이메일 로그인은 현재 없으며 도입 시점과 credential 방식은 미확정
- Access/Refresh Token 수명과 signing key 운용

### 1.3 인터뷰 범위

사용자 확인은 모듈 경계, 의존 방향, transaction 소유권, 인증/권한 경계, agent 통합처럼 변경
비용이 큰 구조 결정에 집중한다. Token TTL, cookie 세부값, pool 크기 같은 운영 기본값은 보안 기준과
일반적인 기본값으로 정하고 설정 가능하게 만들며 구조 인터뷰의 승인 단계로 취급하지 않는다.

이하 구조는 위 승인 결정을 통합한 최종안이다. 구현은 이 문서를 기준으로 작성한 단계별 계획에 따라
진행한다.

## 2. 목표

1. 사적 draft session과 공개 가능한 합의 상태를 명확히 분리한다.
2. session, branch, curation, bundle, toss, proposal, approval, main revision을 제품 도메인으로
   구현한다.
3. FastAPI route, application use case, domain policy, PostgreSQL adapter의 책임을 분리한다.
4. 여러 인증 provider를 통합할 수 있는 실제 사용자 인증과 workspace/session 권한을 모든 명령과
   조회에서 일관되게 적용한다.
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
- 모듈 간 호출은 상대 모듈이 공개한 application port만 사용한다.
- 비동기 fan-out이나 독립 consumer 요구가 생기기 전에는 event bus, outbox와 내부 broker를
  도입하지 않는다.

FastAPI의 Pydantic schema는 presentation adapter의 wire contract다. Route가 이를 Application
command로 mapping하고, query result를 response DTO로 mapping한다. Application과 Domain 객체를
FastAPI response로 직접 serialization하지 않는다.

## 5. 제품 모듈

### 5.1 `identity`

- 인증 provider의 검증된 identity를 SOT user에 연결
- provider adapter를 통합하는 `AuthFacade`
- SOT Access/Refresh Token 발급과 auth session 관리
- local/test 전용 development identity

### 5.2 `workspace`

- Workspace와 WorkspaceMember
- workspace role assignment와 permission evaluation
- tenant context와 `workspace_id` 격리 정책

### 5.3 `document`

- Document와 immutable DocumentRevision
- current main pointer
- revision provenance와 citation 조회
- main 변경의 optimistic concurrency

### 5.4 `session`

- Session, SessionMember, Branch
- `SessionMember ⊆ WorkspaceMember` membership 계층
- 완료된 user/assistant/tool Turn
- private draft 접근 정책, `open/closed` lifecycle과 branch 상태
- curation op, bundle preview와 immutable Bundle
- fork provenance와 공개 attribution snapshot

### 5.5 `sharing`

- bundle share link, 제품 용어로서의 toss
- ShareLink의 `active/revoked/expired` 상태, token hashing, 만료, revoke와 rotate
- 인증 없는 공개 bundle 조회
- destination workspace에 공개된 bundle만 복사하는 sanitized fork
- fork를 통한 source workspace/session 권한 승계를 차단하는 경계

### 5.6 `consensus`

- versioned Proposal
- Proposal version 생성 시 고정되는 required approver snapshot과 version별 Approval
- reject, stale, approved, merged 상태 전이
- 승인 완료와 명시적인 DocumentRevision publication의 분리

초기 Proposal version은 creator와 생성 당시 source Session의 owner/editor를 required approver에
자동 포함한다. Creator는 approver를 추가할 수 있지만 자동 포함된 사용자를 같은 version에서 제거할
수 없다. Session membership이 바뀌어도 이미 생성된 version의 snapshot은 변하지 않는다. Approver
구성 변경은 새 Proposal version 생성으로 표현하며 그 version의 mandatory approver를 다시 검증한다.
마지막 Approval은 Proposal을 `approved`로만 바꾼다. Main publication은 `document.publish` permission을
가진 actor가 별도 `MergeProposal` command로 요청한다.

### 5.7 `agent`

- server-owned instruction과 tool registry
- branch context assembly
- Pydantic AI model/fallback 구성
- AG-UI request와 event 변환
- application use case를 호출하는 tool adapter

`agent`는 제품 aggregate를 소유하지 않는다. agent가 만든 cite나 proposal도 각각 session 또는
consensus application use case를 통해 저장한다.

### 5.8 모듈 의존성 graph

화살표는 호출하는 모듈이 의존하는 application port를 뜻한다.

```text
document  -> workspace authorization
session   -> workspace authorization + document query
sharing   -> workspace authorization + session bundle/fork
consensus -> workspace authorization + document publication + session/sharing query
agent     -> workspace authorization + document/session/consensus commands and queries
```

`identity`는 인증된 Actor를 만드는 경계이며 제품 모듈은 Google adapter나 token 구현을 직접
참조하지 않는다. 위 의존 방향의 반대 import와 module cycle은 허용하지 않는다.

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
├── workspace/
├── document/
├── session/
├── sharing/
├── consensus/
└── agent/
    ├── api.py                 # AG-UI endpoint
    ├── application.py         # context assembly와 run 요청
    ├── models.py              # provider-neutral model construction
    ├── prompts.py
    └── tools.py               # application command adapters

backend/tests/architecture/
└── test_dependencies.py       # layer와 module import 규칙
```

`identity`, `workspace`, `document`, `session`, `sharing`, `consensus` 모듈은 규모에 따라 다음 내부
파일을 가진다.

```text
<module>/
├── api.py                     # inbound HTTP adapter
├── contracts.py               # 다른 모듈에 공개하는 좁은 application API
├── application.py             # command/query handlers
├── domain.py                  # entities, value objects, policy
├── ports.py                   # repository/query ports
└── postgres.py                # outbound persistence adapter
```

각 모듈은 같은 내부 형태를 사용하되 파일이 작을 때 불필요한 하위 디렉터리를 만들지 않는다.
공유 코드는 기술적으로 중립적인 primitive로 제한한다. 제품 정책을 `shared`에 넣지 않는다.

`bootstrap.app.build_app()`은 PostgreSQL pool, Unit of Work factory, module repository/query
adapter, application handler, `AuthFacade`, Pydantic AI agent와 FastAPI router를 조립한다. 런타임에
전역 service locator로 dependency를 조회하지 않는다.

### 6.1 모듈 공개 surface

다른 제품 모듈은 상대 모듈의 `contracts.py`에 선언된 capability `Protocol`과 immutable result DTO만
참조한다. 예를 들어 consensus는 `DocumentPublisher`와 `BundleReader`, sharing은
`ShareableBundleReader`, agent는 `BranchContextReader`, `BranchVersionGuard`, `CompletedTurnsAppender`,
`CiteCreator`, `ProposalCreator`에 의존한다. 내부
application handler, Domain aggregate, repository port와 PostgreSQL adapter는 외부에 공개하지 않는다.

`SessionAuthorizer.require()`는 권한을 확인한 뒤 `id`, `workspace_id`, nullable `document_id`,
`created_by`, `created_at`, `status`만 가진 frozen `SessionView`를 반환한다. `close()` 같은 상태 전이와
mutable Session aggregate의 load/save는 session application 내부에서만 수행한다.

`ShareableBundleReader.require_shareable_snapshot()`는 actor, workspace ID, Bundle ID를 받아 Bundle의
실제 소유 Session을 session 모듈 안에서 조회하고 그 Session의 owner 전용 `PUBLISH_BUNDLE` permission을
검증한다. 별도로 전달받은 Session ID로 권한을 대신 검증하지 않는다. 반환값은 불변 내부 wrapper
`ShareableBundleSnapshot(snapshot: BundleSnapshot, published_by: UserId)`다. `published_by`는 실제 Bundle
게시자이며 공유 링크 생성자를 대신 사용하지 않는다. 기존 `BundleSnapshot`과 모든 공개 응답에는 publisher ID나
private Session/Workspace 소유 정보를 추가하지 않는다. 일반 `BundleReader`의 읽기 권한은 공유 권한이 아니다.

Sharing은 `IdentityAttributionReader.require_attribution(tx, published_by)`로 표시 이름만 읽는다.
공개 `author_display_name`은 **실제 Bundle 게시자의 표시 이름**이며 ShareLink 생성 시점에 고정한다.
이후 프로필 변경은 기존 공개 snapshot과 그 snapshot으로 만든 fork의 attribution을 바꾸지 않는다.
공개 snapshot은 sharing 소유 상태에 저장하며 익명 읽기는 identity/session 조회나 권한 검사를 수행하지 않는다.

`CompletedTurnsAppender.execute()`는 actor, workspace ID, Branch ID, expected version과 완료된
user/assistant/tool message tuple을 받아 새 Turn과 증가한 Branch version을 불변 결과로 반환한다.
session 내부 `AppendCompletedTurns` handler가 이 Protocol을 구조적으로 구현하며 저장과 version 변경을
하나의 짧은 transaction으로 commit한다. Agent는 `session.contracts`에서 이 계약만 import한다.

`BranchVersionGuard`는 agent run ID나 lock을 관리하지 않는다. 같은 transaction 안에서
`expected_branch_version`을 검증하고 Branch version을 증가시킨 뒤 새 version을 반환하는 좁은
session application contract다. 다른 모듈의 tool command는 이 guard와 자기 domain mutation을 하나의
Unit of Work 안에서 조합한다.

인증의 `AuthFacade`는 provider별 진입을 하나의 token 흐름으로 통합하는 명시적인 application
경계이므로 유지한다. 다른 모듈에 범용 Facade 패턴을 자동 적용하지 않는다.

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

각 mutation은 actor, aggregate ID, 입력 payload와 versioned 변경에 필요한 expected version을
명시적으로 받는다. handler 하나가 transaction 하나를 연다. transaction 안에서 권한 확인,
aggregate 로드, domain transition, 저장이 완료된다.

여러 모듈이 함께 필요한 use case도 공개 application port를 동기식으로 조합한다. 호출 관계를
숨기는 mediator나 내부 event bus는 두지 않는다.

최상위 handler가 만든 request-scoped Unit of Work를 하위 호출이 공유한다. Unit of Work는 하나의
PostgreSQL transaction lifecycle만 소유하고 opaque `TransactionContext`를 반환한다. 같은
transaction에 참여하는 repository와 application port는 `tx`를 명시적인 첫 번째 dependency로
받는다. 실제 `psycopg` connection은 infrastructure adapter 밖으로 노출하지 않는다.

Repository와 하위 application port는 commit/rollback하지 않으며 최상위 handler 종료 시 한 번만
결정한다. `contextvar`에 현재 transaction을 숨기거나 모든 module repository를 속성으로 제공하는
거대한 UoW 객체는 두지 않는다.

조회는 transaction을 길게 유지하지 않는다. 조회 전용 port가 응답 projection을 만들 수 있지만
권한 필터를 우회할 수는 없다.

Command repository는 `SessionRepository`, `ProposalRepository`처럼 aggregate 단위로 정의하고
Domain 객체를 load/save한다. 공통 CRUD를 강제하는 generic base repository는 두지 않는다.

Query port는 Domain aggregate를 억지로 조립하지 않고 화면에 필요한 projection DTO를 같은
PostgreSQL에서 직접 조회한다. 이 구분은 코드 책임 분리이며 별도 read model 저장소, event projection,
CQRS 배포를 의미하지 않는다.

Query adapter는 자기 모듈 소유 table만 읽는다. 여러 모듈의 정보가 필요한 화면은 최상위 query
handler가 `DocumentReader`, `ProposalSummaryReader`, `BundleProvenanceReader` 같은 공개 query port를
호출해 result DTO를 조합한다. 일관된 snapshot이 필요하면 같은 read-only `TransactionContext`를
명시적으로 공유한다. 실제 성능 문제가 측정되기 전에는 cross-module SQL JOIN이나 denormalized
projection을 예외로 추가하지 않는다.

## 8. Domain 정책

Domain entity와 value object는 자기 상태 전이와 로컬 불변조건을 직접 검증한다. Application
handler는 actor 권한을 확인하고 aggregate를 load한 뒤 domain method를 호출하며, 여러 aggregate와
모듈 사이의 순서와 transaction을 조율한다. Domain 객체는 repository, 외부 service와 현재 actor를
직접 조회하지 않는다.

### 8.1 핵심 불변 조건

1. draft turn은 branch에 append-only로 저장한다.
2. 완료되지 않은 assistant output은 Turn이 아니다.
3. curation은 원본 turn을 변경하지 않고 공개 projection만 만든다.
4. Bundle은 publish 후 immutable이며 새 정리는 새 version이다.
5. 공개 toss로 선택되지 않은 draft turn을 조회할 수 없다.
6. sanitized fork는 공개 BundleItem만 seed history로 복사해 destination workspace의 새 private
   Session과 Branch를 만든다. 공개 fork Session만 `document_id = None`을 허용하며
   `Session.create_detached_fork()`로 명시적으로 생성한다. 일반 `Session.create()`는 DocumentId가
   필수다. Fork는 destination Document를 자동 생성하거나 source Document를 연결하지 않는다.
7. fork는 source workspace membership이나 source session role을 만들지 않으며 source 변경과
   동기화되지 않는다. 이후 toss revoke도 이미 생성된 fork를 삭제하지 않는다.
8. fork provenance의 `source_bundle_id`는 감사용 opaque ID다. Runtime authorization이나 source
   data 조회에 사용하지 않고 외부에는 공개 시점 attribution snapshot만 노출한다.
9. SessionMember는 Session과 같은 workspace의 WorkspaceMember만 될 수 있다.
10. Required approver 집합과 Approval은 proposal version에 귀속된다.
11. Session membership 변경은 이미 생성된 Proposal version의 required approver snapshot을 바꾸지
    않는다.
12. proposal body나 approver 구성이 바뀌면 새 version이 되며 이전 approval은 효력을 잃는다.
13. required approver가 모두 같은 version을 승인해야 merge할 수 있다.
14. Proposal의 base revision이 current main과 다르면 merge하지 않고 stale로 전환한다.
15. merge는 새 immutable revision 생성, citation 생성, main pointer 이동을 한 transaction에서 한다.
16. 마지막 approval은 Proposal을 `approved`로만 전이하며 main publication을 자동 실행하지 않는다.
17. 중복 command가 유효한 새 요청인지 재시도인지 구분해야 하는 use case는 자기 계약에서
    idempotency 정책을 명시한다.

`JoinTurns`의 provenance source ID 순서는 명시적인 입력 순서를 보존한다. 결과 item은 선택된 item 중
기존 projection의 가장 앞 위치에 놓고 그 item의 role을 유지하며, 선택되지 않은 item의 순서는 유지한다.
이미 join된 item을 다시 join할 때는 그 item의 모든 source ID를 선택해야 한다. 일부만 선택하면 projection과
원본 Turn을 변경하지 않고 `curation_selection_partial`로 거부한다.

### 8.2 상태

```text
Session:   open -> closed
Bundle:    immutable snapshot; 상태 전이 없음
ShareLink: active -> revoked
                  \-> expired
Proposal: open -> approved -> merged
               ├-> rejected
               └-> stale
```

“draft”는 private 작업 내용을 뜻하는 제품 용어이며 Session의 상태값이 아니다. Bundle을 publish하거나
ShareLink를 생성해도 Session은 계속 private `open` 상태다. main도 Session 상태가 아니라 Document가
가리키는 최신 승인 revision이다.

## 9. PostgreSQL

### 9.1 소유 데이터

PostgreSQL은 다음 제품 데이터만 저장한다.

- `sot_user`, `sot_user_identity`, `sot_auth_session`
- `sot_workspace`, `sot_workspace_member`
- `sot_document`, `sot_document_revision`, `sot_revision_citation`
- `sot_session`, `sot_session_member`, `sot_branch`, `sot_turn`, `sot_fork_origin`
- `sot_curation_op`, `sot_bundle`, `sot_bundle_item`
- `sot_share_link`
- `sot_proposal`, `sot_proposal_bundle`, `sot_proposal_approver`, `sot_approval`

다음 데이터는 저장하지 않는다.

- provider streaming chunk
- AG-UI event
- partial assistant message
- agent run, lease, checkpoint 또는 replay cursor
- model provider 내부 상태

### 9.2 저장 방식

- PostgreSQL 16과 `psycopg` async pool을 사용한다.
- ORM을 도입하지 않고 명시적 SQL adapter를 유지한다.
- SQL row와 Domain entity 사이의 mapping은 module persistence adapter 안에 명시적으로 둔다.
- migration은 순방향 SQL 파일이며 애플리케이션 시작과 별도의 명령으로 실행할 수 있어야 한다.
- repository는 aggregate 저장과 조회를 담당하고 transaction을 스스로 commit하지 않는다.
- command repository와 query adapter는 분리하되 같은 PostgreSQL pool과 schema를 사용한다.
- Unit of Work factory가 transaction lifecycle과 opaque `TransactionContext`를 만들고, module
  repository adapter는 이 context를 명시적으로 받는다.
- 외래 키, unique, check constraint로 표현 가능한 불변 조건은 DB에도 둔다.

### 9.3 동시성

- versioned aggregate mutation은 `expected_version`을 검사한다.
- turn ordinal은 `(branch_id, ordinal)` unique와 transaction 안의 순번 할당으로 보호한다.
- Agent run은 context 조회 시 `base_branch_version`을 잡는다. 각 branch-scoped tool command와 완료
  transcript append는 현재 `expected_branch_version`을 조건으로 Branch version을 증가시키고 새
  version을 run에 반환한다.
- 마지막 approval과 publication은 proposal/document row lock 안에서 처리한다.
- `(document_id, revision_number)`와 `(proposal_id, proposal_version, approver_user_id)`는 unique
  constraint로 중복을 막는다.
- 전역 deduplication record 대신 aggregate version과 domain별 unique constraint를 사용한다.

Agent 실행 자체는 재개하거나 exactly-once로 만들지 않는다. 이미 성공한 agent tool의 제품
mutation은 유지되며 자동 재실행하지 않는다. 실제 중복 실행 사례가 생긴 command에만 별도
idempotency key와 constraint를 추가한다.

Branch별 in-memory lock, PostgreSQL advisory lock, 장시간 row lock과 durable agent-run table은 두지
않는다. 같은 Branch의 경쟁 run은 첫 tool mutation 또는 완료 transcript append의 version conflict에서
`RUN_ERROR`로 종료한다. 사용자가 병렬 대화를 원하면 기존 context에서 새 Branch를 먼저 만든다.

### 9.4 Tenant 격리

- 모든 tenant-owned table과 repository method는 `workspace_id`를 필수로 가진다.
- Application handler는 repository 호출 전에 actor의 workspace membership과 permission을 검사한다.
- 하위 row가 다른 workspace의 상위 row를 참조하지 못하도록 `(workspace_id, resource_id)` composite
  foreign key를 사용한다.
- `sot_session_member(workspace_id, user_id)`는
  `sot_workspace_member(workspace_id, user_id)`를 composite foreign key로 참조한다.
- Migration `004_document_session.sql`의 `sot_session.document_id`는 detached public-fork를 위해
  nullable이다. 값이 있으면 `(workspace_id, document_id)` composite foreign key로 같은 workspace의
  Document만 참조한다. NULL은 공개 fork 생성 경로에서만 사용하고 일반 session 생성은 Document를
  필수로 검증한다. Source Document ID를 위한 별도 field/FK는 두지 않는다.
- `sot_fork_origin.source_bundle_id`는 live relation이 아닌 감사용 opaque value이므로 의도적으로
  source bundle foreign key를 두지 않는다. Destination workspace의 attribution snapshot만 일반
  tenant-owned data로 취급한다.
- unique constraint도 전역이 필요한 identity를 제외하고 `workspace_id` 범위로 정의한다.
- v1에는 PostgreSQL RLS와 connection-level tenant session variable을 도입하지 않는다.

### 9.5 Migration 소유권

`backend/migrations/`가 단일 migration timeline을 소유한다. 파일명은 전역 sequence와 변경 대상
module을 나타낸다. Module별 migration runner나 독립 schema version은 두지 않는다. 하나의 변경이
여러 module table과 constraint를 원자적으로 바꿔야 하면 같은 migration에 포함할 수 있다.

애플리케이션 replica는 시작하면서 migration을 실행하지 않는다. 배포 pipeline이나 명시적인 관리
command가 migration을 먼저 적용한 뒤 호환되는 애플리케이션을 시작한다.

## 10. 인증과 권한

### 10.1 단일 인증 Facade

현재 확정된 인증 provider는 Google SSO다. 이메일 로그인은 아직 없으며 도입 시점과 credential
방식은 이후 결정한다. HTTP route는 provider별 사용자·token 처리 로직을 갖지 않고
`AuthFacade`만 호출한다.

v1에는 `GoogleAuthAdapter`만 구현한다. 이메일용 빈 adapter나 사용되지 않는 provider registry는
만들지 않는다. `AuthProvider` contract는 검증된 identity를 `AuthFacade`에 전달하는 최소 경계다.

```text
Future provider ────> AuthProvider ─────┐
                                       ├─> AuthFacade ─> SOT user/session/token
Google OIDC ────────> GoogleAuthAdapter ┘
```

Provider adapter는 credential 또는 외부 token을 검증해 정규화한 identity를 반환한다.
`AuthFacade`는 identity-user 연결, 가입 정책, auth session 생성, SOT token 발급, refresh, logout을
통합 처리한다. Google identity key는 변경 가능한 이메일이 아니라 `(issuer, subject)`다.
Google API를 사용하지 않는 한 Google refresh token은 저장하지 않는다.

`X-SOT-User: alice|bob` 방식은 local/test profile에서만 활성화하며 운영 설정에서는 애플리케이션
시작 단계에 거부한다.

### 10.2 SOT Token

- Access Token은 짧은 수명의 SOT JWT다.
- Frontend는 Access Token을 memory에만 보관하고 `Authorization: Bearer`로 전달한다.
- Refresh Token은 긴 random opaque value이며 DB에는 hash만 저장한다.
- Refresh Token은 `HttpOnly`, `Secure`, `SameSite` cookie로만 전달한다.
- refresh할 때 기존 token을 폐기하고 새 Refresh Token으로 rotation한다.
- provider 종류와 관계없이 같은 Access/Refresh Token 계약을 사용한다.
- refresh-token family 하나가 브라우저·기기 하나의 독립된 auth session을 나타낸다.
- 사용자는 여러 auth session을 동시에 가질 수 있다.
- 현재 기기 logout은 해당 auth session만 revoke하고 전체 logout은 사용자의 모든 auth session을
  revoke한다.

### 10.3 권한

Workspace role:

- `owner`: workspace 관리와 기본 `document.publish` permission
- `member`: session, bundle, proposal 생성과 참여
- `viewer`: 허용된 문서와 session 읽기

Role과 permission catalog는 코드에 고정한다. DB에는 workspace 또는 session scope에 대한 role
assignment만 저장한다. 공통 authorization service가 API와 agent tool에서 동일하게
`(actor, scope, permission)`을 평가한다.

Private Session action의 effective permission은 다음 두 조건을 모두 만족해야 한다.

1. 현재 Workspace membership과 role이 그 종류의 action을 허용한다.
2. 해당 Session의 명시적 membership과 role이 같은 action을 허용한다.

Workspace role은 상한선이므로 Session role이 이를 넘어 권한을 승격하지 않는다. 대표 조합은 다음과
같다.

| Workspace role | Session role | 결과 |
| --- | --- | --- |
| `member` | `editor` | 편집 가능 |
| `member` | `viewer` | 읽기만 가능 |
| `viewer` | `editor` | 읽기만 가능; 편집 불가 |
| `owner` | 없음 | private Session 접근 불가 |

Session role:

- `owner`: member, bundle, toss 관리
- `editor`: turn, curation, proposal 생성
- `viewer`: 읽기

Private session은 session owner와 명시적으로 초대된 사용자만 접근할 수 있다. Workspace owner도
초대 없이 private session 본문을 읽을 수 없다.

Session에 사용자를 초대하려면 그 사용자가 먼저 같은 Workspace의 멤버여야 한다. Workspace role은
Session 초대 자격과 workspace 수준 기능만 결정하고 private Session 본문 권한을 암묵적으로 부여하지
않는다.

공개 toss token은 정확히 하나의 immutable bundle을 읽는 capability다. workspace나 draft 접근권한을
부여하지 않는다. raw token은 생성 응답과 URL에서만 사용하며 DB에는 SHA-256 hash만 저장한다.
공개 응답에는 `Cache-Control: private, no-store`를 설정하고 access log에서 token path를 가린다.

Toss 생성은 `ShareableBundleReader`로 그 Bundle의 실제 소유 Session에 대한 owner 권한을 검증한다.
다른 Session의 owner이거나 대상 Session의 viewer/editor라는 사실로 대상 Bundle을 공유할 수 없다.

인증된 fork 요청의 `workspace_id`는 새 detached Session(`document_id = None`)과 Branch가 속할
destination workspace다. Document를 자동 생성하지 않고 source Document 링크도 저장하지 않는다. Handler는
actor가 그 workspace에 session을 만들 권한이 있는지 먼저 확인하고 공개 BundleItem snapshot만
session 모듈에 전달한다. Source workspace ID나 source session ID는 권한으로 변환되지 않는다.

## 11. HTTP API

모든 제품 API는 `/api/v1` 아래에 둔다. command route는 인증, schema validation, handler 호출,
응답 변환만 담당한다.

아래 표는 공통 `/api/v1` prefix를 생략한다. 인증된 tenant resource route는
`/workspaces/{workspace_id}` 아래에 둔다. Access Token은 사용자만 식별하며 route의
`workspace_id`가 request의 tenant context가 된다. 다만 path에 workspace가 있다는 사실 자체가
접근 권한을 부여하지는 않는다. Application handler는 actor의 workspace/session 권한을 확인하고,
하위 resource ID가 해당 workspace에 속하는지도 workspace-scoped port로 검증한다.

Versioned aggregate 변경은 body의 `expected_version`을 검사한다. API client는 mutation 실패를
자동 재시도하지 않는다. Idempotency가 필요한 use case가 생기면 해당 endpoint 계약에만 key를
추가한다.

### 11.1 Identity와 workspace

| Method | Path | 목적 |
| --- | --- | --- |
| `GET` | `/me` | 현재 사용자 |
| `GET` | `/workspaces` | 접근 가능한 workspace |
| `POST` | `/workspaces` | workspace 생성 |
| `POST` | `/workspaces/{workspace_id}/members` | member 추가 |

### 11.2 Documents와 sessions

| Method | Path | 목적 |
| --- | --- | --- |
| `GET` | `/workspaces/{workspace_id}/documents/{document_id}` | current main과 provenance |
| `GET` | `/workspaces/{workspace_id}/documents/{document_id}/revisions/{number}` | 과거 revision |
| `POST` | `/workspaces/{workspace_id}/documents/{document_id}/sessions` | draft session 생성 |
| `GET` | `/workspaces/{workspace_id}/sessions/{session_id}` | session, branch, turn snapshot |
| `POST` | `/workspaces/{workspace_id}/sessions/{session_id}/branches` | 권한 내 draft branch |
| `POST` | `/workspaces/{workspace_id}/branches/{branch_id}/curation-ops` | 공개 projection 편집 |
| `GET` | `/workspaces/{workspace_id}/branches/{branch_id}/bundle-preview` | 현재 preview |
| `POST` | `/workspaces/{workspace_id}/branches/{branch_id}/bundles` | immutable bundle publish |

### 11.3 Toss와 consensus

| Method | Path | 목적 |
| --- | --- | --- |
| `POST` | `/workspaces/{workspace_id}/bundles/{bundle_id}/tosses` | share capability 생성 |
| `DELETE` | `/workspaces/{workspace_id}/tosses/{toss_id}` | revoke |
| `GET` | `/tosses/{token}` | 인증 없는 공개 bundle 조회 |
| `POST` | `/workspaces/{workspace_id}/tosses/{token}/fork` | 공개 bundle로 독립된 private session/branch 생성 |
| `POST` | `/workspaces/{workspace_id}/documents/{document_id}/proposals` | proposal 생성 |
| `GET` | `/workspaces/{workspace_id}/proposals/{proposal_id}` | proposal과 approval 조회 |
| `PUT` | `/workspaces/{workspace_id}/proposals/{proposal_id}` | 새 proposal version |
| `POST` | `/workspaces/{workspace_id}/proposals/{proposal_id}/decisions` | approve 또는 reject |
| `POST` | `/workspaces/{workspace_id}/proposals/{proposal_id}/merge` | `document.publish` 권한으로 명시적 publication |

### 11.4 Agent

| Method | Path | 목적 |
| --- | --- | --- |
| `POST` | `/workspaces/{workspace_id}/branches/{branch_id}/agent` | 권한 확인 후 AG-UI run 실행 |

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
- state/version 충돌: `409`
- 입력 검증 실패: `422`
- provider 또는 agent 오류: AG-UI `RUN_ERROR`

외부 응답은 내부 예외, SQL, provider credential을 포함하지 않는다.

## 12. Agent 실행

### 12.1 수명

한 `POST /workspaces/{workspace_id}/branches/{branch_id}/agent` 요청은 하나의 asyncio task와
Pydantic AI run을 소유한다. 브라우저가
연결을 끊거나 Stop을 누르면 run 취소를 허용한다. 서버는 연결이 없는 run을 계속 실행하거나
나중에 복구하지 않는다.

Model, server instruction과 tool definition을 가진 Pydantic AI Agent는 application 시작 시 한 번
조립해 재사용한다. Agent 객체에는 현재 actor, branch, message history 같은 mutable request state를
저장하지 않는다. 각 run은 request-scoped `AgentDeps`로 actor, workspace, branch, canonical history,
application port와 Unit of Work factory를 받는다.

```text
authenticate -> authorize branch -> assemble context -> run Pydantic AI
             -> AG-UI text/tool events -> persist completed turns
             -> commit -> RUN_FINISHED
                       \-> failure -> RUN_ERROR
```

Agent endpoint는 `session.contracts.CompletedTurnsAppender`를 통해 완료된 user/assistant/tool Turn을
한 transaction에서 append하고 commit한 뒤에만
`RUN_FINISHED`를 보낸다. Frontend는 transcript 저장 command를 보내지 않고 session snapshot을 다시
조회한다. 저장이 실패하면 `RUN_ERROR`로 끝내며 해당 run의 message는 canonical history가 아니다.
이미 화면에 수신된 text는 partial 응답으로 남을 수 있다.

권한과 canonical context는 짧은 read transaction에서 조회한 뒤 transaction을 닫고 model을
호출한다. 이때 조회한 `base_branch_version`으로 run의 `expected_branch_version`을 시작한다. 각
Agent tool은 자기 application command transaction 안에서 Branch version guard와 제품 mutation을
함께 commit하고 증가된 version을 run에 반환한다. 마지막 transcript append도 가장 최근 version을
사용하는 별도의 짧은 transaction이다. 따라서 느린 provider stream 동안 connection이나 row lock을
점유하지 않는다.

경쟁 run이 Branch를 먼저 변경하면 현재 run은 다음 tool 또는 완료 append에서 즉시 충돌하고 더는
진행하지 않는다. Tool mutation과 version 증가는 한 transaction이므로 충돌한 tool의 제품 부작용은
남지 않는다. 반대로 이미 성공한 이전 tool transaction은 이후 provider 실패나 취소가 발생해도
유지되며 되돌아간 것처럼 처리하지 않는다.

### 12.2 Model

- `SOT_MODELS`는 Pydantic AI model reference의 순서 있는 목록이다.
- 하나면 그대로 사용하고 둘 이상이면 Pydantic AI `FallbackModel`을 만든다.
- provider key는 각 provider의 표준 환경 변수로 주입한다.
- 요청이 임의 model이나 provider credential을 지정할 수 없다.
- test는 `TestModel` 또는 `FunctionModel`을 사용한다.

### 12.3 Context와 tools

서버가 base instruction, 현재 main, 공개 가능한 branch context와 actor 권한을 조립한다. client가
보낸 system prompt나 server tool 구현을 신뢰하지 않는다.

Agent endpoint는 먼저 actor의 branch 접근 권한을 검사하고 PostgreSQL에서 완료된 Turn을 읽어
canonical history를 구성한다. AG-UI request의 과거 message 배열은 canonical history를 덮어쓸 수
없다. Request에서 현재 실행의 마지막 사용자 입력만 검증해 canonical history 뒤에 붙인다.
완성된 user/assistant/tool Turn의 server-side transaction이 commit되기 전까지 해당 입력은 canonical
history가 아니다.

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
- `RUN_FINISHED` 후 session snapshot을 다시 조회한다.
- proposal decision 후 proposal/document snapshot을 다시 조회한다.
- 여러 탭의 즉시 동기화가 제품 요구사항이 되면 PostgreSQL `LISTEN/NOTIFY` 또는 비내구성 SSE를
  별도 설계한다. 이를 위해 event-sourced write model은 도입하지 않는다.

## 14. 오류와 실패 의미

Domain과 Application은 FastAPI `HTTPException`과 HTTP status code를 import하지 않는다. 각 모듈은
`InvalidTransition`, `ProposalStale`처럼 의미 있는 error를 공통 application error base 위에
정의한다. FastAPI global error mapper가 error type/code를 status와 표준 envelope로 변환한다.

- 입력 오류는 domain command 실행 전에 거부한다.
- 예상된 domain 오류는 안정적인 code와 HTTP status로 변환한다.
- transaction 실패는 command 전체를 rollback한다.
- provider 실패와 연결 취소는 완료 turn을 만들지 않는다.
- transcript 저장 실패는 `RUN_ERROR`로 끝내고 수신한 text는 client에 partial 응답으로 남길 수 있다.
  Client가 transcript append를 재시도하거나 성공으로 간주하지 않는다.
- tool mutation 성공 후 stream이 끊기면 이미 완료된 mutation은 유지되며 client가 자동으로 같은
  command를 재실행하지 않는다.
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
- architecture test가 Domain의 FastAPI, Pydantic, psycopg, Pydantic AI import를 거부한다.

### 16.2 Application

- in-memory port와 fake Unit of Work로 권한과 transaction orchestration을 검증한다.
- 각 command의 success, forbidden, conflict, retry를 검증한다.
- architecture test가 application의 FastAPI/psycopg import와 금지된 cross-module import를 거부한다.

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
- 각 제품 command handler의 mutation이 하나의 transaction에 대응한다. 장시간 Agent orchestration은
  context 조회, tool command와 완료 transcript append의 짧은 transaction으로 나뉜다.
- 실제 OIDC identity와 workspace/session authorization이 적용된다.
- 공개 toss로 draft 원문이나 비선택 turn에 접근할 수 없다.
- concurrent approval에서도 main revision이 한 번만 생성된다.
- provider-neutral fallback model이 동작한다.
- browser disconnect 후 agent run을 복구하거나 replay하려 하지 않는다.
- unit, integration, contract, E2E 검증이 모두 통과한다.
