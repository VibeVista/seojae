from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

import yaml

from typing import TYPE_CHECKING

if TYPE_CHECKING:  # chromadb import is deferred to runtime (heavy; skipped by --print-model/--help)
    import chromadb


# --- Constants ---

COLLECTION_NAME = "wiki"
# Derive paths relative to this script so the script works regardless of CWD.
_REPO_ROOT = Path(__file__).parent.parent
INDEX_PATH = str(_REPO_ROOT / "search-index")
WIKI_PATH = str(_REPO_ROOT / "wiki")
MODEL_NAME = "paraphrase-multilingual-MiniLM-L12-v2"


# --- Pure text extraction functions ---

_FM_RE = re.compile(r"\A---[ \t]*\r?\n(.*?)\r?\n---[ \t]*(?:\r?\n|\Z)", re.DOTALL)


def parse_frontmatter(text: str) -> tuple[dict, str]:
    """Parse YAML frontmatter from markdown. Returns (frontmatter_dict, body)."""
    m = _FM_RE.match(text)
    if not m:
        return {}, text

    fm_text = m.group(1)
    body = text[m.end():].strip()

    try:
        fm = yaml.safe_load(fm_text) or {}
        if not isinstance(fm, dict):
            fm = {}
    except yaml.YAMLError:
        fm = {}

    return fm, body


def clean_wikilinks(text: str) -> str:
    """Extract display text from Obsidian wikilinks, removing link syntax."""
    # [[page|display text]] → display text
    text = re.sub(r"\[\[([^|\]]+)\|([^\]]+)\]\]", r"\2", text)
    # [[#heading]] → remove entirely
    text = re.sub(r"\[\[#[^\]]*\]\]", "", text)
    # [[page#heading]] → page
    text = re.sub(r"\[\[([^#\]]+)#[^\]]*\]\]", r"\1", text)
    # [[page]] → page
    text = re.sub(r"\[\[([^\]]+)\]\]", r"\1", text)
    return text


def build_embedding_text(fm: dict, body: str) -> str:
    """Build the text to embed for a wiki page (title + tags + aliases + body[:500])."""
    title = fm.get("title") or ""
    tags = fm.get("tags") or []
    aliases = fm.get("aliases") or []

    tags_str = ", ".join(str(t) for t in tags) if tags else ""
    aliases_str = ", ".join(str(a) for a in aliases) if aliases else ""
    clean_body = clean_wikilinks(body)[:500]

    lines = [f"title: {title}"]
    if tags_str:
        lines.append(f"tags: {tags_str}")
    if aliases_str:
        lines.append(f"aliases: {aliases_str}")
    lines.append("")
    lines.append(clean_body)

    return "\n".join(lines)


# --- ChromaDB operations ---

def get_collection(index_path: str = INDEX_PATH, name: str = COLLECTION_NAME) -> chromadb.Collection:
    """Get or create the named ChromaDB collection with cosine similarity metric."""
    import chromadb
    client = chromadb.PersistentClient(path=index_path)
    return client.get_or_create_collection(
        name=name,
        metadata={"hnsw:space": "cosine"},
    )


def get_existing_collections(index_path: str, names: list[str]) -> list[chromadb.Collection]:
    """Return only collections that already exist; warn to stderr and skip missing ones.

    Query must not get_or_create: a typo'd --collections name would otherwise
    silently persist an empty collection and mask the misconfiguration.
    """
    import chromadb
    client = chromadb.PersistentClient(path=index_path)
    out = []
    for n in names:
        try:
            out.append(client.get_collection(n))
        except Exception:
            print(f"Warning: collection '{n}' not found, skipping", file=sys.stderr)
    return out


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
    fm, body = parse_frontmatter(text)

    if not fm:
        print(f"Warning: {filepath} has no frontmatter, skipping", file=sys.stderr)
        return

    embedding_text = build_embedding_text(fm, body)
    embedding = model.encode(embedding_text).tolist()

    # Normalise to a repo-relative ID (e.g. "wiki/sources/page.md") so IDs
    # are consistent with those produced by reindex(). Fall back to the raw
    # filepath string for paths outside the repo (e.g. tmp_path in tests).
    try:
        doc_id = str(path.resolve().relative_to(Path(_REPO_ROOT).resolve()))
    except ValueError:
        doc_id = str(filepath)

    collection.upsert(
        ids=[doc_id],
        embeddings=[embedding],
        documents=[embedding_text],
        metadatas=[{"path": doc_id}],
    )


def reindex(wiki_path: str, index_path: str, model, name: str = COLLECTION_NAME) -> None:
    """Rebuild the named index from scratch.

    Deletes and recreates the ChromaDB collection to guarantee a clean slate
    (avoids the collection.get() pagination limits that could leave stale IDs).
    """
    import chromadb
    client = chromadb.PersistentClient(path=index_path)
    try:
        client.delete_collection(name)
    except Exception:
        pass  # collection didn't exist yet

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
            # Store ID as path relative to repo root (e.g. "wiki/concepts/vibe-coding.md")
            # Use _REPO_ROOT for consistency with add_page() doc IDs.
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


def query_index(
    q: str,
    top_n: int,
    collection: chromadb.Collection,
    model,
) -> list[tuple[str, float]]:
    """Search the index. Returns list of (filepath, similarity_score) sorted by score desc."""
    count = collection.count()
    if count == 0:
        return []

    embedding = model.encode(q).tolist()
    results = collection.query(
        query_embeddings=[embedding],
        n_results=min(top_n, count),
    )

    output = []
    for doc_id, distance in zip(results["ids"][0], results["distances"][0]):
        score = 1.0 - distance  # hnsw:space=cosine distance ∈ [0,2]; score = cosine similarity ∈ [-1.0, 1.0]
        output.append((doc_id, score))

    return output  # ChromaDB returns results sorted by distance (best first)


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


# --- CLI ---

def main() -> None:
    parser = argparse.ArgumentParser(description="Seojae semantic search")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--query", metavar="TEXT", help="Search query")
    group.add_argument("--add", metavar="FILE", help="Add or update a wiki page")
    group.add_argument("--reindex", action="store_true", help="Rebuild the full index")
    group.add_argument("--print-model", action="store_true",
                       help="Print active backend/model identifiers (two lines)")
    parser.add_argument("--top", type=int, default=5, metavar="N")
    parser.add_argument("--index-path", default=INDEX_PATH, metavar="PATH")
    parser.add_argument("--wiki-path", default=WIKI_PATH, metavar="PATH",
                        help="Wiki directory to scan (used with --reindex)")
    parser.add_argument("--collection", default=COLLECTION_NAME, metavar="NAME",
                        help="Collection name for --add/--reindex (default: wiki)")
    parser.add_argument("--collections", default=None, metavar="LIST",
                        help="Comma-separated collection names for --query (default: wiki only)")
    parser.add_argument("--wiki-root", default=None, metavar="PATH",
                        help="Wiki root for --add: metafiles/nested connected-wikis under it are skipped "
                             "(same exclusion rules as --reindex)")
    args = parser.parse_args()

    index_path = args.index_path

    if args.print_model:
        print("backend=search-chromadb")
        print(f"model={MODEL_NAME}")
        return

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
            cols = get_existing_collections(index_path, names)
            results = query_indexes(args.query, args.top, cols, model)
            for path, score, coll_name in results:
                print(f"{path} [wiki: {coll_name}] [score: {score:.2f}]")
        else:
            # 단일 컬렉션 — 기존 query_index 그대로 호출 → byte-identical
            collection = get_collection(index_path)
            results = query_index(args.query, args.top, collection, model)
            for path, score in results:
                print(f"{path} [score: {score:.2f}]")

    elif args.add is not None:
        from sentence_transformers import SentenceTransformer
        model = SentenceTransformer(MODEL_NAME)
        collection = get_collection(index_path, name=args.collection)
        try:
            add_page(args.add, collection, model, wiki_root=args.wiki_root)
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


if __name__ == "__main__":
    main()
