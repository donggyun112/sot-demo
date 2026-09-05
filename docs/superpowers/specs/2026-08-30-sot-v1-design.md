# SOT v1 제품 설계

- 상태: 사용자 검토 대기
- 작성일: 2026-08-30
- 기준 문서: [`README.md`](../../../README.md)
- 구현 기준: React 프론트엔드 + Python 백엔드 + 내부 `Semora` 에이전트 엔진

## 1. 요약

SOT는 AI가 사람 대신 주장을 만드는 환경에서 세션을 교환해 합의점을 찾는 웹 서비스다.

사용자는 LLM과 대화하며 입장을 만드는 draft session을 가진다. draft는 서버에 저장되지만 owner와 초대된 사용자에게만 보이며 main에는 나타나지 않는다. 사용자는 draft 전체를 공개하지 않고 `drop`, `edit`, `join`, `cite`로 공유할 맥락을 정리해 immutable bundle을 만든다. 이 bundle을 toss 링크로 전달하면 상대는 로그인 없이 읽을 수 있고, 로그인한 뒤 bundle에서 새 branch를 만들어 반례와 조건을 추가할 수 있다.

공유 세션의 목적은 진위를 판정하거나 승자를 고르는 것이 아니다. 참여자들이 이미 동의한 부분, 충돌하는 부분, 합의가 가능한 조건을 찾아 같은 proposal을 승인하는 것이다. 승인된 proposal만 main document의 새 revision이 된다.

정적 HTML 데모는 정보 구조와 카피를 검증하기 위한 참고자료다. 운영 제품은 React와 실제 API로 새로 구현하며 데모 코드를 이식하지 않는다.

## 2. 제품 문제

### 2.1 인간 미트 프록시

사람은 LLM이 만든 정교한 주장을 메신저에서 자기 주장처럼 전달할 수 있다. 그러나 직접 대화에서는 그 주장의 전제, 선택지, 반례를 설명하지 못할 수 있다. 사고 과정 없이 결론에만 애착이 생기면 이견은 논리적 조율이 아니라 맹목적인 고집으로 변한다.

SOT는 AI 사용을 막거나 탐지하지 않는다. 주장을 전달할 때 자신이 설득된 세션의 공개 가능한 상태도 함께 전달하게 한다.

### 2.2 정적인 출처 링크의 한계

세션 ID를 보여주는 것만으로는 충분하지 않다. 상대가 긴 원문을 읽기만 해야 한다면 합의는 여전히 사람의 수작업에 의존한다. SOT의 세션은 다음 행동을 지원해야 한다.

- 선택지와 인간의 선택을 함께 확인한다.
- 상대가 공개된 상태에서 branch를 만든다.
- 새 전제, 반례, 제약 조건을 추가한다.
- 기존 동의점과 새 충돌점을 비교한다.
- 참여자들이 같은 합의안을 승인한다.

### 2.3 투명성과 사적 사고의 경계

SOT는 모든 프롬프트를 공개하는 감시 시스템이 아니다. `local branch`는 물리적으로 사용자 기기에만 저장된다는 뜻이 아니라 Git에서 빌린 은유다. 제품에서는 서버에 저장되는 draft branch이며 main에 승격되지 않았다는 뜻이다.

투명성은 사고를 시작한 순간이 아니라 주장을 공유하는 순간에 요구된다. 공유 링크에는 draft 원본이 아니라 사용자가 공개하기로 선택한 immutable bundle만 나타난다.

## 3. 목표와 비목표

### 3.1 v1 목표

1. 로그인한 사용자가 Semora 에이전트와 draft session을 진행한다.
2. 사용자가 세션 턴을 정리해 공개 가능한 bundle을 만든다.
3. 링크 소지자는 로그인 없이 bundle을 읽는다.
4. 로그인한 상대는 bundle에서 branch를 만들고 대화를 이어간다.
5. 참여자는 합의안의 동의점, 충돌점, 합의 조건을 검토한다.
6. 필요한 참여자가 같은 proposal version을 승인하면 main revision이 생성된다.
7. main의 각 문장은 어떤 bundle과 선택 맥락에서 왔는지 역추적할 수 있다.
8. 에이전트 실행은 실패 후 재개되어도 메시지와 도구 효과를 중복 생성하지 않는다.

### 3.2 v1 비목표

- 사실 여부나 진실 점수 판정
- AI 생성 문장 탐지
- 공개 인터넷 토론 플랫폼
- Slack, Discord, 이메일 네이티브 앱
- 음성·영상 통화
- 익명 사용자의 fork와 합의 참여
- 조직별 복잡한 커스텀 승인 DSL
- 모바일 네이티브 앱
- 오프라인 우선 또는 기기 로컬 저장
- 여러 에이전트 런타임 선택
- 첨부 파일과 대용량 바이너리 저장

## 4. 확정된 설계 결정

| 주제 | v1 결정 |
| --- | --- |
| 제품 형태 | 공유 링크 중심 웹 서비스 |
| 프론트엔드 | Vite, React, TypeScript |
| 백엔드 | Python 3.12+, FastAPI 기반 Platform Server와 Agent Server |
| 에이전트 | 독립 Agent Server가 `Semora`를 사용하며 request와 자기 record만 소유 |
| 실행 형태 | Platform Server와 Agent Server는 AG-UI로 통신하는 별도 서비스/배포 |
| 저장소 | Platform DB와 Agent DB의 소유권·계정·migration 완전 분리 |
| 식별자 | 새 session/thread/run/message/event/interrupt ID는 가능한 모든 경계에서 UUIDv7 |
| Agent 인증 | Platform의 5분 이하 JWT access token 검증, `(iss, sub)`의 SHA-256 opaque owner 사용 |
| 국제화 | UTF-8, BCP 47 locale, RFC 3339 UTC, 원문 보존 + 화면 파생 번역 |
| 실시간 전송 | AG-UI `RunAgentInput` + `BaseEvent` SSE, cursor 재접속은 명시적 transport extension |
| 실행 수명 | LLM run은 브라우저와 독립적으로 완료·실패·명시적 취소까지 지속 |
| 재접속 | DB snapshot의 stream cursor 이후 event를 replay한 뒤 live stream으로 전환 |
| Agent 운영 기본값 | replica당 active run 32, run 15분, request 2 MiB, Redis 장애 시 DB polling |
| draft 의미 | 서버에 저장되지만 main에 미승격된 세션 |
| toss 읽기 | 링크 소지자는 로그인 없이 읽기 가능 |
| 참여 | 로그인한 사용자만 fork, 메시지, 승인 가능 |
| 공유 단위 | draft 원본이 아닌 immutable curated bundle |
| main 의미 | 승인된 현재 합의 문서 revision |
| 합의 기준 | proposal에 지정된 required approver 전원의 동일 version 승인 |
| 정적 HTML | 운영 코드가 아닌 UX 참고자료 |

## 5. 시스템 구조

```text
┌───────────────────────────────────────────────────────────────┐
│ React Web                                                     │
│ snapshot + streaming overlay                                 │
└──────────────┬──────────────────────────────▲─────────────────┘
               │ REST command/query             │ cursor SSE
┌──────────────▼──────────────────────────────┬─┴────────────────┐
│ Platform Server                                               │
│ FastAPI ─ Domain ─ branch↔thread binding │ AG-UI secure proxy │
└──────────────┬──────────────────────────────┴──────────────────┘
               │ AG-UI HTTP: RunAgentInput → BaseEvent SSE
┌──────────────▼─────────────────────────────────────────────────┐
│ Agent Server                                                   │
│ AG-UI API ─ async execution owner ─ Semora                     │
│ transcript/checkpoint/AG-UI event records                      │
└────────────────────────────────────────────────────────────────┘

Platform Server ── owns Platform DB (sot_*)
Agent Server    ── owns Agent DB (agent_* + semora_*)
```

브라우저는 Agent Server나 Semora를 직접 알지 않는다. React는 Platform API/SSE에만 연결하고, Platform Server의 Agent client가 AG-UI HTTP/SSE로 Agent Server를 호출한다. Platform은 Agent 코드, DB, 내부 테이블, Semora 타입을 import하거나 직접 읽지 않는다. Agent Server에는 `session`, `branch`, `bundle`, `toss`, `consensus`, main이나 플랫폼 권한 같은 개념이 존재하지 않는다. Agent는 AG-UI `RunAgentInput`의 `threadId`, `runId`, messages/state/tools/context를 요청으로 받고, 자기 request와 transcript/checkpoint 및 AG-UI `BaseEvent` record만 영속화한다.

두 서버는 monorepo 안에 있어도 각자 `pyproject.toml`, lock/dependency graph, container, migration, DB credential, health check와 배포 lifecycle을 가진다. shared Python composition package나 shared transaction은 두지 않는다. Platform은 자기 DB의 binding에서 branch를 opaque AG-UI `threadId`에 연결하고 인증·권한 확인 후 network로 `RunAgentInput`과 `BaseEvent` stream을 proxy한다. Agent event를 `sot_stream_event`로 복제하지 않는다. Agent message/state 복원은 AG-UI `MESSAGES_SNAPSHOT`/`STATE_SNAPSHOT` 또는 문서화된 Agent read extension만 사용한다.

AG-UI run과 그 HTTP SSE connection은 실행 수명이 다르다. Agent Server process가 Semora async task를 소유하고 SSE generator는 subscriber일 뿐이다. SSE disconnect는 subscriber 제거이며 run 취소는 사용자의 명시적인 별도 abort command다. 최초 실행과 재접속 모두 같은 `POST /ag-ui`와 동일한 `RunAgentInput`을 사용한다. 재접속용 GET attach endpoint나 private body field는 두지 않고 SSE `id`/`Last-Event-ID`만 transport extension으로 사용한다. Platform의 `ResumableAguiClient`가 현재 reference `HttpAgent`에 없는 cursor 보존과 POST 재접속을 보완한다.

`agent_event`는 Agent 자신의 durable AG-UI record이며 replay source다. Redis Stream은 Agent event의 bounded hot/live cache일 뿐이고 canonical state, queue 또는 실행 lock이 아니다. `sot_stream_event`는 Platform product projection에만 사용한다. 어느 쪽도 외부 배송용 outbox가 아니며 Agent subscriber는 Redis miss와 publish 실패를 canonical Agent DB replay로 복구한다.

Redis는 Agent Server 내부의 hot streaming cache로만 사용한다. Agent execution event writer가 Agent DB에 `agent_event(sequence=N)`를 commit한 뒤 Redis Stream에 복제한다. SSE reader는 DB replay와 Redis live buffer를 sequence로 병합하고 gap·TTL 만료·publish 실패·Redis 장애가 있으면 Agent DB로 fallback한다. subscriber마다 전체 stream이 필요하므로 work-distribution consumer group은 사용하지 않는다. Stream은 `agent:v1:run:{<runId>}:events`, `MAXLEN ~ 4096`, TTL 24시간으로 고정하며 삭제 후 DB에서 재구축한다. Platform Server는 Agent Redis에 접근하지 않는다.

### 5.1 Internationalization boundary

모든 DB와 API 문자열은 Unicode/UTF-8이다. locale은 BCP 47 tag(`ko-KR`, `en-US`, 알 수 없으면 `und`), timestamp는 PostgreSQL `timestamptz`와 RFC 3339 UTC `Z` 표현을 사용한다. AG-UI wire JSON은 공식 camelCase field를 그대로 유지하고 Python 내부만 snake_case alias를 사용한다.

Agent `BaseEvent` payload와 transcript 원문은 수신 형태를 보존한다. streaming chunk마다 Unicode normalization을 수행하지 않는다. message가 완성된 뒤 Platform/검색 projection에서 NFC `content_nfc`를 만들고, 원문 `content_raw`와 source locale을 함께 보존한다. 번역은 `message_translation(source_message_id, target_locale, translated_content_nfc, translator, version, created_at)` 같은 파생 record이며 원문을 덮어쓰지 않는다.

React UI chrome은 locale catalog로 번역하고 날짜·숫자·통화는 브라우저 `Intl`로 표시한다. message content는 원문/번역 토글을 제공하고 각 block에 BCP 47 `lang`과 `dir="auto"`를 설정한다. API/Agent error는 안정적인 machine code를 제공하고 사용자용 문장은 UI에서 locale별로 변환한다.

## 6. 저장소 구조

```text
sot-demo/
├── README.md
├── docs/
│   └── superpowers/specs/
├── web/
│   ├── src/
│   │   ├── app/
│   │   ├── routes/
│   │   ├── features/
│   │   ├── components/
│   │   ├── api/
│   │   └── styles/
│   ├── package.json
│   └── vite.config.ts
├── platform-server/
│   ├── src/sot/
│   ├── migrations/
│   ├── tests/
│   ├── pyproject.toml
│   └── Dockerfile
├── agent-server/
│   ├── src/agent_core/
│   │   ├── api/             # AG-UI HTTP/SSE server
│   │   ├── runtime/         # Semora adapter
│   │   └── store/           # request/transcript/checkpoint/event record
│   ├── migrations/
│   ├── tests/
│   ├── pyproject.toml
│   └── Dockerfile
├── compose.yaml
├── index.html              # prototype reference
└── msbd-real.html          # prototype reference
```

`Semora`는 Agent Server만의 잠긴 Python dependency다. Platform Server는 Semora/LangChain/Agent 내부 package를 import하지 않는다. Agent Server는 `sot`을 import하지 않는다. 두 서버가 함께 아는 것은 AG-UI wire schema뿐이며 별도 composition package는 없다.

## 7. 용어와 식별자

| 용어 | 정의 |
| --- | --- |
| session | 한 주제에 대한 제품상 대화 묶음 |
| branch | session 안에서 독립적으로 이어지는 대화선 |
| draft | main에 반영되지 않은 branch 상태 |
| run | 한 입력을 처리하는 Semora 실행 시도 |
| turn | 인간, LLM 또는 도구가 남긴 표시 가능한 메시지 |
| curation op | draft를 공개 가능한 형태로 투영하는 drop/edit/join/cite 연산 |
| bundle | curation 결과를 고정한 공유용 immutable snapshot |
| toss | bundle을 capability link로 전달하는 행위 |
| shared branch | toss된 bundle에서 로그인한 사용자가 시작한 branch |
| proposal | main 문서를 어떻게 바꿀지 나타내는 versioned 합의안 |
| approval | 한 사용자가 특정 proposal version에 내린 결정 |
| main | document의 현재 승인 revision |

모든 공개 식별자는 UUIDv7을 사용한다. share token은 별도 256-bit random value이며 데이터베이스에는 SHA-256 hash만 저장한다.

## 8. 도메인 모델

### 8.1 관계

```text
Workspace 1 ── * Document 1 ── * DocumentRevision ── * RevisionCitation
    │               │                                      │
    │               └── * Proposal ── * Approval           │
    │                         │                             │
    │                         └── * ProposalBundle ─────────┘
    │                                      │
    └── * Session 1 ── * Branch ── * Bundle ── * ShareLink
              │          │
              │          └── 1 Semora conversation_id
              └── * SessionMember
```

### 8.2 불변 조건

1. Semora transcript entry는 append-only다.
2. curation은 raw transcript를 수정하지 않고 projection만 만든다.
3. bundle은 생성 후 수정되지 않는다. 새 정리는 새 bundle version이다.
4. share link는 정확히 한 bundle version을 가리킨다.
5. toss 링크로 draft 원본이나 선택되지 않은 turn을 조회할 수 없다.
6. branch는 정확히 한 `semora_conversation_id`를 가진다.
7. main은 session 상태가 아니다. proposal merge가 document revision을 만든다.
8. approval은 proposal version에 귀속된다. proposal이 바뀌면 이전 approval은 효력을 잃는다.
9. required approver가 모두 승인하지 않으면 shared proposal은 merge되지 않는다.
10. merge는 base revision이 현재 main과 같을 때만 성공한다.
11. browser request와 SSE connection은 Semora run의 소유자가 아니다.
12. 각 stream scope의 event는 commit 순서와 같은 증가 `seq`를 가지며 같은 event를 여러 번 적용해도 결과가 같아야 한다.
13. snapshot은 자신이 반영한 마지막 `stream_cursor`를 함께 반환한다.

## 9. 상태 모델

### 9.1 Session

```text
draft ──toss──▶ shared ──close──▶ closed
  │                │
  └────close───────┘
```

- `draft`: owner만 접근하거나 명시적으로 초대된 member가 접근한다.
- `shared`: 하나 이상의 활성 share link 또는 외부 participant가 있다.
- `closed`: 새 메시지와 fork를 받지 않지만 기존 bundle과 proposal은 읽을 수 있다.

main 반영 여부는 session 상태에 포함하지 않는다.

### 9.2 Bundle

```text
published ──revoke──▶ revoked
```

- publish 전 결과는 branch와 curation ops에서 계산하는 preview이며 아직 bundle이 아니다.
- publish하면 immutable `published` bundle이 생성된다.
- `revoked` bundle의 기존 share link는 410 Gone을 반환한다.
- revoked bundle을 이미 fork한 shared branch는 보존된다.
- main revision이 인용한 bundle data와 workspace 내부 backlink는 revoke 후에도 보존된다.

### 9.3 Proposal

```text
open ──all approve──▶ approved ──merge──▶ merged
 │                         │
 ├──reject──────────────▶ rejected
 └──main advanced───────▶ stale
```

- proposal 내용이 바뀌면 version이 증가하고 approvals가 초기화된다.
- required approver 한 명이 reject하면 `rejected`가 된다.
- current main revision이 base revision과 달라지면 `stale`이 된다.
- stale proposal은 자동 merge하지 않고 새 base에서 다시 생성한다.

### 9.4 Agent run

```text
RunAgentInput accepted ──▶ Semora async execution ──▶ RUN_FINISHED
                                │
                                ├─ interrupt ──▶ RUN_FINISHED(outcome=interrupt)
                                ├─ failure ────▶ RUN_ERROR
                                └─ explicit abort ──▶ RUN_ERROR(code=aborted)

SSE disconnect ──▶ subscriber detached; execution unchanged
```

- run은 SSE connection이 아니라 Agent Server가 소유한다.
- Agent Server에는 별도 queued/running/claimed/attempt 상태머신이 없다.
- 새로고침, 탭 종료, SSE disconnect는 run 상태를 바꾸지 않는다.
- 사용자의 명시적 중단 command만 durable abort intent를 기록하고 Semora `aborted` 경로를 활성화한다.
- process crash 복구는 재접속이 같은 요청을 다시 보냈을 때만 시작한다. 무접속 자동 recovery scanner는 두지 않는다.

## 10. 핵심 사용자 흐름

### 10.1 Draft session 시작

1. 로그인 사용자가 workspace와 선택적 document context를 지정한다.
2. backend가 Session과 첫 Branch를 만든다.
3. Platform이 opaque AG-UI `threadId`와 새 `runId`를 할당한다.
4. Platform의 async Agent client가 공식 `RunAgentInput`을 Agent Server에 POST한다.
5. Agent Server가 request를 commit하고 브라우저 연결과 독립적인 Semora task를 시작한다.
6. Agent Server는 Semora event를 AG-UI `BaseEvent`로 변환해 먼저 `agent_event`에 저장하고 Redis Stream에 mirror한다.
7. Platform Agent client는 AG-UI stream을 소비해 Platform product projection을 갱신한다.
8. React는 Platform snapshot cursor 이후 product event를 replay한 뒤 live event를 적용한다.
9. completed message와 tool result는 Semora transcript에 확정되고 대응하는 AG-UI event가 Agent journal에 기록된다.
10. React는 완료 projection을 받은 뒤 streaming overlay를 canonical Platform snapshot으로 교체한다.

### 10.2 세션 정리

1. 사용자 또는 에이전트가 curation op를 제안한다.
2. domain service가 actor 권한과 branch version을 검사한다.
3. `drop`은 공개 projection에서 turn을 제외한다.
4. `edit`은 원문을 바꾸지 않고 공개 대체문과 편집 표시를 저장한다.
5. `join`은 여러 turn을 하나의 공개 item으로 묶고 source IDs를 모두 보존한다.
6. `cite`는 공개 item과 문서 claim의 관계를 선언한다.
7. preview에서 사용자가 확인한 뒤 bundle을 publish한다.

### 10.3 Toss와 익명 읽기

1. owner가 published bundle에 share link를 만든다.
2. backend는 raw token을 한 번 반환하고 hash만 저장한다.
3. 링크 소지자는 로그인 없이 bundle items, 작성 역할, 편집 여부를 읽는다.
4. draft transcript, 제외된 turn, workspace 내부 정보는 응답에 포함하지 않는다.
5. owner는 링크를 revoke하거나 새 링크로 rotate할 수 있다.

### 10.4 Fork와 공동 조율

1. 상대가 로그인하고 share link의 Fork를 누른다.
2. backend가 bundle items만 사용해 sanitized seed history를 만든다.
3. 같은 Session 안에 `source_bundle_id`를 가진 새 Branch와 새 Semora conversation을 생성한다.
4. 원 draft의 숨겨진 history는 새 conversation context에 들어가지 않는다.
5. 로그인 사용자를 workspace member로 만들지 않고 해당 Session의 guest editor로 추가한다.
6. 상대는 새 조건과 반례를 입력하고 에이전트와 조율한다.
7. 참여자는 branch comparison에서 동의점, 충돌점, 합의 조건을 본다.

### 10.5 합의와 main 반영

1. 참여자 또는 에이전트가 하나 이상의 bundle을 인용해 document patch와 요약을 만든다.
2. required approvers는 proposal creator, session owner, 현재 session의 owner/editor 전원으로 고정한다. creator는 approver를 추가할 수 있지만 자동 포함된 사용자를 제거할 수 없다.
3. proposal 생성 시 current main revision을 base로 고정한다.
4. 각 approver는 동일한 proposal version을 승인하거나 거절한다.
5. 마지막 승인 후 backend가 merge transaction을 시도한다.
6. base가 여전히 current이면 새 immutable DocumentRevision을 만든다.
7. claim anchor와 bundle item을 잇는 revision citation을 생성한다.
8. main pointer를 새 revision으로 이동하고 `main.updated` event를 발행한다.
9. base가 달라졌으면 proposal을 stale로 전환한다.

## 11. Curation 설계

### 11.1 연산

| 연산 | 입력 | 결과 |
| --- | --- | --- |
| `session_drop` | source event IDs, reason | 공개 projection에서 제외 |
| `session_edit` | source event ID, replacement, reason | 원문 링크를 가진 편집 item |
| `session_join` | source event IDs, replacement, reason | 여러 턴을 묶은 item |
| `session_cite` | item IDs, claim anchor, memo | bundle claim mapping |
| `sot_update` | document, base revision, patch, citations | 승인 대상 proposal |

### 11.2 원본과 공개본

`session_edit`와 `session_join`은 transcript를 변경하지 않는다. 공개 bundle item은 다음 정보를 가진다.

```json
{
  "kind": "edited_turn",
  "source_event_ids": ["evt_01"],
  "speaker": "human",
  "content": "공개하기로 정리한 문장",
  "edited": true,
  "edit_reason": "사적 정보 제거"
}
```

익명 독자는 source event 본문을 조회할 수 없다. 권한이 있는 draft member만 원문과 공개본의 차이를 볼 수 있다. 공개 화면은 편집 사실과 편집 이유를 숨기지 않는다.

### 11.3 선택 맥락

사람이 `1`, `B`, `ㅇㅇ`처럼 짧게 답한 경우 해당 답만 독립 citation으로 만들 수 없다. bundle은 바로 앞의 LLM 선택지 turn과 인간 선택 turn을 한 item group으로 묶는다. 선택지를 찾지 못하면 UI와 agent tool 모두 `missing_choice_context` 오류를 반환한다.

## 12. Semora 통합

### 12.1 책임 경계

Semora가 소유하는 것:

- 모델 호출과 message 형식
- tool execution과 call-id idempotency
- control plane과 suspension/resume
- run lease와 crash recovery
- append-only transcript
- event checkpoint 기반 fork

SOT가 소유하는 것:

- 사용자와 workspace 권한
- session과 branch 메타데이터
- curation op와 bundle
- share link
- proposal, approval, main revision
- 제품용 event projection

Platform/SOT code는 Semora package나 `semora_*` 테이블을 전혀 사용하지 않는다. `Transcript`, `ExecutionStore`, `AgentRuntime`과 Semora store API는 Agent Server 내부에서만 사용한다. Platform과 Agent의 유일한 실행 경계는 AG-UI HTTP/SSE다.

### 12.2 런타임 매핑

- AG-UI `threadId`는 Semora `conversation_id`에 대응한다.
- 새 일반 AG-UI `runId`는 Agent invocation ID이자 새 Semora `run_id`다.
- resume request의 새 AG-UI `runId`는 `interruptId`를 통해 원 Semora run에 Answer를 전달한다.
- 같은 `runId`와 같은 payload는 attach/replay하고, 다른 payload는 idempotency conflict다.
- Agent Server process가 Semora task를 직접 소유한다. 별도 worker나 job claim은 없다.
- 여러 replica의 단일 실행 소유권은 Semora PostgreSQL lease/fencing만 사용한다.
- process crash 후 같은 요청이 재접속하면 Agent Server가 내부 Recover를 시도한다.

### 12.3 Prompt assembly과 provider

Agent Server는 AG-UI input mapping과 Semora 실행 사이에 독립 Prompt Assembly Layer를 둔다. HTTP route, tool adapter와 event translator가 제각각 system prompt를 조립하지 않는다.

```text
RunAgentInput -> command mapping -> Prompt Assembly Layer -> Semora -> OpenRouter
```

model provider는 OpenRouter로 단일화한다. API key와 provider credential은 Agent Server
deployment secret이고 `RunAgentInput`으로 전달하지 않는다. 모델은 배포별 하나이며
요청으로 변경할 수 없다. Prompt Assembly는 서버 base prompt, 서버 정책, 선택된 서버
tool 지침, 비권한 `context`/`state` 데이터 순으로 한 번 조립하고, history와 마지막 user
Prompt는 별도 Semora 입력으로 유지한다. 상세 실행 계약은
[`2026-09-03-agent-loop-design.md`](2026-09-03-agent-loop-design.md)가 정본이다.

### 12.4 Agent tools

실제 tool registry, 구현, credentials, 권한, sandbox와 실행은 Agent Server/Semora가 소유한다. `RunAgentInput.tools`는 이 Agent Server가 이미 가진 도구를 요청별로 선택·설정하는 descriptor이며 실행 코드나 credential을 주입하지 않는다.

Agent Server는 Platform의 `session_drop`, `sot_update` 같은 domain operation을 내장하지 않는다. 그런 제품 command는 Platform이 소유한다. V1 Agent tool은 검색·조회 등 non-mutating/read-oriented 범위로 제한하고, 사용자 결정이 필요하면 AG-UI interrupt/resume를 사용한다.

### 12.5 Sanitized fork

draft branch를 그대로 fork하면 drop된 사적 내용이 모델 context에 남을 수 있다. 따라서 toss 후 fork는 원 draft의 `fork_event`를 직접 호출하지 않는다.

1. Platform이 공개 bundle item만 official AG-UI messages로 materialize한다.
2. 새 opaque `threadId`와 `runId`로 `RunAgentInput`을 만든다.
3. Platform Agent client가 독립 Agent Server에 요청한다.
4. Agent Server가 `threadId`를 Semora `conversation_id`로 사용하고 sanitized history를 기록한다.

Platform은 `semora_fork`나 Agent transcript API를 직접 호출하지 않는다. 같은 접근권한 안의 draft edit/fork도 새 `RunAgentInput.messages` snapshot으로 표현하고 Agent Server의 common-prefix rewind/append 경로를 사용한다.

## 13. Backend 모듈

### 13.1 API

FastAPI route는 인증, 입력 파싱, application command 호출, 응답 변환만 담당한다. route 안에서 Semora를 직접 실행하거나 SQL transaction을 조립하지 않는다.

### 13.2 Application

유스케이스 단위 service를 둔다.

```text
CreateSession
SubmitMessage
ApplyCuration
PublishBundle
CreateShareLink
ForkSharedBundle
CreateProposal
DecideProposal
MergeProposal
```

각 command는 actor, aggregate ID, expected version, idempotency key를 받는다.

### 13.3 Domain

Domain layer는 FastAPI, SQL, LangChain, Semora 타입을 import하지 않는다. Session, Bundle, Proposal, DocumentRevision 상태 전이와 정책만 가진다.

### 13.4 Agent

Agent package의 책임은 AG-UI request와 자기 record다. prompt 실행, server-owned tool registration, Semora transcript/execution store, durable AG-UI event를 소유한다. Platform ID나 정책을 해석하지 않으며 platform package를 import하지 않는다. 하나의 Agent Server는 하나의 논리적 agent이고 runtime multi-agent registry를 제공하지 않는다.

Platform 쪽 secure proxy는 branch 권한을 확인하고 branch를 AG-UI `threadId`에 binding한다. 제품 event와 agent event를 한 schema로 합치지 않으며, Agent의 public record stream을 AG-UI transport로 전달한다.

### 13.5 Store

Repository는 domain aggregate를 저장한다. main, proposal, bundle처럼 사용자에게 관찰되는 aggregate 변경과 대응하는 stream event는 같은 PostgreSQL transaction에 기록한다. `sot_stream_event`는 publish 대기열이 아니라 SSE가 직접 읽는 journal이므로 `published_at`과 별도 publisher가 없다.

### 13.6 Async execution and subscription

Agent Server process가 요청 처리 중 생성한 Semora async task를 실행 registry에 보관한다. SSE generator는 그 task의 소유자가 아니라 DB/Redis event subscriber다. connection `finally`에서 task를 취소하지 않는다.

동일 run을 다른 replica가 동시에 복구하려 하면 Semora lease가 하나만 허용한다. `Contended`는 실패 event가 아니라 다른 replica가 실행 중이라는 조정 결과이므로 DB replay와 Redis live subscription으로 전환한다. Agent Server는 Semora와 중복되는 request worker, claim lease, attempt fencing을 구현하지 않는다.

## 14. PostgreSQL 스키마

### 14.1 제품 테이블

| 테이블 | 핵심 컬럼 |
| --- | --- |
| `sot_user` | `id`, `oidc_subject`, `display_name`, `created_at` |
| `sot_workspace` | `id`, `name`, `created_by`, `created_at` |
| `sot_workspace_member` | `workspace_id`, `user_id`, `role` |
| `sot_document` | `id`, `workspace_id`, `slug`, `title`, `current_revision_id` |
| `sot_document_revision` | `id`, `document_id`, `number`, `base_revision_id`, `body_md`, `proposal_id`, `created_by` |
| `sot_session` | `id`, `workspace_id`, `document_id`, `owner_id`, `state`, `version` |
| `sot_session_member` | `session_id`, `user_id`, `role` |
| `sot_branch` | `id`, `session_id`, `parent_branch_id`, `source_bundle_id`, `conversation_id`, `state`, `version`, `created_by` |
| `sot_curation_op` | `id`, `branch_id`, `sequence`, `kind`, `source_event_ids`, `payload`, `created_by` |
| `sot_bundle` | `id`, `branch_id`, `version`, `state`, `title`, `summary`, `content_hash`, `created_by` |
| `sot_bundle_item` | `bundle_id`, `position`, `kind`, `source_event_ids`, `speaker`, `content`, `metadata` |
| `sot_share_link` | `id`, `bundle_id`, `token_hash`, `expires_at`, `revoked_at`, `created_by` |
| `sot_proposal` | `id`, `document_id`, `base_revision_id`, `version`, `body_md`, `status`, `created_by` |
| `sot_proposal_bundle` | `proposal_id`, `bundle_id` |
| `sot_proposal_approver` | `proposal_id`, `user_id` |
| `sot_approval` | `proposal_id`, `proposal_version`, `user_id`, `decision`, `created_at` |
| `sot_revision_citation` | `revision_id`, `claim_anchor`, `bundle_id`, `bundle_item_position` |
| `sot_agent_binding` | `branch_id`, `agent_thread_id`, `created_at` |
| `sot_stream` | `scope_type`, `scope_id`, `next_seq`, `floor_seq`, `created_at` |
| `sot_stream_event` | `scope_type`, `scope_id`, `seq`, `id`, `run_id`, `message_id`, `producer_event_id`, `event_type`, `payload`, `occurred_at`, `expires_at` |

### 14.2 제약 조건

- `sot_user.oidc_subject`는 unique다.
- `(workspace_id, slug)`는 document 내 unique다.
- `(document_id, number)`는 revision unique다.
- `sot_branch.conversation_id`는 unique다.
- sanitized toss fork는 `source_bundle_id`를 가지며 raw draft branch를 parent로 삼지 않는다.
- `(branch_id, sequence)`는 curation op 순서를 보장한다.
- `(branch_id, version)`은 bundle version unique다.
- `sot_bundle.content_hash`는 canonical payload의 SHA-256이다.
- `(proposal_id, user_id, proposal_version)`은 approval unique다.
- `(revision_id, claim_anchor, bundle_id, bundle_item_position)`은 citation unique다.
- `sot_agent_binding.branch_id`와 `agent_thread_id`는 각각 unique다. Platform은 thread ID를 opaque value로만 취급한다.
- `(scope_type, scope_id)`는 stream identity이며 `branch`, `proposal`, `document` scope를 지원한다.
- `(scope_type, scope_id, seq)`는 stream event primary key다.
- producer는 `sot_stream` row를 잠그고 `next_seq`를 할당한 뒤 같은 transaction에서 event를 insert한다. 따라서 같은 scope의 seq 순서와 commit 순서가 일치한다.
- `(scope_type, scope_id, producer_event_id)`는 producer 재시도 중 중복 event 생성을 막는다.

### 14.3 Agent-owned tables

| 테이블 | 핵심 컬럼 |
| --- | --- |
| `agent_request` | `run_id`, `thread_id`, `original_input`, `payload_hash`, `created_at`, `abort_requested_at` |
| `agent_event` | `run_id`, per-run `sequence`, `event_type`, official AG-UI `event`, `created_at` |
| `agent_interrupt` | public UUIDv7 `interrupt_id`, opaque Semora pending/tool ID, original/resolution run |

Agent event payload는 공식 camelCase AG-UI `BaseEvent` serialization이다. `agent_event.sequence`는 payload 밖의 transport cursor이며 SSE `id:`로 전달한다. 진행 중 text content, tool call, state, Semora RAW event와 terminal lifecycle의 canonical replay record는 Agent가 소유한다.

정확한 PostgreSQL 16 DDL과 `agent.append_event()` sequence transaction은 canonical Agent
설계에 확정되어 있다. `run_id`, `thread_id`, Agent event와 public interrupt ID는 UUIDv7이고,
Semora/provider가 생성한 pending/tool/response ID만 opaque text로 보존한다. strict AG-UI
validation 후 RFC 8785 JCS + SHA-256으로 payload hash를 만들며, 같은 owner의 같은 run ID와
다른 hash는 `409 run_id_conflict`다. event/full input은 terminal 후 90일, 최소 idempotency
tombstone은 365일 보존하고 incomplete run은 자동 age-delete하지 않는다.

Agent request table에는 `queued`, `running`, `claimed`, `attempt`, `lease_owner`, `lease_until`을 두지 않는다. 실행 lease와 fencing은 Semora store가 이미 소유한다.

Semora가 제공하는 `semora_transcript`, `semora_run`, `semora_run_model`, `semora_step`, `semora_input`, `semora_run_lease`는 동일 PostgreSQL 인스턴스에 설치한다. SOT migration은 Semora 테이블 정의를 복제하지 않고 패키지가 제공하는 schema를 적용한다.

## 15. HTTP API

모든 Platform product API는 `/api/v1` 아래에 둔다. 독립 Agent Server는 `POST /ag-ui`를 제공한다. Platform mutation은 `Idempotency-Key` header를 요구한다. AG-UI streaming 시작 전 handshake 오류는 `application/problem+json`, 시작 후 Agent 오류는 AG-UI `RUN_ERROR` event로 반환한다.

### 15.1 Session과 branch

| Method | Path | Auth | 목적 |
| --- | --- | --- | --- |
| `POST` | `/sessions` | 로그인 | draft session 생성 |
| `GET` | `/sessions/{session_id}` | member | session snapshot 조회 |
| `POST` | `/sessions/{session_id}/branches` | member | 권한 내 draft fork |
| `GET` | `/branches/{branch_id}` | member | Platform branch/product projection 조회 |
| `POST` | `/branches/{branch_id}/agent` | member | Platform이 Agent invocation을 시작하고 product stream과 연결 |
| `GET` | `/branches/{branch_id}/agent/runs/{run_id}/events` | member | Platform projection replay/live stream; Agent DB 직접 노출 아님 |
| `POST` | `/branches/{branch_id}/agent/runs/{run_id}/cancel` | editor | Platform이 Agent Server에 명시적 abort 전달 |
| `POST` | `/sessions/{session_id}/close` | owner | session 종료 |

Agent Server 자체 public surface는 `POST /ag-ui`와 `POST /runs/{runId}/abort`다. Platform만 이를 호출한다. Agent stream 재접속은 GET attach가 아니라 동일한 `RunAgentInput`을 `POST /ag-ui`에 다시 보내고 `Last-Event-ID`를 전달한다.

Platform command 응답이나 React SSE가 끊겨도 이미 시작한 Agent run을 취소하지 않는다. 같은 Platform idempotency key는 동일한 product command 결과와 Agent `runId`를 반환해야 한다.

Branch snapshot은 projection 외에 `active_runs`와 snapshot이 반영한 `stream_cursor`를 반환한다. SSE endpoint는 표준 `Last-Event-ID` header 또는 동등한 `after` cursor를 받으며 둘이 모두 있으면 header를 우선한다.

### 15.2 Curation과 toss

| Method | Path | Auth | 목적 |
| --- | --- | --- | --- |
| `POST` | `/branches/{branch_id}/curation-ops` | editor | curation op 추가 |
| `GET` | `/branches/{branch_id}/bundle-preview` | editor | 현재 projection 미리보기 |
| `POST` | `/branches/{branch_id}/bundles` | editor | immutable bundle publish |
| `POST` | `/bundles/{bundle_id}/share-links` | owner | toss link 생성 |
| `DELETE` | `/share-links/{share_link_id}` | owner | link revoke |
| `GET` | `/shares/{token}` | 없음 | 공개 bundle 조회 |
| `POST` | `/shares/{token}/fork` | 로그인 | sanitized shared branch 생성 |

### 15.3 Document와 합의

| Method | Path | Auth | 목적 |
| --- | --- | --- | --- |
| `GET` | `/documents/{document_id}` | viewer | current main과 revision 정보 |
| `GET` | `/documents/{document_id}/revisions/{number}` | viewer | 과거 main 조회 |
| `POST` | `/documents/{document_id}/proposals` | member | 합의안 생성 |
| `GET` | `/documents/{document_id}/events` | viewer | document cursor 이후 SSE |
| `GET` | `/proposals/{proposal_id}` | participant | proposal과 approvals 조회 |
| `GET` | `/proposals/{proposal_id}/events` | participant | proposal cursor 이후 SSE |
| `PUT` | `/proposals/{proposal_id}` | creator | 새 version 작성 |
| `POST` | `/proposals/{proposal_id}/decisions` | approver | approve 또는 reject |
| `POST` | `/proposals/{proposal_id}/merge` | 시스템/creator | 승인 완료 후 merge |

### 15.4 오류 코드

| code | 의미 |
| --- | --- |
| `version_conflict` | expected aggregate version 불일치 |
| `run_in_progress` | publish·fork처럼 안정된 branch head가 필요한 동안 active run 존재 |
| `missing_choice_context` | 인간 선택 앞의 선택지 turn이 없음 |
| `bundle_not_published` | share 가능한 상태가 아님 |
| `share_revoked` | toss link 폐기 |
| `approval_required` | required approver 미완료 |
| `proposal_rejected` | approver가 거절 |
| `proposal_stale` | main base가 변경됨 |
| `hidden_source` | 공개 bundle에서 draft source 접근 시도 |

## 16. 실시간 이벤트와 재접속 동기화

### 16.1 두 개의 독립 스트림

```text
React <-> Platform Server       Platform snapshot/product stream
Platform <-> Agent Server      AG-UI RunAgentInput/BaseEvent stream
```

React 연결 종료는 Platform-to-Agent 연결이나 Semora task를 취소하지 않는다. Platform process 또는 Agent 연결이 끊기면 Platform의 `ResumableAguiClient`가 동일한 `RunAgentInput`과 `runId`를 다시 POST한다. 사용자의 중단 버튼만 Platform abort route를 거쳐 Agent Server의 명시적 abort endpoint를 호출한다.

### 16.2 Agent event 형식

Agent SSE의 `data:`는 official AG-UI `BaseEvent` JSON 그대로다. Agent의 per-run sequence는 JSON payload에 private field로 추가하지 않고 SSE `id:`에 둔다.

```text
id: 142
data: {"type":"TEXT_MESSAGE_CONTENT","messageId":"...","delta":"..."}
```

awaited planner/model event와 host control event는 공식 thinking, text, tool, interrupt와
lifecycle event로 변환한다. Semora runtime `EventEnvelope`의 `event_sink`는 best-effort
관측 채널이므로 logs/metrics에만 사용하고 기본 AG-UI stream에 `RAW`로 보내지 않는다.

### 16.3 Agent DB와 Redis live cache

Agent event는 PostgreSQL `agent_event`에 먼저 commit한 뒤 Redis Stream에 XADD한다. PostgreSQL이 canonical이고 Redis는 bounded hot replay/live cache다. Redis는 queue, lease, lock 또는 canonical state로 사용하지 않는다.

Subscriber는 Redis live read를 먼저 시작해 buffer하고, DB에서 마지막 sequence 이후를 replay한 다음 sequence 순으로 병합·중복 제거한다. Redis sequence gap은 DB로 채우고 heartbeat timeout마다 DB high-water mark를 다시 확인한다. 따라서 DB commit 후 Redis publish 전에 process가 죽거나 terminal publish만 유실되어도 canonical event를 회수한다.

Event Outbox와 outbox publisher는 두지 않는다. Redis delivery가 correctness source가 아니고 subscriber가 DB와 직접 reconcile하기 때문이다.

Redis Stream key는 `agent:v1:run:{<runId>}:events`, entry ID는 Agent sequence인 `N-0`이다.
`XADD MAXLEN ~ 4096`과 24시간 TTL을 사용하고 256 KiB보다 큰 event는 DB에만 둔다.
subscriber는 `XREAD COUNT 256 BLOCK 1000`, 2초 DB high-water reconciliation과 15초 SSE
heartbeat를 사용한다. Redis 장애 시 1초 DB polling으로 즉시 fallback하며 Redis는 readiness
실패 조건이 아니다. `agent:v1:control:abort` Pub/Sub은 cross-replica 중단 latency를 줄이는
hint일 뿐이고 durable abort fact는 PostgreSQL이다.

### 16.4 Agent stream 재접속

```text
last SSE id = N
  -> POST /ag-ui with the exact same RunAgentInput
  -> Last-Event-ID: N
  -> DB replay after N
  -> merge buffered Redis live events
```

현재 official `HttpAgent`는 SSE ID 보존과 POST 재접속을 구현하지 않으므로 Platform의 thin transport client가 이 기능만 보완한다. `RunAgentInput.resume[]`는 human-in-the-loop resume이고 transport reconnect에 사용하지 않는다.

Platform snapshot과 React product stream의 구체적인 projection/cursor schema는 Agent stream과 별도이며 아직 확정하지 않았다.

## 17. React 프론트엔드

### 17.1 기술 선택

- Vite
- React + TypeScript strict mode
- React Router
- TanStack Query
- Vitest + React Testing Library
- Playwright
- CSS variables + CSS Modules

서버 상태는 TanStack Query가 소유한다. auth identity만 React context를 사용한다. 선택된 block, turn, panel은 URL search parameter에 저장해 링크와 새로고침을 보존한다. v1에는 별도 전역 상태 라이브러리를 추가하지 않는다.

실시간 화면은 TanStack Query의 canonical snapshot 위에 `realtime` feature가 소유하는 작은 streaming overlay를 합성한다. 이 overlay는 전역 상태 라이브러리가 아니라 branch 화면 수명에 묶인 reducer다.

### 17.2 Route

```text
/login
/w/:workspaceId
/w/:workspaceId/documents/:documentId
/w/:workspaceId/sessions/:sessionId
/w/:workspaceId/sessions/:sessionId/branches/:branchId
/s/:shareToken
/w/:workspaceId/proposals/:proposalId
```

### 17.3 Feature 경계

```text
features/
├── auth
├── documents
├── sessions
├── curation
├── toss
├── consensus
└── realtime
```

feature는 API client와 화면 상태를 함께 소유하지만 다른 feature의 내부 파일을 import하지 않는다. 공통 UI와 domain-neutral hook만 `components`와 `api`에 둔다.

### 17.4 핵심 화면

1. **Document:** main 본문, revision, claim별 bundle link, 근거 없음 표시
2. **Session list:** draft/shared/closed, owner, main 반영 여부가 아닌 proposal 상태
3. **Draft session:** 전체 thread, curation preview, bundle publish
4. **Toss share:** 공개 bundle만 표시, 로그인 후 fork CTA
5. **Shared session:** 참여자, branch 비교, 동의점·충돌점·합의 조건
6. **Proposal:** patch, citations, required approvers, version별 결정

정적 데모의 세 칼럼 문서·본문·근거 구조와 세션 thread 시각 언어는 참고하되 DOM과 JavaScript는 재사용하지 않는다.

### 17.5 Streaming projection

Frontend realtime state는 최소한 다음 값을 가진다.

```text
snapshotCursor
lastAppliedSeq
streamingMessages[messageId]
activeRuns[runId]
```

- `seq <= lastAppliedSeq` event는 중복으로 보고 무시한다.
- `message.delta`는 해당 message의 streaming overlay에 append한다.
- `message.completed`는 branch query를 invalidate하고 새 snapshot을 요청한다.
- 새 snapshot이 completed message와 그 event 이상의 cursor를 포함한 것을 확인한 뒤 overlay를 제거한다. 먼저 제거해 완료 직전에 문장이 사라지는 flicker를 만들지 않는다.
- `stream.reset`은 overlay와 cursor를 버리고 snapshot부터 다시 동기화한다.
- 한 branch를 여러 탭이나 사용자가 구독해도 각 client가 자신의 cursor와 overlay를 독립적으로 관리한다.

## 18. 인증과 권한

### 18.1 인증

OIDC Authorization Code + PKCE를 사용한다. backend는 `issuer`, `audience`, `subject`를 검증하고 `oidc_subject`로 SOT user를 찾는다. 특정 공급자 기능에 의존하지 않는다.

### 18.2 역할

Workspace role:

- `owner`: workspace 관리와 모든 문서 merge
- `member`: session 생성, 참여, proposal 생성
- `viewer`: workspace 문서와 허용된 session 읽기

Session role:

- `owner`: member, bundle, share link 관리
- `editor`: 메시지, curation, proposal 생성
- `viewer`: 읽기만 가능

### 18.3 Share capability

- raw token은 URL fragment가 아니라 path segment로 전달하므로 access log에서 redaction한다.
- 데이터베이스에는 token hash만 저장한다.
- share 응답은 `Cache-Control: private, no-store`를 사용한다.
- owner는 revoke와 rotate를 할 수 있다.
- share link는 bundle 외 workspace API 접근 권한을 부여하지 않는다.
- fork endpoint는 로그인과 명시적 user consent를 요구한다.

### 18.4 Platform에서 Agent로의 인증

Platform은 TLS 위에서 `typ=at+jwt`, Agent audience, opaque end-user `sub`, allow-listed Platform
`azp/client_id`, `agent:run`/`agent:abort` scope와 5분 이하 만료를 가진 JWT access token을
전달한다. JWT/JWS·claim·JWKS 검증은 Platform과 Agent가 함께 사용하는 독립
`service-auth` 패키지에 두되, 각 서비스가 자기 ingress 권한 정책을 소유한다. Agent는
단일 trusted issuer, Agent audience, 명시적인 HTTPS `jwks_uri`와 asymmetric algorithm
allow-list로 토큰을 독립 검증하고 ID token이나 token-provided key URL은 받지 않는다.
raw token/sub는 저장하지 않으며
`SHA-256(UTF8(iss) || 0x00 || UTF8(sub))`을 request owner와 Semora trusted subject로 사용한다.
reattach/resume/abort는 모두 새 token을 검증해 같은 owner인지 확인하고 mismatch는 `404`다.
세부 계약은
[`2026-09-02-shared-service-auth-design.md`](2026-09-02-shared-service-auth-design.md)를 따른다.

## 19. 동시성, 트랜잭션, 멱등성

### 19.1 Branch 메시지

- branch `version`을 optimistic lock으로 사용한다.
- active run이 있으면 새 입력은 Semora input queue에 순서대로 추가한다.
- 같은 idempotency key의 재요청은 기존 job 응답을 반환한다.
- agent tool call은 Semora call ID를 effect idempotency key로 사용한다.
- API connection 종료와 SSE disconnect는 job이나 run의 cancel 조건이 아니다.
- cancel command는 idempotent하며 이미 terminal 상태인 run에는 현재 상태를 반환한다.

### 19.2 Bundle publish

- preview의 branch version과 publish 요청의 expected version이 같아야 한다.
- canonical JSON payload로 content hash를 계산한다.
- 동일 hash 재요청은 기존 bundle을 반환한다.

### 19.3 Proposal merge

한 transaction에서 다음 순서로 처리한다.

1. document row를 `FOR UPDATE`로 잠근다.
2. current revision과 proposal base를 비교한다.
3. proposal version과 required approvals를 검증한다.
4. 새 revision을 insert한다.
5. document current pointer를 갱신한다.
6. proposal을 merged로 갱신한다.
7. 같은 transaction에 `main.updated` stream event를 기록한다.

어느 단계든 실패하면 전체 transaction을 rollback한다.

### 19.4 Stream cursor와 전달

- event 전달 보장은 at-least-once이며 frontend reducer는 `seq` 기준으로 idempotent하게 적용한다.
- seq는 scope별 `sot_stream` row lock 안에서 할당하여 먼저 관찰한 높은 seq 뒤에 낮은 seq가 commit되는 문제를 막는다.
- journal insert가 성공하기 전에는 NOTIFY하지 않는다.
- SSE gateway는 NOTIFY payload가 아니라 journal row를 읽어 전송한다.
- heartbeat timeout마다 journal을 재조회하여 누락된 wake-up을 복구한다.
- journal retention 삭제는 completed transcript가 canonical snapshot에서 조회되는 event만 대상으로 한다.

## 20. 실패와 복구

| 실패 | 처리 |
| --- | --- |
| API process 종료 | client가 mutation을 같은 idempotency key로 재시도 |
| Agent process 종료 | 다음 동일 AG-UI 재접속이 Semora Recover를 시도; lease가 남아 있으면 만료 후 재시도 |
| Semora `Contended` | 다른 replica가 실행 중이므로 error를 내지 않고 Agent event를 구독 |
| model `Indeterminate` | 자동 force-retry 없이 `RUN_ERROR(indeterminate_execution)`; 사용자는 새 runId로 재시도 |
| LLM provider 오류 | run failed event, 사용자가 같은 branch에서 재시도 |
| tool 오류 | Semora tool result로 기록하고 agent가 다음 행동 선택 |
| 새로고침·탭 종료 | backend run은 계속되고 새 client가 snapshot cursor 이후를 replay |
| SSE 연결 종료 | 마지막 적용 cursor로 재연결하고 journal event를 replay |
| Agent Redis event 유실 | sequence gap 또는 heartbeat DB reconciliation으로 복구 |
| DB commit 후 Redis publish 실패 | Agent DB high-water mark 확인으로 terminal event까지 복구 |
| cursor가 retention보다 오래됨 | `stream.reset` 후 canonical snapshot부터 재동기화 |
| share revoke 중 읽기 | 다음 요청부터 410, 이미 열린 화면은 재조회 시 닫힘 |
| proposal 승인 중 main 변경 | proposal stale 전환, 자동 merge 금지 |
| 중복 승인 요청 | unique key로 기존 decision 반환 |
| hidden draft source 요청 | 404로 존재 여부를 숨김 |

Abort는 DB의 `abort_requested_at`을 먼저 commit하고 local `asyncio.Event`, Redis Pub/Sub 순서로
전파한다. 각 replica는 자기 local active run만 1초마다 DB에서 다시 확인하므로 Redis 장애나
Pub/Sub 유실에도 중단 intent가 사라지지 않는다. 사용자 중단에는 `Task.cancel()`을 쓰지
않는다.

모델 `Indeterminate`는 이 서비스의 비핵심·비변이 성격에 맞춰 자동 force-retry하지
않는다. Agent는 typed error를 기록하고 사용자가 새 `runId`로 다시 시도하게 한다.
`Contended`는 다른 replica 실행 구독으로 처리하며 Semora private API/DB를 건드리지
않는다.

## 21. 보안과 개인정보

- 모든 product query는 workspace/session policy를 거친다.
- agent tool도 사용자와 동일한 domain policy를 우회할 수 없다.
- prompt와 tool argument는 기본 애플리케이션 로그에 기록하지 않는다.
- 공개 bundle 생성 전 secret pattern 경고를 제공하지만 자동 삭제하지 않는다.
- 공개 bundle에는 내부 user ID 대신 display attribution만 포함한다.
- OIDC token과 share raw token은 저장 로그에서 redaction한다.
- markdown은 server와 client 양쪽에서 raw HTML을 비활성화한다.
- SSE는 branch 권한을 연결 시점과 재연결 시점에 다시 확인한다.
- dependency와 container image는 lockfile/digest로 고정한다.

## 22. 관측 가능성

로그 공통 필드:

```text
request_id
user_id
workspace_id
session_id
branch_id
run_id
conversation_id
proposal_id
```

메트릭:

- API latency/error by route
- active Agent tasks, Semora lease contention/fencing
- Semora run duration, suspension, recovery count
- SSE connection/reconnect count
- Agent DB replay count/lag, Redis gap/fallback count
- explicit abort와 process-recovery count
- bundle publish와 toss open 수
- toss에서 fork로 전환율
- proposal 승인까지 걸린 시간
- stale/rejected/merged proposal 수
- main revision 생성 수

제품의 핵심 성공 지표는 세션 수가 아니라 `toss → fork → 합의 proposal → main merge` 전환율이다.

## 23. 테스트 전략

### 23.1 Domain unit tests

- session, bundle, proposal 상태 전이
- version 증가 시 approval 무효화
- required approver 정책
- stale merge 방지
- curation 선택 맥락 검증
- hidden source 접근 금지

각 테스트는 한 불변 조건만 검증한다.

### 23.2 Backend integration tests

- 실제 PostgreSQL에서 repository와 transaction 검증
- `PostgresSteps`와 `PostgresTranscript` 연결
- scripted LangChain model을 사용한 Semora 실행
- Agent process crash 후 reconnect-triggered Semora recovery
- Semora Contended가 AG-UI error가 아니라 subscribe로 처리됨
- model Indeterminate가 자동 retry 없이 terminal error가 됨
- message command 응답 연결이 끊겨도 durable run 계속 실행
- Agent DB replay와 Redis live buffer의 sequence merge
- DB commit 후 Redis publish 실패의 heartbeat reconciliation
- retention 밖 cursor의 `stream.reset`
- sanitized fork에 dropped turn이 포함되지 않음
- share revoke와 rotate
- 동시 approval/merge 경쟁
- SSE disconnect, replay, live 전환과 reset

### 23.3 Contract tests

- OpenAPI snapshot
- problem response schema
- official AG-UI RunAgentInput/BaseEvent contract와 SSE `id` transport cursor
- Semora awaited execution event의 AG-UI mapping과 best-effort EventEnvelope 관측 분리
- TypeScript API client 생성 결과

### 23.4 Frontend tests

- route별 loading, empty, error, forbidden 상태
- draft와 공개 bundle 표시 차이
- edited/joined turn 표식
- 익명 toss 읽기와 로그인 fork 전환
- proposal version 변경 후 approval 초기화
- snapshot과 streaming overlay 병합
- SSE 중단 중 발생한 delta replay와 중복 제거
- completed snapshot 확인 후 overlay 제거

### 23.5 End-to-end acceptance tests

정적 데모의 두 시나리오를 실제 backend와 scripted agent로 재현한다.

1. 레이트리밋 결정을 정리하고 toss한 뒤 상대가 fork한다.
2. msbd 선택지 `1`, `B`가 앞의 LLM 선택지와 함께 bundle에 나타난다.
3. 공유 세션에서 새 gVisor 이견을 추가한다.
4. 양쪽이 합의안을 승인한다.
5. main revision이 생성되고 claim에서 bundle로 역추적된다.
6. 긴 agent run 중 페이지를 새로고침해도 run이 계속되고, 끊긴 사이의 delta와 최종 transcript가 중복 없이 복구된다.

## 24. 배포 구조

v1 운영 단위:

```text
web      React 정적 자산
platform Platform FastAPI + AG-UI proxy
agent    Agent FastAPI + direct async Semora execution
platform-db  Platform 전용 PostgreSQL
agent-db     Agent 전용 PostgreSQL
agent-redis  Agent event hot replay/live cache
```

Agent 배포는 AG-UI API와 Semora async execution을 같은 service process에 둔다. 별도 execution worker process는 없다. web은 immutable asset hash를 사용하고 migration은 service 시작 전에 한 번 실행한다. Agent Redis는 target topology에 포함되지만 correctness source가 아니므로 장애 시 Agent DB replay로 동작해야 한다. Kafka와 object storage는 v1 필수 구성요소가 아니다.

Agent는 replica당 Semora task 32개, subject당 local task 4개, request body 2 MiB, whole run
15분을 기본 제한으로 둔다. OpenRouter timeout은 connect 10초, first byte/inter-chunk 60초,
model invocation 5분이다. SIGTERM 시 readiness를 즉시 내리고 35초 drain 후 남은 task를
infrastructure cancellation하며 Kubernetes grace는 45초다. `/livez`는 process만,
`/readyz`는 draining 여부, Agent PostgreSQL/schema, prompt config, OpenRouter credential과
JWKS를 확인한다. Redis와 OpenRouter 실시간 호출은 readiness dependency가 아니다.

로컬 개발은 `compose.yaml`로 Platform PostgreSQL, Agent PostgreSQL과 Redis를 띄우고 web, Platform Server, Agent Server를 별도 명령으로 실행한다. scripted model mode에서는 외부 LLM key 없이 전체 E2E를 실행할 수 있어야 한다.

## 25. 구현 슬라이스

이 설계는 하나의 제품 spec이지만 구현은 다음 수직 슬라이스로 나눈다.

1. **Foundation:** React shell, FastAPI, OIDC, PostgreSQL, workspace/document
2. **Draft Session:** Platform/Agent AG-UI boundary, direct async Semora run, Agent event journal, Redis/DB replay 동기화
3. **Curation:** drop/edit/join/cite, preview, immutable bundle
4. **Toss and Fork:** capability link, anonymous read, authenticated sanitized fork
5. **Consensus:** shared participants, proposal, approval, stale handling
6. **Main:** transactional revision merge, claim-to-bundle navigation
7. **Hardening:** recovery, security, observability, complete E2E

각 슬라이스는 backend API와 React 화면을 함께 끝내며 backend만 먼저 전부 만들지 않는다.

## 26. v1 완료 조건

다음이 모두 충족되어야 v1 제품 흐름이 완성된 것으로 본다.

- 사용자가 실제 Semora agent와 draft session을 진행한다.
- draft가 서버에 저장되고 main에는 자동 반영되지 않는다.
- 선택한 turn만으로 immutable bundle을 만들 수 있다.
- 공개 bundle에서 제외된 draft turn을 어떤 API로도 읽을 수 없다.
- 로그인하지 않은 사용자가 toss link를 읽을 수 있다.
- 로그인한 사용자가 bundle에서 sanitized branch를 만들 수 있다.
- 두 사용자가 같은 proposal version을 승인할 수 있다.
- 승인 전에는 main이 바뀌지 않는다.
- 승인 후 새 main revision과 citation backlink가 생성된다.
- 동시 merge에서 하나만 성공하고 다른 proposal은 stale이 된다.
- Agent process crash 후 재접속이 Semora recovery를 시작하고 committed effect를 중복 실행하지 않는다.
- 새로고침과 SSE disconnect가 진행 중인 LLM run을 취소하지 않는다.
- React UI가 snapshot cursor 이후의 누락 delta를 replay하고 live stream으로 전환한다.
- 중복 event, NOTIFY 유실, retention reset 뒤에도 canonical transcript와 동일한 상태를 복구한다.
- 정적 HTML 데모의 핵심 사용자 흐름을 실제 서비스에서 재현한다.

## 27. 설계상 명시적 제외

다음은 v1 구현 계획에 넣지 않는다.

- 물리적 local-only storage
- raw draft를 공개 링크로 제공
- 하나의 Agent Server 안에서 여러 agent profile을 runtime 선택
- Agent queue worker와 request claim/lease/attempt state machine
- critical mutating Agent tools
- Next.js 또는 서버 렌더링
- session 자체를 main 상태로 변경
- approval 없는 agent 단독 main update
- 진실·신뢰도·승패 score
- anonymous write
- Platform Server와 Agent Server 경계를 넘어선 추가 microservice 분해

이 항목은 데이터 모델과 공개 API를 깨뜨리지 않는 범위에서 v2 이후 검토한다.
