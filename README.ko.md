# Seojae (서재)

Seojae (서재)는 LLM 기반 지식 위키 프레임워크입니다. 원본 소스 — 아티클, 논문,
영상, 노트 — 를 넣으면 LLM 코딩 도구가 자동으로 구조화된 교차 참조 위키를
만들어줍니다.

```
                  사용자가 파일 추가         LLM이 위키 구성
                +-----------+             +-------------+
  아티클    --> |           |   ingest    |             |
  논문      --> |  raw/     | ----------> |  wiki/      |
  영상      --> |           |             |             |
  노트      --> +-----------+             +-------------+
                                                |
                            규칙 정의           |
                          +-------------------+ |
                          | WIKI_SCHEMA.md    |<+
                          | (규칙 & 프롬프트) |
                          +-------------------+
```

스키마 파일(`WIKI_SCHEMA.md`)은 LLM에게 페이지 구성, 교차 참조 유지, 워크플로우
실행 방법을 알려줍니다. 특정 도구에 종속되지 않으며 Claude Code, Codex CLI,
Gemini CLI 등 마크다운 지시문을 읽는 모든 LLM 코딩 도구에서 동작합니다.

## 기능

**5가지 핵심 워크플로우** — 모두 자연어로 실행:

| 워크플로우 | 설명 |
|-----------|------|
| **Ingest** | 원본 소스를 위키 페이지(요약, 엔티티, 개념, 종합 분석)로 변환 |
| **Query** | 시맨틱 검색으로 위키 내용 기반 질문 답변 |
| **Check-New** | 새 원본 소스를 감지하고 일괄 ingest |
| **Lint** | 위키 상태 점검: 고아 페이지, 깨진 링크 탐지 및 성장 제안 |
| **Reindex** | 시맨틱 검색 인덱스 재구성 |

**모듈형 확장 시스템** — `extensions/` 디렉토리에 `.md` 파일을 넣으면 활성화,
삭제하면 비활성화. 확장은 워크플로우 추가, 외부 도구 연동, 내장 컴포넌트 대체가
가능합니다.

**내장 확장:**
- `search-chromadb` — ChromaDB와 sentence-transformers 기반 시맨틱 검색
- `obsidian` — Obsidian vault 연동으로 위키 탐색 및 시각화

## 사전 요구사항

- **Python 3.9+** (pip 포함)
- **~470MB 디스크 공간** (임베딩 모델, 첫 실행 시 자동 다운로드)
- **LLM 코딩 도구** — 다음 중 하나:
  - [Claude Code](https://docs.anthropic.com/en/docs/claude-code)
  - [Codex CLI](https://github.com/openai/codex)
  - [Gemini CLI](https://github.com/google-gemini/gemini-cli)

## 지원 도구

| 도구 | 규칙 파일 | 규칙 읽기 방식 | Import 문법 | 참고 |
|------|----------|---------------|-------------|------|
| **Claude Code** | `CLAUDE.md` | 세션 시작 시 자동 읽기 | `@WIKI_SCHEMA.md` | 첫 셋업 후 세션 재시작 필요 |
| **Codex CLI** | `AGENTS.md` | 세션 시작 시 자동 읽기 | Import 미지원 (32KiB 제한); 전체 내용 인라인 | 즉시 사용 가능 |
| **Gemini CLI** | `GEMINI.md` | 세션 시작 시 자동 읽기 | `@./WIKI_SCHEMA.md` | 첫 셋업 후 세션 재시작 필요 |

각 도구에 맞는 규칙 파일이 리포에 미리 구성되어 있습니다. 규칙 파일은
`WIKI_SCHEMA.md`와 활성 확장을 import(또는 인라인)하므로, 세션을 시작하는 순간부터
LLM이 위키를 관리할 수 있습니다.

## 빠른 시작

```bash
# 1. 리포 클론
git clone https://github.com/Laeyoung/seojae.git
cd seojae

# 2. LLM 도구로 열기 (규칙 파일을 자동으로 읽습니다)
claude          # Claude Code
codex           # Codex CLI
gemini          # Gemini CLI

# 3. 다음과 같이 말하세요:
#    "위키 초기화해줘" 또는 "Initialize this wiki"
```

초기화 과정에서 LLM이 수행하는 작업:
- Python 가상환경(`venv/`) 생성
- `requirements.txt` 의존성 설치
- 시맨틱 검색 인덱스 구성 (첫 실행 시 ~470MB 임베딩 모델 다운로드)
- 테스트 쿼리로 셋업 검증

이후 `raw/` 디렉토리에 파일을 넣고 "새로운 소스 확인해줘"라고 말하면 위키
구축이 시작됩니다.

## 예제

리포에 Andrej Karpathy의 원본 소스 3개가 예제로 포함되어 있습니다:

| 원본 소스 | 생성된 위키 페이지 |
|----------|-------------------|
| `raw/articles/software-2.0.md` | 소스 요약 + 엔티티 + 개념 페이지 |
| `raw/articles/vibe-coding.md` | 소스 요약 + 개념 페이지 |
| `raw/videos/intro-to-llms.md` | 소스 요약 |

총 7개의 위키 페이지(소스 요약 3개, 엔티티 1개, 개념 2개, 종합 분석 1개)가
생성되며, Seojae가 관련 콘텐츠를 교차 참조하는 방식을 보여줍니다.

자세한 안내는 [docs/getting-started.md](docs/getting-started.md)를 참고하세요.

## CLI 레퍼런스

`tools/search.py`는 LLM 도구 없이 독립적으로 사용할 수 있는 유일한 컴포넌트입니다.
Python venv가 활성화된 상태에서 실행해야 합니다.

```bash
# 시맨틱 검색
venv/bin/python tools/search.py --query "attention mechanism" --top 5

# 인덱스에 페이지 추가/업데이트
venv/bin/python tools/search.py --add wiki/concepts/attention-mechanism.md

# 전체 인덱스 재구성
venv/bin/python tools/search.py --reindex
```

| 인자 | 기본값 | 설명 |
|------|--------|------|
| `--query` | -- | 시맨틱 검색 쿼리 |
| `--add` | -- | 위키 페이지 인덱스 추가/업데이트 |
| `--reindex` | -- | 전체 인덱스 재구성 |
| `--top` | `5` | 검색 결과 수 |
| `--index-path` | `search-index/` | ChromaDB 인덱스 디렉토리 |
| `--wiki-path` | `wiki/` | 위키 디렉토리 (`--reindex` 전용) |

**종료 코드:**

| 코드 | 의미 |
|------|------|
| `0` | 성공 (frontmatter 없는 페이지 skip 포함) |
| `1` | 에러 (빈 쿼리, 파일 없음, 위키 경로 없음) |
| `2` | 인덱스 미존재 (`--reindex` 실행 필요) |

## 확장

확장은 Seojae에 기능을 추가하는 마크다운 파일입니다. 각 파일에는 핵심 스키마와
함께 로드되는 LLM 지시문이 포함되어 있습니다.

**확장 사용법:**
1. `.md` 파일을 `extensions/` 디렉토리에 넣기
2. LLM 도구 세션 재시작
3. 확장 활성화 완료

**확장 제거:**
- `extensions/`에서 `.md` 파일을 삭제하고 세션 재시작

**확장 찾기:**
- GitHub에서 [`seojae-extension`](https://github.com/topics/seojae-extension) 토픽 검색

**내장 확장:**
- `search-chromadb.md` — 시맨틱 검색 백엔드 (ChromaDB + sentence-transformers)
- `obsidian.md` — Obsidian vault 연동
- `connected-wikis.md` — 외부 seojae wiki를 토글 가능한 확장 지식 저장소로 연결
  ([사용 가이드](docs/connected-wikis-guide.ko.md)). 공개 샘플 위키
  [`Laeyoung/den`](https://github.com/Laeyoung/den)으로 바로 테스트할 수 있습니다:
  ```bash
  venv/bin/python tools/connected_wikis.py connect https://github.com/Laeyoung/den --id den --decision consent=accept
  venv/bin/python tools/search.py --query "에스프레소 추출" --collections wiki,wiki-ext-den
  ```

직접 만들고 싶다면 [extensions/README.md](extensions/README.md)를 참고하세요.

## 기여

[CONTRIBUTING.md](CONTRIBUTING.md)를 참고하세요.

## 라이선스

[MIT](LICENSE)
