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

### 확정된 설계 결정

1. **전송 방식**: `git` 공개 URL 클론 + 로컬 디렉토리 경로 둘 다 지원.
2. **저장 위치**: `connected-wikis/`를 repo 안에 두고 `.gitignore`에 추가 (`connected-wikis.json`만 커밋해 사용자 머신 간 구성 공유).
3. **토글 단위**: wiki 전체 단위 on/off.
4. **출처 표기**: 답변 본문에 인라인 라벨 `(출처: <wiki-id>)` + 답변 끝에 통합 인용 블록.

---

## User Stories

1. "친구가 운영하는 스페인 여행 wiki를 연결해줘. URL은 `https://github.com/friend/spain-travel-wiki`."
   → LLM이 `connected-wikis.json`에 항목 추가, 로컬에 클론, 인덱싱하고 enabled=true로 등록.
2. "지금부터 일본 요리 wiki는 끄고 한식 wiki만 켜줘."
   → LLM이 config의 `enabled` 플래그만 토글.
3. "마드리드에서 가족 식사로 좋은 곳 추천해줘."
   → LLM이 활성화된 wiki들을 검색, 결과에 출처(로컬 vs 친구의 spain-travel)를 명시해 답변.
4. "연결된 wiki들 최신 상태로 업데이트해줘."
   → LLM이 각 wiki에 `git pull`, 변경된 페이지만 재인덱싱.

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
  "wikis": [
    {
      "id": "spain-travel",
      "name": "Friend's Spain Travel Wiki",
      "source_type": "git",
      "source": "https://github.com/friend/spain-travel-wiki",
      "enabled": true,
      "added": "2026-04-28",
      "last_pulled": "2026-04-28",
      "commit": "abc1234"
    },
    {
      "id": "japanese-cooking",
      "name": "My Local JP Cooking Notes",
      "source_type": "local",
      "source": "/Users/me/other-seojae",
      "enabled": false,
      "added": "2026-04-28"
    }
  ]
}
```

- `source_type: git` → `connected-wikis/<id>/`로 클론, `pull-connected` 시 `git pull`.
- `source_type: local` → 클론 생략, 인덱싱 시 `<source>/wiki`를 직접 스캔.

### B. 검색 (multi-corpus)

`tools/search.py`를 다음과 같이 확장:

- ChromaDB 컬렉션을 `wiki`(로컬) 외에 `wiki-ext-<id>` 형태로 wiki당 1개씩 운영.
- 신규 CLI 옵션: `--collections wiki,wiki-ext-spain-travel,...` — 동시에 여러 컬렉션을 쿼리하고 결과를 점수로 머지.
- 결과 출력 시 각 라인에 `[wiki: <id>]`를 붙여 출처를 표시.

  ```
  wiki/concepts/vibe-coding.md [wiki: local] [score: 0.82]
  connected-wikis/spain-travel/wiki/sources/madrid-restaurants.md [wiki: spain-travel] [score: 0.78]
  ```

- 인덱싱: `add_page`/`reindex`에 `--collection <name>` 옵션 추가, wiki별로 격리.

핵심 리팩터: **`COLLECTION_NAME` 상수를 함수 인자로 매개변수화**하고, `get_collection()`/`reindex()`/`add_page()`/`query_index()`에 collection name을 인자로 받도록 변경 (`tools/search.py:12, 80, 89, 121, 177`).

### C. 신규 워크플로우 (extension에서 정의)

`extensions/connected-wikis.md`가 다음 4개 워크플로우를 추가:

1. **Connect** — `"<repo-url-or-path>을 <id>로 연결해줘"`
   - source가 git URL이면 `git clone <url> connected-wikis/<id>`, 로컬 경로면 클론 생략
   - `connected-wikis.json`에 항목 추가 (`source_type: git|local`, enabled=true)
   - `tools/search.py --reindex --wiki-path <wiki-path> --collection wiki-ext-<id>`
     (git이면 `connected-wikis/<id>/wiki`, local이면 `<source>/wiki`)
   - `log.md`에 `## [date] connect | <id>` 기록, `connected-wikis.json` 커밋

2. **Toggle** — `"<id> 켜/꺼"` 또는 `"여행 관련만 켜줘"`
   - `connected-wikis.json`의 `enabled` 필드만 갱신
   - 인덱스 재구축 불필요 (검색 시 enabled 컬렉션만 포함)
   - `log.md` 기록 (커밋 옵션)

3. **Disconnect** — `"<id> 연결 해제"`
   - `connected-wikis.json`에서 항목 제거
   - 해당 ChromaDB 컬렉션 삭제, `connected-wikis/<id>/` 디렉토리 삭제
   - `log.md` 기록, 커밋

4. **Pull-connected** — `"연결된 wiki들 업데이트"`
   - `source_type: git`인 wiki에만 `git pull`, `source_type: local`은 스킵(파일 시스템 그대로 사용)
   - 변경된 페이지만 `--add`로 재인덱싱 (또는 변경량 많으면 해당 컬렉션만 `--reindex`)
   - `last_pulled`, `commit` 메타 갱신

### D. Query 워크플로우 수정

`WIKI_SCHEMA.md`의 Query step 1을 확장이 보강:

> **After Query step 1:** Read `connected-wikis.json`. For each `enabled: true` wiki, also run `{search.query}` against its collection. Merge by score, then proceed to step 2.

답변 합성 시 LLM은 다음 출처 표기 규칙을 따른다:

- **인라인 라벨**: 외부 wiki에서 가져온 정보 문장 끝에 `(출처: <wiki-id>)`를 표기.
- **인용 블록**: 답변 끝에 `## 인용` 섹션을 두고 사용된 wiki 페이지 전체 목록 (로컬+외부)을 wikilink/경로와 함께 정리.

### E. Extension frontmatter (참고)

```yaml
---
name: connected-wikis
description: Connect external seojae wikis as toggleable extended knowledge sources
requires:
  provides: [search-backend]
  packages: []
  scripts: [tools/search.py, tools/connected_wikis.py]
commands:
  connect: "venv/bin/python tools/connected_wikis.py connect"
  toggle: "venv/bin/python tools/connected_wikis.py toggle"
  disconnect: "venv/bin/python tools/connected_wikis.py disconnect"
  pull: "venv/bin/python tools/connected_wikis.py pull"
---
```

`provides`는 선언하지 않음 → 기존 `search-backend`(chromadb)를 **대체하지 않고 보강**한다.

---

## Critical Files to Modify / Create

| 종류 | 파일 | 변경 내용 |
|---|---|---|
| 수정 | `tools/search.py` | `COLLECTION_NAME` 상수를 함수 인자로 매개변수화, CLI에 `--collection`/`--collections` 추가 |
| 수정 | `WIKI_SCHEMA.md` | Query 워크플로우에 "활성 외부 wiki 검색" 단계 hook 명시, 디렉토리 규칙 표에 `connected-wikis/` 추가 |
| 수정 | `.gitignore` | `connected-wikis/` 추가 (클론본은 커밋하지 않음) |
| 신규 | `extensions/connected-wikis.md` | 본 확장의 정의 (frontmatter + Setup + Workflows + Configuration) |
| 신규 | `tools/connected_wikis.py` | CLI: `connect`/`toggle`/`disconnect`/`pull` 서브커맨드 |
| 신규 | `connected-wikis.json` | 사용자별 연결 상태 (빈 `{"wikis": []}`로 시작, 커밋됨) |
| 신규 | `tests/test_connected_wikis.py` | `tests/test_search.py` 패턴(라인 139-200) 따라 단위 테스트 |

### 재사용할 기존 함수

- `tools/search.py:80 get_collection()` — collection name을 인자로 받도록 시그니처만 확장
- `tools/search.py:89 add_page()` — 동일하게 collection 인자화
- `tools/search.py:121 reindex()` — `wiki_path`/`collection_name` 둘 다 받도록
- `tools/search.py:177 query_index()` — multi-collection 지원: 컬렉션 리스트 받아 각각 쿼리 후 score로 머지
- `extensions/search-chromadb.md`의 frontmatter·섹션 구조를 그대로 참고

---

## Implementation Milestones

1. **M1 — 검색 다중 컬렉션화** (`tools/search.py` 리팩터): 단일 책임 변경, 기존 테스트 모두 통과.
2. **M2 — `connected_wikis.py` CLI**: connect/toggle/disconnect/pull 구현 + 단위 테스트.
3. **M3 — `extensions/connected-wikis.md`**: 워크플로우 문서화, `WIKI_SCHEMA.md` Query 훅 추가.
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
- **회귀**: 외부 wiki가 0개일 때 기존 단일 코퍼스 동작과 출력이 동일한지(score, ranking) 확인.

---

## Risks & Mitigations

- **외부 wiki의 악의적 콘텐츠/프롬프트 인젝션**: 외부 wiki는 제3자 작성. Connect 시 사용자에게 "검토 필요" 경고 표시(extension README의 보안 주석 패턴 참고).
- **로컬 경로 wiki의 파일 변경**: `source_type: local`은 사용자가 동시에 편집 중일 수 있어 인덱스가 stale해질 수 있음 → `pull-connected`에서 mtime 기반 변경 감지로 부분 재인덱싱.
- **id 충돌**: 동일 페이지 파일명이 로컬·외부에 존재할 때 wikilink가 모호해짐 → 검색 결과 출력에 항상 collection prefix를 붙여 LLM이 구분하도록.
- **`connected-wikis/` 디렉토리 누락**: `.gitignore` 처리되어 새 머신에는 없음 → `connect`/`pull-connected` 실행 시 자동 생성하고, `connected-wikis.json`에 목록은 있지만 디렉토리 없는 wiki는 `pull-connected`가 자동 클론 복구.
