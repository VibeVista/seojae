# Seojae × ir 통합 플랜

## Context

친구가 공유한 `ir-fork`(crate `ir-search`, binary `ir`)는 [qmd](https://github.com/tobi/qmd)의 Rust 포트로, **외부 ollama 데몬을 거치지 않고 llama.cpp(Metal GPU)를 직접 임베드**해 동작하는 로컬 시멘틱 검색 엔진이다. "ollama 백엔드 바이패스"라는 표현은 이 점을 가리킨다.

seojae는 `WIKI_SCHEMA.md`의 search-backend 확장 슬롯을 통해 검색 백엔드를 교체할 수 있는 구조다. 현재는 `extensions/search-chromadb.md`(`provides: search-backend`)가 ChromaDB + sentence-transformers로 이 슬롯을 점유하고 있고, 워크플로(Ingest/Query/Lint/Reindex)는 `{search.query}`, `{search.add}`, `{search.reindex}` 토큰으로 추상화돼 있다.

**목표**: `ir`을 빌드해 seojae의 search-backend로 끼워 넣어, 기존 워크플로(Ingest/Query/Lint)가 그대로 ir 위에서 돌도록 만든다. ChromaDB 백엔드는 새 확장이 `overrides`로 비활성화한다. Claude Code 도구로 직접 검색하기 위해 `ir mcp`도 `.mcp.json`에 등록한다.

## TL;DR (실행 순서 5단계)

1. `cd ~/Documents/personal/ir-fork && cargo install --path .` (5–15분 소요, 첫 빌드 시 llama.cpp 컴파일)
2. `ir collection add seojae-wiki ~/Documents/personal/seojae/wiki` 후 `ir preprocessor install ko && ir preprocessor bind ko seojae-wiki`
3. `ir update seojae-wiki && ir embed seojae-wiki` (첫 embed는 ~470MB 모델 다운로드 + 수십 초 멈춤; 빈 `wiki/`도 정상 — `ir status`에 doc=0으로 표시됨)
4. `extensions/search-ir.md` + `tools/ir-search.sh` 작성, `chmod +x tools/ir-search.sh`
5. `.mcp.json` 절대 경로로 작성 + Claude Code 재시작 → MCP 도구 5개 노출 확인

## 권장 접근 — CLI 확장 + MCP

ir의 CLI 표면이 seojae가 요구하는 세 동사(query/add/reindex)와 거의 1:1로 맞는다. 새 확장 `extensions/search-ir.md`를 한 장 추가하고 `overrides: search-chromadb`을 선언해 슬롯을 가져오는 방식이 가장 깔끔하다 — seojae 코어 워크플로를 한 줄도 건드리지 않는다.

### 매핑 표

| seojae 토큰 | ir 명령 | 비고 |
|---|---|---|
| `{search.reindex}` | `ir update seojae-wiki --force && ir embed seojae-wiki --force` | BM25 + 벡터 재구축. 비원자적 — `embed` 실패 시 `ir embed seojae-wiki --force`만 재실행 (`update`는 다시 안 해도 됨). 컬렉션 미등록 시 ir이 exit 1 + "collection not found"; 래퍼가 코드 2로 매핑해 seojae가 fallback 모드로 진입하도록 한다. |
| `{search.add} <path>` | `ir update seojae-wiki && ir embed seojae-wiki` | ir은 per-file add가 없음. 컬렉션 단위 incremental 스캔(SHA-256 해시 비교)이라 변경분만 처리. 단, Ingest 워크플로가 페이지마다 호출하면 매번 update→embed 사이클이 돈다. 데몬이 따뜻하면 ms 단위지만, 세션 첫 호출은 임베더 cold load로 ≤3s 대기 (1회성). 래퍼는 path 인자를 받지만 무시하고 컬렉션 전체를 스캔한다(SHA-256 해시 기반 incremental이라 무해). |
| `{search.query} "<q>" --top 5` | `ir search "<q>" -c seojae-wiki --limit 5 --json --quiet` | jq로 `<path> [score: X.XX]` 변환. ir CLI는 `--top` 대신 `--limit`/`-n` 사용 (`src/cli/mod.rs:41`). |

### 출력 포맷 어댑터

ir 기본 출력은 `<score> <doc_id> <path>` 순서라 seojae 파서와 다르다. `--json`을 받아 jq로 path/score를 추출한 뒤 `awk printf %.2f`로 정확히 소수점 2자리로 포맷한다 — jq의 산술 결과는 trailing zero를 떨어뜨려 `0.90`이 `0.9`로 출력되는 문제를 회피:

```bash
ir search "$Q" -c seojae-wiki --limit "${TOP:-5}" --json --quiet \
  | jq -r '.[] | "\(.path)\t\(.score)"' \
  | awk -F'\t' '{ printf "%s [score: %.2f]\n", $1, $2 }'
```

기존 `tools/search.py:234`의 `{path} [score: {score:.2f}]`와 정확히 동일한 포맷.

ir의 최종 `SearchResult.score`는 코사인 유사도/리랭커 출력 모두 0–1로 정규화된다 (`src/db/vectors.rs:119` `score = 1.0 - distance`, 리랭커는 softmax). seojae의 0.5 fallback 임계값(`WIKI_SCHEMA.md` Query 워크플로 step 1, line 202)과 그대로 호환된다.

### 종료 코드 매핑

ir의 `main.rs:44-48`은 모든 에러 경로를 일률 `exit(1)`로 처리한다. 컬렉션 미존재를 별도로 구분하지 않으므로 래퍼가 사전 검사로 코드 2를 분기한다.

| seojae 약속 | ir 동작 |
|---|---|
| 0 = 성공 | `ir search`/`update`/`embed` 정상 종료 |
| 1 = 일반 오류 | ir도 동일 (모든 에러 1) |
| 2 = 인덱스 없음 (fallback to `index.md`) | 래퍼가 `ir collection ls`로 존재 확인 후 없으면 `exit 2` |

## 파일 변경 / 생성

> **순서 주의**: 아래 파일들을 만들기 전에 §"ir 설치"와 §"한국어 프리프로세서" 섹션을 먼저 실행해 `ir` 바이너리가 PATH에 있고 `seojae-wiki` 컬렉션이 등록된 상태여야 한다. 사전 검사가 안 되면 wrapper의 `command -v ir` / `ir collection ls` 체크가 exit 1/2로 떨어지며 첫 워크플로 실행이 실패한다.

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

핵심 로직 — query/add/reindex 세 서브커맨드. 실행 권한 부여(`chmod +x`). gitignore 비대상이므로 git에 커밋한다. 다음 사양을 반드시 만족시킨다:

```bash
#!/usr/bin/env bash
set -euo pipefail

# 0. 의존성 사전 검사
command -v ir >/dev/null 2>&1 || { echo "ir not found in PATH (cargo install --path . in ir-fork)" >&2; exit 1; }
command -v jq >/dev/null 2>&1 || { echo "jq required (brew install jq)" >&2; exit 1; }

COLLECTION="${IR_COLLECTION:-seojae-wiki}"
SUBCMD="${1:-}"; shift || true

# 1. 컬렉션 존재 검사 → 없으면 exit 2 (seojae fallback 신호)
# `ir collection ls` 출력은 고정폭 패딩 포맷 (`{name:<20} {path}`); awk로 첫 토큰 추출.
# grep은 -F(고정 문자열) 필수: 컬렉션 이름에 정규식 메타문자(. * 등) 포함 시 false-positive 방지.
ir collection ls 2>/dev/null | awk '{print $1}' | grep -Fqx "$COLLECTION" \
  || { echo "collection '$COLLECTION' not registered — run setup" >&2; exit 2; }

case "$SUBCMD" in
  query)
    # seojae 호출 형태: tools/ir-search.sh query "<q>" --top N
    # --top N 플래그 형태와 위치형(3) 둘 다 수용
    Q="${1:?query string required}"; shift || true
    TOP=5
    while [ "$#" -gt 0 ]; do  # POSIX (bash 3.2 호환); (( $# ))은 set -e와 결합 시 마지막 iter에서 조기 종료 가능
      case "$1" in
        --top) TOP="${2:?--top needs value}"; shift 2;;
        --top=*) TOP="${1#--top=}"; shift;;
        [0-9]*) TOP="$1"; shift;;
        *) shift;;
      esac
    done
    # ir 진행 로그는 stderr로 보내고 stdout은 포맷된 결과만 — seojae 파서가 stdout만 본다
    # 빈 결과는 `[]` JSON → jq 무출력 → seojae가 fallback 모드로 진입 (계약대로)
    ir search "$Q" -c "$COLLECTION" --limit "$TOP" --json --quiet \
      | jq -r '.[] | "\(.path)\t\(.score)"' \
      | awk -F'\t' '{ printf "%s [score: %.2f]\n", $1, $2 }'
    ;;
  add)
    # seojae가 path 인자를 넘기지만 무시: ir은 컬렉션 단위 incremental 스캔
    ir update "$COLLECTION" >&2
    ir embed "$COLLECTION" >&2
    ;;
  reindex)
    ir update "$COLLECTION" --force >&2
    ir embed "$COLLECTION" --force >&2
    ;;
  *)
    echo "usage: $0 {query|add|reindex} ..." >&2
    exit 1
    ;;
esac
```

핵심 설계 결정:
- `set -euo pipefail`로 부분 실패 은폐 방지 (`update` 실패 시 `embed`까지 가지 않도록). ir의 `update`/`embed`는 all-or-nothing — 한 파일 실패 시 전체 exit 1, 부분 인덱싱 없음.
- `IR_COLLECTION` 환경변수로 컬렉션 이름 오버라이드 가능 (기본 `seojae-wiki`)
- query는 `--top N` 플래그 형태와 위치형 둘 다 수용 (WIKI_SCHEMA Query 워크플로는 `--top 5`, 검증 단계에서는 `tools/ir-search.sh query "X" 3` 위치형 호출 모두 동작)
- ir 진행 출력은 stderr로 — stdout은 깨끗하게 `<path> [score: X.XX]`만
- 점수 포맷은 `printf %.2f`로 통일 — jq 단독으로는 `0.9` ≠ `0.90` trailing-zero 손실
- `grep -Fqx` 고정 문자열 매칭으로 정규식 메타문자(`.`, `*` 등)가 포함된 컬렉션 이름 false-positive 차단
- 컬렉션 이름은 공백 없이 사용 (포맷이 `{:<20} {path}` — `{:<20}`은 좌측 정렬 + 우측 공백 패딩이고 그 뒤에 literal space가 추가돼 name과 path 사이에 항상 1자 이상의 공백이 보장됨. awk 첫-토큰 추출은 이로써 안전. 단, 이름 자체에 공백이 들어가면 깨짐 — `seojae-wiki`처럼 하이픈/언더스코어 사용).

### 변경: `CLAUDE.md` — 변경 없음

실측: 현재 `seojae/CLAUDE.md`는 `@WIKI_SCHEMA.md` 한 줄만 참조하고 search 확장은 직접 참조하지 않는다. 확장 로딩은 `extensions/` 디렉터리 스캔 기반(WIKI_SCHEMA Loading Rules §1)이라 새 `search-ir.md`는 자동으로 인식되고 `search-chromadb.md`는 `overrides`로 비활성화된다. CLAUDE.md 수정 불필요.

### 비활성화: `extensions/search-chromadb.md`

같은 `provides: search-backend`라도 `search-ir`이 `overrides: search-chromadb`를 선언하면 seojae 로딩 규칙(WIKI_SCHEMA `Loading Rules` §2)에 의해 자동으로 비활성화된다. 파일 자체는 보존해도 무방.

## ir 설치 (이 fork 소스 빌드)

```bash
cd /Users/laeyoung/Documents/personal/ir-fork
cargo install --path .             # ~/.cargo/bin/ir 에 설치 (첫 빌드 5–15분; llama.cpp 컴파일)
ir daemon stop 2>/dev/null || true # 이전 빌드의 데몬 종료 (ir-fork CLAUDE.md 알려진 함정)
ir --version                       # 검증 (예상: `ir 0.14.1` — clap이 binary name 사용)
```

Rust 1.80+ 필요. macOS는 기본 피처(`llama-metal` + `llama-openmp`)가 Intel/Apple Silicon 모두에서 동작 — 별도 조정 불필요. **Linux**는 Metal이 없으므로 `cargo install --path . --no-default-features --features llama-openmp`로 빌드하고 llama-cpp-2 빌드 시 시스템 BLAS(OpenBLAS/MKL) 자동 감지에 의존(불확실하면 `apt install libopenblas-dev` 후 재빌드). 사용 가능한 피처는 `ir-fork/Cargo.toml` `[features]` 섹션 참조.

이 fork에 친구가 적용한 로컬 패치/실험 코드가 그대로 빌드된다.

> **PATH 주의**: `cargo install`은 `~/.cargo/bin/ir`에 설치한다. 셸 PATH에 `~/.cargo/bin`이 없으면 Claude Code의 MCP 등록(아래)이 *조용히* 실패한다. 확인: `which ir`. 없으면 `~/.zshrc`에 `export PATH="$HOME/.cargo/bin:$PATH"` 추가 후 Claude Code 재시작.

> **데몬 재기동 규칙**: ir 바이너리를 재빌드한 뒤에는 반드시 `ir daemon stop` — `ir search`는 자동 재기동이 *없다*. 재빌드 후 옛 데몬이 옛 모델·옛 라우팅으로 응답하는 사일런트 버그가 발생한다 (ir-fork/CLAUDE.md "Known Gotchas").

## 한국어 프리프로세서 (lindera ko) 포함

```bash
ir preprocessor install ko          # 공식 lindera CLI + ko-dic 다운로드 (HF 없이 GitHub releases)
ir preprocessor bind ko seojae-wiki # 자동 재인덱싱
```

바인딩 시 `routing.fused_strong_product = 0.05` 한국어 기본값이 컬렉션 config에 자동 기록됨. 벤치 근거: MIRACL-Korean BM25 단독 nDCG@10 0.0009 → 0.0460 (50× 개선), 하이브리드+rerank 0.8411 (`ir-fork/research/experiment.md`).

## MCP 등록

`seojae/.mcp.json`(없으면 생성). **PATH 이슈 회피를 위해 절대 경로 사용**:

```json
{
  "mcpServers": {
    "ir": {
      "command": "/Users/laeyoung/.cargo/bin/ir",
      "args": ["mcp"]
    }
  }
}
```

`"command": "ir"`만 쓰면 Claude Code가 GUI에서 기동된 경우 `~/.cargo/bin`이 PATH에 없을 수 있어 "command not found"로 *조용히* 실패한다. macOS Finder/Spotlight 시작 시 흔한 함정.

**.gitignore에 `.mcp.json` 추가**: 절대 경로가 박혀 있어 다른 머신에서는 깨진다. 머신-로컬 설정으로 취급한다.

5개 툴 노출: `search`, `get`, `multi_get`, `status`, `update`. 데몬은 첫 호출 시 자동 기동. CLI 확장과 MCP는 독립 — 같은 컬렉션·같은 데몬을 공유하니 충돌 없음.

## 검증 (end-to-end)

1. **ir 단독 동작**:
   ```bash
   ir collection add seojae-wiki ~/Documents/personal/seojae/wiki
   ir update seojae-wiki && ir embed seojae-wiki
   ir search "seojae 위키 구조" -c seojae-wiki --limit 3
   ir status                       # doc count, embedding 수, 데몬 상태 baseline
   ```
   결과 3건이 출력되고 status에 `seojae-wiki` 항목이 보이면 OK.

2. **확장 어댑터 동작**:
   ```bash
   cd ~/Documents/personal/seojae
   tools/ir-search.sh query "위키 구조" --top 3   # 플래그 형태
   tools/ir-search.sh query "위키 구조" 3         # 위치 형태
   ```
   둘 다 `<path> [score: 0.xx]` (소수점 정확히 2자리) 3줄 출력 확인. `tools/ir-search.sh query "" --top 3` 실행 시 `set -e`로 코드 1 종료.

3. **컬렉션 미존재 시 fallback 신호**:
   ```bash
   IR_COLLECTION=does-not-exist tools/ir-search.sh query "x"; echo "exit=$?"
   ```
   `exit=2` 출력 확인 → seojae가 `index.md` fallback으로 분기하는 신호.

4. **워크플로 통합**: Claude Code를 seojae 디렉터리에서 열고 다음 두 trigger를 시도:
   - Query 워크플로: *"위키에서 attention mechanism 관련 페이지를 찾아줘"*
   - Ingest 워크플로: *"raw/articles/foo.md를 ingest해"* (실제 파일 필요)

   **구체적 success signal**: 도구 호출 로그에 `tools/ir-search.sh query` 라인이 보여야 함. `tools/search.py`(chromadb)가 호출되거나 `index.md` 직접 스캔이 나타나면 확장 로딩이 실패한 것 — `provides`/`overrides` 프론트매터를 다시 확인. 추가로 wrapper 디버그 출력을 잠시 활성화하려면 wrapper의 `query)` 케이스 시작 부분(`Q="${1:?...}"` 직후)에 `echo "[ir-search] q=$Q top=$TOP coll=$COLLECTION" >&2` 한 줄 임시 삽입.

5. **Reindex 검증**: `tools/ir-search.sh reindex` → `ir status`로 doc count·embedding 수 비교 (전후 동일해야 정상). 재실행 시 `embed`만 재시도되는지 확인 (`ir update --force`는 빠르고, `ir embed --force`만 모델 호출).

6. **MCP 등록 검증**: Claude Code를 재시작 후 `/mcp` 또는 도구 목록에서 `ir__search`, `ir__get`, `ir__multi_get`, `ir__status`, `ir__update` 5개가 보이는지 확인. Claude Code 채팅에서 *"ir로 위키 구조 검색해"* 호출 시 결과 반환되면 MCP가 정상. 노출 안 되면 `.mcp.json` 절대 경로 오타 또는 Claude Code 재시작 누락.

## Troubleshooting

- **데몬 상태**: `ir daemon status` — 살아있는지/포트/PID 확인. 죽었으면 `ir daemon start`로 수동 기동(첫 search가 자동 기동하지만 디버깅 시 명시적 기동 권장).
- **데몬 재시작**: `ir daemon stop && ir daemon start` — 모델 캐시 리프레시 필요할 때.
- **상태 파일 위치**: `~/.config/ir/` (config.yml, daemon.sock, daemon.pid, collections/*.sqlite, expander_cache.sqlite).
- **상세 로그**: `IR_LLAMA_LOGS=1 ir search "..."` — llama.cpp 내부 로그 활성화 (모델 로드 실패 진단).
- **Wrapper 디버그**: wrapper의 `query)` 케이스 시작(`Q="${1:?...}"` 직후)에 `echo "[ir-search] q=$Q top=$TOP coll=$COLLECTION" >&2` 한 줄 임시 삽입.
- **첫 검색이 느림**: 데몬 cold start (≤7s까지 대기) — Tier 2 모델 로드 대기. 두 번째 검색부터 ~30ms.
- **"GPU context unavailable"**: 샌드박스 셸의 정상 출력 (Metal 미접근). 사용자 터미널에서는 보이지 않음.

## 위험·롤백

- **ChromaDB 인덱스 잔존**: `seojae/search-index/`는 그대로 둬도 `search-ir`이 슬롯을 차지하면 무시된다. 디스크 회수하려면 디렉터리 삭제(gitignored).
- **롤백**:
  1. `extensions/search-ir.md` 삭제 → `search-chromadb`가 자동 재활성화 (코드 변경 0)
  2. `ir daemon stop 2>/dev/null || true` — 메모리에 떠 있는 모델 언로드. 데몬이 이미 꺼져 있어도 무해하게 통과 (롤백 후 데몬이 옛 상태로 살아있으면 다음 검색 호출이 ir 데몬으로 라우팅될 수 있음).
  3. `.mcp.json` 삭제 (MCP 등록한 경우)
  4. ir 컬렉션 항목(`~/.config/ir/config.yml`의 `seojae-wiki`)은 그대로 둬도 무해 — 비활성 상태로 디스크 ~수십 MB 차지. 회수하려면 `ir collection rm seojae-wiki` (config 항목 제거, SQLite는 보존). DB까지 삭제하려면 `--purge` 추가.
- **모델 다운로드(첫 실행)**: EmbeddingGemma 300M ~470MB가 HF Hub에서 받아져 `~/.cache/huggingface/`에 캐시 (모델 캐시 포함 ~1GB 디스크 여유 권장). 첫 `ir embed`는 다운로드 + 모델 로드로 수십 초 멈춰 보일 수 있음 — 행이 아님. 오프라인 환경이면 `IR_EMBEDDING_MODEL=/path/to/local.gguf` 또는 `HF_HUB_OFFLINE=1` 사용. 한국어 위주라면 BGE-M3 (`ggml-org/bge-m3-Q8_0-GGUF`)로 교체 옵션도 있다 — `IR_EMBEDDING_MODEL`로 지정 후 `ir embed --force` (벡터 차원 자동 적응).
- **인덱싱 스코프 차이**: 기존 `tools/search.py`는 frontmatter 있는 페이지만 인덱싱한다 (`tools/search.py:98-100, 149-152`). ir은 디렉터리 내 모든 `.md`를 스캔한다. seojae의 모든 wiki 페이지는 frontmatter 필수(WIKI_SCHEMA Page Format)이므로 정상 사용 시 차이는 없지만, `wiki/` 안에 임시·드래프트·메타 파일(예: 잘못 놓인 README, draft)이 있으면 ir이 추가로 끌어올 수 있다. 첫 인덱싱 후 `ir status`의 doc 수와 `ls wiki/**/*.md | wc -l`을 대조 권장. ir의 스캐너는 `**/*.md` 글롭 + `.gitignore` 존중 + 숨김 디렉터리 진입 — seojae `.gitignore`의 `.obsidian/` 항목 덕에 Obsidian vault를 `wiki/`에 열어도 안전하다.
- **부수 이득 — 페이지 삭제 자동 반영**: 기존 chromadb 백엔드는 삭제된 페이지를 인덱스에서 제거하는 경로가 없다 (`tools/search.py`에 `delete` 서브커맨드 없음). ir의 `ir update`는 컬렉션 스캔 시 사라진 파일을 비활성화하므로, 위키 페이지 삭제·리네이밍이 자동 반영된다.
- **기존 설치자 데이터 안전성**: chromadb의 `search-index/`는 `wiki/` 마크다운에서 파생된 인덱스일 뿐이다 — 모든 지식의 source of truth는 `wiki/` 페이지에 있다. ir로 전환 시 손실되는 데이터는 없으며, ir이 처음부터 다시 인덱싱한다.
- **Python 환경 회수 (선택)**: ChromaDB는 `tools/search.py`의 유일한 사용자다. ir 통합 후 `requirements.txt`에서 `chromadb`/`sentence-transformers`/`numpy` 제거 가능 (`PyYAML`/`pytest` 등 다른 도구가 쓰는지 grep 후 결정), `venv/` 디렉터리 삭제 가능. `~/.cache/huggingface/hub/models--sentence-transformers--paraphrase-multilingual-MiniLM-L12-v2`(~470MB)도 회수 대상.

## 참고 파일 (이 플랜이 의존)

- `seojae/WIKI_SCHEMA.md` (Loading Rules, Search Command Resolution, Query 워크플로 step 1)
- `seojae/extensions/search-chromadb.md` (계약 레퍼런스)
- `ir-fork/README.md` (CLI / 모델 / 한국어 프리프로세서 절)
- `ir-fork/CLAUDE.md` (env vars, gotchas)
- `ir-fork/src/cli/output.rs` (출력 포맷 — `--json` 스키마)
