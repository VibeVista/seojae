# Dev Log — 2026-07-16: 브랜치 정리 & PR 리뷰/머지

> 세션 목표: 미정리 브랜치들의 작업 상태를 파악하고, 진행 중인 작업을 마무리해 PR → 리뷰 → main 머지까지 정리. 진행 내용과 결정 사항을 기록.

## 시작 시점 저장소 상태

| 브랜치 | main 대비 | 내용 | 처리 |
|---|---|---|---|
| `claude/connected-knowledge-base-mnMN7` | +16 / -6 | connected-wikis 기능 전체 (M1–M3) | **PR #2 갱신 + review-pass-3 + 머지 대기** |
| `add-landing-page` | +2 / -3 | 랜딩페이지는 이미 머지(#3–#5), IR 통합 플랜 문서만 미병합 | **PR #7 생성** |
| `food-recipe` | +30 | 레시피 24건 ingest 등 개인 위키 콘텐츠 | 머지 안 함 (아래 결정 참조) |
| `spain-travel`, `develop` | +4 (동일 커밋) | 스페인 여행 콘텐츠 ingest | 머지 안 함 (동일) |
| `ui-kit-template` | +0 | main에 없는 커밋 없음 — 완전히 stale | 삭제 후보 |

- PR #2가 "docs: 1-pager" 제목으로 열려 있었으나 실제로는 기능 전체(+7,151줄)를 담고 있어 제목/본문을 실작업에 맞게 갱신함.

## PR #2 — Connected Knowledge Bases

1. `origin/main` 머지 (landing page 커밋과 충돌 없음), 기존 테스트 106개 통과 확인.
2. PR 제목/본문을 기능 전체를 반영하도록 갱신: `feat: Connected Knowledge Bases (connected-wikis) — multi-collection search, CLI, extension`.
3. **멀티 에이전트 리뷰** 실행: specialist 서브에이전트 4개(testing / maintainability / security / performance) + Claude adversarial + Codex adversarial + 메인 critical pass.
4. 확인된 발견을 **review-pass-3** 커밋(`9bedb9c`)으로 수정. 테스트 30개 추가, **총 136개 통과**.

### Review-pass-3에서 수정한 것 (교차 확인된 발견 위주)

**정확성**
- 증분 pull이 upstream에서 **삭제/리네임된 페이지를 인덱스에서 제거하지 못함** → 삭제/리네임 감지 시, diff 기반이 없을 때, 변경 파일이 `_INCREMENTAL_ADD_LIMIT`(10) 초과일 때 전체 reindex로 폴백. (Codex + adversarial 교차 확인 — 이번 리뷰 최대 성과)
- `--add` 경로가 `--reindex`의 메타파일 제외 규칙(`_should_index`)을 우회 → `--wiki-root` 플래그를 CLI부터 pull 경로까지 배선. (4개 소스 교차 확인)
- 파일당 서브프로세스가 ~470MB 임베딩 모델을 매번 재로딩 → 임계값 초과 시 단일 reindex로 전환.
- `git reset --hard` 실패가 성공적 pull로 보고되던 문제 → `_PullUnreachable`.
- `cmd_init` 실패를 하위 커맨드가 무시하던 문제, 잘못된 `last_pulled` 값으로 pull 전체가 죽던 문제 수정.

**안전성**
- config의 wiki id를 로드 시마다 형식 검증 — 손으로 수정/동기화된 config의 `"id": "../.git"` 같은 항목이 `shutil.rmtree`/lock 경로로 흘러가는 path traversal 차단. (Codex critical)
- README/index 프리뷰: symlink·소스 트리 밖 경로 거부, 2000자 제한 읽기, 터미널 제어문자 제거. 클론된 `wiki/`가 symlink면 연결 거부 (로컬 파일 임의 인덱싱 방지).
- `_git_commit`을 pathspec 범위로 제한 — 사용자가 스테이징해둔 무관한 파일이 자동 커밋에 휩쓸리지 않음. (존재하지 않는 pathspec이 커밋 전체를 실패시키는 버그도 테스트가 잡아서 함께 수정.)
- `git clone/fetch`에 `protocol.ext.allow=never` — `ext::sh -c` 트랜스포트 RCE 차단.
- lock 파일 unlink 제거 (flock inode 우회 창 제거). 자격증명 포함 URL 연결 시 경고.

**품질/성능**
- `--collections` 쿼리가 오타 컬렉션을 조용히 생성하던 것 → get-only + 경고 후 스킵.
- `chromadb` import 지연 로딩 — `--print-model`이 ~2초 → **0.03초**.
- `wiki-ext-{id}` 명명을 `_ext_collection_name()`으로 일원화.

### 의도된 설계로 수용 (수정 안 함)

- **크로스 컬렉션 점수 병합은 동일 임베딩 공간 가정** — 코드 레벨 강제 없음. 강제는 extension 문서의 LLM 절차(쿼리 전 `embedding_model` 일치 확인)에 있음. v2에서 코드 가드 검토 가치 있음.
- **pull이 consent 게이트 없이 재클론** — 커밋된 `connected-wikis.json` 자체가 신뢰 경계라는 설계. 다른 머신에서 config만 동기화된 경우 프리뷰 없이 클론됨을 인지할 것.
- **git 서브프로세스 타임아웃 없음** — 개인 도구 스케일에서 수용. 대형 저장소 연결 시 hang 가능성 있음.
- **reindex의 배치 인코딩 미적용** — `model.encode()`를 페이지당 호출. 수천 페이지 스케일에서 수 배 개선 여지 (future work).

## 브랜치 결정 사항

### 콘텐츠 브랜치(`food-recipe`, `spain-travel`, `develop`)는 main에 머지하지 않음

**이유**: 이 저장소의 main은 Seojae **프레임워크** (스키마·도구·확장·랜딩페이지)이고, 세 브랜치는 프레임워크를 실제로 사용한 **개인 위키 인스턴스** (레시피 24건, 스페인 여행 ingest 등). 콘텐츠를 main에 합치면 프레임워크 저장소가 개인 데이터로 오염되고, README가 약속하는 "빈 위키에서 시작" 경험이 깨진다. 세 브랜치의 프레임워크 관련 변경(.gitignore의 raw PDF 제외, CLAUDE.md 환경 설정)은 WIKI_SCHEMA.md가 안내하는 인스턴스별 설정이라 역시 main 대상이 아님.

- `develop`과 `spain-travel`은 커밋이 완전히 동일 — 사실상 중복 브랜치.
- `food-recipe`는 spain-travel 위에서 스페인 콘텐츠를 제거하고 레시피를 얹은 것.
- **권장**: 콘텐츠 브랜치는 그대로 두거나(데모/개인용), 별도 private 저장소로 옮기는 것. `develop`은 spain-travel과 중복이므로 삭제해도 정보 손실 없음.

### `ui-kit-template` 브랜치

main 대비 신규 커밋 0 — 삭제해도 아무것도 잃지 않음. (자동 삭제는 하지 않고 기록만 남김.)

### IR 통합 플랜 → PR #7

`add-landing-page`에 남아 있던 `IR_INTEGRATION_PLAN.md`를 `docs/plans/2026-04-30-ir-integration-plan.md`로 이동해 PR #7 생성. 문서-only. 머지 후 `add-landing-page` 브랜치는 삭제 가능.

## 미완료 / 사용자 액션 필요

- [ ] **PR #2 머지** — 자동 머지가 권한 정책(사람 승인 없는 self-merge 차단)으로 거부됨. 리뷰 요약은 PR 코멘트에 게시됨. 머지 후 `claude/connected-knowledge-base-mnMN7` 브랜치 삭제.
- [ ] **PR #7 머지** — 문서-only. 머지 후 `add-landing-page` 브랜치 삭제.
- [ ] (선택) `develop`, `ui-kit-template` 브랜치 삭제, 콘텐츠 브랜치 보관 방침 결정.

## 리뷰 방법론 메모 (다음에 참고)

- specialist 병렬 서브에이전트(4) + Claude adversarial + Codex adversarial 조합은 서로 다른 발견을 냈고, **교차 확인된 발견(삭제 미반영, 메타파일 필터 우회, 모델 재로딩)이 가장 신뢰도 높았다**.
- Codex `exec`는 stdin 리다이렉트(`< /dev/null`) 없이는 입력 대기로 hang — 스크립트에서 필수.
- 리뷰 2회를 이미 거친 코드에서도 3차 리뷰(관점을 바꾼)가 실질 이슈를 냈다: "리뷰 통과"보다 "관점 커버리지"가 중요.
