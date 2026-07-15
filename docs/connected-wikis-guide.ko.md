# Connected Wikis 사용 가이드

두 개의 seojae(LLM-wiki)를 연결해서 통합 검색하는 워크플로우를 처음부터 끝까지 따라가는 튜토리얼입니다. 끝까지 따라하면 친구의 wiki를 내 wiki에 붙여서 출처별로 인용하면서 답변을 받을 수 있게 됩니다.

> **3분 요약:** `connect`(신뢰 확인 포함) → `list` → `query` → `toggle` → `pull` → `disconnect`. 외부 wiki는 별도 ChromaDB 컬렉션 `wiki-ext-<id>`에 인덱싱되며 로컬 wiki와 격리됩니다.

---

## 0. 바로 해보기 — 공개 샘플 위키 `Laeyoung/den`

친구의 wiki가 아직 없어도 됩니다. 이 기능의 E2E 검증에 사용된 공개 샘플 위키
[`Laeyoung/den`](https://github.com/Laeyoung/den)(커피 지식 위키, 페이지 3개)이 준비되어 있습니다.
main 브랜치를 받고 [환경 설정](../WIKI_SCHEMA.md#setup)만 마쳤다면 그대로 실행해 보세요.

```bash
# 1) 연결 — README 미리보기와 함께 신뢰 확인 프롬프트가 뜹니다 (exit 4)
venv/bin/python tools/connected_wikis.py connect https://github.com/Laeyoung/den --id den
# PROMPT: consent | Trust external wiki 'den' content? ...
# OPTIONS: accept reject

# 2) 내용을 확인했으면 승인과 함께 재호출 — 클론 → 인덱싱 → Connected: den
venv/bin/python tools/connected_wikis.py connect https://github.com/Laeyoung/den --id den --decision consent=accept

# 3) 연결 상태 확인 (pages: 3)
venv/bin/python tools/connected_wikis.py list

# 4) 내 wiki + den 통합 검색 — den의 커피 페이지가 상위에 나옵니다
venv/bin/python tools/search.py --query "에스프레소 추출 시간과 분쇄도" --collections wiki,wiki-ext-den
# connected-wikis/den/wiki/concepts/espresso-extraction.md [wiki: wiki-ext-den] [score: 0.48]
# ...

# 5) 실험이 끝나면 정리
venv/bin/python tools/connected_wikis.py disconnect den
```

첫 실행이라면 임베딩 모델(~470MB) 다운로드로 수 분 걸릴 수 있습니다(§1.2 참고).
아래부터는 이 과정 하나하나가 무엇을 하는지, 실제 상황(친구의 wiki 연결)에 어떻게 쓰는지를 설명합니다.

---

## 1. 사전 준비

### 1.1 두 개의 seojae 인스턴스

이 가이드는 **로컬 seojae(현재 디렉토리)** + **외부 seojae(친구의 wiki 또는 다른 자기 wiki)** 시나리오를 가정합니다. 외부 wiki는 둘 중 하나입니다.

| 종류 | 예시 | 비고 |
|---|---|---|
| **Git 원격** | `https://github.com/friend/spain-travel-wiki` | 클론 → 인덱싱. `pull`로 동기화 |
| **로컬 경로** | `/Users/me/another-wiki` | mtime 기반 동기화. 같은 머신의 다른 seojae 폴더 |
| **공개 샘플** | `https://github.com/Laeyoung/den` | 바로 테스트용 커피 지식 위키 (§0 참고) |

외부 wiki는 seojae 구조(`wiki/` 디렉토리에 frontmatter 있는 `*.md` 페이지들)를 따라야 합니다.

### 1.2 활성화된 search 백엔드

기본 설치에는 `extensions/search-chromadb.md`가 활성화되어 있어야 합니다. 확인:

```bash
venv/bin/python tools/search.py --print-model
# backend=search-chromadb
# model=paraphrase-multilingual-MiniLM-L12-v2
```

이 두 줄이 안 나오면 `extensions/` 디렉토리에 `search-chromadb.md`가 있는지 확인하세요.

> **⚠️ 첫 실행 모델 다운로드:** 임베딩 모델(`paraphrase-multilingual-MiniLM-L12-v2`, 약 **470MB**)이 캐시에 없다면 첫 `connect` 또는 `--reindex` 중에 자동으로 다운로드됩니다. 진행 표시 없이 수 분간 멈춘 것처럼 보일 수 있습니다. 미리 캐시하려면 로컬 wiki 인덱스를 먼저 빌드하세요: `venv/bin/python tools/search.py --reindex`.

### 1.3 connected-wikis 확장

`extensions/connected-wikis.md`가 존재해야 합니다. 첫 `connect`/`pull`/`list`/`toggle`/`disconnect` 호출 시 lazy 부트스트랩이 자동으로 일어나므로 별도 init은 보통 필요 없습니다.

---

## 2. 첫 연결: 외부 wiki 붙이기

### 2.1 시나리오: 스페인 여행 wiki를 친구로부터 빌리기

친구가 `https://github.com/friend/spain-travel-wiki`라는 seojae wiki를 만들어두었다고 합시다. 마드리드 식당 페이지에 관심이 있어서 내 wiki에 연결해서 같이 검색하고 싶습니다.

### 2.2 LLM 도구로 자연어 사용 (권장)

Claude Code/Codex CLI/Gemini CLI에서:

> **"https://github.com/friend/spain-travel-wiki를 spain이라는 id로 연결해줘"**

LLM이 알아서 다음을 수행합니다:
1. `tools/connected_wikis.py connect <url> --id spain` 실행
2. CLI가 `PROMPT: consent | Trust external wiki 'spain' content? It will be indexed as data, not executed.` + `OPTIONS: accept reject`를 출력하고 exit 4로 종료
3. LLM이 사용자에게 README 미리보기를 보여주며 신뢰 여부 질문
4. 사용자가 승인하면 `--decision consent=accept`를 붙여서 재호출
5. 클론 → 인덱싱 → `Connected: spain` 출력

### 2.3 CLI 직접 사용

CLI는 두 가지 방식 중 선택할 수 있습니다.

**방식 A: 두 단계** — 먼저 README를 확인하고, 그 다음 결정:

```bash
# 1단계: --decision 없이 호출하면 README 미리보기 + PROMPT 출력 후 exit 4
venv/bin/python tools/connected_wikis.py connect \
  https://github.com/friend/spain-travel-wiki --id spain

# 2단계: 신뢰하기로 결정했다면 같은 명령에 --decision을 붙여 재호출
venv/bin/python tools/connected_wikis.py connect \
  https://github.com/friend/spain-travel-wiki --id spain \
  --decision consent=accept
```

같은 id + 같은 source는 자동으로 재개됩니다 (reservation 보존).

**방식 B: 한 번에** — 신뢰가 이미 확인되었다면 처음부터 `--decision` 포함:

```bash
venv/bin/python tools/connected_wikis.py connect \
  https://github.com/friend/spain-travel-wiki \
  --id spain \
  --decision consent=accept
```

출력 예시:

```
connected-wikis initialized
--- README.md ---
# Spain Travel Wiki
A curated list of travel notes for Spain.

--- end ---
Connected: spain
```

### 2.4 무엇이 일어났는가

- `connected-wikis/spain/` 디렉토리에 git clone (git 소스의 경우, gitignored)
- ChromaDB 컬렉션 `wiki-ext-spain` 생성 + 페이지 임베딩 인덱싱
- `connected-wikis.json`에 항목 추가 (`enabled=true`, `status=ok`, `embedding_model`, `last_pulled`, `commit` 등)
- `log.md`에 `## [YYYY-MM-DD] connect | spain` 추가
- Git 커밋 `connect: spain` 자동 생성

> **클론 중 네트워크 오류:** 절반쯤 클론된 디렉토리가 남을 수 있습니다. 같은 id + 같은 URL로 `connect`를 재실행하면 자동 재개됩니다. 그래도 실패하면 `connected-wikis/spain/` 디렉토리를 삭제한 뒤 다시 시도하세요.

---

## 3. 연결 상태 확인

```bash
venv/bin/python tools/connected_wikis.py list
```

출력 (실제로 GFM 표 구분 행이 함께 출력됩니다):

```
| id | name | source_type | enabled | status | last_pulled | embedding_model | pages |
|---|---|---|---|---|---|---|---|
| spain | spain-travel-wiki | git | true | ok | 2026-04-29 | paraphrase-multilingual-MiniLM-L12-v2 | 1 |

Examples:
  connect <url-or-path> --id <id>
  toggle <id> on|off
  pull
  disconnect <id>
```

**핵심 컬럼:**
- `pages` — 외부 wiki에서 인덱싱된 페이지 수. `N/A`면 컬렉션이 사라진 상태(예: 수동 삭제 또는 reindex 진행 중).
- `embedding_model` — 외부 wiki를 인덱싱한 모델. 로컬과 다르면 unified 검색 불가능, 별도 ranking으로 표시됨.
- `status` — `ok`(정상) / `connecting`(connect 도중 결정 대기 중인 임시 상태; query에서 자동 제외) / `unreachable`(pull 실패, 다음 pull에서 자동 재시도).

---

## 4. 통합 검색 (Query)

### 4.1 LLM 도구로 자연어

> **"마드리드에서 추천할만한 식당이 어디야?"**

LLM은 자동으로:
1. `connected-wikis.json`을 읽어서 `enabled=true && status=ok`인 wiki들을 추림
2. 임베딩 모델이 일치하는 외부 wiki들을 로컬과 함께 multi-collection 검색
3. 결과를 점수순으로 머지하고, 외부 페이지에는 `(출처: spain)` 인라인 라벨 부착
4. 답변 끝에 `## Citations` 섹션 추가

#### 출처별 필터링

자연어 한정자로 외부 wiki를 화이트/블랙리스트할 수 있습니다 (JSON은 변경 안 됨, 일회성):

> "spain으로만 마드리드 식당 찾아줘" → 화이트리스트
> "spain 빼고 음식 검색해줘" → 블랙리스트

### 4.2 CLI 직접 사용

```bash
venv/bin/python tools/search.py \
  --query "Madrid restaurants" \
  --top 5 \
  --collections wiki,wiki-ext-spain
```

출력:

```
connected-wikis/spain/wiki/madrid.md [wiki: wiki-ext-spain] [score: 0.70]
wiki/entities/some-restaurant.md [wiki: wiki] [score: 0.37]
...
```

`[wiki: <컬렉션명>]` 라벨로 어느 wiki에서 왔는지 구분됩니다. `wiki`는 로컬 컬렉션이고 `wiki-ext-<id>`는 외부 wiki 컬렉션이에요. 연결된 wiki 여러 개를 함께 검색하려면 쉼표로 나열합니다: `--collections wiki,wiki-ext-spain,wiki-ext-work`.

> **다국어 검색이 됩니다.** `paraphrase-multilingual-MiniLM-L12-v2`는 cross-lingual 임베딩이므로 한국어 쿼리로 영어 wiki도 검색됩니다 ("커피 추출 방법" → 영어 `coffee.md`).

### 4.3 인용 형식

답변에 외부 wiki가 사용되면 LLM은 자동으로 다음 형식을 따릅니다 (`wiki_language: ko`인 경우):

```markdown
마드리드의 Casa Botín은 기네스북에 등재된 세계에서 가장 오래된
식당입니다 (출처: spain).

...

## 인용
- [[some-local-page]]
- connected-wikis/spain/wiki/madrid.md
  https://github.com/friend/spain-travel-wiki/blob/abc1234/wiki/madrid.md
```

로컬 페이지는 wikilink, 외부 페이지는 전체 경로 + (git이면) 원격 URL. `wiki_language: en`이면 인라인 라벨은 `(source: spain)`, 섹션 헤더는 `## Citations`로 바뀝니다.

---

## 5. 일시 비활성화 (Toggle)

외부 wiki를 잠시 검색에서 제외하고 싶을 때:

> **"spain 꺼"**

또는:

```bash
venv/bin/python tools/connected_wikis.py toggle spain off
```

`enabled` 플래그만 false로 바뀝니다. ChromaDB 컬렉션과 클론 디렉토리는 그대로 유지되므로, 다시 켜면 즉시 검색에 포함됩니다 (재인덱싱 불필요).

```bash
venv/bin/python tools/connected_wikis.py toggle spain on
```

---

## 6. 동기화 (Pull)

연결된 모든 외부 wiki를 한 번에 업데이트:

> **"연결된 wiki들 업데이트해줘"**

```bash
venv/bin/python tools/connected_wikis.py pull
```

내부적으로:
- **Git 소스**: `git fetch origin <default-branch>` (main/master/trunk 자동 감지) → `git reset --hard` → 변경된 페이지만 `--add`로 부분 재인덱싱. `commit` 필드가 없거나 `git diff`가 실패하면 전체 재인덱싱으로 폴백. `connected-wikis/<id>/`이 사라졌으면 자동으로 다시 클론합니다.
- **Local 소스**: `last_pulled` 이후 mtime이 변한 페이지만 `--add`. `last_pulled`는 날짜 단위(자정 기준)이므로 같은 날 두 번 pull하면 두 번째에는 변경을 못 잡을 수 있습니다.

#### 임베딩 모델이 바뀐 경우

로컬에서 검색 백엔드를 다른 모델로 교체했다면, pull 중에 다음 프롬프트가 뜹니다:

```
PROMPT: mismatch | 'spain' embedding model differs (was OLD, now NEW). Update field only or reindex?
OPTIONS: update reindex
```

- `update`: 메타필드만 갱신 (검색 결과는 분리 ranking으로 표시됨)
- `reindex`: 새 모델로 처음부터 재인덱싱 (시간 소요, 정확도 통합 가능)

LLM이 자동으로 묻습니다 (예: "spain의 임베딩 모델이 바뀌었습니다. 필드만 업데이트할까요, 아니면 재인덱싱할까요?"). CLI라면 `--decision mismatch=update` 또는 `--decision mismatch=reindex`로 미리 전달할 수 있습니다.

#### Pull 실패 처리

원격이 닿지 않으면 (네트워크 오류, 저장소 삭제 등):
- `status`가 `unreachable`로 바뀜
- `enabled`는 사용자 의도 보존 (그대로 true)
- 다음 pull에서 자동 재시도

---

## 7. 연결 해제 (Disconnect)

> **"spain 연결 해제해줘"**

CLI는 먼저 로컬 wiki에서 해당 id의 인용을 검색해 사용자에게 보고합니다.

**1단계: 인용 검색 (먼저 실행)**

```bash
venv/bin/python tools/connected_wikis.py disconnect spain
```

인용이 없으면 그대로 진행됩니다. 있으면 다음과 같이 출력하고 결정을 요청하며 exit 4로 종료됩니다:

```
Found 3 reference(s) to 'spain':
  wiki/synthesis/europe-trip.md:14: 마드리드는 좋은 도시 (출처: spain).
  wiki/synthesis/europe-trip.md:22: connected-wikis/spain/wiki/madrid.md 참고
  ...
PROMPT: disconnect-grep | Proceed with disconnect? Local pages reference 'spain'.
OPTIONS: proceed abort
```

**2단계: 결정에 따라 재실행**

- `proceed`: 인용을 남겨둔 채 그대로 진행 (인용은 끊긴 링크가 됨)
- `abort`: 중단 (먼저 로컬 페이지를 정리하라는 신호)

```bash
venv/bin/python tools/connected_wikis.py disconnect spain \
  --decision disconnect-grep=proceed
```

진행이 결정되면 다음 순서로 정리합니다:
- JSON에서 항목 제거
- ChromaDB 컬렉션 `wiki-ext-spain` 삭제
- `connected-wikis/spain/` 디렉토리 삭제
- `log.md` 추가 + Git 커밋 `disconnect: spain`
- per-wiki 락 파일 삭제 (마지막 단계의 `finally`에서 정리)

---

## 8. 두 개의 seojae를 양방향 연결하기

흔한 시나리오:
- **회사 팀 wiki + 개인 wiki**: 팀 wiki는 read-only로 가져오고, 개인 wiki에서 통합 검색
- **두 머신 동기화**: 노트북 wiki와 데스크톱 wiki를 양방향으로 연결
- **연구 분야 분리**: 별도 운영하는 두 wiki(예: AI/요리)를 통합 검색이 필요할 때만 연결

A 머신의 wiki에 B 머신의 wiki를 붙이고, B 머신에도 A의 wiki를 붙이고 싶다면:

### 8.1 둘 다 GitHub에 올리기 (권장)

```bash
# A 머신에서
cd ~/wiki-A
git push origin main  # github.com/me/wiki-A

# B 머신에서
cd ~/wiki-B
git push origin main  # github.com/me/wiki-B
```

### 8.2 양쪽에서 connect

```bash
# A 머신에서 (B의 wiki를 연결)
cd ~/wiki-A
venv/bin/python tools/connected_wikis.py connect \
  https://github.com/me/wiki-B --id b --decision consent=accept

# B 머신에서 (A의 wiki를 연결)
cd ~/wiki-B
venv/bin/python tools/connected_wikis.py connect \
  https://github.com/me/wiki-A --id a --decision consent=accept
```

이제 양쪽 모두 통합 검색이 가능합니다. 한쪽에서 변경하고 push하면 반대편에서 `pull` 명령으로 동기화됩니다.

### 8.3 같은 머신의 두 wiki

별도 git 원격 없이 같은 머신의 두 폴더만 연결하려면 local 소스 사용:

```bash
cd ~/wiki-A
venv/bin/python tools/connected_wikis.py connect \
  /Users/me/wiki-B --id b --decision consent=accept
```

`pull`은 mtime 기반으로 변경 페이지를 감지합니다.

---

## 9. 자주 묻는 질문

**Q1. 외부 wiki에서 페이지를 추가/수정하면 자동으로 보이나요?**
아니요. `pull`을 명시적으로 실행해야 합니다. 자동화하려면 `/loop` 또는 cron으로 주기적 pull을 걸어두세요.

**Q2. 외부 wiki의 페이지가 로컬 wiki와 같은 이름이면 어떻게 되나요?**
별개의 ChromaDB 컬렉션에 저장되므로 충돌하지 않습니다. 검색 결과에 둘 다 노출되며 `[wiki: ...]` 라벨로 구분됩니다.

**Q3. 외부 wiki가 메타파일(`README.md`, `log.md`, `index.md`, `WIKI_SCHEMA.md`, `connected-wikis.json`)을 가지고 있으면?**
인덱싱에서 자동 제외됩니다. 외부 wiki 안의 `connected-wikis/` 하위(외부 wiki의 외부 wiki)도 제외됩니다.

**Q4. id 명명 규칙은?**
`^[a-z0-9]([a-z0-9-]{0,29}[a-z0-9])?$` — 소문자/숫자/하이픈, 31자 이내, 양 끝은 영숫자, 연속 하이픈 금지(`sp--ain` ❌). `wiki`/`local`/`ext`/`default`는 예약어.

**Q5. Windows에서도 되나요?**
v1은 POSIX 전용입니다. `fcntl.flock` 의존성 때문에 Linux/macOS에서만 동작합니다.

**Q6. 같은 id로 connect 도중에 LLM이 죽었어요. 다시 시도하면?**
같은 id + 같은 source로 다시 호출하면 자동으로 재개됩니다. 다른 source로 시도하면 명시적 에러 메시지로 거부합니다 (`disconnect`로 정리 후 재시도).

**Q7. JSON이 손상되면?**
`tools/connected_wikis.py`의 `load_config`이 `ConfigCorrupt` 예외를 던지면서 복구 힌트를 표시합니다. `git checkout connected-wikis.json`으로 이전 버전을 복원하거나, 파일을 삭제하면 빈 상태로 재시작됩니다.

---

## 10. 부록: 명령어 한눈에

| 명령 | 설명 |
|---|---|
| `connect <source> --id <id> [--name <n>] [--decision consent=accept]` | 외부 wiki 연결 |
| `list` | 연결된 wiki 목록 표 |
| `toggle <id> on\|off` | 검색 활성화 토글 |
| `pull [--decision mismatch=update\|reindex]` | 모든 외부 wiki 동기화 |
| `disconnect <id> [--decision disconnect-grep=proceed]` | 연결 해제 + 정리 |
| `init` | 수동 부트스트랩 (lazy로 자동 실행됨) |

| 종료 코드 | 의미 |
|---|---|
| `0` | 성공 |
| `1` | 일반 에러 (id 충돌, 경로 없음, reindex 실패 등) |
| `4` | 사용자 결정 필요 (`PROMPT:`/`OPTIONS:` 출력됨, `--decision`으로 재호출) |

전체 설계와 정책은 `docs/connected-knowledge-bases.md` 스펙을 참고하세요.
