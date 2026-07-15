import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from tools.search import parse_frontmatter, clean_wikilinks, build_embedding_text


# --- parse_frontmatter ---

def test_parse_frontmatter_basic():
    text = "---\ntitle: Test\ntags:\n  - ai\n  - coding\n---\nBody text"
    fm, body = parse_frontmatter(text)
    assert fm == {"title": "Test", "tags": ["ai", "coding"]}
    assert body == "Body text"


def test_parse_frontmatter_no_frontmatter():
    text = "No frontmatter here"
    fm, body = parse_frontmatter(text)
    assert fm == {}
    assert body == "No frontmatter here"


def test_parse_frontmatter_aliases():
    text = '---\ntitle: Vibe Coding\naliases:\n  - "바이브 코딩"\n---\nBody'
    fm, body = parse_frontmatter(text)
    assert fm["aliases"] == ["바이브 코딩"]
    assert body == "Body"


def test_parse_frontmatter_malformed_yaml():
    text = "---\n: bad: yaml:\n---\nBody"
    fm, body = parse_frontmatter(text)
    assert fm == {}
    assert body == "Body"


def test_parse_frontmatter_unclosed():
    text = "---\ntitle: Test\nno closing marker"
    fm, body = parse_frontmatter(text)
    assert fm == {}
    assert body == text


def test_parse_frontmatter_non_dict_yaml():
    text = "---\n- item1\n- item2\n---\nBody"
    fm, body = parse_frontmatter(text)
    assert fm == {}
    assert body == "Body"


def test_parse_frontmatter_embedded_dashes():
    """Closing --- must be on its own line; dashes inside YAML values should not close FM."""
    text = '---\ntitle: "See --- for details"\ntags: []\n---\nBody'
    fm, body = parse_frontmatter(text)
    assert fm.get("title") == "See --- for details"
    assert body == "Body"


# --- clean_wikilinks ---

def test_clean_wikilinks_simple():
    assert clean_wikilinks("[[Vibe Coding]]") == "Vibe Coding"


def test_clean_wikilinks_pipe():
    assert clean_wikilinks("[[vibe-coding|바이브 코딩]]") == "바이브 코딩"


def test_clean_wikilinks_heading_only():
    # [[#overview]] is removed entirely, leaving two spaces between "see" and "here"
    assert clean_wikilinks("see [[#overview]] here") == "see" + "  " + "here"


def test_clean_wikilinks_page_with_heading():
    assert clean_wikilinks("[[Attention Mechanism#scaled-dot-product]]") == "Attention Mechanism"


def test_clean_wikilinks_mixed():
    text = "See [[Vibe Coding]] and [[agentic-engineering|Agentic Engineering]]."
    assert clean_wikilinks(text) == "See Vibe Coding and Agentic Engineering."


# --- build_embedding_text ---

def test_build_embedding_text_full():
    fm = {"title": "Vibe Coding", "tags": ["ai", "coding"], "aliases": ["바이브 코딩"]}
    body = "Vibe coding is [[Andrej Karpathy|Karpathy's]] term."
    result = build_embedding_text(fm, body)
    assert "title: Vibe Coding" in result
    assert "tags: ai, coding" in result
    assert "aliases: 바이브 코딩" in result
    assert "Karpathy's" in result
    assert "[[" not in result


def test_build_embedding_text_truncates_body():
    fm = {"title": "T", "tags": [], "aliases": []}
    body = "x" * 1000
    result = build_embedding_text(fm, body)
    last_line = result.split("\n")[-1]
    assert len(last_line) <= 500


def test_build_embedding_text_empty_tags_omitted():
    fm = {"title": "T", "tags": [], "aliases": []}
    result = build_embedding_text(fm, "Body")
    assert "tags:" not in result
    assert "aliases:" not in result
    assert "title: T" in result


import numpy as np
import pytest
import chromadb
from unittest.mock import MagicMock
from tools.search import add_page


# --- Test helpers ---

def _make_collection(tmp_path):
    client = chromadb.PersistentClient(path=str(tmp_path / "index"))
    return client.get_or_create_collection(
        name="wiki", metadata={"hnsw:space": "cosine"}
    )


def _mock_model(dim: int = 384):
    """Mock model whose encode() returns a numpy array (same as real SentenceTransformer)."""
    model = MagicMock()
    model.encode.return_value = np.array([0.1] * dim)
    return model


# --- add_page tests ---

def test_add_page_inserts(tmp_path):
    page = tmp_path / "page.md"
    page.write_text("---\ntitle: Test\ntags:\n  - foo\n---\nTest body", encoding="utf-8")
    collection = _make_collection(tmp_path)
    model = _mock_model()

    add_page(str(page), collection, model)

    assert collection.count() == 1


def test_add_page_upserts_existing(tmp_path):
    page = tmp_path / "page.md"
    page.write_text("---\ntitle: V1\ntags: []\n---\nBody v1", encoding="utf-8")
    collection = _make_collection(tmp_path)
    model = _mock_model()

    add_page(str(page), collection, model)
    page.write_text("---\ntitle: V2\ntags: []\n---\nBody v2", encoding="utf-8")
    add_page(str(page), collection, model)

    assert collection.count() == 1  # upserted, not duplicated


def test_add_page_no_frontmatter_skips(tmp_path, capsys):
    page = tmp_path / "no-fm.md"
    page.write_text("Just body, no frontmatter", encoding="utf-8")
    collection = _make_collection(tmp_path)
    model = _mock_model()

    add_page(str(page), collection, model)

    assert collection.count() == 0
    assert "Warning" in capsys.readouterr().err


def test_add_page_missing_file_raises(tmp_path):
    collection = _make_collection(tmp_path)
    model = _mock_model()

    with pytest.raises(FileNotFoundError):
        add_page("nonexistent/path.md", collection, model)


from tools.search import reindex


def test_reindex_indexes_all_valid_pages(tmp_path):
    wiki = tmp_path / "wiki"
    wiki.mkdir()
    (wiki / "page-a.md").write_text("---\ntitle: A\ntags: []\n---\nBody A", encoding="utf-8")
    (wiki / "page-b.md").write_text("---\ntitle: B\ntags: []\n---\nBody B", encoding="utf-8")
    (wiki / "no-fm.md").write_text("No frontmatter", encoding="utf-8")

    idx = str(tmp_path / "index")
    model = _mock_model()

    reindex(str(wiki), idx, model)

    import chromadb as _chromadb
    _client = _chromadb.PersistentClient(path=idx)
    assert _client.get_collection("wiki").count() == 2  # no-fm.md skipped


def test_reindex_removes_deleted_pages(tmp_path):
    wiki = tmp_path / "wiki"
    wiki.mkdir()
    page = wiki / "page.md"
    page.write_text("---\ntitle: T\ntags: []\n---\nBody", encoding="utf-8")

    idx = str(tmp_path / "index")
    model = _mock_model()
    reindex(str(wiki), idx, model)

    import chromadb as _chromadb
    _client1 = _chromadb.PersistentClient(path=idx)
    assert _client1.get_collection("wiki").count() == 1
    import gc
    del _client1  # release SQLite file handle before next reindex
    gc.collect()

    page.unlink()  # delete the file
    reindex(str(wiki), idx, model)
    _client2 = _chromadb.PersistentClient(path=idx)
    assert _client2.get_collection("wiki").count() == 0  # stale entry gone
    del _client2
    gc.collect()


from tools.search import query_index


def test_query_returns_results(tmp_path):
    collection = _make_collection(tmp_path)
    model = _mock_model()

    page = tmp_path / "vibe.md"
    page.write_text("---\ntitle: Vibe Coding\ntags: [ai]\n---\nBody", encoding="utf-8")
    add_page(str(page), collection, model)

    results = query_index("vibe coding", top_n=5, collection=collection, model=model)

    assert len(results) == 1
    path, score = results[0]
    assert path.endswith("vibe.md")
    assert isinstance(score, float)
    assert -0.01 <= score <= 1.01  # allow small float imprecision


def test_query_empty_collection_returns_empty(tmp_path):
    collection = _make_collection(tmp_path)
    model = _mock_model()

    results = query_index("anything", top_n=5, collection=collection, model=model)
    assert results == []


def test_query_score_is_one_minus_distance(tmp_path):
    """Identical embedding vectors → distance ≈ 0 → score ≈ 1.0."""
    collection = _make_collection(tmp_path)
    model = _mock_model()  # always returns same vector

    page = tmp_path / "p.md"
    page.write_text("---\ntitle: P\ntags: []\n---\nBody", encoding="utf-8")
    add_page(str(page), collection, model)

    results = query_index("anything", top_n=1, collection=collection, model=model)

    assert len(results) == 1
    _, score = results[0]
    assert score > 0.99  # identical vectors → cosine distance ≈ 0 → score ≈ 1


import os
import subprocess
import sys as _sys


def _run(args: list[str], tmp_index: Path) -> subprocess.CompletedProcess:
    # Use sys.executable to guarantee we run under the same Python/venv as pytest
    return subprocess.run(
        [_sys.executable, "tools/search.py"] + args + ["--index-path", str(tmp_index)],
        capture_output=True,
        text=True,
        cwd=str(Path(__file__).parent.parent),
    )


# This test loads the real SentenceTransformer model (~470MB on first run, cached thereafter).
# Set SKIP_MODEL_TESTS=true to skip in offline/restricted environments.
_needs_model = pytest.mark.skipif(
    os.environ.get("SKIP_MODEL_TESTS", "false").lower() == "true",
    reason="Skipped: SKIP_MODEL_TESTS=true (requires real model download)",
)


@_needs_model
def test_cli_add_then_query(tmp_path):
    wiki = tmp_path / "wiki"
    wiki.mkdir()
    page = wiki / "vibe-coding.md"
    page.write_text(
        "---\ntitle: Vibe Coding\ntags: [ai]\naliases: ['바이브 코딩']\n---\nAI-assisted development.",
        encoding="utf-8",
    )
    idx = tmp_path / "idx"

    add_result = _run(["--add", str(page)], idx)
    assert add_result.returncode == 0

    query_result = _run(["--query", "vibe coding", "--top", "3"], idx)
    assert query_result.returncode == 0
    assert "vibe-coding.md" in query_result.stdout
    assert "[score: " in query_result.stdout


def test_cli_query_no_index_exits_2(tmp_path):
    result = _run(["--query", "test"], tmp_path / "nonexistent")
    assert result.returncode == 2
    assert result.stdout.strip() == ""
    assert "--reindex" in result.stderr


def test_cli_query_empty_string_exits_1(tmp_path):
    result = _run(["--query", ""], tmp_path / "idx")
    assert result.returncode == 1
    assert "Error" in result.stderr


def test_cli_query_whitespace_only_exits_1(tmp_path):
    result = _run(["--query", "   "], tmp_path / "idx")
    assert result.returncode == 1
    assert "Error" in result.stderr


def test_cli_add_missing_file_exits_1(tmp_path):
    result = _run(["--add", "nonexistent.md"], tmp_path / "idx")
    assert result.returncode == 1


# --- M1 multi-collection tests ---

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
    (wiki / "real-page.md").write_text("---\ntitle: Real\ntags: []\n---\nBody", encoding="utf-8")
    (wiki / "README.md").write_text("---\ntitle: R\ntags: []\n---\nBody", encoding="utf-8")
    (wiki / "log.md").write_text("---\ntitle: L\ntags: []\n---\nBody", encoding="utf-8")
    (wiki / "index.md").write_text("---\ntitle: I\ntags: []\n---\nBody", encoding="utf-8")
    (wiki / "WIKI_SCHEMA.md").write_text("---\ntitle: S\ntags: []\n---\nBody", encoding="utf-8")
    nested = wiki / "connected-wikis" / "other"
    nested.mkdir(parents=True)
    (nested / "leak.md").write_text("---\ntitle: L\ntags: []\n---\nBody", encoding="utf-8")

    idx = str(tmp_path / "idx")
    reindex(str(wiki), idx, _mock_model(), name="wiki-ext-bar")

    client = _ch.PersistentClient(path=idx)
    assert client.get_collection("wiki-ext-bar").count() == 1


def test_add_page_skips_metafile_inside_wiki(tmp_path, capsys):
    from tools.search import add_page
    wiki = tmp_path / "wiki"
    wiki.mkdir()
    meta = wiki / "log.md"
    meta.write_text("---\ntitle: L\ntags: []\n---\nBody", encoding="utf-8")

    collection = _make_collection(tmp_path)
    model = _mock_model()
    add_page(str(meta), collection, model, wiki_root=str(wiki))

    assert collection.count() == 0
    assert "skipping metafile" in capsys.readouterr().err.lower()


def test_add_page_skips_outside_wiki_root(tmp_path, capsys):
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


def test_query_indexes_merges_by_score(tmp_path):
    """두 컬렉션 결과를 점수 내림차순으로 머지."""
    from tools.search import add_page, query_indexes
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
    coll_names = [r[2] for r in results]
    assert "wiki" in coll_names and "wiki-ext-foo" in coll_names
    assert results[0][1] >= results[1][1]


def test_query_indexes_empty_collections(tmp_path):
    from tools.search import query_indexes
    results = query_indexes("q", top_n=5, collections=[], model=_mock_model())
    assert results == []


@_needs_model
def test_cli_reindex_custom_collection(tmp_path):
    """--collection wiki-ext-X로 격리된 컬렉션 빌드."""
    wiki = tmp_path / "wiki"
    wiki.mkdir()
    (wiki / "p.md").write_text("---\ntitle: P\ntags: []\n---\nBody", encoding="utf-8")

    idx = tmp_path / "idx"
    result = _run(["--reindex", "--wiki-path", str(wiki), "--collection", "wiki-ext-foo"], idx)
    assert result.returncode == 0

    import chromadb as _ch
    client = _ch.PersistentClient(path=str(idx))
    assert client.get_collection("wiki-ext-foo").count() == 1


@_needs_model
def test_cli_reindex_isolation_preserves_default(tmp_path):
    """--reindex --collection wiki-ext-X가 'wiki' 컬렉션을 byte-identical 보존."""
    wiki = tmp_path / "wiki"
    wiki.mkdir()
    (wiki / "local.md").write_text("---\ntitle: L\ntags: []\n---\nLocal body", encoding="utf-8")
    idx = tmp_path / "idx"

    r1 = _run(["--reindex", "--wiki-path", str(wiki)], idx)
    assert r1.returncode == 0

    import chromadb as _ch
    client = _ch.PersistentClient(path=str(idx))
    before_count = client.get_collection("wiki").count()
    before_ids = set(client.get_collection("wiki").get()["ids"])
    del client
    import gc; gc.collect()

    ext = tmp_path / "ext"; ext.mkdir()
    (ext / "ext.md").write_text("---\ntitle: E\ntags: []\n---\nExt body", encoding="utf-8")
    r2 = _run(["--reindex", "--wiki-path", str(ext), "--collection", "wiki-ext-foo"], idx)
    assert r2.returncode == 0

    client = _ch.PersistentClient(path=str(idx))
    after_count = client.get_collection("wiki").count()
    after_ids = set(client.get_collection("wiki").get()["ids"])
    assert before_count == after_count
    assert before_ids == after_ids


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
    assert "[wiki: " in result.stdout
    assert "wiki-ext-spain" in result.stdout


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
    assert "[wiki:" not in line
    assert "[score:" in line


# --- Review pass 3 ---

def test_query_indexes_mixed_empty_and_populated(tmp_path):
    """An empty collection mixed with a populated one must be skipped, not raise."""
    from tools.search import query_indexes
    client = chromadb.PersistentClient(path=str(tmp_path / "index"))
    populated = client.get_or_create_collection("wiki", metadata={"hnsw:space": "cosine"})
    empty = client.get_or_create_collection("wiki-ext-empty", metadata={"hnsw:space": "cosine"})
    populated.upsert(ids=["a.md"], embeddings=[[0.1] * 384],
                     documents=["d"], metadatas=[{"path": "a.md"}])

    results = query_indexes("q", 5, [populated, empty], _mock_model())
    assert len(results) == 1
    assert results[0][0] == "a.md"
    assert results[0][2] == "wiki"


def test_get_existing_collections_skips_missing(tmp_path, capsys):
    """--collections must never get_or_create: missing names are warned and skipped."""
    from tools.search import get_existing_collections
    index = str(tmp_path / "index")
    client = chromadb.PersistentClient(path=index)
    client.get_or_create_collection("wiki", metadata={"hnsw:space": "cosine"})

    cols = get_existing_collections(index, ["wiki", "wiki-ext-typo"])
    assert [c.name for c in cols] == ["wiki"]
    assert "wiki-ext-typo" in capsys.readouterr().err
    # The missing collection must NOT have been created as a side effect.
    names = {c.name for c in client.list_collections()}
    assert "wiki-ext-typo" not in names
