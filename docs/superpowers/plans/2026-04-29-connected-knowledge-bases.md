# Connected Knowledge Bases 구현 Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 외부 seojae wiki를 토글 가능한 확장 지식 저장소로 연결할 수 있게 하여, Query 워크플로우가 로컬 + 활성화된 외부 wiki들을 함께 검색하고 출처를 구분해 인용한다.

**Architecture:** `tools/search.py`를 multi-collection 지원으로 리팩터(M1) → 신규 `tools/connected_wikis.py` CLI로 connect/toggle/disconnect/pull/list 구현(M2) → `extensions/connected-wikis.md`에 워크플로우와 Query hook 정의(M3) → 수동 E2E 검증(M4). 외부 wiki는 `connected-wikis/<id>/`에 클론되며 `connected-wikis.json` 메타파일과 ChromaDB 컬렉션 `wiki-ext-<id>`로 격리된다.

**Tech Stack:** Python 3.9+, ChromaDB, sentence-transformers, PyYAML, POSIX `fcntl.flock`, git CLI, pytest.

**Spec Source:** `docs/connected-knowledge-bases.md` (이 문서가 모든 캐노니컬 정책의 단일 출처. 충돌 시 spec이 우선).

**Korean naming convention:** Spec과 동일하게 한국어 주석/메시지를 우선하되, 코드 식별자·CLI 인자·커밋 prefix는 영어. log/commit 메시지 prefix는 spec C/Critical Files 섹션을 따른다.

---

## File Structure

| 종류 | 경로 | 책임 |
|---|---|---|
| 수정 | `tools/search.py` | `COLLECTION_NAME`을 함수 인자로 매개변수화. `--collection`/`--collections`/`--print-model` CLI 추가. 외부 wiki 인덱싱 시 메타파일·중첩 디렉토리 제외 |
| 수정 | `tests/test_search.py` | 다중 컬렉션 add/reindex/query 케이스 + 메타파일 가드 + `--print-model` 컨트랙트 |
| 신규 | `tools/connected_wikis.py` | `connect`/`toggle`/`disconnect`/`pull`/`list`/`init` 서브커맨드 구현 |
| 신규 | `tests/test_connected_wikis.py` | 단위·통합 테스트 (id 검증, 락·동시성, 마이그레이션, 롤백, default branch, 인터랙션 프로토콜) |
| 신규 | `connected-wikis.json` | `{"schema_version": 1, "wikis": []}`로 시작, 커밋 |
| 신규 | `extensions/connected-wikis.md` | 본 확장 정의 (frontmatter + Setup + Workflows + Configuration + Query hook) |
| 수정 | `WIKI_SCHEMA.md` | Directory Rules 행 2개 추가, log actions에 `connect/toggle/disconnect/pull/extension` 추가, Git Commit Conventions에 신규 prefix 추가 |
| 수정 | `.gitignore` | `connected-wikis/`, `connected-wikis.lock` 추가 |

**Test fixture 구조** (`tests/test_connected_wikis.py`에 둠):
- `_make_collection(tmp_path, name)` — 단일 client에서 다중 컬렉션 생성
- `_fake_remote(tmp_path, branch="main", files=...)` — `git init`으로 임시 bare-like repo 생성하여 clone 가능한 fake remote 제공
- `_mock_model()` — `tests/test_search.py`에 이미 존재. 재사용

---

## Milestone Summary

- **M1 (Tasks 1.1–1.8)** — `tools/search.py` multi-collection 리팩터. backward-compatible.
- **M2 (Tasks 2.1–2.18, 2.17b)** — `tools/connected_wikis.py` CLI 구현.
- **M3 (Tasks 3.1–3.4)** — `extensions/connected-wikis.md` 작성, `WIKI_SCHEMA.md`/`.gitignore` 갱신.
- **M4 (Tasks 4.1–4.2)** — 샘플 외부 wiki로 수동 E2E 검증.

각 milestone 종료 시 `git push` 가능한 상태여야 한다.

---

# M1 — `tools/search.py` 다중 컬렉션화

목표: `COLLECTION_NAME` 상수를 함수 인자로 매개변수화하고 multi-collection 쿼리 함수를 추가. 기존 단일 컬렉션 호출자(코어 Query/Ingest/Reindex)는 byte-identical 동작 유지.

### Task 1.1: `get_collection()`에 `name` 파라미터 추가

**Files:**
- Modify: `tools/search.py:80-86`
- Test: `tests/test_search.py`

- [ ] **Step 1: failing 테스트 작성**

`tests/test_search.py`에 추가:

```python
def test_get_collection_default_name(tmp_path):
    from tools.search import get_collection
    c = get_collection(str(tmp_path / "idx"))
    assert c.name == "wiki"


def test_get_collection_custom_name(tmp_path):
    from tools.search import get_collection
    c = get_collection(str(tmp_path / "idx"), name="wiki-ext-spain")
    assert c.name == "wiki-ext-spain"


def test_get_collection_two_collections_same_path(tmp_path):
    """두 컬렉션이 동일 persistence 디렉토리에서 격리되는지 확인."""
    from tools.search import get_collection
    a = get_collection(str(tmp_path / "idx"), name="wiki")
    b = get_collection(str(tmp_path / "idx"), name="wiki-ext-spain")
    assert a.name != b.name
    assert a.count() == 0 and b.count() == 0
```

- [ ] **Step 2: 테스트 실패 확인**

```
venv/bin/python -m pytest tests/test_search.py::test_get_collection_custom_name -v
```
Expected: FAIL — `get_collection() got unexpected keyword argument 'name'`

- [ ] **Step 3: 구현**

`tools/search.py:80`을 다음으로 교체:

```python
def get_collection(index_path: str = INDEX_PATH, name: str = COLLECTION_NAME) -> chromadb.Collection:
    """Get or create the named ChromaDB collection with cosine similarity metric."""
    client = chromadb.PersistentClient(path=index_path)
    return client.get_or_create_collection(
        name=name,
        metadata={"hnsw:space": "cosine"},
    )
```

- [ ] **Step 4: 테스트 통과 확인**

```
venv/bin/python -m pytest tests/test_search.py -v
```
Expected: 모든 기존 테스트 + 신규 3개 PASS.

- [ ] **Step 5: Commit**

```bash
git add tools/search.py tests/test_search.py
git commit -m "refactor(search): parameterize get_collection() name"
```

---

### Task 1.2: `reindex()`에 `name` 파라미터 추가 + 메타파일 필터

**Files:**
- Modify: `tools/search.py:121-174`
- Test: `tests/test_search.py`

- [ ] **Step 1: failing 테스트 작성**

`tests/test_search.py`에 추가:

```python
def test_reindex_custom_collection_name(tmp_path):
    from tools.search import reindex
    import chromadb as _ch
    wiki = tmp_path / "wiki"
    wiki.mkdir()
    (wiki / "p.md").write_text("---\ntitle: P\ntags: []\n---\nBody", encoding="utf-8")

    idx = str(tmp_path / "idx")
    reindex(str(wiki), idx, _mock_model(), name="wiki-ext-foo")

    client = _ch.PersistentClient(path=idx)
    assert client.get_collection("wiki-ext-foo").count() == 1


def test_reindex_excludes_metafiles(tmp_path):
    """외부 wiki의 메타파일이 wiki/ 안에 섞여 있어도 필터로 제외."""
    from tools.search import reindex
    import chromadb as _ch
    wiki = tmp_path / "ext-wiki"
    wiki.mkdir()
    # wiki 루트 안의 정상 페이지 — 인덱싱됨
    (wiki / "real-page.md").write_text("---\ntitle: Real\ntags: []\n---\nBody", encoding="utf-8")
    # wiki/ 내부에 메타파일이 섞인 경우 (외부 wiki가 잘못 만들었을 수 있음) — 필터로 제외
    (wiki / "README.md").write_text("---\ntitle: R\ntags: []\n---\nBody", encoding="utf-8")
    (wiki / "log.md").write_text("---\ntitle: L\ntags: []\n---\nBody", encoding="utf-8")
    (wiki / "index.md").write_text("---\ntitle: I\ntags: []\n---\nBody", encoding="utf-8")
    (wiki / "WIKI_SCHEMA.md").write_text("---\ntitle: S\ntags: []\n---\nBody", encoding="utf-8")
    # wiki/ 내부에 중첩 connected-wikis 디렉토리 (외부 wiki의 외부 wiki) — 필터로 제외
    nested = wiki / "connected-wikis" / "other"
    nested.mkdir(parents=True)
    (nested / "leak.md").write_text("---\ntitle: L\ntags: []\n---\nBody", encoding="utf-8")

    idx = str(tmp_path / "idx")
    reindex(str(wiki), idx, _mock_model(), name="wiki-ext-bar")

    client = _ch.PersistentClient(path=idx)
    # real-page.md만 인덱싱, 메타파일 4개와 leak.md 1개는 모두 제외됨
    assert client.get_collection("wiki-ext-bar").count() == 1
```

- [ ] **Step 2: 테스트 실패 확인**

```
venv/bin/python -m pytest tests/test_search.py::test_reindex_custom_collection_name -v
```
Expected: FAIL — `reindex() got unexpected keyword argument 'name'`

- [ ] **Step 3: 구현**

`tools/search.py:121`을 다음으로 교체:

```python
# 외부 wiki 인덱싱 시 제외할 파일/디렉토리 (B 섹션 인덱싱 범위 규칙)
_EXCLUDED_FILENAMES = frozenset({
    "README.md", "log.md", "index.md", "WIKI_SCHEMA.md", "connected-wikis.json",
})


def _should_index(page: Path, wiki_root: Path) -> bool:
    """True if page is inside wiki_root and not a metafile/nested-connected-wikis path."""
    try:
        rel = page.resolve().relative_to(wiki_root.resolve())
    except ValueError:
        return False  # outside wiki_root: skip (defensive)
    parts = rel.parts
    if "connected-wikis" in parts:
        return False
    if page.name in _EXCLUDED_FILENAMES:
        return False
    return True


def reindex(wiki_path: str, index_path: str, model, name: str = COLLECTION_NAME) -> None:
    """Rebuild the named index from scratch."""
    client = chromadb.PersistentClient(path=index_path)
    try:
        client.delete_collection(name)
    except Exception:
        pass

    collection = client.get_or_create_collection(
        name=name, metadata={"hnsw:space": "cosine"}
    )

    wiki_root = Path(wiki_path)
    pages = [p for p in wiki_root.rglob("*.md") if _should_index(p, wiki_root)]
    success, skipped = 0, 0

    for page in pages:
        try:
            text = page.read_text(encoding="utf-8")
        except Exception as e:
            print(f"Warning: could not read {page}: {e}", file=sys.stderr)
            skipped += 1
            continue

        fm, body = parse_frontmatter(text)
        if not fm:
            print(f"Warning: {page} has no frontmatter, skipping", file=sys.stderr)
            skipped += 1
            continue

        try:
            embedding_text = build_embedding_text(fm, body)
            embedding = model.encode(embedding_text).tolist()
            try:
                doc_id = str(page.resolve().relative_to(Path(_REPO_ROOT).resolve()))
            except ValueError:
                doc_id = str(page)
            collection.upsert(
                ids=[doc_id],
                embeddings=[embedding],
                documents=[embedding_text],
                metadatas=[{"path": doc_id}],
            )
            success += 1
        except Exception as e:
            print(f"Warning: failed to index {page}: {e}", file=sys.stderr)
            skipped += 1

    print(f"Reindex complete: {success} pages indexed, {skipped} skipped")
```

- [ ] **Step 4: 테스트 통과 확인**

```
venv/bin/python -m pytest tests/test_search.py -v
```
Expected: 기존 테스트 모두 PASS + 신규 2개 PASS.

- [ ] **Step 5: Commit**

```bash
git add tools/search.py tests/test_search.py
git commit -m "refactor(search): parameterize reindex() name + exclude metafiles"
```

---

### Task 1.3: `add_page()`에 메타파일 가드 (defense-in-depth)

**Files:**
- Modify: `tools/search.py:89-118`
- Test: `tests/test_search.py`

- [ ] **Step 1: failing 테스트 작성**

```python
def test_add_page_skips_metafile_inside_wiki(tmp_path, capsys):
    """wiki/ 안에 메타파일이 섞여 있을 때 add_page도 방어적으로 skip."""
    from tools.search import add_page
    wiki = tmp_path / "wiki"
    wiki.mkdir()
    meta = wiki / "log.md"  # 일부러 wiki/ 안에 둔 metafile
    meta.write_text("---\ntitle: L\ntags: []\n---\nBody", encoding="utf-8")

    collection = _make_collection(tmp_path)
    model = _mock_model()
    add_page(str(meta), collection, model, wiki_root=str(wiki))

    assert collection.count() == 0
    assert "skipping metafile" in capsys.readouterr().err.lower()


def test_add_page_skips_outside_wiki_root(tmp_path, capsys):
    """wiki_root 밖 파일은 _should_index가 False → add_page도 skip (방어적)."""
    from tools.search import add_page
    wiki = tmp_path / "wiki"
    wiki.mkdir()
    outside = tmp_path / "elsewhere.md"
    outside.write_text("---\ntitle: O\ntags: []\n---\nBody", encoding="utf-8")

    collection = _make_collection(tmp_path)
    model = _mock_model()
    add_page(str(outside), collection, model, wiki_root=str(wiki))

    assert collection.count() == 0
    assert "skipping metafile" in capsys.readouterr().err.lower()


def test_add_page_no_wiki_root_indexes_anyway(tmp_path):
    """wiki_root 미지정 시 기존 동작 유지 (코어 Ingest 호환)."""
    from tools.search import add_page
    page = tmp_path / "p.md"
    page.write_text("---\ntitle: P\ntags: []\n---\nBody", encoding="utf-8")
    collection = _make_collection(tmp_path)
    model = _mock_model()
    add_page(str(page), collection, model)
    assert collection.count() == 1
```

- [ ] **Step 2: 실패 확인**

```
venv/bin/python -m pytest tests/test_search.py::test_add_page_skips_metafile -v
```
Expected: FAIL — `add_page() got unexpected keyword argument 'wiki_root'`

- [ ] **Step 3: 구현**

`tools/search.py:89` 시그니처를 변경하고 가드 추가:

```python
def add_page(filepath: str, collection: chromadb.Collection, model, wiki_root: str | None = None) -> None:
    """Add or update a single wiki page in the index (upsert by file path ID).

    If wiki_root is provided, metafiles and nested connected-wikis paths under it are skipped.
    """
    path = Path(filepath)
    if not path.exists():
        raise FileNotFoundError(f"{filepath} not found")

    if wiki_root is not None and not _should_index(path, Path(wiki_root)):
        print(f"Warning: skipping metafile {filepath}", file=sys.stderr)
        return

    text = path.read_text(encoding="utf-8")
    # ... (기존 로직 유지)
```

- [ ] **Step 4: 통과 확인**

```
venv/bin/python -m pytest tests/test_search.py -v
```

- [ ] **Step 5: Commit**

```bash
git add tools/search.py tests/test_search.py
git commit -m "refactor(search): add metafile guard to add_page"
```

---

### Task 1.4: 신규 `query_indexes()` multi-collection 머지 함수

**Files:**
- Modify: `tools/search.py` (신규 함수 추가, `query_index`는 손대지 않음 — byte-identical 보장)
- Test: `tests/test_search.py`

- [ ] **Step 1: failing 테스트 작성**

```python
def test_query_indexes_merges_by_score(tmp_path):
    """두 컬렉션 결과를 점수 내림차순으로 머지."""
    from tools.search import add_page, get_collection, query_indexes
    import chromadb as _ch

    idx = str(tmp_path / "idx")
    client = _ch.PersistentClient(path=idx)
    c_local = client.get_or_create_collection("wiki", metadata={"hnsw:space": "cosine"})
    c_ext = client.get_or_create_collection("wiki-ext-foo", metadata={"hnsw:space": "cosine"})

    p1 = tmp_path / "a.md"
    p1.write_text("---\ntitle: A\ntags: []\n---\nBody", encoding="utf-8")
    p2 = tmp_path / "b.md"
    p2.write_text("---\ntitle: B\ntags: []\n---\nBody", encoding="utf-8")

    add_page(str(p1), c_local, _mock_model())
    add_page(str(p2), c_ext, _mock_model())

    results = query_indexes("anything", top_n=5, collections=[c_local, c_ext], model=_mock_model())

    assert len(results) == 2
    paths = [r[0] for r in results]
    coll_names = [r[2] for r in results]
    assert "wiki" in coll_names and "wiki-ext-foo" in coll_names
    # 점수 내림차순
    assert results[0][1] >= results[1][1]


def test_query_indexes_empty_collections(tmp_path):
    from tools.search import query_indexes
    results = query_indexes("q", top_n=5, collections=[], model=_mock_model())
    assert results == []
```

- [ ] **Step 2: 실패 확인**

```
venv/bin/python -m pytest tests/test_search.py::test_query_indexes_merges_by_score -v
```
Expected: FAIL — `cannot import name 'query_indexes'`

- [ ] **Step 3: 구현**

`tools/search.py`의 `query_index` **다음 줄에** 추가 (기존 `query_index`는 변경 금지):

```python
def query_indexes(
    q: str,
    top_n: int,
    collections: list[chromadb.Collection],
    model,
) -> list[tuple[str, float, str]]:
    """Multi-collection search. Returns (path, score, collection_name) sorted by score desc.

    Each collection is queried for top_n candidates; results are merged and the global
    top_n is returned. Score = 1.0 - cosine distance (assumes shared embedding space).
    """
    if not collections:
        return []

    embedding = model.encode(q).tolist()
    merged: list[tuple[str, float, str]] = []
    for c in collections:
        count = c.count()
        if count == 0:
            continue
        res = c.query(query_embeddings=[embedding], n_results=min(top_n, count))
        for doc_id, distance in zip(res["ids"][0], res["distances"][0]):
            merged.append((doc_id, 1.0 - distance, c.name))

    merged.sort(key=lambda x: x[1], reverse=True)
    return merged[:top_n]
```

- [ ] **Step 4: 통과 확인**

```
venv/bin/python -m pytest tests/test_search.py -v
```

- [ ] **Step 5: Commit**

```bash
git add tools/search.py tests/test_search.py
git commit -m "feat(search): add query_indexes() for multi-collection search"
```

---

### Task 1.5: CLI에 `--collection` 플래그 추가 (`--add`, `--reindex`)

**Files:**
- Modify: `tools/search.py:204-252` (main CLI)
- Test: `tests/test_search.py`

- [ ] **Step 1: failing 테스트 작성**

```python
def test_cli_reindex_custom_collection(tmp_path):
    """--collection wiki-ext-X로 격리된 컬렉션 빌드."""
    wiki = tmp_path / "wiki"
    wiki.mkdir()
    (wiki / "p.md").write_text("---\ntitle: P\ntags: []\n---\nBody", encoding="utf-8")

    # 환경변수로 모델 다운로드 회피하려면 SKIP_MODEL_TESTS=true로 skip; 여기는 model 필요
    pytest.importorskip("sentence_transformers")
    if os.environ.get("SKIP_MODEL_TESTS", "false").lower() == "true":
        pytest.skip("requires real model download")

    idx = tmp_path / "idx"
    result = _run(["--reindex", "--wiki-path", str(wiki), "--collection", "wiki-ext-foo"], idx)
    assert result.returncode == 0

    import chromadb as _ch
    client = _ch.PersistentClient(path=str(idx))
    assert client.get_collection("wiki-ext-foo").count() == 1


def test_cli_reindex_isolation_preserves_default(tmp_path):
    """--reindex --collection wiki-ext-X가 'wiki' 컬렉션을 byte-identical 보존."""
    pytest.importorskip("sentence_transformers")
    if os.environ.get("SKIP_MODEL_TESTS", "false").lower() == "true":
        pytest.skip("requires real model download")

    wiki = tmp_path / "wiki"
    wiki.mkdir()
    (wiki / "local.md").write_text("---\ntitle: L\ntags: []\n---\nLocal body", encoding="utf-8")
    idx = tmp_path / "idx"

    # 1) 로컬 'wiki' 컬렉션 빌드
    r1 = _run(["--reindex", "--wiki-path", str(wiki)], idx)
    assert r1.returncode == 0

    import chromadb as _ch
    client = _ch.PersistentClient(path=str(idx))
    before_count = client.get_collection("wiki").count()
    before_ids = set(client.get_collection("wiki").get()["ids"])
    del client
    import gc; gc.collect()

    # 2) 외부 컬렉션 reindex
    ext = tmp_path / "ext"; ext.mkdir()
    (ext / "ext.md").write_text("---\ntitle: E\ntags: []\n---\nExt body", encoding="utf-8")
    r2 = _run(["--reindex", "--wiki-path", str(ext), "--collection", "wiki-ext-foo"], idx)
    assert r2.returncode == 0

    # 3) 'wiki' 컬렉션은 byte-identical
    client = _ch.PersistentClient(path=str(idx))
    after_count = client.get_collection("wiki").count()
    after_ids = set(client.get_collection("wiki").get()["ids"])
    assert before_count == after_count
    assert before_ids == after_ids
```

- [ ] **Step 2: 실패 확인**

```
venv/bin/python -m pytest tests/test_search.py::test_cli_reindex_custom_collection -v
```
Expected: FAIL — argparse `unrecognized arguments: --collection wiki-ext-foo`

- [ ] **Step 3: 구현**

`tools/search.py` `main()`의 argparse 설정에 추가:

```python
parser.add_argument("--collection", default=COLLECTION_NAME, metavar="NAME",
                    help="Collection name for --add/--reindex (default: wiki)")
parser.add_argument("--collections", default=None, metavar="LIST",
                    help="Comma-separated collection names for --query (default: wiki only)")
```

각 분기에서 `name=args.collection`을 사용하도록 변경:

```python
elif args.add is not None:
    from sentence_transformers import SentenceTransformer
    model = SentenceTransformer(MODEL_NAME)
    collection = get_collection(index_path, name=args.collection)
    try:
        add_page(args.add, collection, model)
    except FileNotFoundError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)

elif args.reindex:
    if not Path(args.wiki_path).exists():
        print(f"Error: wiki path not found: {args.wiki_path}", file=sys.stderr)
        sys.exit(1)
    from sentence_transformers import SentenceTransformer
    model = SentenceTransformer(MODEL_NAME)
    reindex(args.wiki_path, index_path, model, name=args.collection)
```

- [ ] **Step 4: 통과 확인**

```
venv/bin/python -m pytest tests/test_search.py -v
```

- [ ] **Step 5: Commit**

```bash
git add tools/search.py tests/test_search.py
git commit -m "feat(search): add --collection flag for --add/--reindex"
```

---

### Task 1.6: CLI `--query --collections` multi-collection 검색

**Files:**
- Modify: `tools/search.py` `main()` query 분기
- Test: `tests/test_search.py`

- [ ] **Step 1: failing 테스트 작성**

```python
@_needs_model
def test_cli_query_multi_collections(tmp_path):
    wiki = tmp_path / "wiki"
    wiki.mkdir()
    (wiki / "local.md").write_text("---\ntitle: Vibe\ntags: [ai]\n---\nLocal", encoding="utf-8")
    ext = tmp_path / "ext"; ext.mkdir()
    (ext / "spain.md").write_text("---\ntitle: Madrid\ntags: [travel]\n---\nMadrid info", encoding="utf-8")

    idx = tmp_path / "idx"
    _run(["--reindex", "--wiki-path", str(wiki)], idx)
    _run(["--reindex", "--wiki-path", str(ext), "--collection", "wiki-ext-spain"], idx)

    result = _run(["--query", "Madrid", "--top", "5",
                   "--collections", "wiki,wiki-ext-spain"], idx)
    assert result.returncode == 0
    # 출력 라인에 [wiki: <id>] 라벨이 포함됨
    assert "[wiki: " in result.stdout
    assert "wiki-ext-spain" in result.stdout
```

- [ ] **Step 2: 실패 확인**

```
venv/bin/python -m pytest tests/test_search.py::test_cli_query_multi_collections -v
```
Expected: FAIL — 출력 포맷이 다름.

- [ ] **Step 3: 구현**

`tools/search.py`의 query 분기를 다음으로 교체:

```python
if args.query is not None:
    if not args.query.strip():
        print("Error: --query requires a non-empty string", file=sys.stderr)
        sys.exit(1)
    if not Path(index_path).exists():
        print(
            f"Warning: {index_path} not found. Run: python tools/search.py --reindex",
            file=sys.stderr,
        )
        sys.exit(2)

    from sentence_transformers import SentenceTransformer
    model = SentenceTransformer(MODEL_NAME)

    if args.collections:
        names = [n.strip() for n in args.collections.split(",") if n.strip()]
        cols = [get_collection(index_path, name=n) for n in names]
        results = query_indexes(args.query, args.top, cols, model)
        for path, score, coll_name in results:
            print(f"{path} [wiki: {coll_name}] [score: {score:.2f}]")
    else:
        # 단일 컬렉션 — 기존 query_index 그대로 호출 → byte-identical
        collection = get_collection(index_path)
        results = query_index(args.query, args.top, collection, model)
        for path, score in results:
            print(f"{path} [score: {score:.2f}]")
```

- [ ] **Step 4: 통과 확인**

```
venv/bin/python -m pytest tests/test_search.py -v
```
회귀 테스트 (`test_cli_add_then_query`)도 통과해야 함 — `--collections` 미지정 분기는 byte-identical.

- [ ] **Step 5: Commit**

```bash
git add tools/search.py tests/test_search.py
git commit -m "feat(search): add --collections multi-collection query"
```

---

### Task 1.7: `--print-model` introspection 명령

**Files:**
- Modify: `tools/search.py` `main()` (mutually-exclusive group에 추가)
- Test: `tests/test_search.py`

- [ ] **Step 1: failing 테스트 작성**

```python
def test_cli_print_model_format(tmp_path):
    """--print-model은 정확히 두 줄 (backend=, model=) 출력."""
    result = _run(["--print-model"], tmp_path / "idx")
    assert result.returncode == 0
    lines = result.stdout.strip().split("\n")
    assert len(lines) == 2
    assert lines[0].startswith("backend=")
    assert lines[1].startswith("model=")
    assert "search-chromadb" in lines[0]
    assert "paraphrase-multilingual-MiniLM-L12-v2" in lines[1]
```

- [ ] **Step 2: 실패 확인**

```
venv/bin/python -m pytest tests/test_search.py::test_cli_print_model_format -v
```
Expected: FAIL.

- [ ] **Step 3: 구현**

`tools/search.py`의 mutually-exclusive group에 추가:

```python
group.add_argument("--print-model", action="store_true",
                   help="Print active backend/model identifiers (two lines)")
```

분기 처리 (다른 분기들 앞에서 처리):

```python
if args.print_model:
    print("backend=search-chromadb")
    print(f"model={MODEL_NAME}")
    return
```

- [ ] **Step 4: 통과 확인**

```
venv/bin/python -m pytest tests/test_search.py -v
```

- [ ] **Step 5: Commit**

```bash
git add tools/search.py tests/test_search.py
git commit -m "feat(search): add --print-model introspection"
```

---

### Task 1.8: 회귀 — 단일 컬렉션 byte-identical 검증

**Files:**
- Test: `tests/test_search.py`

- [ ] **Step 1: 회귀 테스트 추가**

```python
def test_query_index_byte_identical_signature():
    """query_index 시그니처가 변경되지 않았는지 — byte-identical 호환 보장."""
    import inspect
    from tools.search import query_index
    sig = inspect.signature(query_index)
    params = list(sig.parameters.keys())
    assert params == ["q", "top_n", "collection", "model"]


@_needs_model
def test_cli_query_single_collection_format_unchanged(tmp_path):
    """--collections 미지정 시 출력 포맷이 본 변경 이전과 byte-identical."""
    wiki = tmp_path / "wiki"
    wiki.mkdir()
    (wiki / "p.md").write_text("---\ntitle: Test\ntags: []\n---\nBody", encoding="utf-8")
    idx = tmp_path / "idx"
    _run(["--reindex", "--wiki-path", str(wiki)], idx)

    result = _run(["--query", "test", "--top", "1"], idx)
    assert result.returncode == 0
    line = result.stdout.strip().split("\n")[0]
    # 정확히 "<path> [score: X.XX]" — [wiki: ...] 라벨 없음
    assert "[wiki:" not in line
    assert "[score:" in line
```

- [ ] **Step 2: 통과 확인**

```
venv/bin/python -m pytest tests/test_search.py -v
```

- [ ] **Step 3: Commit**

```bash
git add tests/test_search.py
git commit -m "test(search): regression for single-collection byte-identical behavior"
```

---

# M2 — `tools/connected_wikis.py` CLI

목표: connect/toggle/disconnect/pull/list/init 서브커맨드 구현. atomic write + flock + 두-단계 reservation + 인터랙션 프로토콜 + 롤백 정책.

### Task 2.1: 모듈 스켈레톤 + JSON 헬퍼

**Files:**
- Create: `tools/connected_wikis.py`
- Create: `tests/test_connected_wikis.py`

- [ ] **Step 1: failing 테스트 작성**

`tests/test_connected_wikis.py` 신규:

```python
import json
import os
import sys
import subprocess
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from tools.connected_wikis import (
    load_config, save_config, DEFAULT_CONFIG, CONFIG_VERSION,
)


def test_load_config_missing_returns_default(tmp_path):
    cfg = load_config(tmp_path / "connected-wikis.json")
    assert cfg == DEFAULT_CONFIG
    assert cfg["schema_version"] == CONFIG_VERSION


def test_save_then_load_roundtrip(tmp_path):
    p = tmp_path / "connected-wikis.json"
    cfg = {"schema_version": 1, "wikis": [{"id": "foo", "name": "Foo", "enabled": True,
            "source_type": "git", "source": "https://x", "status": "ok",
            "added": "2026-04-29"}]}
    save_config(p, cfg)
    assert load_config(p) == cfg


def test_save_is_atomic(tmp_path):
    """tmp 파일 + os.replace로 원자적이어야 함 — 부분 쓰기 검증."""
    p = tmp_path / "connected-wikis.json"
    save_config(p, {"schema_version": 1, "wikis": []})
    # tmp 파일이 남지 않아야 함
    leftover = list(tmp_path.glob("*.tmp*"))
    assert leftover == []
```

- [ ] **Step 2: 실패 확인**

```
venv/bin/python -m pytest tests/test_connected_wikis.py -v
```
Expected: FAIL — module not found.

- [ ] **Step 3: 구현**

`tools/connected_wikis.py` 신규:

```python
"""Connected Knowledge Bases — manage external seojae wikis as toggleable sources.

See docs/connected-knowledge-bases.md for the canonical design.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

CONFIG_VERSION = 1
DEFAULT_CONFIG: dict = {"schema_version": CONFIG_VERSION, "wikis": []}

_REPO_ROOT = Path(__file__).parent.parent
CONFIG_PATH = _REPO_ROOT / "connected-wikis.json"
CONNECTED_DIR = _REPO_ROOT / "connected-wikis"
LOCK_DIR = CONNECTED_DIR / ".locks"
GLOBAL_LOCK = _REPO_ROOT / "connected-wikis.lock"


def load_config(path: Path) -> dict:
    """Read connected-wikis.json. Returns DEFAULT_CONFIG if missing.

    Performs in-memory field backfill (status, embedding_*) but does NOT write back —
    the next save_config() call persists backfilled values.
    """
    if not path.exists():
        return dict(DEFAULT_CONFIG, wikis=[])

    with path.open("r", encoding="utf-8") as f:
        cfg = json.load(f)

    cfg.setdefault("schema_version", CONFIG_VERSION)
    cfg.setdefault("wikis", [])
    for w in cfg["wikis"]:
        _backfill_wiki(w)
    return cfg


def _backfill_wiki(w: dict) -> None:
    """Add missing fields (status, embedding_backend, embedding_model)."""
    w.setdefault("status", "ok")
    if "embedding_backend" not in w or "embedding_model" not in w:
        backend, model = _resolve_active_model_or_none()
        w.setdefault("embedding_backend", backend)
        w.setdefault("embedding_model", model)


def _resolve_active_model_or_none() -> tuple[str | None, str | None]:
    """Return (backend, model) by calling tools/search.py --print-model. (None, None) on failure."""
    import subprocess
    try:
        r = subprocess.run(
            [sys.executable, str(_REPO_ROOT / "tools" / "search.py"), "--print-model"],
            capture_output=True, text=True, timeout=10,
        )
    except Exception:
        return (None, None)
    if r.returncode != 0:
        return (None, None)
    backend = model = None
    for line in r.stdout.strip().split("\n"):
        if line.startswith("backend="):
            backend = line[len("backend="):]
        elif line.startswith("model="):
            model = line[len("model="):]
    return (backend, model)


def save_config(path: Path, cfg: dict) -> None:
    """Atomic write: tmp file + fsync + os.replace."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with tmp.open("w", encoding="utf-8") as f:
        json.dump(cfg, f, indent=2, ensure_ascii=False)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, path)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="connected_wikis", description="Manage connected wikis")
    sub = parser.add_subparsers(dest="cmd", required=True)
    sub.add_parser("init", help="Initialize connected-wikis.json + .gitignore")
    sub.add_parser("list", help="List connected wikis")
    args = parser.parse_args(argv)
    # 추가 서브커맨드는 후속 task에서 채움
    if args.cmd == "init":
        return cmd_init()
    if args.cmd == "list":
        return cmd_list()
    return 2


def cmd_init() -> int:
    raise NotImplementedError  # Task 2.5


def cmd_list() -> int:
    raise NotImplementedError  # Task 2.6


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 4: 통과 확인**

```
venv/bin/python -m pytest tests/test_connected_wikis.py -v
```

- [ ] **Step 5: Commit**

```bash
git add tools/connected_wikis.py tests/test_connected_wikis.py
git commit -m "feat(connected-wikis): module skeleton + JSON config helpers"
```

---

### Task 2.2: 락 헬퍼 (글로벌 + per-wiki) — POSIX `fcntl.flock`

**Files:**
- Modify: `tools/connected_wikis.py`
- Test: `tests/test_connected_wikis.py`

- [ ] **Step 1: failing 테스트 작성**

```python
def test_global_lock_serializes_writes(tmp_path):
    """두 프로세스가 동시에 같은 JSON을 쓰면 직렬화돼야 한다."""
    import threading
    from tools.connected_wikis import with_global_lock, save_config, load_config

    cfg_path = tmp_path / "cfg.json"
    lock_path = tmp_path / "cfg.lock"
    save_config(cfg_path, {"schema_version": 1, "wikis": []})

    barrier = threading.Barrier(2)
    errors: list[Exception] = []

    def worker(wiki_id: str):
        try:
            barrier.wait()
            with with_global_lock(lock_path):
                cfg = load_config(cfg_path)
                cfg["wikis"].append({"id": wiki_id, "name": wiki_id, "enabled": True,
                                     "source_type": "local", "source": "/x",
                                     "status": "ok", "added": "2026-04-29"})
                save_config(cfg_path, cfg)
        except Exception as e:
            errors.append(e)

    t1 = threading.Thread(target=worker, args=("a",))
    t2 = threading.Thread(target=worker, args=("b",))
    t1.start(); t2.start(); t1.join(); t2.join()

    assert errors == []
    final = load_config(cfg_path)
    ids = {w["id"] for w in final["wikis"]}
    assert ids == {"a", "b"}  # 둘 다 살아있음 (직렬화 성공 — 잃지 않음)


def test_per_wiki_lock_blocks_concurrent_acquire(tmp_path):
    """같은 id로의 per-wiki 락은 두 번째 시도를 (non-blocking 시) 거절해야 한다."""
    from tools.connected_wikis import acquire_per_wiki_lock
    lock_dir = tmp_path / ".locks"
    lock_dir.mkdir()

    fd1 = acquire_per_wiki_lock(lock_dir, "foo", blocking=False)
    assert fd1 is not None
    fd2 = acquire_per_wiki_lock(lock_dir, "foo", blocking=False)
    assert fd2 is None
    os.close(fd1)
```

- [ ] **Step 2: 실패 확인**

```
venv/bin/python -m pytest tests/test_connected_wikis.py::test_global_lock_serializes_writes -v
```
Expected: FAIL — `cannot import name 'with_global_lock'`

- [ ] **Step 3: 구현**

`tools/connected_wikis.py`에 추가:

```python
import contextlib
import fcntl


@contextlib.contextmanager
def with_global_lock(lock_path: Path):
    """Hold an exclusive flock on lock_path for the duration of the with-block.

    Used for short read-modify-write sections on connected-wikis.json.
    POSIX-only (Windows not supported in v1).
    """
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(str(lock_path), os.O_RDWR | os.O_CREAT, 0o644)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX)
        yield
    finally:
        try:
            fcntl.flock(fd, fcntl.LOCK_UN)
        finally:
            os.close(fd)


def acquire_per_wiki_lock(lock_dir: Path, wiki_id: str, blocking: bool = True) -> int | None:
    """Acquire <lock_dir>/<wiki_id>.lock (LOCK_EX). Returns fd or None on failure (non-blocking)."""
    lock_dir.mkdir(parents=True, exist_ok=True)
    lock_path = lock_dir / f"{wiki_id}.lock"
    fd = os.open(str(lock_path), os.O_RDWR | os.O_CREAT, 0o644)
    flags = fcntl.LOCK_EX | (0 if blocking else fcntl.LOCK_NB)
    try:
        fcntl.flock(fd, flags)
        return fd
    except BlockingIOError:
        os.close(fd)
        return None


def release_per_wiki_lock(fd: int) -> None:
    try:
        fcntl.flock(fd, fcntl.LOCK_UN)
    finally:
        os.close(fd)
```

- [ ] **Step 4: 통과 확인**

```
venv/bin/python -m pytest tests/test_connected_wikis.py -v
```

- [ ] **Step 5: Commit**

```bash
git add tools/connected_wikis.py tests/test_connected_wikis.py
git commit -m "feat(connected-wikis): POSIX flock helpers (global + per-wiki)"
```

---

### Task 2.3: id 검증 (정규식 + 예약어 + 중복)

**Files:**
- Modify: `tools/connected_wikis.py`
- Test: `tests/test_connected_wikis.py`

- [ ] **Step 1: failing 테스트 작성**

```python
def test_validate_id_format():
    from tools.connected_wikis import validate_id, IdError
    # ok
    assert validate_id("spain-travel", []) is None
    assert validate_id("a", []) is None
    assert validate_id("a1b2", []) is None
    # bad: 대문자
    with pytest.raises(IdError):
        validate_id("Spain", [])
    # bad: trailing hyphen
    with pytest.raises(IdError):
        validate_id("spain-", [])
    # bad: leading hyphen
    with pytest.raises(IdError):
        validate_id("-spain", [])
    # bad: consecutive hyphens
    with pytest.raises(IdError):
        validate_id("sp--ain", [])
    # bad: 32 chars
    with pytest.raises(IdError):
        validate_id("a" * 32, [])
    # bad: reserved
    for r in ("wiki", "local", "ext", "default"):
        with pytest.raises(IdError):
            validate_id(r, [])
    # bad: duplicate
    existing = [{"id": "spain-travel"}]
    with pytest.raises(IdError):
        validate_id("spain-travel", existing)
```

- [ ] **Step 2: 실패 확인**

```
venv/bin/python -m pytest tests/test_connected_wikis.py::test_validate_id_format -v
```
Expected: FAIL.

- [ ] **Step 3: 구현**

`tools/connected_wikis.py`에 추가:

```python
import re

_ID_RE = re.compile(r"^[a-z0-9]([a-z0-9-]{0,29}[a-z0-9])?$")
_RESERVED_IDS = frozenset({"wiki", "local", "ext", "default"})


class IdError(ValueError):
    pass


def validate_id(wiki_id: str, existing_wikis: list[dict]) -> None:
    """Raise IdError on invalid id. Otherwise return None."""
    if not _ID_RE.match(wiki_id):
        raise IdError(
            f"invalid id '{wiki_id}': must match ^[a-z0-9]([a-z0-9-]{{0,29}}[a-z0-9])?$ "
            "(lowercase alphanumeric, hyphens allowed in middle, max 31 chars)"
        )
    if "--" in wiki_id:
        raise IdError(f"invalid id '{wiki_id}': consecutive hyphens not allowed")
    if wiki_id in _RESERVED_IDS:
        raise IdError(f"invalid id '{wiki_id}': reserved word")
    if any(w["id"] == wiki_id for w in existing_wikis):
        raise IdError(f"invalid id '{wiki_id}': already exists")
```

- [ ] **Step 4: 통과 확인**

```
venv/bin/python -m pytest tests/test_connected_wikis.py -v
```

- [ ] **Step 5: Commit**

```bash
git add tools/connected_wikis.py tests/test_connected_wikis.py
git commit -m "feat(connected-wikis): id validation"
```

---

### Task 2.4: 마이그레이션 (필드 보강) 단위 테스트

**Files:**
- Modify: `tools/connected_wikis.py` (이미 Task 2.1에 `_backfill_wiki` 있음)
- Test: `tests/test_connected_wikis.py`

- [ ] **Step 1: failing 테스트 작성**

```python
def test_load_config_backfills_status(tmp_path):
    """status 없으면 'ok'로 채움."""
    p = tmp_path / "cfg.json"
    p.write_text(json.dumps({
        "schema_version": 1,
        "wikis": [{"id": "x", "name": "X", "source_type": "local", "source": "/x",
                   "enabled": True, "added": "2026-04-29"}]
    }), encoding="utf-8")

    cfg = load_config(p)
    assert cfg["wikis"][0]["status"] == "ok"


def test_load_config_backfills_embedding_fields_when_print_model_succeeds(tmp_path, monkeypatch):
    """--print-model 성공 시 embedding_backend/model 채움."""
    from tools import connected_wikis as cw
    monkeypatch.setattr(cw, "_resolve_active_model_or_none",
                        lambda: ("search-chromadb", "paraphrase-multilingual-MiniLM-L12-v2"))
    p = tmp_path / "cfg.json"
    p.write_text(json.dumps({
        "schema_version": 1,
        "wikis": [{"id": "x", "name": "X", "source_type": "local", "source": "/x",
                   "enabled": True, "added": "2026-04-29", "status": "ok"}]
    }), encoding="utf-8")

    cfg = cw.load_config(p)
    assert cfg["wikis"][0]["embedding_backend"] == "search-chromadb"
    assert cfg["wikis"][0]["embedding_model"] == "paraphrase-multilingual-MiniLM-L12-v2"


def test_load_config_backfills_to_null_when_print_model_fails(tmp_path, monkeypatch):
    """--print-model 비-0 시 null sentinel."""
    from tools import connected_wikis as cw
    monkeypatch.setattr(cw, "_resolve_active_model_or_none", lambda: (None, None))
    p = tmp_path / "cfg.json"
    p.write_text(json.dumps({
        "schema_version": 1,
        "wikis": [{"id": "x", "name": "X", "source_type": "local", "source": "/x",
                   "enabled": True, "added": "2026-04-29", "status": "ok"}]
    }), encoding="utf-8")

    cfg = cw.load_config(p)
    assert cfg["wikis"][0]["embedding_backend"] is None
    assert cfg["wikis"][0]["embedding_model"] is None
```

- [ ] **Step 2: 통과 확인**

이미 Task 2.1의 `_backfill_wiki`에서 처리되므로 추가 구현 없이 통과해야 함. 실패하면 `_backfill_wiki` 로직 점검.

```
venv/bin/python -m pytest tests/test_connected_wikis.py -v
```

- [ ] **Step 3: Commit**

```bash
git add tests/test_connected_wikis.py
git commit -m "test(connected-wikis): migration backfill cases"
```

---

### Task 2.5: `init` 서브커맨드 (lazy 부트스트랩)

**Files:**
- Modify: `tools/connected_wikis.py`
- Test: `tests/test_connected_wikis.py`

- [ ] **Step 1: failing 테스트 작성**

```python
def test_init_aborts_without_wiki_dir(tmp_path, monkeypatch):
    """프로젝트가 부트스트랩되지 않은 경우 abort."""
    from tools import connected_wikis as cw
    monkeypatch.setattr(cw, "_REPO_ROOT", tmp_path)
    monkeypatch.setattr(cw, "CONFIG_PATH", tmp_path / "connected-wikis.json")
    monkeypatch.setattr(cw, "CONNECTED_DIR", tmp_path / "connected-wikis")
    monkeypatch.setattr(cw, "LOCK_DIR", tmp_path / "connected-wikis" / ".locks")
    monkeypatch.setattr(cw, "GLOBAL_LOCK", tmp_path / "connected-wikis.lock")
    # wiki/ 부재
    rc = cw.cmd_init()
    assert rc == 1


def test_init_creates_config_and_gitignore(tmp_path, monkeypatch, capsys):
    from tools import connected_wikis as cw
    (tmp_path / "wiki").mkdir()
    (tmp_path / ".gitignore").write_text("# existing\n", encoding="utf-8")
    monkeypatch.setattr(cw, "_REPO_ROOT", tmp_path)
    monkeypatch.setattr(cw, "CONFIG_PATH", tmp_path / "connected-wikis.json")
    monkeypatch.setattr(cw, "CONNECTED_DIR", tmp_path / "connected-wikis")
    monkeypatch.setattr(cw, "LOCK_DIR", tmp_path / "connected-wikis" / ".locks")
    monkeypatch.setattr(cw, "GLOBAL_LOCK", tmp_path / "connected-wikis.lock")

    rc = cw.cmd_init()
    assert rc == 0
    assert (tmp_path / "connected-wikis.json").exists()
    cfg = json.loads((tmp_path / "connected-wikis.json").read_text())
    assert cfg == {"schema_version": 1, "wikis": []}
    gi = (tmp_path / ".gitignore").read_text()
    assert "connected-wikis/" in gi
    assert "connected-wikis.lock" in gi


def test_init_idempotent(tmp_path, monkeypatch):
    from tools import connected_wikis as cw
    (tmp_path / "wiki").mkdir()
    (tmp_path / ".gitignore").write_text("connected-wikis/\nconnected-wikis.lock\n", encoding="utf-8")
    (tmp_path / "connected-wikis.json").write_text(
        json.dumps({"schema_version": 1, "wikis": []}), encoding="utf-8")
    monkeypatch.setattr(cw, "_REPO_ROOT", tmp_path)
    monkeypatch.setattr(cw, "CONFIG_PATH", tmp_path / "connected-wikis.json")
    monkeypatch.setattr(cw, "CONNECTED_DIR", tmp_path / "connected-wikis")
    monkeypatch.setattr(cw, "LOCK_DIR", tmp_path / "connected-wikis" / ".locks")
    monkeypatch.setattr(cw, "GLOBAL_LOCK", tmp_path / "connected-wikis.lock")

    rc = cw.cmd_init()
    assert rc == 0
    # .gitignore 중복 추가 안 됨
    gi_lines = (tmp_path / ".gitignore").read_text().split("\n")
    assert gi_lines.count("connected-wikis/") == 1
    assert gi_lines.count("connected-wikis.lock") == 1
```

- [ ] **Step 2: 실패 확인**

```
venv/bin/python -m pytest tests/test_connected_wikis.py::test_init_creates_config_and_gitignore -v
```
Expected: FAIL — `NotImplementedError`.

- [ ] **Step 3: 구현**

`cmd_init()` 교체:

```python
def cmd_init() -> int:
    """Lazy bootstrap. Idempotent."""
    wiki_dir = _REPO_ROOT / "wiki"
    if not wiki_dir.exists():
        print("Error: wiki/ directory not found. Run project init first.", file=sys.stderr)
        return 1

    # 1) connected-wikis.json
    if not CONFIG_PATH.exists():
        with with_global_lock(GLOBAL_LOCK):
            if not CONFIG_PATH.exists():
                save_config(CONFIG_PATH, dict(DEFAULT_CONFIG, wikis=[]))

    # 2) .gitignore (멱등)
    gi_path = _REPO_ROOT / ".gitignore"
    needed = ["connected-wikis/", "connected-wikis.lock"]
    if gi_path.exists():
        existing = set(gi_path.read_text(encoding="utf-8").split("\n"))
    else:
        existing = set()
    missing = [n for n in needed if n not in existing]
    if missing:
        with gi_path.open("a", encoding="utf-8") as f:
            for n in missing:
                f.write(f"{n}\n")

    print("connected-wikis initialized")
    return 0
```

- [ ] **Step 4: 통과 확인**

```
venv/bin/python -m pytest tests/test_connected_wikis.py -v
```

- [ ] **Step 5: Commit**

```bash
git add tools/connected_wikis.py tests/test_connected_wikis.py
git commit -m "feat(connected-wikis): init subcommand with lazy bootstrap"
```

---

### Task 2.6: `list` 서브커맨드 (markdown 표 출력)

**Files:**
- Modify: `tools/connected_wikis.py`
- Test: `tests/test_connected_wikis.py`

- [ ] **Step 1: failing 테스트 작성**

```python
def test_list_empty(tmp_path, monkeypatch, capsys):
    from tools import connected_wikis as cw
    (tmp_path / "wiki").mkdir()
    monkeypatch.setattr(cw, "_REPO_ROOT", tmp_path)
    monkeypatch.setattr(cw, "CONFIG_PATH", tmp_path / "connected-wikis.json")
    monkeypatch.setattr(cw, "CONNECTED_DIR", tmp_path / "connected-wikis")
    monkeypatch.setattr(cw, "LOCK_DIR", tmp_path / "connected-wikis" / ".locks")
    monkeypatch.setattr(cw, "GLOBAL_LOCK", tmp_path / "connected-wikis.lock")
    monkeypatch.setattr(cw, "INDEX_PATH", str(tmp_path / "search-index"))

    cw.cmd_init()
    rc = cw.cmd_list()
    out = capsys.readouterr().out
    assert rc == 0
    assert "| id |" in out  # 헤더
    assert "no connected wikis" in out.lower() or "0 wikis" in out.lower()


def test_list_renders_table_with_pages(tmp_path, monkeypatch, capsys):
    from tools import connected_wikis as cw
    import chromadb as _ch
    (tmp_path / "wiki").mkdir()
    idx = tmp_path / "search-index"
    client = _ch.PersistentClient(path=str(idx))
    coll = client.get_or_create_collection("wiki-ext-spain", metadata={"hnsw:space": "cosine"})
    coll.upsert(ids=["a"], embeddings=[[0.1] * 384], documents=["x"], metadatas=[{"path": "a"}])
    del client
    import gc; gc.collect()

    cfg_path = tmp_path / "connected-wikis.json"
    cfg_path.write_text(json.dumps({"schema_version": 1, "wikis": [
        {"id": "spain", "name": "Spain", "source_type": "git", "source": "https://x",
         "enabled": True, "status": "ok", "added": "2026-04-29",
         "embedding_backend": "search-chromadb",
         "embedding_model": "paraphrase-multilingual-MiniLM-L12-v2",
         "last_pulled": "2026-04-29"}
    ]}), encoding="utf-8")

    monkeypatch.setattr(cw, "_REPO_ROOT", tmp_path)
    monkeypatch.setattr(cw, "CONFIG_PATH", cfg_path)
    monkeypatch.setattr(cw, "CONNECTED_DIR", tmp_path / "connected-wikis")
    monkeypatch.setattr(cw, "LOCK_DIR", tmp_path / "connected-wikis" / ".locks")
    monkeypatch.setattr(cw, "GLOBAL_LOCK", tmp_path / "connected-wikis.lock")
    monkeypatch.setattr(cw, "INDEX_PATH", str(idx))

    rc = cw.cmd_list()
    out = capsys.readouterr().out
    assert rc == 0
    assert "spain" in out
    assert "wiki-ext-spain" not in out  # 컬렉션명이 아니라 id가 보여야 함
    # pages 컬럼에 0보다 큰 수
    lines = [l for l in out.split("\n") if "spain" in l and "|" in l]
    assert len(lines) >= 1
```

- [ ] **Step 2: 실패 확인**

```
venv/bin/python -m pytest tests/test_connected_wikis.py::test_list_renders_table_with_pages -v
```
Expected: FAIL — `NotImplementedError`.

- [ ] **Step 3: 구현**

`tools/connected_wikis.py`에 추가:

```python
INDEX_PATH = str(_REPO_ROOT / "search-index")  # 모듈 상수 (Task 2.6에서 도입)


def _collection_count(index_path: str, collection_name: str) -> int | None:
    """Return collection count or None if missing."""
    import chromadb
    try:
        client = chromadb.PersistentClient(path=index_path)
        return client.get_collection(collection_name).count()
    except Exception:
        return None


def cmd_list() -> int:
    cmd_init()  # lazy bootstrap

    cfg = load_config(CONFIG_PATH)
    wikis = cfg["wikis"]

    if not wikis:
        print("no connected wikis (0 wikis)")
        _print_help_examples()
        return 0

    # markdown 표
    cols = ["id", "name", "source_type", "enabled", "status",
            "last_pulled", "embedding_model", "pages"]
    print("| " + " | ".join(cols) + " |")
    print("|" + "|".join(["---"] * len(cols)) + "|")
    for w in wikis:
        count = _collection_count(INDEX_PATH, f"wiki-ext-{w['id']}")
        pages = "N/A" if count is None else str(count)
        row = [
            w["id"],
            w.get("name", ""),
            w.get("source_type", ""),
            "true" if w.get("enabled") else "false",
            w.get("status", ""),
            w.get("last_pulled", "—"),
            w.get("embedding_model") or "—",
            pages,
        ]
        print("| " + " | ".join(row) + " |")

    _print_help_examples()
    return 0


def _print_help_examples() -> None:
    print()
    print("Examples:")
    print('  connect <url-or-path> --id <id>')
    print('  toggle <id> on|off')
    print('  pull')
    print('  disconnect <id>')
```

argparse subparsers에 `init`은 이미 있음. 위 구현으로 `list` 분기 처리됨.

- [ ] **Step 4: 통과 확인**

```
venv/bin/python -m pytest tests/test_connected_wikis.py -v
```

- [ ] **Step 5: Commit**

```bash
git add tools/connected_wikis.py tests/test_connected_wikis.py
git commit -m "feat(connected-wikis): list subcommand with markdown table"
```

---

### Task 2.7: `toggle` 서브커맨드

**Files:**
- Modify: `tools/connected_wikis.py`
- Test: `tests/test_connected_wikis.py`

- [ ] **Step 1: failing 테스트 작성**

```python
def _setup_repo(tmp_path, monkeypatch, with_wiki=True):
    """Common test fixture: monkey-patch module paths to tmp_path."""
    from tools import connected_wikis as cw
    if with_wiki:
        (tmp_path / "wiki").mkdir(exist_ok=True)
    monkeypatch.setattr(cw, "_REPO_ROOT", tmp_path)
    monkeypatch.setattr(cw, "CONFIG_PATH", tmp_path / "connected-wikis.json")
    monkeypatch.setattr(cw, "CONNECTED_DIR", tmp_path / "connected-wikis")
    monkeypatch.setattr(cw, "LOCK_DIR", tmp_path / "connected-wikis" / ".locks")
    monkeypatch.setattr(cw, "GLOBAL_LOCK", tmp_path / "connected-wikis.lock")
    monkeypatch.setattr(cw, "INDEX_PATH", str(tmp_path / "search-index"))
    return cw


def test_toggle_flips_enabled(tmp_path, monkeypatch):
    cw = _setup_repo(tmp_path, monkeypatch)
    cw.cmd_init()
    save_config(cw.CONFIG_PATH, {"schema_version": 1, "wikis": [
        {"id": "x", "name": "X", "source_type": "local", "source": "/x",
         "enabled": True, "status": "ok", "added": "2026-04-29",
         "embedding_backend": None, "embedding_model": None}
    ]})

    rc = cw.cmd_toggle("x", "off")
    assert rc == 0
    cfg = cw.load_config(cw.CONFIG_PATH)
    assert cfg["wikis"][0]["enabled"] is False

    rc = cw.cmd_toggle("x", "on")
    cfg = cw.load_config(cw.CONFIG_PATH)
    assert cfg["wikis"][0]["enabled"] is True


def test_toggle_unknown_id_returns_1(tmp_path, monkeypatch):
    cw = _setup_repo(tmp_path, monkeypatch)
    cw.cmd_init()
    rc = cw.cmd_toggle("nope", "on")
    assert rc == 1
```

- [ ] **Step 2: 실패 확인**

```
venv/bin/python -m pytest tests/test_connected_wikis.py::test_toggle_flips_enabled -v
```
Expected: FAIL — `cmd_toggle` not defined.

- [ ] **Step 3: 구현**

argparse에 추가:

```python
p_tog = sub.add_parser("toggle", help="Enable/disable a wiki")
p_tog.add_argument("wiki_id")
p_tog.add_argument("state", choices=["on", "off"])
```

main 분기:

```python
if args.cmd == "toggle":
    return cmd_toggle(args.wiki_id, args.state)
```

함수:

```python
def cmd_toggle(wiki_id: str, state: str) -> int:
    cmd_init()
    with with_global_lock(GLOBAL_LOCK):
        cfg = load_config(CONFIG_PATH)
        for w in cfg["wikis"]:
            if w["id"] == wiki_id:
                w["enabled"] = (state == "on")
                save_config(CONFIG_PATH, cfg)
                _append_log(f"toggle | {wiki_id} {state}")
                _git_commit(f"config: toggle {wiki_id}")
                print(f"{wiki_id}: enabled={w['enabled']}")
                return 0
        print(f"Error: wiki '{wiki_id}' not found", file=sys.stderr)
        return 1


def _append_log(line: str) -> None:
    """Append `## [YYYY-MM-DD] <action> | ...` to log.md if it exists."""
    from datetime import date
    log_path = _REPO_ROOT / "log.md"
    if not log_path.exists():
        return
    with log_path.open("a", encoding="utf-8") as f:
        f.write(f"\n## [{date.today().isoformat()}] {line}\n")


def _git_commit(message: str) -> None:
    """Stage tracked changes and commit. Best-effort — silent on failure (dev environments)."""
    import subprocess
    try:
        subprocess.run(["git", "add", "connected-wikis.json", "log.md", ".gitignore"],
                       cwd=str(_REPO_ROOT), capture_output=True, check=False)
        subprocess.run(["git", "commit", "-m", message],
                       cwd=str(_REPO_ROOT), capture_output=True, check=False)
    except FileNotFoundError:
        pass
```

- [ ] **Step 4: 통과 확인**

```
venv/bin/python -m pytest tests/test_connected_wikis.py -v
```

- [ ] **Step 5: Commit**

```bash
git add tools/connected_wikis.py tests/test_connected_wikis.py
git commit -m "feat(connected-wikis): toggle subcommand"
```

---

### Task 2.8: 인터랙션 프로토콜 헬퍼 (`PROMPT:` + exit 4 + `--decision`)

**Files:**
- Modify: `tools/connected_wikis.py`
- Test: `tests/test_connected_wikis.py`

- [ ] **Step 1: failing 테스트 작성**

```python
def test_request_decision_exits_4_when_not_tty(monkeypatch, capsys):
    """non-TTY 환경에서 결정 요청 시 PROMPT/OPTIONS 출력하고 exit 4."""
    from tools.connected_wikis import request_decision, DecisionPending

    monkeypatch.setattr(sys.stdin, "isatty", lambda: False)
    with pytest.raises(DecisionPending):
        request_decision(prompt_key="consent",
                         question="Trust this wiki?",
                         options=["accept", "reject"],
                         decisions={})
    out = capsys.readouterr().out
    assert "PROMPT: consent | Trust this wiki?" in out
    assert "OPTIONS: accept reject" in out


def test_request_decision_returns_value_from_decisions():
    from tools.connected_wikis import request_decision
    val = request_decision(prompt_key="consent",
                           question="Trust?",
                           options=["accept", "reject"],
                           decisions={"consent": "accept"})
    assert val == "accept"


def test_request_decision_rejects_invalid_value():
    from tools.connected_wikis import request_decision, IdError  # reuse error type
    with pytest.raises(ValueError):
        request_decision(prompt_key="consent",
                         question="?",
                         options=["accept", "reject"],
                         decisions={"consent": "maybe"})
```

- [ ] **Step 2: 실패 확인**

```
venv/bin/python -m pytest tests/test_connected_wikis.py::test_request_decision_exits_4_when_not_tty -v
```
Expected: FAIL.

- [ ] **Step 3: 구현**

```python
EXIT_DECISION_PENDING = 4


class DecisionPending(SystemExit):
    """Raised when CLI needs an interactive decision; encoded as exit 4."""
    def __init__(self):
        super().__init__(EXIT_DECISION_PENDING)


def request_decision(*, prompt_key: str, question: str, options: list[str],
                     decisions: dict[str, str]) -> str:
    """Resolve an interactive decision.

    Three paths:
    1. decisions[prompt_key] present → validate against options, return.
    2. stdin is TTY → prompt with input(), return user's choice.
    3. else → print PROMPT/OPTIONS and raise DecisionPending (exit 4).
    """
    if prompt_key in decisions:
        val = decisions[prompt_key]
        if val not in options:
            raise ValueError(f"invalid decision for '{prompt_key}': '{val}' not in {options}")
        return val

    if sys.stdin.isatty():
        prompt = f"{question} [{'/'.join(options)}]: "
        while True:
            ans = input(prompt).strip()
            if ans in options:
                return ans
            print(f"Invalid. Choose: {options}")

    # Non-TTY: emit and signal
    print(f"PROMPT: {prompt_key} | {question}")
    print(f"OPTIONS: {' '.join(options)}")
    raise DecisionPending()


def parse_decisions(raw: list[str] | None) -> dict[str, str]:
    """Parse --decision key=value pairs into a dict."""
    out: dict[str, str] = {}
    if not raw:
        return out
    for entry in raw:
        if "=" not in entry:
            raise ValueError(f"--decision must be key=value, got '{entry}'")
        k, v = entry.split("=", 1)
        out[k.strip()] = v.strip()
    return out
```

argparse에 `--decision`을 connect/pull/disconnect 서브커맨드에 부착 (다음 task에서 사용).

- [ ] **Step 4: 통과 확인**

```
venv/bin/python -m pytest tests/test_connected_wikis.py -v
```

- [ ] **Step 5: Commit**

```bash
git add tools/connected_wikis.py tests/test_connected_wikis.py
git commit -m "feat(connected-wikis): interactive decision protocol"
```

---

### Task 2.9: `connect` 서브커맨드 — local source

먼저 더 단순한 local 경로부터. git 경로는 Task 2.10에서.

**Files:**
- Modify: `tools/connected_wikis.py`
- Test: `tests/test_connected_wikis.py`

- [ ] **Step 1: failing 테스트 작성**

```python
def test_connect_local_happy_path(tmp_path, monkeypatch):
    cw = _setup_repo(tmp_path, monkeypatch)
    cw.cmd_init()

    # 외부 wiki 디렉토리 준비
    ext = tmp_path / "ext"
    (ext / "wiki").mkdir(parents=True)
    (ext / "wiki" / "page.md").write_text("---\ntitle: Page\ntags: []\n---\nBody",
                                          encoding="utf-8")
    (ext / "README.md").write_text("Trust me", encoding="utf-8")

    # mock _resolve_active_model_or_none 성공
    monkeypatch.setattr(cw, "_resolve_active_model_or_none",
                        lambda: ("search-chromadb", "paraphrase-multilingual-MiniLM-L12-v2"))
    # mock reindex 호출 — 실제 모델 없이 fake collection 생성
    def _fake_reindex_subprocess(*args, **kwargs):
        import chromadb as _ch
        client = _ch.PersistentClient(path=str(tmp_path / "search-index"))
        coll = client.get_or_create_collection("wiki-ext-myext", metadata={"hnsw:space": "cosine"})
        coll.upsert(ids=["x"], embeddings=[[0.1] * 384], documents=["d"], metadatas=[{"path": "x"}])
        class R: returncode = 0; stdout = "Reindex complete: 1 pages indexed, 0 skipped"; stderr = ""
        return R()
    monkeypatch.setattr(cw, "_run_reindex", _fake_reindex_subprocess)

    rc = cw.cmd_connect(source=str(ext), wiki_id="myext", name=None,
                        source_type="local", decisions={"consent": "accept"})
    assert rc == 0
    cfg = cw.load_config(cw.CONFIG_PATH)
    assert len(cfg["wikis"]) == 1
    w = cfg["wikis"][0]
    assert w["id"] == "myext"
    assert w["source_type"] == "local"
    assert w["status"] == "ok"
    assert w["enabled"] is True
    assert w["embedding_backend"] == "search-chromadb"


def test_connect_local_path_missing(tmp_path, monkeypatch):
    cw = _setup_repo(tmp_path, monkeypatch)
    cw.cmd_init()
    rc = cw.cmd_connect(source="/nonexistent/path", wiki_id="x",
                        name=None, source_type="local", decisions={"consent": "accept"})
    assert rc == 1
    assert cw.load_config(cw.CONFIG_PATH)["wikis"] == []


def test_connect_local_no_wiki_subdir(tmp_path, monkeypatch):
    cw = _setup_repo(tmp_path, monkeypatch)
    cw.cmd_init()
    bad = tmp_path / "bad"
    bad.mkdir()
    rc = cw.cmd_connect(source=str(bad), wiki_id="x",
                        name=None, source_type="local", decisions={"consent": "accept"})
    assert rc == 1
    assert cw.load_config(cw.CONFIG_PATH)["wikis"] == []


def test_connect_consent_required_emits_prompt(tmp_path, monkeypatch, capsys):
    cw = _setup_repo(tmp_path, monkeypatch)
    cw.cmd_init()
    ext = tmp_path / "ext"
    (ext / "wiki").mkdir(parents=True)
    (ext / "wiki" / "p.md").write_text("---\ntitle: P\ntags: []\n---\nBody", encoding="utf-8")
    monkeypatch.setattr(sys.stdin, "isatty", lambda: False)

    with pytest.raises(SystemExit) as exc:
        cw.cmd_connect(source=str(ext), wiki_id="x",
                       name=None, source_type="local", decisions={})
    assert exc.value.code == 4
    out = capsys.readouterr().out
    assert "PROMPT: consent" in out
```

- [ ] **Step 2: 실패 확인**

```
venv/bin/python -m pytest tests/test_connected_wikis.py::test_connect_local_happy_path -v
```
Expected: FAIL.

- [ ] **Step 3: 구현**

argparse:

```python
p_conn = sub.add_parser("connect", help="Connect an external wiki")
p_conn.add_argument("source", help="Git URL or local path")
p_conn.add_argument("--id", dest="wiki_id", required=True)
p_conn.add_argument("--name", default=None)
p_conn.add_argument("--source-type", choices=["git", "local"], default=None,
                    help="Auto-detected from source (https://* → git, else local)")
p_conn.add_argument("--decision", action="append", dest="decisions", default=[])
```

main 분기:

```python
if args.cmd == "connect":
    return cmd_connect(args.source, args.wiki_id, args.name,
                       args.source_type, parse_decisions(args.decisions))
```

함수:

```python
from datetime import date


def _infer_source_type(source: str) -> str:
    if source.startswith(("http://", "https://", "git@", "ssh://", "git://")):
        return "git"
    return "local"


def _infer_name(source: str, source_type: str) -> str:
    if source_type == "git":
        # https://host/owner/repo(.git) → repo
        slug = source.rstrip("/").split("/")[-1]
        return slug[:-4] if slug.endswith(".git") else slug
    return Path(source).name


def _run_reindex(wiki_path: str, collection: str):
    """Run tools/search.py --reindex --collection <collection>. Override-able for tests."""
    import subprocess
    return subprocess.run(
        [sys.executable, str(_REPO_ROOT / "tools" / "search.py"),
         "--reindex", "--wiki-path", wiki_path, "--collection", collection],
        capture_output=True, text=True,
    )


def _delete_collection(name: str) -> None:
    import chromadb
    try:
        client = chromadb.PersistentClient(path=INDEX_PATH)
        client.delete_collection(name)
    except Exception:
        pass


def cmd_connect(source: str, wiki_id: str, name: str | None,
                source_type: str | None, decisions: dict[str, str]) -> int:
    cmd_init()

    if source_type is None:
        source_type = _infer_source_type(source)
    if name is None:
        name = _infer_name(source, source_type)
    today = date.today().isoformat()
    coll_name = f"wiki-ext-{wiki_id}"
    clone_dir = CONNECTED_DIR / wiki_id

    # 1) id 검증 (reservation 전, cleanup 불필요)
    cfg = load_config(CONFIG_PATH)
    try:
        validate_id(wiki_id, cfg["wikis"])
    except IdError as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1

    # 2) Two-phase reservation
    with with_global_lock(GLOBAL_LOCK):
        cfg = load_config(CONFIG_PATH)
        # double-check (다른 프로세스가 그 사이에 reserve했을 수도)
        if any(w["id"] == wiki_id for w in cfg["wikis"]):
            print(f"Error: id '{wiki_id}' already reserved", file=sys.stderr)
            return 1
        cfg["wikis"].append({
            "id": wiki_id, "name": name, "source_type": source_type, "source": source,
            "enabled": True, "status": "connecting", "added": today,
            "embedding_backend": None, "embedding_model": None,
        })
        save_config(CONFIG_PATH, cfg)

    lock_fd = acquire_per_wiki_lock(LOCK_DIR, wiki_id, blocking=True)
    try:
        # 3) 클론/접근 + 구조 검증
        if source_type == "local":
            if not Path(source).exists():
                _rollback_connect(wiki_id, coll_name, clone_dir, source_type)
                print(f"Error: local path not found: {source}", file=sys.stderr)
                return 1
            wiki_subdir = Path(source) / "wiki"
        else:  # git
            return _connect_git_phase(source, wiki_id, name, today, decisions, lock_fd)
            # ↑ Task 2.10에서 채움 — 여기서는 local만 처리

        if not wiki_subdir.exists() or not any(wiki_subdir.glob("*.md")):
            _rollback_connect(wiki_id, coll_name, clone_dir, source_type)
            print(f"Error: source has no wiki/*.md: {wiki_subdir}", file=sys.stderr)
            return 1

        # 4) 신뢰 경계 동의
        readme = (Path(source) / "README.md") if (Path(source) / "README.md").exists() \
                 else (wiki_subdir / "index.md") if (wiki_subdir / "index.md").exists() else None
        readme_preview = readme.read_text(encoding="utf-8")[:2000] if readme else "(no README/index.md)"
        print(f"--- {readme.name if readme else 'preview'} ---\n{readme_preview}\n--- end ---")
        try:
            decision = request_decision(
                prompt_key="consent",
                question=f"Trust external wiki '{wiki_id}' content? It will be indexed but not executed.",
                options=["accept", "reject"],
                decisions=decisions,
            )
        except DecisionPending:
            # CLI가 exit 4로 끝나도 reservation은 디스크에 남아 idempotent 재호출 가능
            raise
        if decision != "accept":
            _rollback_connect(wiki_id, coll_name, clone_dir, source_type)
            print("Connect aborted: consent rejected", file=sys.stderr)
            return 1

        # 5) embedding model 식별
        backend, model = _resolve_active_model_or_none()
        if backend is None or model is None:
            _rollback_connect(wiki_id, coll_name, clone_dir, source_type)
            print("Error: no active search-backend extension. "
                  "Enable extensions/search-chromadb.md or another search-backend provider.",
                  file=sys.stderr)
            return 1

        # 6) reindex
        r = _run_reindex(str(wiki_subdir), coll_name)
        if r.returncode != 0:
            _rollback_connect(wiki_id, coll_name, clone_dir, source_type)
            print(f"Error: reindex failed: {r.stderr}", file=sys.stderr)
            return 1
        if "skipped" in r.stdout:
            # Reindex complete: N pages indexed, M skipped
            import re as _re
            m = _re.search(r"(\d+) pages indexed, (\d+) skipped", r.stdout)
            if m and int(m.group(2)) > 0:
                print(f"Note: {m.group(2)} pages skipped during reindex", file=sys.stderr)

        # 7) status: connecting → ok + 메타 갱신
        with with_global_lock(GLOBAL_LOCK):
            cfg = load_config(CONFIG_PATH)
            for w in cfg["wikis"]:
                if w["id"] == wiki_id:
                    w["status"] = "ok"
                    w["embedding_backend"] = backend
                    w["embedding_model"] = model
            save_config(CONFIG_PATH, cfg)

        _append_log(f"connect | {wiki_id}")
        _git_commit(f"connect: {wiki_id}")
        print(f"Connected: {wiki_id}")
        return 0
    finally:
        release_per_wiki_lock(lock_fd)


def _rollback_connect(wiki_id: str, coll_name: str, clone_dir: Path, source_type: str) -> None:
    """Idempotent rollback (spec 'common abort policy')."""
    import shutil
    # 1) ChromaDB 컬렉션 삭제
    try:
        _delete_collection(coll_name)
    except Exception as e:
        print(f"Rollback: collection delete failed: {e}", file=sys.stderr)
    # 2) 클론 디렉토리 삭제 (git만)
    if source_type == "git":
        try:
            if clone_dir.exists():
                shutil.rmtree(clone_dir)
        except Exception as e:
            print(f"Rollback: clone dir delete failed: {e}", file=sys.stderr)
    # 3) JSON 항목 제거
    try:
        with with_global_lock(GLOBAL_LOCK):
            cfg = load_config(CONFIG_PATH)
            cfg["wikis"] = [w for w in cfg["wikis"] if w["id"] != wiki_id]
            save_config(CONFIG_PATH, cfg)
    except Exception as e:
        print(f"Rollback: JSON cleanup failed: {e}", file=sys.stderr)
    # 4) lock 파일 삭제
    try:
        (LOCK_DIR / f"{wiki_id}.lock").unlink(missing_ok=True)
    except Exception:
        pass


def _connect_git_phase(*args, **kwargs) -> int:
    raise NotImplementedError  # Task 2.10
```

- [ ] **Step 4: 통과 확인**

```
venv/bin/python -m pytest tests/test_connected_wikis.py -v
```

- [ ] **Step 5: Commit**

```bash
git add tools/connected_wikis.py tests/test_connected_wikis.py
git commit -m "feat(connected-wikis): connect subcommand for local sources + rollback"
```

---

### Task 2.10: `connect` — git source (clone + default branch)

**Files:**
- Modify: `tools/connected_wikis.py`
- Test: `tests/test_connected_wikis.py`

- [ ] **Step 1: failing 테스트 작성** (fake remote 사용)

```python
def _make_fake_remote(tmp_path: Path, branch: str = "main") -> Path:
    """Create a local git repo that can be cloned. Returns path."""
    import subprocess as sp
    repo = tmp_path / "fake-remote"
    repo.mkdir()
    sp.run(["git", "init", "-b", branch], cwd=repo, check=True, capture_output=True)
    sp.run(["git", "config", "user.email", "t@t"], cwd=repo, check=True, capture_output=True)
    sp.run(["git", "config", "user.name", "t"], cwd=repo, check=True, capture_output=True)
    (repo / "wiki").mkdir()
    (repo / "wiki" / "p.md").write_text("---\ntitle: P\ntags: []\n---\nBody", encoding="utf-8")
    (repo / "README.md").write_text("Trust me", encoding="utf-8")
    sp.run(["git", "add", "."], cwd=repo, check=True, capture_output=True)
    sp.run(["git", "commit", "-m", "init"], cwd=repo, check=True, capture_output=True)
    return repo


def test_connect_git_happy_path(tmp_path, monkeypatch):
    cw = _setup_repo(tmp_path, monkeypatch)
    cw.cmd_init()
    remote = _make_fake_remote(tmp_path)

    monkeypatch.setattr(cw, "_resolve_active_model_or_none",
                        lambda: ("search-chromadb", "paraphrase-multilingual-MiniLM-L12-v2"))

    def _fake_reindex(wiki_path, coll):
        import chromadb as _ch
        client = _ch.PersistentClient(path=cw.INDEX_PATH)
        c = client.get_or_create_collection(coll, metadata={"hnsw:space": "cosine"})
        c.upsert(ids=["x"], embeddings=[[0.1] * 384], documents=["d"], metadatas=[{"path": "x"}])
        class R: returncode = 0; stdout = "Reindex complete: 1 pages indexed, 0 skipped"; stderr = ""
        return R()
    monkeypatch.setattr(cw, "_run_reindex", _fake_reindex)

    rc = cw.cmd_connect(source=str(remote), wiki_id="g", name=None,
                        source_type="git", decisions={"consent": "accept"})
    assert rc == 0
    assert (tmp_path / "connected-wikis" / "g" / "wiki" / "p.md").exists()
    cfg = cw.load_config(cw.CONFIG_PATH)
    assert cfg["wikis"][0]["status"] == "ok"
    assert "commit" in cfg["wikis"][0]


@pytest.mark.parametrize("branch", ["main", "master", "trunk"])
def test_connect_git_default_branch_detection(tmp_path, monkeypatch, branch):
    cw = _setup_repo(tmp_path, monkeypatch)
    cw.cmd_init()
    remote = _make_fake_remote(tmp_path, branch=branch)

    monkeypatch.setattr(cw, "_resolve_active_model_or_none",
                        lambda: ("search-chromadb", "paraphrase-multilingual-MiniLM-L12-v2"))

    def _fake_reindex(wiki_path, coll):
        class R: returncode = 0; stdout = "Reindex complete: 0 pages indexed, 0 skipped"; stderr = ""
        return R()
    monkeypatch.setattr(cw, "_run_reindex", _fake_reindex)

    rc = cw.cmd_connect(source=str(remote), wiki_id=f"g{branch}", name=None,
                        source_type="git", decisions={"consent": "accept"})
    assert rc == 0
    detected = cw._detect_default_branch(tmp_path / "connected-wikis" / f"g{branch}")
    assert detected == branch


def test_connect_git_rollback_on_reindex_failure(tmp_path, monkeypatch):
    cw = _setup_repo(tmp_path, monkeypatch)
    cw.cmd_init()
    remote = _make_fake_remote(tmp_path)

    monkeypatch.setattr(cw, "_resolve_active_model_or_none",
                        lambda: ("search-chromadb", "paraphrase-multilingual-MiniLM-L12-v2"))

    def _fail_reindex(wiki_path, coll):
        class R: returncode = 1; stdout = ""; stderr = "boom"
        return R()
    monkeypatch.setattr(cw, "_run_reindex", _fail_reindex)

    rc = cw.cmd_connect(source=str(remote), wiki_id="g", name=None,
                        source_type="git", decisions={"consent": "accept"})
    assert rc == 1
    # 모든 cleanup이 byte-identical로 이전 상태 회복
    assert cw.load_config(cw.CONFIG_PATH)["wikis"] == []
    assert not (tmp_path / "connected-wikis" / "g").exists()
```

- [ ] **Step 2: 실패 확인**

```
venv/bin/python -m pytest tests/test_connected_wikis.py::test_connect_git_happy_path -v
```
Expected: FAIL — `NotImplementedError`.

- [ ] **Step 3: 구현**

Task 2.9의 `cmd_connect`을 다음 **전체 본문으로 교체**한다. `_connect_git_phase` stub은 함께 제거.

```python
def cmd_connect(source: str, wiki_id: str, name: str | None,
                source_type: str | None, decisions: dict[str, str]) -> int:
    cmd_init()

    if source_type is None:
        source_type = _infer_source_type(source)
    if name is None:
        name = _infer_name(source, source_type)
    today = date.today().isoformat()
    coll_name = f"wiki-ext-{wiki_id}"
    clone_dir = CONNECTED_DIR / wiki_id

    # 1) id 검증 (reservation 전이므로 cleanup 불필요)
    cfg = load_config(CONFIG_PATH)
    try:
        validate_id(wiki_id, cfg["wikis"])
    except IdError as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1

    # 2) Two-phase reservation — status="connecting"으로 슬롯 선점
    with with_global_lock(GLOBAL_LOCK):
        cfg = load_config(CONFIG_PATH)
        if any(w["id"] == wiki_id for w in cfg["wikis"]):
            print(f"Error: id '{wiki_id}' already reserved", file=sys.stderr)
            return 1
        cfg["wikis"].append({
            "id": wiki_id, "name": name, "source_type": source_type, "source": source,
            "enabled": True, "status": "connecting", "added": today,
            "embedding_backend": None, "embedding_model": None,
        })
        save_config(CONFIG_PATH, cfg)

    lock_fd = acquire_per_wiki_lock(LOCK_DIR, wiki_id, blocking=True)
    try:
        # 3) 클론 또는 로컬 접근
        if source_type == "git":
            clone_dir.parent.mkdir(parents=True, exist_ok=True)
            import subprocess as _sp
            r = _sp.run(["git", "clone", source, str(clone_dir)],
                        capture_output=True, text=True)
            if r.returncode != 0:
                _rollback_connect(wiki_id, coll_name, clone_dir, source_type)
                print(f"Error: git clone failed: {r.stderr}", file=sys.stderr)
                return 1
            wiki_subdir = clone_dir / "wiki"
        else:  # local
            if not Path(source).exists():
                _rollback_connect(wiki_id, coll_name, clone_dir, source_type)
                print(f"Error: local path not found: {source}", file=sys.stderr)
                return 1
            wiki_subdir = Path(source) / "wiki"

        # 4) seojae 구조 검증
        if not wiki_subdir.exists() or not any(wiki_subdir.glob("*.md")):
            _rollback_connect(wiki_id, coll_name, clone_dir, source_type)
            print(f"Error: source has no wiki/*.md: {wiki_subdir}", file=sys.stderr)
            return 1

        # 5) 신뢰 경계 동의 (PROMPT/exit 4 또는 stdin 폴백)
        readme_root = clone_dir if source_type == "git" else Path(source)
        readme = (readme_root / "README.md") if (readme_root / "README.md").exists() \
                 else (wiki_subdir / "index.md") if (wiki_subdir / "index.md").exists() \
                 else None
        readme_preview = readme.read_text(encoding="utf-8")[:2000] if readme else "(no README/index.md)"
        print(f"--- {readme.name if readme else 'preview'} ---\n{readme_preview}\n--- end ---")
        decision = request_decision(
            prompt_key="consent",
            question=f"Trust external wiki '{wiki_id}' content? It will be indexed as data, not executed.",
            options=["accept", "reject"],
            decisions=decisions,
        )
        if decision != "accept":
            _rollback_connect(wiki_id, coll_name, clone_dir, source_type)
            print("Connect aborted: consent rejected", file=sys.stderr)
            return 1

        # 6) embedding backend/model 식별
        backend, model = _resolve_active_model_or_none()
        if backend is None or model is None:
            _rollback_connect(wiki_id, coll_name, clone_dir, source_type)
            print("Error: no active search-backend extension. "
                  "Enable extensions/search-chromadb.md or another search-backend provider.",
                  file=sys.stderr)
            return 1

        # 7) reindex into wiki-ext-<id>
        r = _run_reindex(str(wiki_subdir), coll_name)
        if r.returncode != 0:
            _rollback_connect(wiki_id, coll_name, clone_dir, source_type)
            print(f"Error: reindex failed: {r.stderr}", file=sys.stderr)
            return 1
        import re as _re
        m = _re.search(r"(\d+) pages indexed, (\d+) skipped", r.stdout)
        if m and int(m.group(2)) > 0:
            print(f"Note: {m.group(2)} pages skipped during reindex", file=sys.stderr)

        # 8) connecting → ok, 메타 갱신 (git이면 commit hash 포함)
        commit_hash = _git_head_sha(clone_dir) if source_type == "git" else None
        with with_global_lock(GLOBAL_LOCK):
            cfg = load_config(CONFIG_PATH)
            for w in cfg["wikis"]:
                if w["id"] == wiki_id:
                    w["status"] = "ok"
                    w["embedding_backend"] = backend
                    w["embedding_model"] = model
                    w["last_pulled"] = today
                    if commit_hash:
                        w["commit"] = commit_hash
            save_config(CONFIG_PATH, cfg)

        _append_log(f"connect | {wiki_id}")
        _git_commit(f"connect: {wiki_id}")
        print(f"Connected: {wiki_id}")
        return 0
    finally:
        release_per_wiki_lock(lock_fd)
```

`_detect_default_branch` 헬퍼:

```python
def _detect_default_branch(repo_dir: Path) -> str:
    """Detect via `git symbolic-ref refs/remotes/origin/HEAD`. Falls back to `main`."""
    import subprocess as _sp
    for attempt in range(2):
        r = _sp.run(["git", "symbolic-ref", "refs/remotes/origin/HEAD"],
                    cwd=str(repo_dir), capture_output=True, text=True)
        if r.returncode == 0:
            ref = r.stdout.strip()
            return ref.removeprefix("refs/remotes/origin/")
        if attempt == 0:
            _sp.run(["git", "remote", "set-head", "origin", "--auto"],
                    cwd=str(repo_dir), capture_output=True)
    return "main"


def _git_head_sha(repo_dir: Path) -> str:
    import subprocess as _sp
    r = _sp.run(["git", "rev-parse", "HEAD"], cwd=str(repo_dir),
                capture_output=True, text=True)
    return r.stdout.strip()[:7] if r.returncode == 0 else ""
```

- [ ] **Step 4: 통과 확인**

```
venv/bin/python -m pytest tests/test_connected_wikis.py -v
```

- [ ] **Step 5: Commit**

```bash
git add tools/connected_wikis.py tests/test_connected_wikis.py
git commit -m "feat(connected-wikis): connect git source + default branch detection"
```

---

### Task 2.11: Two-phase reservation race 테스트

**Files:**
- Test: `tests/test_connected_wikis.py`

- [ ] **Step 1: 회귀 테스트 추가**

```python
def test_two_phase_reservation_collision(tmp_path, monkeypatch):
    """동시에 같은 id로 connect 시도 시 한 쪽만 reservation 성공."""
    import threading
    cw = _setup_repo(tmp_path, monkeypatch)
    cw.cmd_init()

    ext_a = tmp_path / "a"; (ext_a / "wiki").mkdir(parents=True)
    (ext_a / "wiki" / "p.md").write_text("---\ntitle: P\ntags: []\n---\n", encoding="utf-8")
    ext_b = tmp_path / "b"; (ext_b / "wiki").mkdir(parents=True)
    (ext_b / "wiki" / "p.md").write_text("---\ntitle: P\ntags: []\n---\n", encoding="utf-8")

    monkeypatch.setattr(cw, "_resolve_active_model_or_none",
                        lambda: ("search-chromadb", "model-x"))
    def _fake_reindex(wp, coll):
        class R: returncode = 0; stdout = "Reindex complete: 1 pages indexed, 0 skipped"; stderr = ""
        return R()
    monkeypatch.setattr(cw, "_run_reindex", _fake_reindex)

    barrier = threading.Barrier(2)
    results = {}

    def worker(label, source):
        barrier.wait()
        rc = cw.cmd_connect(source=source, wiki_id="dup",
                            name=None, source_type="local",
                            decisions={"consent": "accept"})
        results[label] = rc

    t1 = threading.Thread(target=worker, args=("a", str(ext_a)))
    t2 = threading.Thread(target=worker, args=("b", str(ext_b)))
    t1.start(); t2.start(); t1.join(); t2.join()

    # 한 쪽 성공, 한 쪽 실패
    rcs = sorted(results.values())
    assert rcs == [0, 1]
    cfg = cw.load_config(cw.CONFIG_PATH)
    assert len(cfg["wikis"]) == 1
    assert cfg["wikis"][0]["id"] == "dup"
```

- [ ] **Step 2: 통과 확인** (이미 reservation 로직이 있어야 통과)

```
venv/bin/python -m pytest tests/test_connected_wikis.py::test_two_phase_reservation_collision -v
```

- [ ] **Step 3: Commit**

```bash
git add tests/test_connected_wikis.py
git commit -m "test(connected-wikis): two-phase reservation race"
```

---

### Task 2.12: `disconnect` 서브커맨드 (grep + 락 + cleanup)

**Files:**
- Modify: `tools/connected_wikis.py`
- Test: `tests/test_connected_wikis.py`

- [ ] **Step 1: failing 테스트 작성**

```python
def test_disconnect_unknown_id_warns_no_op(tmp_path, monkeypatch, capsys):
    cw = _setup_repo(tmp_path, monkeypatch)
    cw.cmd_init()
    rc = cw.cmd_disconnect("nope", decisions={})
    assert rc == 0  # no-op
    assert "not found" in capsys.readouterr().err.lower()


def test_disconnect_grep_finds_references(tmp_path, monkeypatch, capsys):
    cw = _setup_repo(tmp_path, monkeypatch)
    cw.cmd_init()
    # 가상 외부 wiki 등록
    save_config(cw.CONFIG_PATH, {"schema_version": 1, "wikis": [
        {"id": "es", "name": "ES", "source_type": "local", "source": "/x",
         "enabled": True, "status": "ok", "added": "2026-04-29",
         "embedding_backend": "search-chromadb", "embedding_model": "m"}
    ]})
    # synthesis 페이지에 (출처: es) 인용
    syn = tmp_path / "wiki" / "synthesis"
    syn.mkdir(parents=True)
    (syn / "trip.md").write_text(
        "---\ntitle: Trip\ntags: []\n---\nMadrid is fun (출처: es).\n", encoding="utf-8")

    rc = cw.cmd_disconnect("es", decisions={"disconnect-grep": "proceed"})
    assert rc == 0
    captured = capsys.readouterr()  # 단일 호출 — 다중 호출 시 버퍼 비워짐
    combined = captured.out + captured.err
    assert "trip.md" in combined


def test_disconnect_cleans_collection_and_dir(tmp_path, monkeypatch):
    cw = _setup_repo(tmp_path, monkeypatch)
    cw.cmd_init()
    # 컬렉션과 클론 디렉토리 모두 만든다
    import chromadb as _ch
    client = _ch.PersistentClient(path=cw.INDEX_PATH)
    client.get_or_create_collection("wiki-ext-es", metadata={"hnsw:space": "cosine"})
    del client
    import gc; gc.collect()
    clone = tmp_path / "connected-wikis" / "es"
    clone.mkdir(parents=True)
    (clone / "marker").write_text("x", encoding="utf-8")

    save_config(cw.CONFIG_PATH, {"schema_version": 1, "wikis": [
        {"id": "es", "name": "ES", "source_type": "git", "source": "https://x",
         "enabled": True, "status": "ok", "added": "2026-04-29",
         "embedding_backend": "search-chromadb", "embedding_model": "m"}
    ]})

    rc = cw.cmd_disconnect("es", decisions={"disconnect-grep": "proceed"})
    assert rc == 0
    assert not clone.exists()
    cfg = cw.load_config(cw.CONFIG_PATH)
    assert cfg["wikis"] == []
    client = _ch.PersistentClient(path=cw.INDEX_PATH)
    with pytest.raises(Exception):
        client.get_collection("wiki-ext-es")


def test_disconnect_lock_held_aborts(tmp_path, monkeypatch):
    cw = _setup_repo(tmp_path, monkeypatch)
    cw.cmd_init()
    save_config(cw.CONFIG_PATH, {"schema_version": 1, "wikis": [
        {"id": "es", "name": "ES", "source_type": "local", "source": "/x",
         "enabled": True, "status": "ok", "added": "2026-04-29",
         "embedding_backend": None, "embedding_model": None}
    ]})

    fd = cw.acquire_per_wiki_lock(cw.LOCK_DIR, "es", blocking=True)
    try:
        rc = cw.cmd_disconnect("es", decisions={"disconnect-grep": "proceed"})
        assert rc == 1  # locked elsewhere
    finally:
        cw.release_per_wiki_lock(fd)


def test_disconnect_does_not_disturb_in_flight_pull(tmp_path, monkeypatch):
    """In-flight Pull이 per-wiki 락을 들고 있는 동안 Disconnect는 abort하고
    Pull은 영향 없이 진행되어야 한다 (spec Verification: Disconnect 락 선점)."""
    import threading, time
    cw = _setup_repo(tmp_path, monkeypatch)
    cw.cmd_init()
    src = tmp_path / "src"
    (src / "wiki").mkdir(parents=True)
    (src / "wiki" / "p.md").write_text("---\ntitle: P\ntags: []\n---\n", encoding="utf-8")
    save_config(cw.CONFIG_PATH, {"schema_version": 1, "wikis": [
        {"id": "es", "name": "ES", "source_type": "local", "source": str(src),
         "enabled": True, "status": "ok", "added": "2026-04-29",
         "embedding_backend": "search-chromadb", "embedding_model": "m",
         "last_pulled": "2026-01-01"}
    ]})

    pull_done = threading.Event()
    add_calls: list[str] = []

    def _slow_add(f, c):
        time.sleep(0.3)  # 락을 잡은 채 잠깐 머물도록
        add_calls.append(str(f))
        class R: returncode = 0; stdout = ""; stderr = ""
        return R()
    monkeypatch.setattr(cw, "_run_add_page", _slow_add)

    def run_pull():
        cw.cmd_pull(decisions={})
        pull_done.set()

    pull_thread = threading.Thread(target=run_pull)
    pull_thread.start()
    time.sleep(0.05)  # Pull이 락을 잡을 시간을 줌

    rc = cw.cmd_disconnect("es", decisions={"disconnect-grep": "proceed"})
    assert rc == 1  # Pull이 락을 잡고 있어 disconnect abort
    pull_thread.join(timeout=5)
    assert pull_done.is_set()
    # Pull은 정상적으로 add_page를 호출했어야 함
    assert any("p.md" in c for c in add_calls)
    # 그리고 wiki는 여전히 connected 상태
    cfg = cw.load_config(cw.CONFIG_PATH)
    assert any(w["id"] == "es" for w in cfg["wikis"])
```

- [ ] **Step 2: 실패 확인**

```
venv/bin/python -m pytest tests/test_connected_wikis.py::test_disconnect_cleans_collection_and_dir -v
```
Expected: FAIL — `cmd_disconnect` not defined.

- [ ] **Step 3: 구현**

argparse:

```python
p_dis = sub.add_parser("disconnect", help="Disconnect an external wiki")
p_dis.add_argument("wiki_id")
p_dis.add_argument("--decision", action="append", dest="decisions", default=[])
```

main:

```python
if args.cmd == "disconnect":
    return cmd_disconnect(args.wiki_id, parse_decisions(args.decisions))
```

함수:

```python
def cmd_disconnect(wiki_id: str, decisions: dict[str, str]) -> int:
    cmd_init()
    cfg = load_config(CONFIG_PATH)
    if not any(w["id"] == wiki_id for w in cfg["wikis"]):
        print(f"Warning: wiki '{wiki_id}' not found, no-op", file=sys.stderr)
        return 0

    lock_fd = acquire_per_wiki_lock(LOCK_DIR, wiki_id, blocking=False)
    if lock_fd is None:
        print(f"Error: '{wiki_id}' is locked by another operation. Try again later.",
              file=sys.stderr)
        return 1

    try:
        # 1) grep 사전 점검
        refs = _grep_references(wiki_id)
        if refs:
            print(f"Found {len(refs)} reference(s) to '{wiki_id}':")
            for path, line_no, line in refs[:20]:  # cap output
                print(f"  {path}:{line_no}: {line.strip()}")
            decision = request_decision(
                prompt_key="disconnect-grep",
                question=f"Proceed with disconnect? Local pages reference '{wiki_id}'.",
                options=["proceed", "abort"],
                decisions=decisions,
            )
            if decision == "abort":
                print("Disconnect aborted.", file=sys.stderr)
                return 1

        # 2) JSON 항목 제거
        with with_global_lock(GLOBAL_LOCK):
            cfg = load_config(CONFIG_PATH)
            cfg["wikis"] = [w for w in cfg["wikis"] if w["id"] != wiki_id]
            save_config(CONFIG_PATH, cfg)

        # 3) 컬렉션 삭제
        _delete_collection(f"wiki-ext-{wiki_id}")

        # 4) 클론 디렉토리 삭제
        import shutil
        clone_dir = CONNECTED_DIR / wiki_id
        if clone_dir.exists():
            shutil.rmtree(clone_dir)

        _append_log(f"disconnect | {wiki_id}")
        _git_commit(f"disconnect: {wiki_id}")
        print(f"Disconnected: {wiki_id}")
        return 0
    finally:
        release_per_wiki_lock(lock_fd)
        # lock 파일 자체 삭제
        try:
            (LOCK_DIR / f"{wiki_id}.lock").unlink(missing_ok=True)
        except Exception:
            pass


def _grep_references(wiki_id: str) -> list[tuple[str, int, str]]:
    """Search wiki/{synthesis,concepts,entities,sources} for citation patterns."""
    import re as _re
    patterns = [
        _re.compile(rf"\(출처:\s*{_re.escape(wiki_id)}\s*\)"),
        _re.compile(rf"\(source:\s*{_re.escape(wiki_id)}\s*\)"),
        _re.compile(rf"connected-wikis/{_re.escape(wiki_id)}/"),
    ]
    matches: list[tuple[str, int, str]] = []
    for sub in ("synthesis", "concepts", "entities", "sources"):
        d = _REPO_ROOT / "wiki" / sub
        if not d.exists():
            continue
        for md in d.rglob("*.md"):
            try:
                for i, line in enumerate(md.read_text(encoding="utf-8").split("\n"), start=1):
                    if any(p.search(line) for p in patterns):
                        matches.append((str(md.relative_to(_REPO_ROOT)), i, line))
            except Exception:
                continue
    return matches
```

- [ ] **Step 4: 통과 확인**

```
venv/bin/python -m pytest tests/test_connected_wikis.py -v
```

- [ ] **Step 5: Commit**

```bash
git add tools/connected_wikis.py tests/test_connected_wikis.py
git commit -m "feat(connected-wikis): disconnect subcommand with grep guard"
```

---

### Task 2.13: `pull` — git source (default branch + diff-based 부분 reindex)

**Files:**
- Modify: `tools/connected_wikis.py`
- Test: `tests/test_connected_wikis.py`

- [ ] **Step 1: failing 테스트 작성**

```python
def test_pull_git_partial_reindex_on_diff(tmp_path, monkeypatch):
    """변경된 페이지만 --add로 재인덱싱."""
    import subprocess as sp
    cw = _setup_repo(tmp_path, monkeypatch)
    cw.cmd_init()
    remote = _make_fake_remote(tmp_path)

    monkeypatch.setattr(cw, "_resolve_active_model_or_none",
                        lambda: ("search-chromadb", "model-v1"))

    add_calls: list[tuple[str, str]] = []
    def _fake_add_page(file, coll):
        add_calls.append((str(file), coll))
        class R: returncode = 0; stdout = ""; stderr = ""
        return R()
    def _fake_reindex(wp, coll):
        import chromadb as _ch
        client = _ch.PersistentClient(path=cw.INDEX_PATH)
        client.get_or_create_collection(coll, metadata={"hnsw:space": "cosine"})
        class R: returncode = 0; stdout = "Reindex complete: 0 pages indexed, 0 skipped"; stderr = ""
        return R()
    monkeypatch.setattr(cw, "_run_reindex", _fake_reindex)
    monkeypatch.setattr(cw, "_run_add_page", _fake_add_page)

    # connect 1회
    rc = cw.cmd_connect(source=str(remote), wiki_id="g", name=None,
                        source_type="git", decisions={"consent": "accept"})
    assert rc == 0
    cfg = cw.load_config(cw.CONFIG_PATH)
    initial_commit = cfg["wikis"][0]["commit"]

    # remote에 새 페이지 추가
    (remote / "wiki" / "new.md").write_text(
        "---\ntitle: New\ntags: []\n---\nfresh", encoding="utf-8")
    sp.run(["git", "add", "."], cwd=remote, check=True, capture_output=True)
    sp.run(["git", "commit", "-m", "add new"], cwd=remote, check=True, capture_output=True)

    add_calls.clear()
    rc = cw.cmd_pull(decisions={})
    assert rc == 0
    cfg = cw.load_config(cw.CONFIG_PATH)
    assert cfg["wikis"][0]["commit"] != initial_commit
    # new.md만 add 호출됐어야
    new_md_calls = [c for c in add_calls if c[0].endswith("new.md")]
    assert len(new_md_calls) == 1


def test_pull_unreachable_preserves_enabled(tmp_path, monkeypatch):
    cw = _setup_repo(tmp_path, monkeypatch)
    cw.cmd_init()
    save_config(cw.CONFIG_PATH, {"schema_version": 1, "wikis": [
        {"id": "g", "name": "G", "source_type": "git",
         "source": "https://nonexistent.invalid/x.git",
         "enabled": True, "status": "ok", "added": "2026-04-29",
         "embedding_backend": "search-chromadb", "embedding_model": "m",
         "last_pulled": "2026-04-29", "commit": "abc1234"}
    ]})
    # 클론 디렉토리는 부재 (연결됐다고 가정)
    rc = cw.cmd_pull(decisions={})
    assert rc == 0
    cfg = cw.load_config(cw.CONFIG_PATH)
    w = cfg["wikis"][0]
    assert w["enabled"] is True
    assert w["status"] == "unreachable"


def test_pull_local_mtime_based(tmp_path, monkeypatch):
    cw = _setup_repo(tmp_path, monkeypatch)
    cw.cmd_init()
    src = tmp_path / "loc"
    (src / "wiki").mkdir(parents=True)
    p1 = src / "wiki" / "old.md"
    p1.write_text("---\ntitle: O\ntags: []\n---\nold", encoding="utf-8")
    save_config(cw.CONFIG_PATH, {"schema_version": 1, "wikis": [
        {"id": "loc", "name": "L", "source_type": "local", "source": str(src),
         "enabled": True, "status": "ok", "added": "2026-04-29",
         "embedding_backend": "search-chromadb", "embedding_model": "m",
         "last_pulled": "2026-01-01"}
    ]})

    add_calls: list[str] = []
    monkeypatch.setattr(cw, "_run_add_page", lambda f, c: (add_calls.append(str(f)) or type("R", (), {"returncode": 0, "stdout":"", "stderr":""})()))

    rc = cw.cmd_pull(decisions={})
    assert rc == 0
    # mtime 이후 변경된 page만 — old.md는 last_pulled(2026-01-01)보다 미래 mtime
    assert any("old.md" in c for c in add_calls)
```

- [ ] **Step 2: 실패 확인**

```
venv/bin/python -m pytest tests/test_connected_wikis.py::test_pull_unreachable_preserves_enabled -v
```
Expected: FAIL — `cmd_pull` not defined.

- [ ] **Step 3: 구현**

argparse:

```python
p_pull = sub.add_parser("pull", help="Update all connected wikis")
p_pull.add_argument("--decision", action="append", dest="decisions", default=[])
```

main:

```python
if args.cmd == "pull":
    return cmd_pull(parse_decisions(args.decisions))
```

함수:

```python
def _run_add_page(filepath: str, collection: str):
    import subprocess
    return subprocess.run(
        [sys.executable, str(_REPO_ROOT / "tools" / "search.py"),
         "--add", filepath, "--collection", collection],
        capture_output=True, text=True,
    )


def cmd_pull(decisions: dict[str, str]) -> int:
    cmd_init()

    cfg = load_config(CONFIG_PATH)
    today = date.today().isoformat()
    success_n = 0
    fail_n = 0
    meta_changed = False
    summary_lines: list[str] = []
    became_unreachable = 0

    backend, model = _resolve_active_model_or_none()

    for w in cfg["wikis"]:
        wid = w["id"]
        lock_fd = acquire_per_wiki_lock(LOCK_DIR, wid, blocking=True)
        try:
            try:
                if w["source_type"] == "git":
                    _pull_git(w, today, backend, model, decisions)
                else:
                    _pull_local(w, today, backend, model)
                # 성공 (fetch/access 성공 — spec C4 "성공" 정의)
                meta_changed = True  # last_pulled 갱신 = 메타 변경
                success_n += 1
            except _PullUnreachable:
                fail_n += 1
                # status가 실제로 변할 때만 meta_changed 세트
                # (이미 unreachable이고 다시 실패한 경우 → 진짜 no-op)
                if w.get("status") != "unreachable":
                    w["status"] = "unreachable"
                    meta_changed = True
                    became_unreachable += 1
        finally:
            release_per_wiki_lock(lock_fd)

    if meta_changed:
        with with_global_lock(GLOBAL_LOCK):
            save_config(CONFIG_PATH, cfg)
        if success_n > 0:
            msg = f"pull: {success_n} wikis updated"
        else:
            msg = f"pull: 0 fresh updates ({became_unreachable} became unreachable)"
        _append_log(f"pull | {success_n} success / {fail_n} failed")
        _git_commit(msg)
    else:
        print("pull: no changes")

    print(f"Pull summary: {success_n} success / {fail_n} failed")
    return 0


class _PullUnreachable(Exception):
    pass


def _pull_git(w: dict, today: str, backend: str | None, model: str | None,
              decisions: dict[str, str]) -> bool:
    """Returns True if w was mutated (meta change). Raises _PullUnreachable on access failure."""
    import subprocess as _sp
    clone_dir = CONNECTED_DIR / w["id"]
    if not clone_dir.exists():
        # auto-recover clone
        clone_dir.parent.mkdir(parents=True, exist_ok=True)
        r = _sp.run(["git", "clone", w["source"], str(clone_dir)],
                    capture_output=True, text=True)
        if r.returncode != 0:
            raise _PullUnreachable(r.stderr)

    # default branch 검출
    branch = _detect_default_branch(clone_dir)

    # fetch
    r = _sp.run(["git", "fetch", "origin", branch],
                cwd=str(clone_dir), capture_output=True, text=True)
    if r.returncode != 0:
        raise _PullUnreachable(r.stderr)

    old_commit = w.get("commit")
    # reset --hard
    _sp.run(["git", "reset", "--hard", f"origin/{branch}"],
            cwd=str(clone_dir), capture_output=True, check=False)
    new_commit = _git_head_sha(clone_dir)

    # 임베딩 모델 mismatch
    if backend and model and (w.get("embedding_backend") != backend
                              or w.get("embedding_model") != model):
        decision = request_decision(
            prompt_key="mismatch",
            question=f"'{w['id']}' embedding model differs (was {w.get('embedding_model')}, now {model}). Update field only or reindex?",
            options=["update", "reindex"],
            decisions=decisions,
        )
        if decision == "reindex":
            _run_reindex(str(clone_dir / "wiki"), f"wiki-ext-{w['id']}")
        # 둘 다 메타 갱신
        w["embedding_backend"] = backend
        w["embedding_model"] = model

    # diff
    if old_commit:
        d = _sp.run(["git", "diff", "--name-only", old_commit, "HEAD"],
                    cwd=str(clone_dir), capture_output=True, text=True)
        if d.returncode == 0:
            for fname in d.stdout.strip().split("\n"):
                if not fname or not fname.startswith("wiki/") or not fname.endswith(".md"):
                    continue
                _run_add_page(str(clone_dir / fname), f"wiki-ext-{w['id']}")
        else:
            # ref missing → fallback reindex
            _run_reindex(str(clone_dir / "wiki"), f"wiki-ext-{w['id']}")
    else:
        _run_reindex(str(clone_dir / "wiki"), f"wiki-ext-{w['id']}")

    # 메타 갱신
    w["last_pulled"] = today
    w["commit"] = new_commit
    if w.get("status") != "ok":
        w["status"] = "ok"
    return True


def _pull_local(w: dict, today: str, backend: str | None, model: str | None) -> bool:
    src = Path(w["source"])
    if not src.exists():
        raise _PullUnreachable(f"local path missing: {src}")

    last_pulled = w.get("last_pulled", "1970-01-01")
    import time as _time
    from datetime import datetime
    threshold = datetime.fromisoformat(last_pulled).timestamp()

    wiki_subdir = src / "wiki"
    if not wiki_subdir.exists():
        raise _PullUnreachable(f"no wiki/ in {src}")

    for md in wiki_subdir.rglob("*.md"):
        if md.stat().st_mtime > threshold:
            _run_add_page(str(md), f"wiki-ext-{w['id']}")

    if backend and model:
        w["embedding_backend"] = backend
        w["embedding_model"] = model
    w["last_pulled"] = today
    if w.get("status") != "ok":
        w["status"] = "ok"
    return True
```

- [ ] **Step 4: 통과 확인**

```
venv/bin/python -m pytest tests/test_connected_wikis.py -v
```

- [ ] **Step 5: Commit**

```bash
git add tools/connected_wikis.py tests/test_connected_wikis.py
git commit -m "feat(connected-wikis): pull subcommand (git diff + local mtime)"
```

---

### Task 2.14: Pull 부분 실패 보고 + commit 정책 단위 테스트

**Files:**
- Test: `tests/test_connected_wikis.py`

- [ ] **Step 1: 추가 테스트**

```python
def test_pull_partial_failure_summary(tmp_path, monkeypatch, capsys):
    """1개 ok, 1개 unreachable일 때 종합 보고와 단일 commit."""
    cw = _setup_repo(tmp_path, monkeypatch)
    cw.cmd_init()
    src_ok = tmp_path / "ok"; (src_ok / "wiki").mkdir(parents=True)
    save_config(cw.CONFIG_PATH, {"schema_version": 1, "wikis": [
        {"id": "ok", "name": "OK", "source_type": "local", "source": str(src_ok),
         "enabled": True, "status": "ok", "added": "2026-04-29",
         "embedding_backend": "search-chromadb", "embedding_model": "m",
         "last_pulled": "2026-04-29"},
        {"id": "bad", "name": "B", "source_type": "local", "source": "/no/such/path",
         "enabled": True, "status": "ok", "added": "2026-04-29",
         "embedding_backend": "search-chromadb", "embedding_model": "m",
         "last_pulled": "2026-04-29"}
    ]})
    monkeypatch.setattr(cw, "_run_add_page",
                        lambda f, c: type("R", (), {"returncode": 0, "stdout":"", "stderr":""})())

    rc = cw.cmd_pull(decisions={})
    assert rc == 0
    cfg = cw.load_config(cw.CONFIG_PATH)
    by_id = {w["id"]: w for w in cfg["wikis"]}
    assert by_id["ok"]["status"] == "ok"
    assert by_id["bad"]["status"] == "unreachable"
    assert by_id["bad"]["enabled"] is True  # 사용자 의도 보존
    out = capsys.readouterr().out
    assert "1 success / 1 failed" in out


def test_pull_no_meta_change_no_commit(tmp_path, monkeypatch, capsys):
    """모든 wiki가 이미 unreachable이고 fetch 또 실패해 메타 변경 0건이면 no-op."""
    cw = _setup_repo(tmp_path, monkeypatch)
    cw.cmd_init()
    save_config(cw.CONFIG_PATH, {"schema_version": 1, "wikis": [
        {"id": "g", "name": "G", "source_type": "local", "source": "/no/such",
         "enabled": True, "status": "unreachable", "added": "2026-04-29",
         "embedding_backend": None, "embedding_model": None,
         "last_pulled": "2026-04-29"}
    ]})

    rc = cw.cmd_pull(decisions={})
    assert rc == 0
    out = capsys.readouterr().out
    assert "no changes" in out
```

- [ ] **Step 2: 통과 확인**

```
venv/bin/python -m pytest tests/test_connected_wikis.py -v
```

`_pull_local`에서 unreachable일 때 `status`가 이미 unreachable이면 변경 없음으로 처리되도록 `cmd_pull` 로직 점검 (필요 시 `meta_changed` 갱신 로직 수정).

- [ ] **Step 3: Commit**

```bash
git add tests/test_connected_wikis.py
git commit -m "test(connected-wikis): pull partial-failure and no-op cases"
```

---

### Task 2.15: 인터랙션 프로토콜 — 다중 결정 (consent + mismatch)

**Files:**
- Test: `tests/test_connected_wikis.py`

- [ ] **Step 1: 테스트**

```python
def test_pull_mismatch_decision_required(tmp_path, monkeypatch):
    """Pull에서 embedding model이 다르면 mismatch 결정 요청."""
    cw = _setup_repo(tmp_path, monkeypatch)
    cw.cmd_init()
    remote = _make_fake_remote(tmp_path)
    save_config(cw.CONFIG_PATH, {"schema_version": 1, "wikis": [
        {"id": "g", "name": "G", "source_type": "git", "source": str(remote),
         "enabled": True, "status": "ok", "added": "2026-04-29",
         "embedding_backend": "search-chromadb", "embedding_model": "OLD-MODEL",
         "last_pulled": "2026-04-29", "commit": "abc1234"}
    ]})
    # 클론 디렉토리 미리 생성
    import subprocess as sp
    sp.run(["git", "clone", str(remote), str(tmp_path / "connected-wikis" / "g")],
           check=True, capture_output=True)

    monkeypatch.setattr(cw, "_resolve_active_model_or_none",
                        lambda: ("search-chromadb", "NEW-MODEL"))
    monkeypatch.setattr(sys.stdin, "isatty", lambda: False)

    with pytest.raises(SystemExit) as exc:
        cw.cmd_pull(decisions={})
    assert exc.value.code == 4

    # 다시 호출 — decision 누적
    monkeypatch.setattr(cw, "_run_reindex",
                        lambda wp, c: type("R", (), {"returncode": 0, "stdout":"", "stderr":""})())
    rc = cw.cmd_pull(decisions={"mismatch": "update"})
    assert rc == 0
    cfg = cw.load_config(cw.CONFIG_PATH)
    assert cfg["wikis"][0]["embedding_model"] == "NEW-MODEL"
```

- [ ] **Step 2: 통과 확인**

```
venv/bin/python -m pytest tests/test_connected_wikis.py -v
```

- [ ] **Step 3: Commit**

```bash
git add tests/test_connected_wikis.py
git commit -m "test(connected-wikis): pull mismatch decision flow"
```

---

### Task 2.16: CLI 통합 — 전체 서브커맨드 argparse 정리

**Files:**
- Modify: `tools/connected_wikis.py` — `main()` 정합성 점검
- Test: `tests/test_connected_wikis.py`

- [ ] **Step 1: smoke 테스트 추가**

```python
def _cli_run(args: list[str], cwd: Path) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, "tools/connected_wikis.py"] + args,
        capture_output=True, text=True, cwd=str(cwd),
    )


def test_cli_help_shows_all_subcommands():
    repo_root = Path(__file__).parent.parent
    r = _cli_run(["--help"], repo_root)
    assert r.returncode == 0
    for cmd in ("init", "list", "connect", "toggle", "disconnect", "pull"):
        assert cmd in r.stdout


def test_cli_init_smoke(tmp_path):
    """실제 디렉토리에서 init 동작 확인 (subprocess)."""
    # tmp_path를 가짜 repo로 설정
    (tmp_path / "wiki").mkdir()
    (tmp_path / "tools").mkdir()
    # tools/connected_wikis.py를 복사 (또는 symlink 회피로 PYTHONPATH로)
    import shutil
    shutil.copy(Path(__file__).parent.parent / "tools" / "connected_wikis.py",
                tmp_path / "tools" / "connected_wikis.py")
    (tmp_path / "tools" / "__init__.py").write_text("", encoding="utf-8")
    # search.py도 필요 — _resolve_active_model_or_none 호출 (실패해도 OK)
    shutil.copy(Path(__file__).parent.parent / "tools" / "search.py",
                tmp_path / "tools" / "search.py")

    r = _cli_run(["init"], tmp_path)
    assert r.returncode == 0
    assert (tmp_path / "connected-wikis.json").exists()
```

- [ ] **Step 2: 모든 서브커맨드 argparse가 등록됐는지 확인**

`main()`에서 각 cmd 분기가 모두 처리되는지 점검. 누락된 게 있으면 추가.

- [ ] **Step 3: 통과 확인**

```
venv/bin/python -m pytest tests/test_connected_wikis.py -v
```

- [ ] **Step 4: Commit**

```bash
git add tools/connected_wikis.py tests/test_connected_wikis.py
git commit -m "feat(connected-wikis): finalize CLI argparse + smoke tests"
```

---

### Task 2.17: `connected-wikis.json` 초기 파일 + `.gitignore`

**Files:**
- Create: `connected-wikis.json`
- Modify: `.gitignore`

- [ ] **Step 1: 빈 config 파일 생성**

```bash
echo '{"schema_version": 1, "wikis": []}' > /Users/laeyoung/Documents/personal/seojae/connected-wikis.json
```

- [ ] **Step 2: `.gitignore` 갱신**

`.gitignore`에 다음 추가:

```
# Connected Knowledge Bases (clones are user-machine-specific)
connected-wikis/
connected-wikis.lock
```

(Init이 멱등 추가하지만 PR에서 미리 둬도 안전.)

- [ ] **Step 3: 검증**

```bash
git status
# connected-wikis.json은 staged, connected-wikis/는 ignore
```

- [ ] **Step 4: Commit**

```bash
git add connected-wikis.json .gitignore
git commit -m "chore(connected-wikis): seed config + gitignore"
```

---

### Task 2.17b: 필드 자동 채움 단위 테스트 (`name`, `added`)

**Files:**
- Test: `tests/test_connected_wikis.py`

- [ ] **Step 1: 테스트 추가**

```python
def test_infer_name_from_git_url():
    from tools.connected_wikis import _infer_name
    assert _infer_name("https://github.com/friend/spain-travel-wiki", "git") == "spain-travel-wiki"
    assert _infer_name("https://github.com/friend/spain-travel-wiki.git", "git") == "spain-travel-wiki"
    assert _infer_name("git@github.com:friend/foo.git", "git") == "foo"


def test_infer_name_from_local_path():
    from tools.connected_wikis import _infer_name
    assert _infer_name("/Users/me/some-wiki", "local") == "some-wiki"


def test_connect_fills_added_date_and_name(tmp_path, monkeypatch):
    cw = _setup_repo(tmp_path, monkeypatch)
    cw.cmd_init()
    src = tmp_path / "myname-source"
    (src / "wiki").mkdir(parents=True)
    (src / "wiki" / "p.md").write_text("---\ntitle: P\ntags: []\n---\n", encoding="utf-8")

    monkeypatch.setattr(cw, "_resolve_active_model_or_none",
                        lambda: ("search-chromadb", "m"))
    def _fake_reindex(wp, c):
        import chromadb as _ch
        client = _ch.PersistentClient(path=cw.INDEX_PATH)
        client.get_or_create_collection(c, metadata={"hnsw:space": "cosine"})
        class R: returncode = 0; stdout = "Reindex complete: 1 pages indexed, 0 skipped"; stderr = ""
        return R()
    monkeypatch.setattr(cw, "_run_reindex", _fake_reindex)

    rc = cw.cmd_connect(source=str(src), wiki_id="myid", name=None,
                        source_type="local", decisions={"consent": "accept"})
    assert rc == 0
    w = cw.load_config(cw.CONFIG_PATH)["wikis"][0]
    # name은 path basename에서 자동 유도
    assert w["name"] == "myname-source"
    # added는 ISO 날짜 — 오늘
    from datetime import date
    assert w["added"] == date.today().isoformat()


def test_connect_explicit_name_overrides_inference(tmp_path, monkeypatch):
    cw = _setup_repo(tmp_path, monkeypatch)
    cw.cmd_init()
    src = tmp_path / "raw-folder"
    (src / "wiki").mkdir(parents=True)
    (src / "wiki" / "p.md").write_text("---\ntitle: P\ntags: []\n---\n", encoding="utf-8")

    monkeypatch.setattr(cw, "_resolve_active_model_or_none",
                        lambda: ("search-chromadb", "m"))
    monkeypatch.setattr(cw, "_run_reindex",
                        lambda wp, c: type("R", (), {"returncode": 0, "stdout":"", "stderr":""})())

    rc = cw.cmd_connect(source=str(src), wiki_id="myid",
                        name="Friendly Display Name",
                        source_type="local", decisions={"consent": "accept"})
    assert rc == 0
    w = cw.load_config(cw.CONFIG_PATH)["wikis"][0]
    assert w["name"] == "Friendly Display Name"
```

- [ ] **Step 2: 통과 확인**

```
venv/bin/python -m pytest tests/test_connected_wikis.py -v
```

- [ ] **Step 3: Commit**

```bash
git add tests/test_connected_wikis.py
git commit -m "test(connected-wikis): name/added field auto-fill"
```

---

### Task 2.18: 에러 컨트랙트 회귀 (`--print-model` 비-0 시 abort)

**Files:**
- Test: `tests/test_connected_wikis.py`

- [ ] **Step 1: 테스트**

```python
def test_connect_aborts_when_print_model_fails(tmp_path, monkeypatch):
    cw = _setup_repo(tmp_path, monkeypatch)
    cw.cmd_init()
    ext = tmp_path / "ext"; (ext / "wiki").mkdir(parents=True)
    (ext / "wiki" / "p.md").write_text("---\ntitle: P\ntags: []\n---\n", encoding="utf-8")

    monkeypatch.setattr(cw, "_resolve_active_model_or_none", lambda: (None, None))

    rc = cw.cmd_connect(source=str(ext), wiki_id="x", name=None,
                        source_type="local", decisions={"consent": "accept"})
    assert rc == 1
    assert cw.load_config(cw.CONFIG_PATH)["wikis"] == []  # rollback 완전 cleanup
```

- [ ] **Step 2: 통과 확인**

```
venv/bin/python -m pytest tests/test_connected_wikis.py -v
```

- [ ] **Step 3: Commit**

```bash
git add tests/test_connected_wikis.py
git commit -m "test(connected-wikis): print-model failure abort contract"
```

---

# M3 — Extension + Schema 문서

목표: `extensions/connected-wikis.md` 생성, `WIKI_SCHEMA.md`에 Directory Rules / log actions / commit prefixes 추가. Query 워크플로우 본문은 손대지 않음.

### Task 3.1: `WIKI_SCHEMA.md` Directory Rules + log actions + commit prefixes

**Files:**
- Modify: `WIKI_SCHEMA.md`

- [ ] **Step 1: Directory Rules 표에 행 추가**

`WIKI_SCHEMA.md`의 "Directory Rules" 표 (`| `raw/` | User only | ...`로 시작하는 표)의 마지막에 두 행 추가:

```markdown
| `connected-wikis/` | LLM only (clone/pull) | LLM + User | None |
| `connected-wikis.json` | LLM only | LLM + User | None |
```

- [ ] **Step 2: log.md actions 갱신**

"log.md Rules" 섹션의 `- Actions:` 줄을 다음으로 교체:

```markdown
- Actions: `init`, `ingest`, `query`, `lint`, `check-new`, `connect`, `toggle`, `disconnect`, `pull`, `extension`
```

- [ ] **Step 3: Git Commit Conventions 추가**

"Git Commit Conventions" 섹션 끝에 추가:

```markdown
- `extension: enable <name>` — Extension activation (e.g., connected-wikis bootstrap)
- `connect: <id>` — External wiki connected
- `disconnect: <id>` — External wiki disconnected
- `pull: <N wikis updated>` — Connected wikis refreshed
- `config: toggle <id>` — External wiki enabled/disabled
```

- [ ] **Step 4: 검증**

`WIKI_SCHEMA.md`를 sanity check — Query 워크플로우 본문은 변경되지 않았어야 함.

```
git diff WIKI_SCHEMA.md
```

확인: Directory Rules 표 + log actions + Git Commit Conventions 세 군데만 변경.

- [ ] **Step 5: Commit**

```bash
git add WIKI_SCHEMA.md
git commit -m "schema: add connected-wikis directory rules, log actions, commit prefixes"
```

---

### Task 3.2: `extensions/connected-wikis.md` 작성

**Files:**
- Create: `extensions/connected-wikis.md`

- [ ] **Step 1: 파일 생성**

`extensions/connected-wikis.md` 신규:

````markdown
---
name: connected-wikis
description: Connect external seojae wikis as toggleable extended knowledge sources
min_schema_version: "1.0"
requires:
  provides: [search-backend]
  packages: []
  scripts: [tools/search.py, tools/connected_wikis.py]
---

## Setup

This extension is initialized lazily — the first `connect`/`pull`/`list` invocation
runs `tools/connected_wikis.py init` automatically, which:

1. Creates `connected-wikis.json` with `{"schema_version": 1, "wikis": []}`.
2. Adds `connected-wikis/` and `connected-wikis.lock` to `.gitignore`.
3. Commits with `extension: enable connected-wikis`.

Manual init: `venv/bin/python tools/connected_wikis.py init`

## Workflows

This extension adds six workflows (`Init`, `Connect`, `Toggle`, `Disconnect`,
`Pull`, `List/Status`) and a hook that augments the core `Query` workflow.

### Init — implicit/lazy

Triggered automatically by Connect/Pull/List on first invocation when
`connected-wikis.json` is missing or `.gitignore` lacks `connected-wikis/`.
Manually: `venv/bin/python tools/connected_wikis.py init`. Aborts if `wiki/`
is missing (run project init first). See Setup section for details.

### Connect — `"<repo-url-or-path>을 <id>로 연결해줘"` / `"connect the <name> wiki"`

1. Run `venv/bin/python tools/connected_wikis.py connect <source> --id <id> [--name <name>]`
2. The CLI may emit `PROMPT: consent | ...` followed by `OPTIONS: accept reject` and exit code 4.
   When this happens, present the prompt to the user, get their answer, and re-invoke the same
   command with `--decision consent=<answer>` appended. CLI is idempotent — reservation persists
   across re-invocations until success or rollback.
3. Re-invoke as needed for additional decisions (e.g., `--decision mismatch=reindex`).
4. On success: external wiki is cloned to `connected-wikis/<id>/`, indexed into ChromaDB
   collection `wiki-ext-<id>`, and registered in `connected-wikis.json` with `enabled=true,
   status=ok`.

### Toggle — `"<id> 켜/꺼"`

`venv/bin/python tools/connected_wikis.py toggle <id> on|off`

Updates `enabled` flag only — no reindex needed.

### Disconnect — `"<id> 연결 해제"`

`venv/bin/python tools/connected_wikis.py disconnect <id> [--decision disconnect-grep=proceed]`

CLI greps `wiki/{synthesis,concepts,entities,sources}/` for `(출처: <id>)` /
`(source: <id>)` / `connected-wikis/<id>/` patterns and reports findings. User must
acknowledge with `disconnect-grep=proceed` to continue. Then deletes the JSON entry,
ChromaDB collection, clone directory, and per-wiki lock file.

### Pull — `"연결된 wiki들 업데이트"`

`venv/bin/python tools/connected_wikis.py pull [--decision mismatch=update|reindex]`

Per-wiki:
- `git`: `git fetch` + `git reset --hard origin/<default-branch>`. Diff-based partial reindex
  via `--add`. fetch failure → `status="unreachable"` (preserves `enabled`).
- `local`: mtime-based partial reindex. Path missing → `status="unreachable"`.

Embedding model mismatch surfaces an interactive `mismatch` prompt
(`update` = update field only / `reindex` = recompute embeddings).

### List/Status — `"연결된 wiki 목록 보여줘"`

`venv/bin/python tools/connected_wikis.py list`

Outputs a markdown table: `id | name | source_type | enabled | status | last_pulled |
embedding_model | pages`. No commit, no log entry — read-only.

### Query Hook (augments core Query workflow)

**After Query step 1 (running `{search.query}`):**

1. Read `connected-wikis.json`.
2. Filter `wikis[]` to those with `enabled == true && status == "ok"`.
   Apply per-query overrides if the user said `"<id>로만"` / `"using only <id>"`
   (whitelist) or `"<id> 빼고"` / `"excluding <id>"` (blacklist) — these do **not**
   mutate `connected-wikis.json`. If both are present, whitelist takes precedence,
   then blacklist is applied to the whitelisted set.
3. For each candidate, compare `embedding_backend`/`embedding_model` to the active
   backend (from `venv/bin/python tools/search.py --print-model`). If they match →
   include in unified `--collections wiki,wiki-ext-<id1>,...` query and merge
   results by score. If they mismatch → run that collection's query separately
   and present its top hits in a labeled section ("출처 모델 불일치 — 점수 비교
   불가"), without merging into the unified ranking. Warn (don't fail).
4. Then proceed to Query step 2 with the merged + segregated result set.

Multi-collection invocation must use `tools/search.py` directly (the `{search.*}`
token resolver does not support `--collection` flags).

#### Citation Format (replaces Query step 3 default when external wiki used)

- **Inline label**: each sentence sourced from an external wiki ends with
  `(출처: <id>)` (or `(source: <id>)` if `wiki_language: en`).
- **Citations block**: if any external wiki was used in the answer, append a
  `## Citations` (or `## 인용` for `wiki_language: ko`) section listing all
  pages cited. Local pages as wikilinks; external pages as full paths
  `connected-wikis/<id>/wiki/...` (NOT wikilinks). For `source_type: git` external
  pages, also include the upstream URL: `https://<host>/<owner>/<repo>/blob/<commit>/wiki/...`.

If 0 external wikis are enabled or no external result was cited, fall back to
the core Query step 3 citation behavior.

## Configuration

| Option | Default | Description |
|--------|---------|-------------|
| Config path | `connected-wikis.json` | Per-machine wiki list (committed) |
| Clone path | `connected-wikis/<id>/` | Where git sources are cloned (gitignored) |
| Lock dir | `connected-wikis/.locks/` | Per-wiki POSIX flocks |
| Global lock | `connected-wikis.lock` | JSON read-modify-write critical section |
| Collection prefix | `wiki-ext-<id>` | ChromaDB collection name format |
| ID format | `^[a-z0-9]([a-z0-9-]{0,29}[a-z0-9])?$` | Reserved: `wiki`, `local`, `ext`, `default` |

## Platform Support

POSIX-only (Linux/macOS). Windows is not supported in v1.
````

- [ ] **Step 2: 검증**

확장 frontmatter는 `extensions/README.md`의 필수 섹션(Setup/Workflows/Configuration)을 포함해야 함. 위 문서는 모두 포함.

- [ ] **Step 3: Commit**

```bash
git add extensions/connected-wikis.md
git commit -m "feat(extension): connected-wikis with workflows and Query hook"
```

---

### Task 3.3: 확장 로드 회귀 — `tools/search.py --print-model` 살아있음 확인

**Files:**
- Test: ad-hoc bash check

- [ ] **Step 1: smoke**

```bash
venv/bin/python tools/search.py --print-model
```
Expected stdout (정확히 두 줄):
```
backend=search-chromadb
model=paraphrase-multilingual-MiniLM-L12-v2
```

- [ ] **Step 2: 단위 테스트 회귀 통과**

```
venv/bin/python -m pytest tests/ -v
```
모든 테스트 PASS.

- [ ] **Step 3: 별도 commit 없음** — 회귀 통과 확인용 단계.

---

### Task 3.4: README/문서 갱신 (선택적)

**Files:**
- Modify: `README.md`, `README.ko.md` (간단한 한 줄 추가)

- [ ] **Step 1: 한 줄 언급 추가**

`README.md` 및 `README.ko.md`의 Extensions 또는 Features 섹션에 추가:

```markdown
- **connected-wikis** — Toggle external seojae wikis as extended knowledge sources
  (see `extensions/connected-wikis.md`).
```

- [ ] **Step 2: Commit**

```bash
git add README.md README.ko.md
git commit -m "docs: mention connected-wikis extension in README"
```

---

# M4 — End-to-End 검증

목표: 샘플 외부 wiki repo로 connect → query → toggle → disconnect 흐름을 실제 환경에서 수동 검증.

### Task 4.1: 로컬 fake remote E2E

**Files:** none (수동 검증)

- [ ] **Step 1: 임시 외부 wiki 준비**

```bash
mkdir -p /tmp/sample-wiki/wiki
cat > /tmp/sample-wiki/wiki/madrid.md <<'EOF'
---
title: Madrid Restaurants
type: source
tags: [travel, spain]
created: 2026-04-29
updated: 2026-04-29
---
Recommended: Casa Botin (oldest restaurant in the world per Guinness).
EOF
cat > /tmp/sample-wiki/README.md <<'EOF'
# Sample Spain Travel Wiki

A curated list of travel notes for Spain.
EOF

cd /tmp/sample-wiki
git init -b main && git add . && \
  git -c user.email=t@t -c user.name=t commit -m "init"
cd -
```

- [ ] **Step 2: connect**

```bash
cd /Users/laeyoung/Documents/personal/seojae
venv/bin/python tools/connected_wikis.py connect /tmp/sample-wiki --id sample \
  --decision consent=accept
```
Expected: `Connected: sample`. `connected-wikis/sample/wiki/madrid.md` 존재.

- [ ] **Step 3: list**

```bash
venv/bin/python tools/connected_wikis.py list
```
Expected: 표에 `sample | enabled=true | status=ok | pages=1`.

- [ ] **Step 4: query (multi-collection)**

```bash
venv/bin/python tools/search.py --query "madrid restaurants" \
  --collections wiki,wiki-ext-sample
```
Expected: 결과에 `connected-wikis/sample/wiki/madrid.md [wiki: wiki-ext-sample]`.

- [ ] **Step 5: toggle off**

```bash
venv/bin/python tools/connected_wikis.py toggle sample off
```
Expected: enabled=false. 단순 single-collection 검색은 영향 없음.

- [ ] **Step 6: disconnect**

```bash
venv/bin/python tools/connected_wikis.py disconnect sample --decision disconnect-grep=proceed
```
Expected: `connected-wikis/sample/` 디렉토리 삭제, 컬렉션 제거, JSON 항목 제거.

- [ ] **Step 7: 정리 + log 확인**

```bash
grep -E "^## \[" log.md | tail -10
```
Expected: connect/toggle/disconnect 항목 모두 보임.

```bash
git log --oneline -10
```
Expected: `connect: sample`, `config: toggle sample`, `disconnect: sample` 커밋 보임.

- [ ] **Step 8: cleanup**

```bash
rm -rf /tmp/sample-wiki
```

---

### Task 4.2: 풀 회귀 + cross-test

**Files:** none (전체 테스트 수행)

- [ ] **Step 1: 전체 단위 테스트**

```
venv/bin/python -m pytest tests/ -v
```
Expected: 모든 테스트 PASS (M1, M2 추가분 포함).

- [ ] **Step 2: 기존 워크플로우 회귀 — 단일 컬렉션 query 호환**

```bash
venv/bin/python tools/search.py --query "vibe coding" --top 3
```
Expected: 출력 포맷이 본 PR 전과 byte-identical (`<path> [score: X.XX]`, `[wiki:...]` 라벨 없음).

- [ ] **Step 3: 다국어 smoke (spec Verification: 다국어 회귀)**

한국어 쿼리가 영어 인덱싱 외부 컬렉션에서도 결과를 반환하는지 확인:

```bash
mkdir -p /tmp/eng-wiki/wiki
cat > /tmp/eng-wiki/wiki/coffee.md <<'EOF'
---
title: Coffee Brewing
type: source
tags: [coffee, food]
created: 2026-04-29
updated: 2026-04-29
---
Pour-over methods like V60 produce clean cups with bright acidity.
EOF
cd /tmp/eng-wiki && git init -b main && git add . && \
  git -c user.email=t@t -c user.name=t commit -m "init" && cd -

cd /Users/laeyoung/Documents/personal/seojae
venv/bin/python tools/connected_wikis.py connect /tmp/eng-wiki --id eng \
  --decision consent=accept

# 한국어 쿼리로 영어 컬렉션 검색
venv/bin/python tools/search.py --query "커피 추출 방법" --top 5 \
  --collections wiki,wiki-ext-eng
```
Expected: `coffee.md`가 결과에 포함됨 (paraphrase-multilingual-MiniLM이 cross-lingual 임베딩 지원).

```bash
# cleanup
venv/bin/python tools/connected_wikis.py disconnect eng --decision disconnect-grep=proceed
rm -rf /tmp/eng-wiki
```

- [ ] **Step 4: docs 일관성 점검**

다음을 수동으로 확인:
- `WIKI_SCHEMA.md`에 `connect/toggle/disconnect/pull/extension` log action이 있다
- `WIKI_SCHEMA.md`에 `connect:`/`disconnect:`/`pull:`/`config:`/`extension:` commit prefix가 있다
- `extensions/connected-wikis.md`이 frontmatter + Setup + Workflows + Configuration 섹션을 모두 가진다
- Workflows 섹션에 6개 워크플로우(Init, Connect, Toggle, Disconnect, Pull, List/Status) 모두 명시 (spec E 섹션 카운트 일치)

- [ ] **Step 5: 최종 commit (필요 시)**

문제가 있으면 수정 후 commit. 없으면 스킵.

---

## Self-Review Checklist

본 plan을 spec(`docs/connected-knowledge-bases.md`)과 대조해 다음을 확인:

**Spec coverage:**
- [x] A. 저장 구조 → Tasks 2.1, 2.5, 2.17, 3.1
- [x] A. `connected-wikis.json` 스키마 → Task 2.1
- [x] A. id 규칙 → Task 2.3
- [x] A. 마이그레이션(필드 보강) → Tasks 2.1, 2.4
- [x] A. 동시성(글로벌+per-wiki 락) → Tasks 2.2, 2.11
- [x] A. 인터랙션 프로토콜 → Tasks 2.8, 2.15
- [x] B. multi-corpus 검색 (collection/collections/print-model) → Tasks 1.1–1.7
- [x] B. 메타파일·중첩 제외 → Tasks 1.2, 1.3
- [x] B. 컬렉션 격리 회귀 → Task 1.5
- [x] B. wikilink 정책 → Task 3.2 (extension 문서)
- [x] C0. Init lazy bootstrap → Task 2.5
- [x] C1. Connect (git/local + reservation + rollback + consent) → Tasks 2.9, 2.10, 2.18
- [x] C2. Toggle → Task 2.7
- [x] C3. Disconnect (grep + 락) → Task 2.12
- [x] C4. Pull (default branch + diff + mismatch) → Tasks 2.13, 2.14, 2.15
- [x] C5. List/Status → Task 2.6
- [x] D. Query hook → Task 3.2
- [x] E. Extension frontmatter → Task 3.2
- [x] Verification 항목 (단위 테스트, race, rollback, default branch, etc.) → 분산 적용
- [x] WIKI_SCHEMA.md 갱신 (3개 섹션) → Task 3.1
- [x] .gitignore → Task 2.17

**Placeholder scan:** 없음. 모든 step에 실제 코드 또는 명령어 포함.

**Type consistency:** `cmd_connect/cmd_toggle/cmd_disconnect/cmd_pull/cmd_list/cmd_init` 함수명 일관. `_run_reindex/_run_add_page` 헬퍼 일관. `validate_id` / `IdError` / `DecisionPending` / `request_decision` 모두 정의되고 사용처 명시.

**Spec Verification 22항목 매핑:**
- 단위 테스트, CLI 스모크, 워크플로우 시나리오 → Task 1.x, 2.x, 4.1
- 회귀(byte-identical), 컬렉션 격리 → Tasks 1.5, 1.8
- 다국어 회귀 → Task 4.2 Step 3
- Frontmatter 견고성 → Task 2.9 (reindex skipped count 보고)
- 임베딩 모델 불일치 → Task 2.15 (CLI mismatch decision); D 섹션 hook(Task 3.2)이 unified vs 분리 ranking 책임
- Disconnect grep / Disconnect 락 선점(in-flight Pull 무영향 포함) → Task 2.12
- Pull 부분 실패, 메타-변경-0건 no-op → Task 2.14
- id 검증, JSON 동시성, 마이그레이션 → Tasks 2.3, 2.2, 2.4
- 에러 컨트랙트(`--print-model` 비-0) → Task 2.18
- Connect rollback → Task 2.10 (`test_connect_git_rollback_on_reindex_failure`)
- Default branch 검출(`main`/`master`/`trunk`) → Task 2.10 parametrize
- Two-phase Connect race → Task 2.11
- 인터랙션 프로토콜(consent + mismatch 다중 결정) → Tasks 2.8, 2.15
- 선결 조건 검증(`wiki/` 부재) → Task 2.5
- 필드 자동 채움(`name` URL/path 유도, `added` 날짜) → Task 2.17b

**Placeholder scan:** "이전과 동일", "TODO", "..." 류 모두 제거됨. Task 2.10은 전체 함수 본문 명시.

**Type consistency 점검:**
- `cmd_init/cmd_list/cmd_toggle/cmd_connect/cmd_disconnect/cmd_pull` — 모두 `() -> int` 또는 `(args) -> int`로 일관.
- `_run_reindex(wiki_path, collection)` / `_run_add_page(filepath, collection)` — 같은 형식의 `subprocess.CompletedProcess` 반환.
- `validate_id` raises `IdError`; `request_decision` raises `DecisionPending`(SystemExit 4) 또는 `ValueError`.
- `query_indexes` returns `list[tuple[str, float, str]]` (path, score, collection_name).
- `_should_index(page, wiki_root)` returns False for outside-wiki_root files (defensive); naturally invoked from inside `reindex` where rglob 결과는 항상 wiki_root 안.

**Open notes:**
- E2E(Task 4.1)는 `SKIP_MODEL_TESTS=true`에서 부분 skip 가능. 모델 다운로드 후 재실행 권장.
- `_pull_local` mtime 비교는 ISO date(자정) 기준이므로 같은 날 두 번 pull 시 두 번째는 변경 미감지 — spec 의도와 일치.
- 임베딩 모델 mismatch unified-vs-분리 ranking 정책은 D 섹션 hook이 LLM 책임. CLI는 mismatch를 메타에만 기록하고 hook 텍스트가 분리 표시 지시.
- `cmd_pull` 같은 날 fetch 성공 + 파일 변경 0건 시 `last_pulled` 동일값 갱신으로 JSON 바이트는 같지만 spec C4는 이를 "성공"으로 카운트하므로 `meta_changed=True`. `_git_commit`은 best-effort (`check=False`)로 빈 변경 시 silent fail — 동작상 안전.
- POSIX 한정(fcntl): Windows 환경은 v1 비지원이라고 spec 및 extension 문서에 명시됨.
