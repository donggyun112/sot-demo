# SOT

> 사고는 로컬에서, 합의는 main에.

SOT는 AI가 사람 대신 말하는 시대를 위한 합의 프로토콜이다.

사람이 어떤 주장을 전달할 때 완성된 문장만 보내는 대신, 자신이 그 주장에 이르게 된 LLM 세션에서 선별한 근거를 `toss`한다. 상대는 공개된 Bundle을 독립적인 비공개 세션으로 fork하고, 빠진 전제와 반례를 넣고, 서로 수용할 수 있는 조건을 찾는다. 문서에 연결된 원래 세션에서는 Proposal을 만들고, 필요한 승인과 명시적인 Merge를 거쳐 main을 갱신한다.

SOT가 관리하는 것은 진실이 아니라 **사람들 사이의 현재 합의 상태**다.

## 문제: 인간 미트 프록시

LLM을 이용하면 누구나 메신저에서 정교한 주장과 유창한 설명을 만들 수 있다. 그런데 그 사람과 직접 대화하면 같은 주장을 설명하거나, 반박에 답하거나, 전제가 바뀌었을 때 입장을 갱신하지 못하는 경우가 생긴다.

그 주장을 만든 사람이 인간이 아니라 LLM이었기 때문이다.

문제는 LLM을 사용했다는 사실이 아니다. LLM이 만든 주장을 자기 사고 과정에서 나온 것처럼 전달하면서, 그 주장에 대한 고집만 인간에게 남는다는 점이다. 자신이 왜 설득됐는지 설명할 근거가 없으면 이견은 논쟁이 아니라 맹목적인 대치가 된다.

SOT의 답은 단순하다.

> 주장을 보낼 거라면, 자신이 설득된 세션도 함께 보내라.

세션 ID는 출처 표시만을 위한 영수증이 아니다. 상대가 그 주장을 다시 열고, 반박하고, 설득하고, 합의점을 찾을 수 있는 **사고 상태의 주소**다.

## 세션을 toss한다는 것

일반적인 메신저에서는 결론만 이동한다.

```text
LLM의 주장 → 인간이 복사 → 상대에게 전달
                         ↓
                 전제와 선택지는 유실
                         ↓
             반박을 받아도 설명하거나 갱신할 수 없음
```

SOT에서는 결론이 만들어진 세션 상태가 함께 이동한다.

```text
A의 로컬 세션
      │ 정리
      ▼
불변 Bundle ── toss ──▶ B의 독립적인 private fork

문서에 연결된 원래 세션
      │ Proposal 생성 (승인자와 citation 고정)
      ▼
필수 승인 완료 → approved → document.publish 권한자의 Merge → main
```

목표는 누가 옳은지 판정하거나 LLM을 굴복시키는 것이 아니다. 각자가 어떤 전제와 선택지를 통해 현재 입장에 도달했는지 드러내고, 다음 세 가지를 찾는 것이다.

- 이미 합의된 부분
- 아직 충돌하는 부분
- 무엇이 바뀌면 합의할 수 있는지

반박은 승패를 가르기 위한 공격이 아니라 합의 가능한 조건을 발견하는 입력이다.

## 왜 모든 세션을 공개하지 않는가

투명성은 사고 과정 전체를 네이키드하게 공개한다는 뜻이 아니다.

사람은 안전한 공간에서 틀리고, 번복하고, 감정적으로 말하고, 사적인 정보를 사용하면서 생각할 수 있어야 한다. 모든 프롬프트가 자동으로 공개된다면 사람은 솔직하게 탐색하지 못하고 SOT도 감시 도구가 된다.

그래서 SOT에는 main에 올라가지 않는 세션과 로컬 분기가 있다.

| SOT | 역할 | Git에 비유하면 |
| --- | --- | --- |
| 비공개 세션 | owner와 명시적인 세션 멤버만 보는 draft | untracked work |
| 로컬 세션·분기 | 아직 공유하거나 합의하지 않은 draft | local branch |
| `session_drop/edit/join` | 공개할 사고 단위를 정리 | staging |
| Bundle 발행 | 정리한 공개 근거를 불변 snapshot으로 고정 | commit |
| 공개 fork | 공개 BundleItem만 복사한 독립 세션 | new branch |
| `sot_update` | 문서 변경 Proposal 생성 | pull request |
| Merge | 승인된 Proposal을 새 main revision으로 반영 | merge |
| main 문서 | 현재 구성원이 승인한 합의 상태 | main |

여기서 `로컬`은 물리적인 기기 저장이 아니라 main에 올라가지 않은 draft라는 은유다. draft는 서버에 저장될 수 있다. main으로 가는 것은 원본 대화 전체가 아니라, 공개하기로 선택하고 정리한 세션이다. 정리된 세션은 원본인 척하지 않으며 어떤 턴을 골랐고 편집했는지 표시한다.

투명성의 경계는 생각을 시작한 순간이 아니라 **주장을 공개하는 순간**에 생긴다.

## main의 의미

main은 다음 중 어느 것도 아니다.

- 절대적인 진실
- LLM이 내린 정답
- 모든 사람의 전체 대화 기록
- 다수결에서 이긴 주장

main은 현재 참여자들이 공개적으로 책임지고 함께 사용하기로 승인한 상태다.

합의되지 않은 내용은 잘못된 내용으로 삭제되지 않는다. 로컬 분기나 공유 세션에 남아 이후 합의의 재료가 된다. 새로운 반례나 조건이 생기면 main을 직접 덮어쓰지 않고 기존 합의에서 다시 fork한다.

```text
private/local  → 자유롭게 탐색
shared         → 차이를 드러내고 조율
main           → 합의된 것만 반영
```

## 제품 원칙

### 1. 주장이 아니라 세션을 전달한다

완성된 문장만으로는 그 사람이 무엇을 직접 말했고 LLM이 무엇을 제안했는지 알 수 없다. SOT는 선택지를 낸 LLM 턴과 그것을 고른 인간 턴을 함께 보존한다. 사람이 실제로 입력한 것이 `1`이나 `B`뿐이라면 그 사실도 보여준다.

### 2. 읽을 수 있을 뿐 아니라 fork할 수 있어야 한다

세션은 정적인 인용 링크가 아니다. 상대가 같은 맥락에서 이견, 반례, 제약 조건을 추가하고 새로운 합의안을 만들 수 있어야 한다.

### 3. 사적인 사고와 공개 주장을 분리한다

로컬 세션은 자동으로 문서나 main을 바꾸지 않는다. `sot_update`는 Proposal을 만들며, 필수 승인 완료 후 별도 Merge가 공식 상태를 갱신한다.

### 4. 합의되지 않은 것을 억지로 합치지 않는다

합의하지 못한 세션은 실패가 아니다. 충돌 지점과 합의 조건을 보존한 유효한 분기다.

### 5. AI 사용을 숨기지 않되 인간의 책임도 지우지 않는다

LLM이 문장을 만들었더라도 무엇을 선택하고, 정리하고, 공유하고, main에 올릴지는 인간의 행위다. 세션 공개는 책임을 LLM에 떠넘기기 위한 면책 장치가 아니다.

## SOT가 아닌 것

SOT는 다음 제품이 아니다.

- AI 채팅 기록 백업·검색 서비스
- AI가 쓴 문장을 적발하는 탐지기
- 주장이나 사람의 진위를 판정하는 팩트체커
- 모든 프롬프트를 공개하는 감시 시스템
- 문서에 출처 링크만 붙이는 provenance 뷰어
- 누가 토론에서 이겼는지 판정하는 심판

세션 보관과 출처 표시는 필요한 기반이지만 목적은 아니다. 목적은 서로 다른 사고 상태를 교환하고, 공개 가능한 합의 상태를 함께 만드는 것이다.

## 실행

Docker Compose를 사용한다. `.env.example`을 `.env`로 복사한 뒤 Google Web client ID와
32바이트 이상의 무작위 JWT signing secret을 설정한다. Google의 authorized JavaScript
origin에는 frontend 주소를 등록한다. 운영 환경은 HTTPS reverse proxy 뒤에서 실행한다.
기본 모델 `test`는 외부 모델 API를 호출하지 않지만 실제 로그인에는 Google 설정이 필요하다.

```bash
cp .env.example .env
# .env의 placeholder를 실제 배포 설정으로 교체한 뒤:
docker compose build && \
docker compose up -d --wait db && \
docker compose run --rm --no-deps backend sot-migrate && \
docker compose up -d --wait backend frontend
```

로컬 브라우저 주소는 <http://localhost:3000>이다. Compose 서비스는 `db`, `backend`, `frontend`
세 개다. migration은 backend 이미지를 사용하는 일회성 command이며 별도 상주 서비스가 아니다.
웹 replica는 migration을 실행하지 않는다. 시작 시 migration ledger를 읽어 누락되거나 다른
schema를 거부하므로 배포 단계가 완료되기 전에 웹이 준비 상태가 될 수 없다. `/healthz`는
프로세스 생존, `/readyz`는 DB 연결과 schema 준비 상태를 확인한다.

DB는 빈 상태로 시작한다. Migration 007은 canonical 전환 표시만 기록하며 001의 legacy table과
기존 row를 보존한다. Legacy actor alias에는 검증된 Google identity나 workspace 매핑이 없어
자동 이관하지 않는다. 이 데이터의 이관에는 명시적인 identity/tenant 매핑이 필요하다.
Alice/Bob 데이터는 폐기 가능한 브라우저 테스트 DB에서만 만든다. Workspace 생성은
`POST /api/v1/workspaces`를 사용한다. 문서 생성 UI/HTTP endpoint는 현재 slice에 없으므로 실제
문서의 초기 입력은 `document.application.CreateDocument`를 호출하는 관리 단계가 필요하다.

Google client ID는 frontend build에도 전달되므로 변경 후 frontend 이미지를 다시 빌드한다.
JWT secret과 provider key는 backend 런타임 환경에만 전달한다. 실제 모델을 쓰려면
`SOT_MODELS`를 Pydantic AI 모델 참조의 JSON 배열로 바꾸고 선택한 provider key만 설정한다.

```dotenv
SOT_MODELS=["openai:gpt-5.2","anthropic:claude-sonnet-4-5"]
```

## 구현 구조

```text
React + generated OpenAPI / TanStack Query + native AG-UI
  ├─ REST ─────────────▶ FastAPI application handlers ─▶ PostgreSQL 16
  └─ AG-UI SSE ────────▶ Pydantic AI Agent ────────────┘
```

단일 FastAPI deployable을 `identity`, `workspace`, `document`, `session`, `sharing`,
`consensus`, `agent`의 일곱 모듈로 구성한다. 각 모듈은 API, application, 순수 Python domain,
port, psycopg adapter를 소유한다. `bootstrap.app.build_app()`이 pool/UoW, capability port,
handler, AuthFacade, 한 개의 Pydantic AI Agent와 router를 명시적으로 조립한다. 모듈 간 협업은
`contracts.py`의 좁은 공개 port로만 이루어지며 최상위 application command가 transaction을 소유한다.

Google Identity Services의 ID token을 `POST /api/v1/auth/google`로 보내면 Google adapter가
검증하고 AuthFacade가 SOT Access Token과 Refresh Token을 발급한다. Access Token은 frontend
메모리에만 보관하며 `Authorization: Bearer`로 전송한다. Refresh Token은 `HttpOnly`, `Secure`,
`SameSite=Lax` cookie로만 전달하고 `/auth/refresh`에서 rotation한다. Workspace는 token에
고정하지 않고 `/api/v1/workspaces/{workspace_id}/...` URL로 지정한다.

Workspace owner도 명시적인 Session membership 없이는 private Turns를 읽을 수 없다.
인증 없는 예외는 `GET /api/v1/tosses/{token}`의 공개 Bundle snapshot이다. Fork는
`POST /api/v1/workspaces/{destination_workspace_id}/tosses/{token}/fork`로 요청하며 공개
BundleItem과 attribution만 복사한다. 생성된 Session은 `document_id=null`이며 원본 권한,
문서 링크, 이후 변경을 승계하지 않는다. Fork에서 문서 Proposal을 만들 수 없다.

Agent 정의는 application 수명 동안 재사용하고 actor/workspace/branch/history/version은 각
요청의 deps에 둔다. 모델 호출 동안 DB transaction을 유지하지 않는다. 서버가 권한을 확인하고
완료된 Branch Turns를 읽으며 client message 배열에서는 최신 사용자 입력만 받는다. 완료된
user/assistant/tool Turns를 짧은 transaction으로 원자 저장한 뒤 `RUN_FINISHED`를 보낸다.
Frontend는 stream을 표시하고 해당 Branch의 Turns와 metadata만 다시 조회한다. 취소/실패한
partial output은 저장하지 않으며 별도 worker나 실행 복구 경로는 없다.

서버 도구는 `session_cite`와 `sot_update`다. 각 tool mutation과 Branch version 증가는 같은
transaction에 참여한다. 같은 Branch에서 경쟁한 run은 첫 충돌에서 `version_conflict`의
`RUN_ERROR`로 종료하고 실패한 tool의 부작용을 남기지 않는다.

Proposal의 필수 승인자와 Bundle/item/claim citation은 version마다 고정된다. 추가 승인자는
같은 Workspace 멤버여야 하며 Proposal form의 ID 입력으로 지정해도 Session 접근권한을 얻지
않는다. 마지막 승인은 status를 `approved`로만 바꾼다. `document.publish` 권한자가
`POST /api/v1/workspaces/{workspace_id}/proposals/{proposal_id}/merge`를 호출하면 base
revision을 다시 검사하고 revision/citation/main pointer를 한 transaction에서 변경한다.

`GET /api/v1/workspaces/{workspace_id}/documents/{document_id}` 응답 예시 (ID 축약):

```json
{
  "document": {
    "id": "…", "workspace_id": "…", "title": "요청 제한 토큰",
    "current_revision_id": "…", "version": 2
  },
  "current_revision": {
    "id": "…", "workspace_id": "…", "document_id": "…",
    "number": 2, "content": "합의된 내용", "proposal_id": "…",
    "created_by": "…", "created_at": "2026-09-06T00:00:00Z",
    "citations": [{ "bundle_id": "…", "bundle_item_position": 0, "claim_anchor": "합의된 내용" }]
  }
}
```

Sessions, Branches, Turns, Proposals는 각각 workspace 범위의 독립적인 read resource다.
오류는 `{"error":{"code":"version_conflict","message":"…"}}` 형태이며 인증 실패는 401,
not-found는 404, 권한 오류는 403, 상태 충돌은 409, 요청 검증 오류는 422다.

## 개발 검증

```bash
uv run --project backend pytest backend/tests -q
uv run --project backend ruff check backend
uv run --project backend mypy backend/src backend/tests
pnpm --dir frontend test
pnpm --dir frontend typecheck
pnpm --dir frontend build
docker compose build
pnpm --dir frontend e2e
```

백엔드 integration/E2E는 PostgreSQL 16 서버에 CREATE DATABASE 권한이 필요하다. 기본 테스트
접속은 `postgresql://sot:sot@localhost:54329/postgres`이며
`SOT_TEST_POSTGRES_ADMIN_URL`로 지정할 수 있다. 각 실행은 `sot_test_<random UUID>` DB를
만들고 종료 시 그 DB만 삭제한다. 기존 application DB는 테스트 대상으로 사용하지 않는다.

Playwright는 18000/18001 포트에서 frontend와 `backend/tests/e2e_app.py`를 직접 실행한다.
테스트 harness는 `SOT_ENVIRONMENT=test`에서만 실행되며 Google의 외부 credential 경계와
Pydantic AI FunctionModel만 대체한다. `/auth/google`, SOT token, 모든 application command와
PostgreSQL은 실제 경로다. Alice/Bob 두 workspace, private draft → curation/Bundle/Toss →
anonymous read → detached fork, 원본 문서의 별도 승인/Merge와 concurrent tool conflict를 검증한다.
Google/모델 provider 실제 네트워크 호출은 이 로컬 검증에 포함되지 않는다. 브라우저 trace에는
인증 정보가 포함될 수 있어 자동 저장을 끈다. 종료되지 않은 서버를 재사용하지 않는다.

로컬에서 migration만 실행하려면 다음을 사용한다.

```bash
SOT_DATABASE_URL=postgresql://sot:sot@localhost:54329/sot uv run --project backend sot-migrate
```

## 한 문장으로

> SOT는 사람이 LLM의 주장을 자기 말처럼 전달하는 대신, 자신이 설득된 세션을 상대에게 toss하고 함께 fork하여 합의된 상태만 main에 올리게 하는 프로토콜이다.
