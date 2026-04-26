# Seojae (서재) — 오픈소스 공개 가이드

이 문서는 `go-open-source-project` 브랜치의 내용을 새 GitHub 리포지토리로 공개하는 절차를 안내합니다.

---

## 사전 준비

### 필요한 것

- GitHub 계정 (리포 생성 권한)
- Git CLI 또는 `gh` CLI
- 현재 `go-open-source-project` 브랜치가 최신 상태인지 확인

### 공개 전 체크리스트

- [ ] 개인 정보 제거 확인 — `git ls-files`로 tracked 파일 목록 검토
- [ ] `LLM-Wiki` 문자열이 남아있지 않은지 확인: `grep -r "LLM-Wiki" *.md`
- [ ] 리포 URL이 `seojae`로 통일되어 있는지 확인
- [ ] LICENSE 파일의 저작자 이름 확인

---

## Step 1: GitHub 리포지토리 생성

### 옵션 A: GitHub 웹에서 생성

1. https://github.com/new 접속
2. Repository name: `seojae`
3. Description: `LLM-powered knowledge wiki framework — 서재(書齋)`
4. **Public** 선택
5. **Initialize this repository with** 항목 모두 체크 해제 (README, .gitignore, license 모두 이미 있음)
6. **Create repository** 클릭

### 옵션 B: `gh` CLI로 생성

```bash
gh repo create Laeyoung/seojae --public --description "LLM-powered knowledge wiki framework — 서재(書齋)"
```

---

## Step 2: 파일 복사 및 첫 커밋

`go-open-source-project` 브랜치의 git 히스토리에는 개인 콘텐츠 삭제 이력이 남아 있으므로, **새 리포에 깨끗한 첫 커밋**으로 시작합니다.

```bash
# 1. 새 디렉토리 생성 및 git 초기화
mkdir ../seojae
cd ../seojae
git init

# 2. 원본 브랜치에서 파일 복사 (.git 제외)
cp ../LLM-Wiki/.gitignore .
cp ../LLM-Wiki/WIKI_SCHEMA.md .
cp ../LLM-Wiki/CLAUDE.md .
cp ../LLM-Wiki/AGENTS.md .
cp ../LLM-Wiki/GEMINI.md .
cp ../LLM-Wiki/README.md .
cp ../LLM-Wiki/README.ko.md .
cp ../LLM-Wiki/CONTRIBUTING.md .
cp ../LLM-Wiki/CONTRIBUTING.ko.md .
cp ../LLM-Wiki/LICENSE .
cp ../LLM-Wiki/index.md .
cp ../LLM-Wiki/log.md .
cp ../LLM-Wiki/requirements.txt .

# 3. 디렉토리 구조 복사
cp -r ../LLM-Wiki/extensions .
cp -r ../LLM-Wiki/tools .
cp -r ../LLM-Wiki/tests .
cp -r ../LLM-Wiki/raw .
cp -r ../LLM-Wiki/wiki .
cp -r ../LLM-Wiki/docs .

# 4. 첫 커밋
git add -A
git commit -m "init: Seojae (서재) — LLM-powered knowledge wiki framework"
```

---

## Step 3: 복사 결과 검증

```bash
# 파일 수 확인 (36개여야 함)
git ls-files | wc -l

# 개인 정보 누출 검사
grep -r "LLM-Wiki" . --include="*.md"         # 결과 없어야 함
grep -r "user@example.com" . --include="*.md"      # 결과 없어야 함
grep -r "오늘의집" . --include="*.md"            # 결과 없어야 함
grep -r ".claude/commands" . --include="*.md"  # 결과 없어야 함

# 파일 구조 확인
find . -not -path './.git/*' -type f | sort
```

**예상 파일 목록 (36개):**

```
.gitignore
AGENTS.md
CLAUDE.md
CONTRIBUTING.ko.md
CONTRIBUTING.md
GEMINI.md
LICENSE
README.ko.md
README.md
WIKI_SCHEMA.md
docs/getting-started.md
extensions/README.md
extensions/obsidian.md
extensions/search-chromadb.md
index.md
log.md
raw/articles/software-2.0.md
raw/articles/vibe-coding.md
raw/assets/.gitkeep
raw/books/.gitkeep
raw/misc/.gitkeep
raw/myself/.gitkeep
raw/papers/.gitkeep
raw/videos/intro-to-llms.md
requirements.txt
tests/__init__.py
tests/test_search.py
tools/__init__.py
tools/search.py
wiki/concepts/software-2-0.md
wiki/concepts/vibe-coding.md
wiki/entities/andrej-karpathy.md
wiki/sources/intro-to-llms.md
wiki/sources/software-2.0.md
wiki/sources/vibe-coding-karpathy.md
wiki/synthesis/karpathy-software-evolution.md
```

---

## Step 4: Remote 연결 및 Push

```bash
# remote 추가
git remote add origin https://github.com/Laeyoung/seojae.git

# main 브랜치로 push
git branch -M main
git push -u origin main
```

---

## Step 5: GitHub 리포 설정

### 5-1. About 섹션

리포 페이지 우측 톱니바퀴(Settings) → About:
- **Description:** `LLM-powered knowledge wiki framework — 서재(書齋)`
- **Website:** (선택) 프로젝트 문서 URL
- **Topics:** `llm`, `knowledge-management`, `wiki`, `claude-code`, `codex`, `gemini-cli`, `obsidian`, `rag`, `personal-wiki`, `seojae`

### 5-2. Social Preview 이미지 (선택)

Settings → Social preview에 1280x640px 이미지 업로드. 프로젝트 이름과 간단한 다이어그램 포함하면 좋음.

### 5-3. GitHub Topics

리포 홈 → About 옆 "Manage topics" 클릭:
```
llm  knowledge-management  wiki  personal-wiki  claude-code
codex  gemini-cli  obsidian  chromadb  seojae
```

---

## Step 6: 동작 확인

새 리포를 클론해서 실제로 동작하는지 확인합니다.

```bash
# 다른 디렉토리에서 클론
cd /tmp
git clone https://github.com/Laeyoung/seojae.git
cd seojae

# Python 환경 셋업
python3 -m venv venv
venv/bin/pip install -r requirements.txt

# 검색 인덱스 구축 (첫 실행: ~470MB 모델 다운로드)
venv/bin/python tools/search.py --reindex

# 테스트 쿼리
venv/bin/python tools/search.py --query "vibe coding"

# 테스트 실행
SKIP_MODEL_TESTS=true venv/bin/python -m pytest tests/test_search.py -v
```

**예상 결과:**
- `--reindex`: `Reindex complete: 7 pages indexed, 0 skipped`
- `--query "vibe coding"`: Karpathy 관련 위키 페이지들이 검색 결과로 나옴
- `pytest`: 모든 unit 테스트 통과

---

## Step 7: 공개 후 안내

### Release 생성 (선택)

```bash
gh release create v1.0.0 --title "v1.0.0 — Initial Release" --notes "$(cat <<'EOF'
# Seojae (서재) v1.0.0

LLM-powered knowledge wiki framework의 첫 번째 릴리스입니다.

## Features

- **WIKI_SCHEMA.md** — 도구 중립적 위키 스키마 (Claude Code, Codex, Gemini CLI 지원)
- **Extension System** — 마크다운 파일 추가/제거로 기능 확장
- **Semantic Search** — ChromaDB + sentence-transformers 기반 시맨틱 검색
- **Karpathy 예시** — Software 2.0, Vibe Coding, Intro to LLMs 테마 예시 콘텐츠
- **이중 언어 문서** — 영어 + 한국어 README, CONTRIBUTING, 튜토리얼

## Getting Started

```bash
git clone https://github.com/Laeyoung/seojae.git
cd seojae
# Open with your LLM coding tool and say: "initialize this wiki"
```

See [docs/getting-started.md](docs/getting-started.md) for the full tutorial.
EOF
)"
```

### 공유할 곳

- [ ] 개인 블로그 / Velog에 소개 글
- [ ] Twitter/X에 공유 (Karpathy 예시 언급하면 주목도 높음)
- [ ] Reddit r/LocalLLaMA, r/ObsidianMD
- [ ] Hacker News (Show HN)
- [ ] 한국 개발자 커뮤니티 (GeekNews, Disquiet 등)

---

## 문제 해결

### Push가 거부되는 경우

```bash
# GitHub에서 리포 생성 시 README/LICENSE를 추가했다면:
git pull origin main --allow-unrelated-histories
# 충돌 해결 후:
git push -u origin main
```

### 파일이 누락된 경우

```bash
# 원본 브랜치에서 특정 파일 다시 복사
cp ../LLM-Wiki/<missing-file> .
git add <missing-file>
git commit -m "fix: add missing file"
git push
```

### 민감 정보가 발견된 경우

```bash
# 해당 파일 수정 후
git add <file>
git commit -m "fix: remove sensitive content"
git push

# 이미 push한 커밋에서 민감 정보 제거가 필요하면:
# (주의: force push는 기존 클론에 영향)
git filter-branch 또는 BFG Repo-Cleaner 사용
```

---

## 요약 플로우차트

```
1. GitHub 리포 생성 (seojae, public, empty)
   ↓
2. 파일 복사 (go-open-source-project 브랜치 → 새 디렉토리)
   ↓
3. 검증 (36개 파일, 개인정보 없음)
   ↓
4. Push (origin/main)
   ↓
5. GitHub 설정 (description, topics, social preview)
   ↓
6. 동작 확인 (clone → setup → reindex → query → test)
   ↓
7. Release 생성 + 공유
```
