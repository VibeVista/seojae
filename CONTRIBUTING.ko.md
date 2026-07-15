# Seojae 기여 가이드

Seojae에 관심을 가져주셔서 감사합니다! 이 가이드는 기여를 시작하는
방법, 받아들이는 기여 유형, 그리고 따르는 컨벤션을 설명합니다.

이 프로젝트에 참여하는 것은 [행동 강령(Code of Conduct)](CODE_OF_CONDUCT.md)을
준수하는 것에 동의함을 의미합니다.

## 기여 방법

**이슈** — 버그 리포트, 기능 요청, 확장(Extension) 아이디어를 환영합니다.
새 이슈를 만들기 전에 기존 이슈를 먼저 검색해 주세요.

**Pull Request** — 기본 워크플로우:

1. 저장소를 Fork합니다
2. 기능 브랜치를 만듭니다 (`git checkout -b my-feature`)
3. 변경 사항을 작업합니다
4. Fork에 Push하고 Pull Request를 엽니다

PR은 하나의 기능 또는 수정에 집중해 주세요. 리뷰가 빨라지고
git 히스토리가 깔끔해집니다.

## 개발 환경 설정

```bash
# 저장소 클론
git clone https://github.com/VibeVista/seojae.git
cd seojae

# 가상 환경 생성
python3 -m venv venv

# 의존성 설치
venv/bin/pip install -r requirements.txt

# 테스트 실행 (470MB 임베딩 모델이 필요한 테스트 건너뜀)
SKIP_MODEL_TESTS=true venv/bin/python -m pytest tests/ -v
```

`SKIP_MODEL_TESTS=true` 플래그는 `paraphrase-multilingual-MiniLM-L12-v2`
임베딩 모델(~470MB) 다운로드가 필요한 테스트를 건너뜁니다.
모델이 이미 캐시되어 있거나 전체 테스트를 실행하려면 플래그를 생략하세요.

## 도구 지원 추가

Seojae는 도구에 종속되지 않습니다 — 마크다운 지침을 읽는 모든 LLM 코딩
도구(Claude Code, Codex CLI, Gemini CLI 등)에서 동작합니다.

새 도구 지원을 추가하려면:

1. **저장소 루트에 스텁 규칙 파일 생성** (예: `MYTOOL.md`)
   - 도구가 파일 import를 지원하면 `WIKI_SCHEMA.md`와 활성 확장을
     참조하는 import 구문 사용:
     ```
     @WIKI_SCHEMA.md
     @extensions/search-chromadb.md
     ```
   - 도구가 import를 지원하지 않으면 `WIKI_SCHEMA.md`와 활성 확장의
     전체 내용을 규칙 파일에 인라인합니다.
2. **`WIKI_SCHEMA.md`의 Setup 섹션에 도구 추가** —
   "### 1. Update your tool's rule file" 아래에 Claude Code, Codex CLI,
   Gemini CLI의 기존 패턴을 따라 추가합니다.
3. **도구별 특이사항 문서화** — 규칙 파일의 Environment 섹션에 기록:
   - Import 구문 차이 (`@file` vs `@./file`)
   - 파일 크기 제한 (Codex의 `project_doc_max_bytes` 기본값 32KB)
   - `venv` 활성화가 명령 간 유지되는지 여부

## 확장(Extension) 만들기

확장은 `extensions/` 디렉토리의 마크다운 파일로 위키에 기능을 추가합니다.
`extensions/search-chromadb.md`를 참조 구현으로 활용하세요.

### Frontmatter 필드

```yaml
---
name: my-extension
description: 확장이 하는 일에 대한 한 줄 요약
provides: capability-name       # 선택 — 배타적 기능 소유권
overrides: other-extension      # 선택 — 대체할 확장
requires:
  packages: [package1>=1.0]     # 필요한 pip 패키지
  scripts: [tools/my-script.py] # 필요한 저장소 스크립트
  provides: [search-backend]    # 기능 의존성
min_schema_version: "1.0"       # 최소 WIKI_SCHEMA.md 버전
commands:                        # 워크플로우 통합용 명명된 명령
  my-cmd: "venv/bin/python tools/my-script.py --flag"
---
```

### 필수 섹션

- **`## Setup`** — 일회성 설치 및 구성 단계.
- **`## Workflows`** — 새 워크플로우 또는 기존 코어 워크플로우 수정.
  따르는 단계를 참조합니다 (예: "Ingest 3단계 후에 X도 실행").
- **`## Configuration`** — 설정 가능한 옵션과 기본값.

### 기능 모델

- 기능을 **대체하는** 확장은 `provides:`와 `overrides:`를 모두 선언합니다
  — 하나의 기능에는 하나의 확장만 소유할 수 있습니다.
- 기존 워크플로우를 **보강하는** 확장(단계 추가, 통합)은 `provides:`가
  필요 없으며 항상 활성화됩니다.

## 스키마 변경

`WIKI_SCHEMA.md`는 모든 LLM 도구가 읽는 핵심 스키마입니다. 변경 시
하위 영향이 있습니다:

1. **`AGENTS.md` 업데이트** — Codex CLI는 파일 import를 지원하지 않아
   `AGENTS.md`에 스키마의 인라인 복사본이 들어 있습니다.
   `WIKI_SCHEMA.md`의 모든 변경은 `AGENTS.md`에도 반영해야 합니다.
2. **크기 예산 확인** — Codex는 기본 `project_doc_max_bytes`가
   32,768바이트입니다:
   ```bash
   wc -c AGENTS.md
   ```
   `AGENTS.md`에 확장 내용도 인라인하는 경우, 제한에 맞게 예산을
   배분하세요.
3. **`schema_version` 업데이트** — 확장 호환성에 영향을 주는 변경이면
   `WIKI_SCHEMA.md` 상단의 YAML 설정 블록에서 버전을 올립니다.

## 코드 스타일

- **Python**: [PEP 8](https://peps.python.org/pep-0008/) 스타일
  가이드라인을 따릅니다.
- **테스트 필수**: `tools/` 파일 변경 시 `tests/`에 대응하는 테스트를
  포함해야 합니다.
- **CI/오프라인 환경**: 임베딩 모델 다운로드가 필요한 테스트를
  건너뛰려면 `SKIP_MODEL_TESTS=true`를 사용합니다:
  ```bash
  SKIP_MODEL_TESTS=true venv/bin/python -m pytest tests/ -v
  ```
- **Markdown**: ATX 스타일 헤더(`#`), 펜스 코드 블록을 사용하고
  가능한 한 줄당 80자 이내를 유지합니다.
