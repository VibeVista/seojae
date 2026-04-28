# Connected Knowledge Bases — 외부 LLM-wiki 연결 기능 (1-pager)

> 개발 1-pager. 본 문서는 **설계 제안**이며, 아직 구현되지 않았다.

## Context

Seojae는 현재 `wiki/` 디렉토리 한 개를 단일 검색 코퍼스로 가정한다 (`tools/search.py:12` `COLLECTION_NAME = "wiki"`, 단일 ChromaDB 컬렉션). 사용자는 본인이 모은 정보 외에, 신뢰하는 타인이 운영하는 다른 seojae wiki를 **상황에 따라 켜고 끄는** 방식으로 확장 지식 저장소처럼 쓰고 싶어 한다.

예시 시나리오:

- 스페인 여행 정보가 부족할 때 → 친구의 "스페인 여행" wiki를 연결
- 일본 요리를 할 때 → 일본 요리 전문가의 wiki를 켜고, 한식 할 땐 끄고 한식 전문가의 wiki를 연결

이 기능은 **대화 중 LLM이 답변에 활용할 수 있는 정보의 풀**을 동적으로 넓히는 것이 목표다. 기존 단일 코퍼스 가정을 깨지 않으면서 확장 시스템(`extensions/`)을 통해 모듈식으로 추가한다.

---

## Goals / Non-goals

**Goals**

- 외부 seojae wiki를 **선언/연결/해제**할 수 있다 (사람이 직접 + LLM이 워크플로우 중에).
- `Query` 워크플로우에서 **로컬 wiki + 활성화된 외부 wiki들**을 함께 검색하고, 출처를 구분해 인용한다.
- 외부 wiki의 콘텐츠는 로컬과 명확히 분리되어 저장·인덱싱되어, 실수로 로컬 wiki에 섞이지 않는다.
- 기존 코어 워크플로우(Ingest, Lint, Reindex 등)를 깨지 않고 **확장(Extension)** 형태로 추가한다.

**Non-goals**

- 외부 wiki 쓰기/기여(write-back) — 외부 wiki는 **읽기 전용**.
- 실시간 동기화·구독 — 명시적 `pull` 시점에만 갱신.
- 인증·비공개 wiki 지원(v1) — 공개 git repo 또는 로컬 폴더 경로만.
- 외부 wiki 콘텐츠를 로컬 `wiki/`로 복사/병합 — 별도 네임스페이스 유지.
- 카테고리·태그 단위 부분 활성화 — v1은 **wiki 단위 on/off**만.
- 외부 wiki 페이지를 로컬 `index.md`에 등재하지 않는다 (별도 네임스페이스 유지 원칙과 동일선).
- 외부 wiki 간/외부↔로컬 wikilink 자동 resolve를 시도하지 않는다 — 외부 wiki의 `[[...]]` 링크는 그 wiki 내부에서만 의미 있다.

### 확정된 설계 결정

1. **전송 방식**: `git` 공개 URL 클론 + 로컬 디렉토리 경로 둘 다 지원.
2. **저장 위치**: `connected-wikis/`를 repo 안에 두고 `.gitignore`에 추가 (`connected-wikis.json`만 커밋해 사용자 머신 간 구성 공유).
3. **토글 단위**: wiki 전체 단위 on/off.
4. **출처 표기**: 답변 본문에 인라인 라벨 `(출처: <wiki-id>)` + 답변 끝에 통합 인용 블록 (외부 wiki가 1개 이상 사용된 경우에만).
5. **임베딩 모델 일치 정책**: 모든 컬렉션은 동일한 임베딩 모델·버전으로 인덱싱되어야 unified ranking 머지가 유의미하다 (기본: `extensions/search-chromadb.md`가 지정하는 모델). 모델 식별자를 `connected-wikis.json`의 `embedding_backend`/`embedding_model` 필드에 기록. 쿼리 시 불일치 컬렉션은 unified ranking에 머지하지 않고 별도 섹션으로 표시 + 경고 (캐노니컬 정의는 D 섹션).

---

## User Stories

1. "친구가 운영하는 스페인 여행 wiki를 연결해줘. URL은 `https://github.com/friend/spain-travel-wiki`."
   → LLM이 `connected-wikis.json`에 항목 추가, 로컬에 클론, 인덱싱하고 enabled=true로 등록.
2. "지금부터 일본 요리 wiki는 끄고 한식 wiki만 켜줘."
   → LLM이 `enabled` 플래그를 갱신하고 `config: toggle <id>` 커밋.
3. "마드리드에서 가족 식사로 좋은 곳 추천해줘."
   → LLM이 `enabled && status==ok` wiki들을 검색, 결과에 출처(로컬 vs 친구의 spain-travel)를 명시해 답변.
4. "연결된 wiki들 최신 상태로 업데이트해줘."
   → LLM이 각 wiki를 `git fetch + reset --hard`로 동기화하고 변경된 페이지만 재인덱싱. unreachable wiki는 `enabled` 보존 + `status="unreachable"` 갱신, 임베딩 모델 변경 시 경고. `<성공 N / 실패 M>` 보고 후 `pull: <N wikis updated>` 커밋.
5. "지금 연결된 wiki 목록 보여줘." → LLM이 List/Status 워크플로우로 표를 출력 (커밋 없음).

---

## Proposed Approach

### A. 저장 구조

```
seojae/
├── wiki/                          # 로컬 wiki (변경 없음)
├── connected-wikis/               # 신규: 외부 wiki들이 클론되는 위치 (.gitignore에 추가)
│   ├── spain-travel/              # 외부 wiki 1 (git repo 클론본)
│   │   └── wiki/...
│   └── japanese-cooking/          # 외부 wiki 2
│       └── wiki/...
├── connected-wikis.json           # 신규: 연결된 wiki 메타·토글 상태 (커밋됨)
├── search-index/                  # 변경: 컬렉션이 wiki별로 늘어남
└── extensions/
    └── connected-wikis.md         # 신규: 본 기능을 정의하는 확장 모듈
```

`connected-wikis.json` 스키마 (git/local 두 가지 source 타입 지원):

```json
{
  "schema_version": 1,
  "wikis": [
    {
      "id": "spain-travel",
      "name": "Friend's Spain Travel Wiki",
      "source_type": "git",
      "source": "https://github.com/friend/spain-travel-wiki",
      "enabled": true,
      "status": "ok",
      "added": "2026-04-28",
      "last_pulled": "2026-04-28",
      "commit": "abc1234",
      "embedding_backend": "search-chromadb",
      "embedding_model": "paraphrase-multilingual-MiniLM-L12-v2"
    },
    {
      "id": "japanese-cooking",
      "name": "My Local JP Cooking Notes",
      "source_type": "local",
      "source": "/Users/me/other-seojae",
      "enabled": false,
      "status": "ok",
      "added": "2026-04-28",
      "embedding_backend": "search-chromadb",
      "embedding_model": "paraphrase-multilingual-MiniLM-L12-v2"
    }
  ]
}
```

- `source_type: git` → `connected-wikis/<id>/`로 클론, Pull 시 `git fetch + git reset --hard origin/<default-branch>` (C4 참고).
- `source_type: local` → 클론 생략, 인덱싱 시 `<source>/wiki`를 직접 스캔. **주의**: 절대경로는 기기마다 다를 수 있어 `connected-wikis.json` 동기화 시 다른 머신에서는 path가 존재하지 않을 수 있다 → Connect/Pull 시 path 부재면 경고 후 해당 wiki를 skip(에러로 중단하지 않음).
- **`enabled` vs `status`**: `enabled`는 사용자 의도(켜고 싶은가)만 표현. `status`는 시스템 관찰 결과로 다음 enum 값 중 하나: `ok | error | unreachable | connecting`. transient 실패 시 `enabled`를 건드리지 않고 `status`만 갱신해 사용자 의도를 보존. Query는 `enabled && status == "ok"`인 wiki만 사용. `connecting`은 두-단계 reservation 동안만 디스크에 존재하는 transient 상태로, Connect만 쓰고 Query는 자동 skip한다 (사실상 비활성).
- **인덱싱 범위**: 외부 wiki 인덱싱은 `<repo>/wiki/**/*.md`로만 한정한다. 외부 wiki repo의 `connected-wikis.json`/`log.md`/`index.md`/`WIKI_SCHEMA.md`/`README.md`/`connected-wikis/`(중첩) 등 메타·트랜지티브 자료는 인덱싱하지 않는다 (외부 wiki의 외부 wiki를 따라가지 않음).
- **`id` 규칙**: `^[a-z0-9]([a-z0-9-]{0,29}[a-z0-9])?$`만 허용 (소문자 영숫자 시작·종료, 최대 31자, 연속·trailing 하이픈 금지). 예약어(`wiki`, `local`, `ext`, `default`)와 기존 항목과 중복은 거부.
- **마이그레이션 (필드 보강)**: 기존 `connected-wikis.json`에 신규 필드가 없으면 읽기 시점에 보강한다. 정확한 규칙:
  - `status`: 없으면 `"ok"`로 채움.
  - `embedding_backend`/`embedding_model`: `tools/search.py --print-model`이 exit 0이면 그 값으로 채움. 비-0(backend 미활성)이면 `null` sentinel을 두고 다음 성공한 Connect/Pull 시 재해결한다 (이 단일 규칙이 "재사용·신규 함수" 섹션의 에러 컨트랙트와 캐노니컬하게 일치).
  - 다음 디스크 쓰기 시점에 보강된 값이 반영된다.
  - `schema_version`은 현재 `1`이 유일하며 향후 스키마 변경 대비용으로 미리 둔다 (이번 PR에서는 분기 없음).
- **동시성 (락 범위·순서)**: 두 종류의 락 사용.
  - **글로벌 JSON 락** `<repo>/connected-wikis.lock` (POSIX `fcntl.flock`): `connected-wikis.json` read-modify-write 짧은 critical section만 보호. 순서: `open(lockfile,'w') → flock(LOCK_EX) → read JSON → mutate → write tmp → fsync → os.replace → flock(LOCK_UN) → close`.
  - **per-wiki 락** `<repo>/connected-wikis/.locks/<id>.lock`: 클론·git 작업·재인덱싱 같은 장기 실행을 보호. Pull은 per-wiki 락을 길게 잡고 git 작업 후 글로벌 락은 메타 갱신 시점에만 짧게 잡음 → deadlock 회피.
  - **POSIX 한정** — Windows 환경은 v1 비지원으로 명시 (필요 시 v2에서 `portalocker` 도입 검토). 락 파일들은 `.gitignore`에 추가.
- **인터랙션 프로토콜 (CLI ↔ LLM ↔ User)**: Connect의 신뢰 경계 동의, Pull의 임베딩 모델 mismatch (a/b) 선택, Disconnect의 grep 결과 확인 등은 모두 동일한 메커니즘을 사용한다.
  - CLI는 인터랙티브 결정이 필요할 때 stdout에 `PROMPT: <question>` 한 줄 + 가능한 옵션을 출력하고 **exit 4** (interactive-decision-required)로 종료. PROMPT 라인 다음에 옵션 토큰 목록을 한 줄로 명시 (예: `OPTIONS: accept reject`).
  - LLM은 해당 출력을 사용자에게 제시하고 응답을 받아, 동일 명령에 **통일된 플래그 `--decision <prompt-key>=<value>`**를 더해 재호출. `<prompt-key>`는 PROMPT 라인에 함께 출력되는 식별자(예: `consent`, `mismatch`, `disconnect-grep`)이고 `<value>`는 OPTIONS 중 하나. 예: `connect ... --decision consent=accept`, `pull --decision mismatch=reindex`.
  - stdin이 TTY인 경우(사용자가 CLI 직접 호출): CLI가 직접 `input()` 프롬프트로 폴백 — exit 4 없이 진행.
  - **다중 프롬프트**: 한 호출에서 결정이 여러 개 필요한 경우(예: Connect가 consent + mismatch 둘 다 필요) CLI는 한 번에 하나씩만 PROMPT/exit 4를 발생시킨다. LLM은 `--decision`을 누적해서 재호출(`--decision consent=accept --decision mismatch=update`); 다음 결정이 더 필요하면 또 exit 4. 모든 결정 수집 시 정상 진행.
  - 모든 재호출은 idempotent하도록 설계 (이전 단계의 상태는 디스크 또는 락으로 보존).

### B. 검색 (multi-corpus)

`tools/search.py`를 다음과 같이 확장:

- ChromaDB 컬렉션을 `wiki`(로컬) 외에 `wiki-ext-<id>` 형태로 wiki당 1개씩 운영.
- 신규 CLI 옵션: `--collections wiki,wiki-ext-spain-travel,...` — 동시에 여러 컬렉션을 쿼리하고 결과를 점수로 머지.
- 결과 출력 시 각 라인에 `[wiki: <id>]`를 붙여 출처를 표시.

  ```
  wiki/concepts/vibe-coding.md [wiki: local] [score: 0.82]
  connected-wikis/spain-travel/wiki/sources/madrid-restaurants.md [wiki: spain-travel] [score: 0.78]
  ```

- 인덱싱: `add_page`/`reindex`에 `--collection <name>` 옵션 추가, wiki별로 격리. **`--reindex --collection X`는 컬렉션 X만 삭제·재구축**하며 다른 컬렉션(특히 로컬 `wiki`)은 절대 건드리지 않음 (회귀 테스트로 byte-identical 확인).
- **공유 persistence 디렉토리**: 모든 컬렉션은 단일 `search-index/` 디렉토리(ChromaDB `PersistentClient`) 안에서 컬렉션 이름으로 격리된다 — wiki별 별도 디렉토리가 아님.
- **활성 모델 식별**: 임베딩 모델 이름은 `tools/search.py --print-model` 신규 introspection 명령으로 조회한다 (검색 백엔드 확장이 무엇이든 단일 진입점). 출력 형식은 정확히 두 줄: `backend=<id>\nmodel=<id>` (예: `backend=search-chromadb\nmodel=paraphrase-multilingual-MiniLM-L12-v2`). Connect/Pull은 이 두 값을 `embedding_backend`/`embedding_model` 필드에 기록.
- **점수 머지 가정**: 모든 컬렉션이 동일 임베딩 모델로 인덱싱된 경우에만 cosine similarity 비교가 유의미. 정책의 캐노니컬 정의는 D 섹션 참고 — B/Risks는 D를 따른다.
- **Wikilink 해석 정책**: 외부 wiki 페이지에 포함된 `[[Page Name]]` 링크는 **그 wiki 내부에서만 해석**한다 (Obsidian shortest-path가 로컬 페이지로 잘못 매핑되는 것을 방지). LLM이 외부 wiki 페이지를 인용할 때는 wikilink가 아닌 경로 형태(`connected-wikis/<id>/wiki/...`)로 인용하고, synthesis 페이지 본문에 외부 페이지를 wikilink로 끌어오지 않는다.
- **`{search.*}` 토큰 처리**: 본 확장의 multi-collection 호출은 스키마의 `{search.*}` 토큰을 통하지 않고 `tools/search.py`를 직접 호출한다 (토큰 resolver가 `--collection` 플래그를 모르기 때문). 단일 컬렉션 코어 워크플로우는 기존 `{search.*}` 토큰을 그대로 사용.

핵심 리팩터: **`COLLECTION_NAME` 상수를 함수 인자로 매개변수화** (`tools/search.py:12, 80, 89, 121, 177`).

- `get_collection(index_path, name="wiki")`/`reindex(wiki_path, index_path, model, name="wiki")`/`add_page(filepath, collection, model)`은 기본값 `"wiki"`로 backward-compatible.
- `query_index(q, top_n, collection, model)`은 인자 *타입*이 `chromadb.Collection` 단일 객체이므로 기본값으로는 호환 불가. **별도 신규 함수** `query_indexes(q, top_n, collections: list[Collection], model) -> list[(path, score, collection_name)]`을 추가해 multi-collection 호출용으로 사용. 단일 컬렉션 호출자(코어 Query 워크플로우)는 기존 `query_index`를 그대로 호출 → byte-identical 동작 보장.
- 외부 wiki 인덱싱 시 메타파일·중첩 `connected-wikis/` 제외는 `reindex()`의 `rglob('*.md')` 결과에 필터를 적용하고, 방어적으로 `add_page()`에도 동일 가드를 둔다.

### C. 신규 워크플로우 (extension에서 정의)

> 트리거 예시는 한국어로 표기 (`wiki_language: ko` 환경 가정). 실제로는 사용자의 자연어 표현이 의도만 명확하면 인식된다 (예: "connect the spain wiki at <url>" / "list connected wikis").

`extensions/connected-wikis.md`가 다음 6개 워크플로우를 추가:

0. **Init** — Connect/Pull/List 등 다른 워크플로우 실행 시점에 `connected-wikis.json`이 없거나 `.gitignore`에 `connected-wikis/` 항목이 빠져 있으면 자동 1회 실행 (List도 lazy하게 트리거 — "read-only"는 사용자 데이터 변경 없음을 의미하지 부트스트랩 자동 생성을 막는 의미가 아님).
   - **선결 조건**: 프로젝트 자체가 부트스트랩되어 `wiki/` 디렉토리가 존재해야 한다. 없으면 abort + "프로젝트 init을 먼저 실행해 주세요" 안내.
   - `connected-wikis.json` 생성 (`{"schema_version": 1, "wikis": []}`)
   - `.gitignore`에 `connected-wikis/` 및 `connected-wikis.lock` 추가 (이미 있으면 skip)
   - 별도 커밋: `extension: enable connected-wikis` (스키마의 `init:`은 프로젝트 최초 부트스트랩 1회용이므로 확장 활성화에는 신규 prefix `extension:` 사용)
   - **PR vs runtime**: Init이 runtime에 자동 처리하므로 PR에서 `.gitignore` 수동 수정은 불필요. PR에 미리 추가해도 Init의 "이미 있으면 skip" 로직으로 안전 (이중 추가 없음).

1. **Connect** — `"<repo-url-or-path>을 <id>로 연결해줘"`
   - **인자 처리**: `id`는 사용자 입력. `name`은 사용자가 명시(`--name <str>`)하지 않으면 git URL의 repo 슬러그(`<owner>/<repo>` 중 `<repo>`) 또는 로컬 경로의 마지막 디렉토리 이름에서 자동 유도. `added`는 Connect 실행 시각의 ISO 날짜(`YYYY-MM-DD`).
   - **id 검증**: A 섹션 정규식 + 예약어/중복 거부. 실패 시 사용자에게 다른 id를 요청. (이 단계 실패는 클론 전이므로 cleanup 불필요)
   - **Two-phase reservation**: 글로벌 JSON 락을 짧게 잡아 `{id, name, source_type, source, status: "connecting", added, ...}` 항목을 먼저 추가하고 락 해제 → 이로써 동일 id로의 동시 Connect를 차단(reservation collision; id-validation 통과 후 reservation 단계에서 거부). 이후 per-wiki 락(`connected-wikis/.locks/<id>.lock`)을 길게 잡고 클론·검증·reindex 진행. 모든 단계 성공 시 마지막에 글로벌 락을 다시 짧게 잡아 `status: "connecting"` → `"ok"`로 전환.
   - source가 git URL이면 `git clone <url> connected-wikis/<id>`, 로컬 경로면 클론 생략. 로컬 경로 부재 시 즉시 abort (rollback으로 reservation 항목 제거).
   - **seojae 구조 검증**: 클론/접근 직후 `<repo>/wiki/` 디렉토리와 그 안에 `*.md` 파일이 있는지 확인. 없으면 abort.
   - **신뢰 경계 확인**: 외부 wiki의 `README.md`(또는 `wiki/index.md`)를 인터랙션 프로토콜(A 섹션)으로 사용자에게 제시하고 동의를 받는다 (`PROMPT:` + exit 4 또는 stdin 폴백). 외부 wiki 콘텐츠는 데이터로만 취급되며, 그 안의 명령형 문장을 LLM이 지시문으로 따르지 않음을 명시. 거부 시 abort.
   - `tools/search.py --print-model`로 활성 backend/model 조회 (비-0 종료 시 abort)
   - reservation 항목의 메타 필드(`source_type`, `enabled=true`, `embedding_backend`, `embedding_model`) 갱신 (글로벌 락 짧게).
   - `tools/search.py --reindex --wiki-path <wiki-path> --collection wiki-ext-<id>`
     (git이면 `connected-wikis/<id>/wiki`, local이면 `<source>/wiki`. 메타파일·중첩 `connected-wikis/`는 인덱서가 자동 제외 — A 섹션 인덱싱 범위 규칙)
   - reindex 실패 시 rollback (아래 공통 정책) 후 abort.
   - reindex 출력의 `M skipped`가 0보다 크면 사용자에게 건수와 샘플 경로를 보고.
   - 모든 단계 성공 시 글로벌 락 짧게 잡아 `status: "connecting"` → `"ok"`로 전환.
   - `log.md`에 `## [date] connect | <id>` 기록, `connect: <id>` 커밋.
   - **공통 abort 정책 (rollback)**: 위 어느 단계에서든 abort 발생 시 다음 순서로 정리하며, 각 단계는 독립 try/except로 실패해도 다음 단계 진행한다:
     1. **ChromaDB 컬렉션 삭제** (생성됐다면) — 인덱스 orphan 우선 차단.
     2. **`source_type: git` 클론 디렉토리 삭제** (`rm -rf connected-wikis/<id>/`).
     3. **JSON 항목 제거** (글로벌 락 짧게 잡고 atomic write로 reservation/메타 항목 삭제).
     4. **per-wiki 락 파일 정리** (`connected-wikis/.locks/<id>.lock`) — flock 해제는 프로세스 종료 시 OS가 처리, 파일 자체는 삭제.

     사용자에게 abort 사유 + 각 cleanup step 성공/실패를 보고. Rollback은 idempotent (이미 정리된 자원은 no-op).

2. **Toggle** — `"<id> 켜/꺼"` 또는 `"여행 관련만 켜줘"`
   - `connected-wikis.json`의 `enabled` 필드만 갱신 (atomic write + lock)
   - 인덱스 재구축 불필요 (검색 시 enabled+ok wiki만 포함)
   - 런타임 메커니즘(매 Query 시 JSON을 읽어 `--collections`를 동적 구성)의 단일 진실 출처는 D 섹션.
   - `log.md`에 `## [date] toggle | <id> on|off` 기록, `config: toggle <id>` 커밋

3. **Disconnect** — `"<id> 연결 해제"`
   - `<id>`가 `connected-wikis.json`에 없으면 stderr 경고 후 no-op 종료 (에러 아님).
   - **per-wiki 락 선점**: `connected-wikis/.locks/<id>.lock`을 먼저 잡는다 (in-flight Pull과 race 방지). 락 획득 실패 시 사용자에게 "다른 작업 진행 중, 잠시 후 재시도" 안내 후 abort.
   - 사전 점검: `wiki/synthesis/`, `wiki/concepts/`, `wiki/entities/`, `wiki/sources/` 4개 카테고리 전부에서 `(출처: <id>)` / `(source: <id>)` 또는 `connected-wikis/<id>/` 경로 참조를 grep. 발견되면 인터랙션 프로토콜로 사용자에게 보고하고 "출처 끊김" 주석 추가 여부 확인 후 진행.
   - `connected-wikis.json`에서 항목 제거 (atomic write + 글로벌 락). 항목이 사라지면 auto-recover 대상에서 제외됨.
   - 해당 ChromaDB 컬렉션 삭제, `connected-wikis/<id>/` 디렉토리 삭제, per-wiki 락 해제 후 `.locks/<id>.lock` 파일 삭제.
   - `log.md`에 `## [date] disconnect | <id>` 기록, `disconnect: <id>` 커밋.

4. **Pull** — `"연결된 wiki들 업데이트"` (이전 명세상 "Pull-connected")
   - 각 wiki당 `connected-wikis/.locks/<id>.lock`으로 직렬화 (auto-recover clone race 방지). 디렉토리는 `mkdir(parents=True, exist_ok=True)`로 lazy 생성.
   - **default branch 검출**: 각 git wiki당 `git symbolic-ref refs/remotes/origin/HEAD`로 default branch를 식별 (필요 시 `git remote set-head origin --auto`로 갱신 후 재시도). 결과 ref에서 `refs/remotes/origin/` prefix를 제거해 사용. `main`/`master`/임의 이름 모두 지원.
   - `source_type: git`: read-only 미러 가정으로 `git fetch` + `git reset --hard origin/<default-branch>` (force-push divergence·로컬 변경 모두 안전하게 처리). 그 후 `git diff --name-only <stored_commit> HEAD`로 변경 페이지 추출 → `--add` 부분 재인덱싱. `stored_commit` 없거나 ref 누락이면 해당 컬렉션 `--reindex` 폴백. **fetch 실패(접근 불가)**: `enabled` 그대로 두고 `status="unreachable"`만 갱신 (사용자 의도 보존). 임베딩 모델이 `embedding_model` 필드와 다르면 인터랙션 프로토콜(A 섹션)로 (a) 필드만 갱신(빠르지만 점수 비교성 손상) 또는 (b) 해당 컬렉션 재인덱싱 중 선택을 받음. 미응답·기본값은 (b).
   - `source_type: local`: path 부재면 `status="unreachable"` + skip. 존재하면 `wiki/` 하위 파일 mtime이 `last_pulled` 이후 변경된 페이지만 `--add`.
   - **"성공" 정의**: 원격 fetch/local path 접근이 성공한 경우를 의미하며 파일 변경 유무와 무관하다. 파일 변경이 0건이어도 fetch가 성공했다면 `last_pulled`는 갱신된다.
   - **성공 시**: `last_pulled`(현재 시각), `commit`(git만), `embedding_*` 메타 갱신 + 이전이 unreachable이었다면 `status="ok"`로 복구.
   - **커밋·로그 정책**: `connected-wikis.json`에 메타 변경이 1건이라도 발생하면 (`last_pulled`/`commit`/`embedding_*`/`status` 갱신) `log.md` append + `pull:` 커밋 생성. 모든 wiki가 unreachable로만 끝나도 `status` 전환은 메타 변경이므로 커밋 생성됨. 형태: `pull: <N wikis updated>`, 모두 unreachable로 새로 전환된 경우 `pull: 0 fresh updates (M became unreachable)`. **메타 변경 0건**(예: 모든 wiki가 이미 unreachable이고 fetch도 다시 실패해 상태가 그대로)일 때는 `log.md` 추가 없이 사용자에게 요약만 보고하고 종료(no-op).
   - 사용자에게 `<성공 N / 실패 M>` 요약을 보고.

5. **List/Status** — `"연결된 wiki 목록 보여줘"`
   - `connected-wikis.json` + 각 컬렉션의 페이지 수(`ChromaDB count`)를 모아 표로 출력: `id | name | source_type | enabled | status | last_pulled | embedding_model | pages`. 컬렉션이 존재하지 않으면 `pages: N/A`로 표기 (JSON ↔ index drift 가시화, 자동 생성 안 함).
   - **출력 형식**: GitHub-flavored markdown table (헤더 행 + 구분 행 + 데이터 행). 긴 필드는 잘라내지 않음 — 사용자 터미널 너비는 호출자 책임.
   - **Concurrency**: 락을 잡지 않는다. JSON 읽기는 `os.replace` atomic write 덕분에 best-effort로 일관됨. ChromaDB count는 reindex 중이면 transient한 값을 보일 수 있고 이는 허용된다.
   - 함께 출력: 사용 가능한 워크플로우 트리거 예시 (Help/Discovery 역할). 새 사용자가 `id`로 무엇을 할 수 있는지 한 눈에 보이게 한다.
   - 사용자 데이터 변경 없음(커밋·로그 기록 없음). 단, JSON·`.gitignore`이 없으면 Init이 lazy 트리거되어 부트스트랩 커밋이 생성될 수 있음.

> **명시적 거부**: "spain-travel의 X 페이지를 내 wiki로 가져와줘" 같은 외부→로컬 복사 요청은 거부 (Non-goals). 대신 사용자에게 원본 raw source를 직접 ingest하도록 안내한다.

### D. Query 워크플로우 수정

이 hook은 **확장 파일(`extensions/connected-wikis.md`) 내부에 정의**되며, `WIKI_SCHEMA.md`의 Query 워크플로우 본문은 수정하지 않는다 (스키마의 "What Extensions Can Do" 규칙: 확장은 코어 워크플로우 단계에 append 가능). 확장이 로드되지 않으면 기존 단일 코퍼스 동작이 그대로 유지된다.

확장 파일에 다음 hook 텍스트가 캐노니컬 정책으로 포함된다 (B/Risks의 임베딩·머지 정책은 모두 이 정의를 따름):

> **After Query step 1:**
> 1. Read `connected-wikis.json`.
> 2. Filter `wikis[]` to those with `enabled == true && status == "ok"`. Apply per-query overrides if the user said `"<id>로만"` / `"using only <id>"` (whitelist) or `"<id> 빼고"` / `"excluding <id>"` (blacklist) — these do **not** mutate `connected-wikis.json`. If both are present in one utterance: whitelist takes precedence, then the blacklist is applied as a further exclusion on the whitelisted set.
> 3. For each candidate, compare `embedding_backend`/`embedding_model` to the active backend (from `tools/search.py --print-model`, format `backend=<x>\nmodel=<y>`). If they match → include the collection in the unified `--collections wiki,wiki-ext-<id1>,...` query and merge results by score. If they mismatch → run that collection's query separately and present its top hits in a labeled section ("출처 모델 불일치 — 점수 비교 불가"), without merging into the unified ranking. Warn (don't fail).
> 4. Then proceed to Query step 2 with the merged + segregated result set.

확장의 multi-collection 호출은 `tools/search.py`를 직접 사용한다 (B 섹션 `{search.*}` 토큰 처리 규칙).

답변 합성 시 LLM은 다음 출처 표기 규칙을 따른다:

- **인라인 라벨**: 외부 wiki에서 가져온 정보 문장 끝에 `(출처: <wiki-id>)`를 표기. 라벨 텍스트는 `wiki_language` 설정에 맞게 로컬라이즈 (예: en → `(source: <id>)`, ko → `(출처: <id>)`).
- **인용 블록**: 외부 wiki가 1개 이상 사용된 답변에만 끝에 `## Citations` (또는 `wiki_language`에 맞는 로컬라이즈된 제목, 예: ko → `## 인용`) 섹션을 두고 사용된 wiki 페이지 전체 목록을 정리. 로컬 페이지는 wikilink, 외부 페이지는 `connected-wikis/<id>/wiki/...` 경로로 표기 (wikilink로 적지 않음 — B 섹션 정책). `source_type: git`인 외부 페이지는 추가로 원본 repo URL `https://<host>/<owner>/<repo>/blob/<commit>/wiki/...`도 함께 표기 (chat-only 환경에서도 클릭 가능하도록).
- 외부 wiki가 0개 enabled이거나 외부 결과를 인용하지 않은 답변은 기존 Query step 3의 인용 동작을 그대로 따른다.

### E. Extension frontmatter (참고)

```yaml
---
name: connected-wikis
description: Connect external seojae wikis as toggleable extended knowledge sources
min_schema_version: "1.0"
requires:
  provides: [search-backend]
  packages: []
  scripts: [tools/search.py, tools/connected_wikis.py]
---
```

- `provides`는 선언하지 않음 → 새로운 capability를 독점하지 않고 기존 워크플로우를 보강하므로 (스키마 Extensions 가이드라인). 기존 `search-backend`(chromadb)를 **대체하지 않고 보강**한다.
- `commands` 필드는 사용하지 않는다. 스키마의 "Search Command Resolution"은 `{search.*}` 토큰만 resolve하므로, 확장의 신규 CLI는 워크플로우 본문에 명시 경로(`venv/bin/python tools/connected_wikis.py ...`)로 직접 적는다.
- **부트스트랩 순서**: `tools/connected_wikis.py`는 M2에서 생성된다. M3 전까지는 확장 파일을 `extensions/`에 두지 않고 **별도 PR(또는 `docs/`)로 보관**한다. (`extensions/disabled/`는 스키마 loader 동작이 비재귀라는 해석에 의존하므로 더 안전한 기본은 `extensions/` 자체에 두지 않는 것이다.)

---

## Critical Files to Modify / Create

| 종류 | 파일 | 변경 내용 |
|---|---|---|
| 수정 | `tools/search.py` | `COLLECTION_NAME` 상수를 함수 인자로 매개변수화 (기본값 `"wiki"`), CLI에 `--collection`/`--collections` 및 `--print-model` 추가. 인덱싱 시 외부 wiki 메타파일·중첩 `connected-wikis/`는 자동 제외. |
| 수정 | `WIKI_SCHEMA.md` | **(1) Directory Rules 표 행 추가**: `\| connected-wikis/ \| LLM only (clone/pull) \| LLM + User \| None \|` 및 `\| connected-wikis.json \| LLM only \| LLM + User \| None \|`. **(2) log.md actions 목록에 추가**: `connect`, `toggle`, `disconnect`, `pull`, `extension` (Init은 `extension` 액션 사용 — 기존 `init`은 프로젝트 부트스트랩 1회용으로 보존). **(3) Git Commit Conventions 추가**: `extension: enable <name>`, `connect: <id>`, `disconnect: <id>`, `pull: <N wikis updated>`, `config: toggle <id>`. log 액션과 commit prefix는 의도적으로 다름 — 액션은 동작 분류, prefix는 커밋 grep용 이름. **Query 워크플로우 본문은 수정하지 않음** (D 참고). |
| 수정 | `.gitignore` | `connected-wikis/` 추가 (클론본·`.locks/` 포함). 별도로 `connected-wikis.lock`(글로벌 락 사이드카)도 추가. |
| 신규 | `extensions/connected-wikis.md` | 본 확장의 정의 (frontmatter + Setup + Workflows + Configuration). `extensions/README.md`의 필수 섹션(Setup/Workflows/Configuration) 준수. |
| 신규 | `tools/connected_wikis.py` | CLI: `connect`/`toggle`/`disconnect`/`pull`/`list` 서브커맨드. atomic write + `fcntl.flock` (POSIX 전용; A 섹션 락 순서 준수). |
| 신규 | `connected-wikis.json` | 사용자별 연결 상태. 빈 `{"schema_version": 1, "wikis": []}`로 시작, 커밋됨 |
| 신규 | `tests/test_connected_wikis.py` | `tests/test_search.py`의 `_make_collection`/`add_page`/`query_index` 테스트 패턴을 베이스로 두 fixture 추가 필요: (a) 단일 client 내 다중 컬렉션을 만드는 `_make_collection(tmp_path, name)` 헬퍼, (b) `subprocess`로 `git init` 한 임시 repo를 만드는 fake-remote fixture. 단위 테스트는 Verification 항목 전부 커버. |

### 재사용·신규 함수

- `tools/search.py:80 get_collection()` — `name="wiki"` 기본값 인자 추가 (backward-compatible)
- `tools/search.py:89 add_page()` — collection 인자는 이미 받음. 메타파일 가드만 추가
- `tools/search.py:121 reindex()` — `name="wiki"` 기본값 인자 추가, `rglob` 결과에 메타파일 필터
- `tools/search.py:177 query_index()` — **시그니처 변경 없음, byte-identical 유지**
- 신규 `query_indexes(q, top_n, collections: list[Collection], model)` — multi-collection 머지 전용
- 신규 `tools/search.py --print-model` — backend/model 식별 (B 섹션 형식 + 아래 에러 컨트랙트 참고)
- `extensions/search-chromadb.md`의 frontmatter·섹션 구조를 그대로 참고

**`--print-model` 에러 컨트랙트**: exit 0 = 정상 (stdout에 정확히 두 줄 출력). exit 3 = `search-backend` 확장 미활성, stderr에 정확히 다음 메시지: `error: no active search-backend extension. Enable extensions/search-chromadb.md or another search-backend provider.` exit 1 = 기타 오류 (stderr에 원인). Connect/Pull은 비-0 종료 시 즉시 abort하며 stderr 메시지를 사용자에게 그대로 relay. 읽기 시 backfill은 backend 미활성이면 `null` sentinel을 두고 다음 성공 시 재해결.

---

## Implementation Milestones

1. **M1 — 검색 다중 컬렉션화** (`tools/search.py` 리팩터): 단일 책임 변경, 기존 테스트 모두 통과.
2. **M2 — `connected_wikis.py` CLI**: connect/toggle/disconnect/pull/list 구현 + 단위 테스트 (id 검증, atomic write + flock, 마이그레이션 포함).
3. **M3 — `extensions/connected-wikis.md`**: 워크플로우 문서화 (Query hook 텍스트 포함). 동시에 `WIKI_SCHEMA.md`에는 Directory Rules 행, log actions, commit prefixes 추가 (Query 워크플로우 본문은 변경하지 않음).
4. **M4 — End-to-end 검증**: 샘플 외부 wiki repo 1개를 만들어 connect → query → toggle off → query 흐름 수동 테스트.

---

## Verification

- **단위 테스트**: `venv/bin/python -m pytest tests/test_search.py tests/test_connected_wikis.py` — 다중 컬렉션 add/reindex/query 검증.
- **CLI 스모크**:

  ```
  venv/bin/python tools/connected_wikis.py connect <url> --id sample
  venv/bin/python tools/connected_wikis.py toggle sample off
  venv/bin/python tools/search.py --query "테스트" --collections wiki
  venv/bin/python tools/search.py --query "테스트" --collections wiki,wiki-ext-sample
  ```

- **워크플로우 시나리오**: 사용자 발화 "스페인 여행 wiki 연결" → LLM이 워크플로우 따라 실행 → "마드리드 식당" 쿼리에서 외부 wiki 결과 포함되는지 확인.
- **회귀 (정확 동등성)**: `connected-wikis.json`이 `{"schema_version": 1, "wikis": []}`이고 `--collections` 미지정일 때, `query_index`가 정확히 컬렉션 `"wiki"`에 1회만 호출되며 출력 포맷이 본 변경 이전과 byte-identical. 이를 단위 테스트로 assert.
- **컬렉션 격리**: `--reindex --collection wiki-ext-<id>` 실행이 로컬 `wiki` 컬렉션의 page count·content를 byte-identical로 보존하는지 단위 테스트.
- **다국어 회귀**: 한국어 쿼리 vs 영어 인덱싱 외부 컬렉션 조합에서 결과가 (정상 점수로) 반환되는지 smoke 테스트.
- **Frontmatter 견고성**: 외부 wiki에 비표준/누락 frontmatter 페이지가 섞였을 때 `--reindex --collection wiki-ext-<id>`가 skip 카운트를 정확히 보고하고 exit 0으로 종료되는지 확인.
- **임베딩 모델 불일치**: `embedding_model`이 활성 모델과 다른 외부 컬렉션을 enabled로 두고 쿼리 시 (1) warning 메시지 출력 (2) 결과가 unified ranking에 머지되지 않고 별도 섹션으로 분리되는지 assert.
- **Disconnect grep**: `wiki/synthesis/`, `wiki/concepts/`, `wiki/entities/`, `wiki/sources/` 4개 카테고리 전부에서 `(출처: <id>)` / `(source: <id>)` 또는 `connected-wikis/<id>/` 참조가 있을 때 Disconnect가 사전 보고 후 사용자 확인을 요구하는지 검증 (각 카테고리별 케이스 포함).
- **Pull 부분 실패**: 1개 wiki는 정상 pull, 1개는 unreachable일 때 (1) 정상 wiki는 메타 갱신 (2) unreachable wiki는 `enabled` 그대로, `status="unreachable"`로 갱신 (3) 종합 결과 보고 (4) `pull:` 커밋 1회 생성.
- **id 검증**: 예약어(`wiki`, `local`, `ext`, `default`), 형식 위반, 중복 id로 connect 시도가 사용자에게 거부되는지 단위 테스트.
- **JSON 동시성**: 두 프로세스가 동시에 `toggle`을 시도해도 둘 다 atomic write + flock으로 직렬화되어 마지막 상태가 파일에 일관되게 반영되는지 (race 테스트).
- **마이그레이션**: `embedding_*`/`status` 필드 없는 기존 `connected-wikis.json`을 읽어 첫 쓰기 후 모든 필드가 채워지는지 단위 테스트.
- **에러 컨트랙트**: (1) `--print-model`이 비-0 종료할 때 Connect/Pull이 abort하고 사용자에게 명확한 메시지를 출력하는지. (2) Disconnect를 미존재 id로 호출 시 no-op + 경고만 내고 exit 0인지. (3) Connect 시 외부 repo에 `wiki/` 디렉토리·`*.md` 부재 시 `connected-wikis.json` 항목을 만들지 않고 abort하는지.
- **Connect rollback**: reindex 단계에서 의도적으로 실패시켰을 때 (a) JSON 항목이 제거되고 (b) 클론 디렉토리·컬렉션·락 파일이 모두 정리되어 시스템이 Connect 이전 상태와 byte-identical인지 검증.
- **Default branch 검출**: `master` 브랜치만 가진 fake-remote, `main`만 가진 fake-remote, 비표준 이름(`trunk` 등)을 가진 fake-remote 3종에 대해 Pull이 정상 동작하는지 단위 테스트.
- **Two-phase Connect race**: 양쪽 모두 id-validation 시점에 항목이 없는 상태에서 출발하여 (id-validation 단계 통과), 한 쪽이 `status="connecting"` reservation을 선점한 뒤 다른 한 쪽이 reservation 단계에서 충돌로 reject되는지 단위 테스트. `threading.Barrier` 또는 `multiprocessing` + 임의 sleep injection으로 timing을 강제. id-validation 충돌 케이스(이미 `"ok"` 상태 항목 존재)와 별도 분리.
- **인터랙션 프로토콜**: (1) TTY 부재 시 CLI가 stdout `PROMPT:` + `OPTIONS:` + exit 4를 반환하는지 (2) `--decision <key>=<value>` 누적 재호출이 idempotent하게 진행되며 추가 결정이 필요하면 다시 exit 4가 발생하는지 (3) TTY 환경에서는 stdin 폴백이 동작하는지 (4) Connect가 consent + mismatch 둘을 순차로 prompting하는 다중 결정 케이스.
- **선결 조건 검증**: `wiki/`가 없는 디렉토리에서 Init 트리거 시 abort + 안내 메시지 출력하는지 단위 테스트.
- **필드 자동 채움**: Connect 시 `name`(URL/path 자동 유도 + `--name` 오버라이드), `added`(현재 날짜), `embedding_backend`/`embedding_model`이 `connected-wikis.json` 항목에 정확히 채워지는지 단위 테스트.
- **Disconnect 락 선점**: per-wiki 락이 다른 프로세스에 잡혀 있을 때 Disconnect가 abort + 사용자 안내로 종료하고 in-flight Pull이 영향받지 않는지 race 테스트.

---

## Risks & Mitigations

**보안**

- **악의적 콘텐츠/프롬프트 인젝션**: 외부 wiki는 제3자 작성. Connect 시 외부 README/index를 사용자에게 표시하고 인덱싱 동의 확보. 외부 wiki 콘텐츠는 데이터로만 취급 (LLM이 그 안의 명령형 문장을 지시문으로 따르지 않음). 답변 내 외부 출처 문장은 항상 `(출처: <id>)` 인라인 라벨을 시각적으로 구분되게 표기.
- **임베딩 모델 드리프트로 인한 ranking 오염**: 캐노니컬 정책은 D 섹션 (mismatch는 unified ranking에서 분리).

**UX**

- **Wikilink 네임스페이스 충돌**: 동일 파일명이 로컬·외부에 존재할 때 Obsidian shortest-path가 잘못 매핑할 수 있음 → 검색 결과 출력에 `[wiki: <id>]` prefix, 외부 페이지 인용은 반드시 경로 형태(B/D 섹션 정책).
- **Disconnect 후 synthesis 끊김**: 로컬 synthesis 페이지가 외부 wiki를 인용 중일 수 있음 → Disconnect 1단계에서 grep으로 참조를 찾아 보고 + "출처 끊김" 주석 옵션 제공 (C3 워크플로우).
- **외부 source URL 접근 불가 (transient/permanent)**: `enabled`는 보존, `status="unreachable"`만 갱신. Query는 자동 skip + 답변에 명시. Pull 성공 시 `status="ok"`로 복구 (C4).
- **외부 wiki frontmatter 비표준**: regex 파서 skip이 silent하지 않도록 Connect가 `M skipped > 0` 시 사용자에게 보고.

**구현**

- **로컬 경로 stale**: `source_type: local`은 사용자 편집과 race → mtime 기반 부분 재인덱싱 (C4).
- **로컬 경로 비이식성**: 절대경로는 머신별 → Connect/Pull에서 path 검사, 부재면 경고+skip. `connected-wikis.json` 푸시 전 local 항목 검토를 README에 문서화.
- **`connected-wikis.json` 동시 쓰기 + 마이그레이션**: A 섹션 정책 (atomic write + flock + 필드 보강) 위임.
- **`connected-wikis/` 디렉토리 누락**: `.gitignore` 처리 + 자동 클론 복구 (Init·Pull).
