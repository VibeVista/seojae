# Seojae × ir 통합 플랜

## Context

친구가 공유한 `ir-fork`(crate `ir-search`, binary `ir`)는 [qmd](https://github.com/tobi/qmd)의 Rust 포트로, **외부 ollama 데몬을 거치지 않고 llama.cpp(Metal GPU)를 직접 임베드**해 동작하는 로컬 시멘틱 검색 엔진이다. "ollama 백엔드 바이패스"라는 표현은 이 점을 가리킨다.

seojae는 `WIKI_SCHEMA.md`의 search-backend 확장 슬롯을 통해 검색 백엔드를 교체할 수 있는 구조다. 현재는 `extensions/search-chromadb.md`(`provides: search-backend`)가 ChromaDB + sentence-transformers로 이 슬롯을 점유하고 있고, 워크플로(Ingest/Query/Lint/Reindex)는 `{search.query}`, `{search.add}`, `{search.reindex}` 토큰으로 추상화돼 있다.

**목표**: `ir`을 빌드해 seojae의 search-backend로 끼워 넣어, 기존 워크플로(Ingest/Query/Lint)가 그대로 ir 위에서 돌도록 만든다. ChromaDB 백엔드는 새 확장이 `overrides`로 비활성화한다. 부수적으로 Claude Code의 도구로 직접 검색하고 싶다면 `ir mcp`를 `.mcp.json`에 등록한다.

## 권장 접근 — CLI 확장 + (선택) MCP

ir의 CLI 표면이 seojae가 요구하는 세 동사(query/add/reindex)와 거의 1:1로 맞는다. 새 확장 `extensions/search-ir.md`를 한 장 추가하고 `overrides: search-chromadb`을 선언해 슬롯을 가져오는 방식이 가장 깔끔하다 — seojae 코어 워크플로를 한 줄도 건드리지 않는다.

### 매핑 표

| seojae 토큰 | ir 명령 | 비고 |
|---|---|---|
| `{search.reindex}` | `ir update seojae-wiki --force && ir embed seojae-wiki --force` | BM25 + 벡터 재구축 |
| `{search.add} <path>` | `ir update seojae-wiki` | ir은 per-file add가 없음. 컬렉션 단위 incremental 스캔(SHA-256 해시 비교)이라 단일 파일만 변했어도 ms 단위로 끝남. 그 뒤 `ir embed seojae-wiki`로 변경분만 재임베딩 |
| `{search.query} "<q>" --top 5` | `ir search "<q>" -c seojae-wiki --limit 5 --json` | seojae가 기대하는 `<path> [score: X.XX]` 포맷은 jq 한 줄로 변환 |

### 출력 포맷 어댑터

ir 기본 출력은 `<score> <doc_id> <path>` 순서라 seojae 파서와 다르다. `--json`을 받아 jq로 변환:

```bash
ir search "$Q" -c seojae-wiki --limit "${TOP:-5}" --json --quiet \
  | jq -r '.[] | "\(.path) [score: \(.score)]"'
```

ir 점수는 코사인 유사도 0–1 범위라 seojae의 0.5 fallback 임계값(`WIKI_SCHEMA.md` Query 워크플로 step 1)과 그대로 호환된다.

### 종료 코드 매핑

| seojae 약속 | ir 동작 |
|---|---|
| 0 = 성공 | `ir search`/`update`/`embed` 정상 종료 |
| 1 = 일반 오류 | ir도 동일 |
| 2 = 인덱스 없음 | ir은 컬렉션 미등록 시 1을 던진다 → 래퍼에서 `ir collection ls`로 존재 확인 후 없으면 `exit 2` |

## 파일 변경 / 생성

### 생성: `extensions/search-ir.md`

골격 (실행자가 채울 부분 명시):

```markdown
---
name: search-ir
description: Local hybrid BM25 + vector search via ir (Rust, llama.cpp-backed)
provides: search-backend
overrides: search-chromadb
requires:
  scripts: [tools/ir-search.sh]
commands:
  query:   "tools/ir-search.sh query"
  add:     "tools/ir-search.sh add"
  reindex: "tools/ir-search.sh reindex"
---

## Setup
1. ir 바이너리 설치: `cd ~/Documents/personal/ir-fork && cargo install --path .`
2. 컬렉션 등록: `ir collection add seojae-wiki ~/Documents/personal/seojae/wiki`
3. ko 프리프로세서: `ir preprocessor install ko && ir preprocessor bind ko seojae-wiki`
4. 초기 인덱싱: `ir update seojae-wiki && ir embed seojae-wiki`

## Workflows
이 확장은 search-chromadb를 대체한다. 워크플로 토큰만 교체되고 `WIKI_SCHEMA.md`
는 변경하지 않는다.

## Configuration
| Option | 기본값 | 비고 |
|---|---|---|
| Collection name | `seojae-wiki` | `IR_COLLECTION` 환경변수로 오버라이드 |
| Top-K | 5 | `--top` 인자로 전달 |
```

### 생성: `tools/ir-search.sh`

핵심 로직 — query/add/reindex 세 서브커맨드. 종료 코드 규약 보존, JSON→seojae 포맷 변환, 컬렉션 미존재 시 코드 2 반환. 실행 권한 부여(`chmod +x`).

### 변경: `CLAUDE.md` (선택)

기존 `CLAUDE.md`는 `@extensions/search-chromadb.md`를 참조하고 있다(WIKI_SCHEMA에 예시로 적힌 패턴). 실제로 그렇게 적혀 있는지 확인하고, 적혀 있다면 `@extensions/search-ir.md`로 교체. 안 적혀 있으면 변경 불필요(확장 로딩 규칙은 디렉터리 스캔 기반이라 자동 인식).

### 비활성화: `extensions/search-chromadb.md`

같은 `provides: search-backend`라도 `search-ir`이 `overrides: search-chromadb`를 선언하면 seojae 로딩 규칙(WIKI_SCHEMA `Loading Rules` §2)에 의해 자동으로 비활성화된다. 파일 자체는 보존해도 무방.

## ir 설치 (이 fork 소스 빌드)

```bash
cd /Users/laeyoung/Documents/personal/ir-fork
cargo install --path .          # ~/.cargo/bin/ir 에 설치
ir --version                    # 검증 (예상: ir-search 0.14.1)
```

Rust 1.80+ 필요. macOS는 Metal 자동 링크. 이 fork에 친구가 적용한 로컬 패치/실험 코드가 그대로 빌드된다.

## 한국어 프리프로세서 (lindera ko) 포함

```bash
ir preprocessor install ko          # 공식 lindera CLI + ko-dic 다운로드 (HF 없이 GitHub releases)
ir preprocessor bind ko seojae-wiki # 자동 재인덱싱
```

바인딩 시 `routing.fused_strong_product = 0.05` 한국어 기본값이 컬렉션 config에 자동 기록됨. 벤치 근거: MIRACL-Korean BM25 단독 nDCG@10 0.0009 → 0.0460 (50× 개선), 하이브리드+rerank 0.8411 (`ir-fork/research/experiment.md`).

## MCP 등록

`seojae/.mcp.json`(없으면 생성):

```json
{
  "mcpServers": {
    "ir": { "command": "ir", "args": ["mcp"] }
  }
}
```

5개 툴 노출: `search`, `get`, `multi_get`, `status`, `update`. 데몬은 첫 호출 시 자동 기동. CLI 확장과 MCP는 독립 — 같은 컬렉션·같은 데몬을 공유하니 충돌 없음.

## 검증 (end-to-end)

1. **ir 단독 동작**:
   ```bash
   ir collection add seojae-wiki ~/Documents/personal/seojae/wiki
   ir update seojae-wiki && ir embed seojae-wiki
   ir search "seojae 위키 구조" -c seojae-wiki --limit 3
   ```
   결과 3건이 출력되면 OK.

2. **확장 어댑터 동작**:
   ```bash
   cd ~/Documents/personal/seojae
   tools/ir-search.sh query "위키 구조" 3
   ```
   `<path> [score: 0.xx]` 포맷 3줄 출력 확인.

3. **워크플로 통합**: Claude Code에서 seojae 디렉터리를 열고 *"위키에 대해 X를 질문해"* — Query 워크플로가 `tools/ir-search.sh query`를 호출하고 결과를 합성하는지 로그로 확인.

4. **Reindex 검증**: `tools/ir-search.sh reindex` → `ir status`로 doc count·embedding 수 확인.

## 위험·롤백

- **ChromaDB 인덱스 잔존**: `seojae/search-index/`는 그대로 둬도 `search-ir`이 슬롯을 차지하면 무시된다. 디스크 회수하려면 디렉터리 삭제(gitignored).
- **롤백**: `extensions/search-ir.md` 삭제만 하면 자동으로 `search-chromadb`가 다시 활성화된다 — 코드 변경 없음.
- **모델 다운로드(첫 실행)**: EmbeddingGemma 300M ~470MB이 HF Hub에서 받아져 `~/.cache/huggingface/`에 캐시. 오프라인 환경이면 `IR_EMBEDDING_MODEL` 환경변수로 로컬 GGUF 지정.

## 참고 파일 (이 플랜이 의존)

- `seojae/WIKI_SCHEMA.md` (Loading Rules, Search Command Resolution, Query 워크플로 step 1)
- `seojae/extensions/search-chromadb.md` (계약 레퍼런스)
- `ir-fork/README.md` (CLI / 모델 / 한국어 프리프로세서 절)
- `ir-fork/CLAUDE.md` (env vars, gotchas)
- `ir-fork/src/cli/output.rs` (출력 포맷 — `--json` 스키마)
