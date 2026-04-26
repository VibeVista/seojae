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
