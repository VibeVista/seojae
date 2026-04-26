---
name: search-chromadb
description: Semantic search using ChromaDB and sentence-transformers
provides: search-backend
requires:
  packages: [chromadb>=0.5.0,<0.6.0, sentence-transformers>=3.0.0,<4.0.0, PyYAML>=6.0, numpy>=1.24]
  scripts: [tools/search.py]
commands:
  query: "venv/bin/python tools/search.py --query"
  add: "venv/bin/python tools/search.py --add"
  reindex: "venv/bin/python tools/search.py --reindex"
---

## Setup

Install dependencies (handled by `requirements.txt` during wiki initialization):

```bash
venv/bin/pip install chromadb sentence-transformers PyYAML numpy
```

Build the search index:

```bash
venv/bin/python tools/search.py --reindex
```

Note: First run downloads the `paraphrase-multilingual-MiniLM-L12-v2` embedding
model (~470MB) from Hugging Face. Subsequent runs use the cached model.

## Workflows

This extension provides the search backend for core workflows.
The commands below are referenced in WIKI_SCHEMA.md as `{search.*}` tokens.

### Search CLI Reference

```bash
venv/bin/python tools/search.py --query "<text>" [--top N] [--index-path PATH]
venv/bin/python tools/search.py --add <filepath> [--index-path PATH]
venv/bin/python tools/search.py --reindex [--wiki-path PATH] [--index-path PATH]
```

| Argument | Default | Description |
|----------|---------|-------------|
| `--query` | — | Semantic search query |
| `--add` | — | Add/update a wiki page in the index |
| `--reindex` | — | Rebuild the full index |
| `--top` | `5` | Number of results |
| `--index-path` | `search-index/` | ChromaDB index directory |
| `--wiki-path` | `wiki/` | Wiki directory (`--reindex` only) |

### Exit Codes

| Code | Meaning |
|------|---------|
| `0` | Success (includes skipping pages without frontmatter) |
| `1` | Error (empty query, file not found, wiki path not found) |
| `2` | Index not found (run `--reindex` first) |

### Integration with Core Workflows

- **Ingest step 7:** Run `{search.add} <wiki page path>` for each new/modified page
- **Query step 1:** Run `{search.query} "<question>" --top 5`
- **Lint step 10:** Run `{search.add} <modified wiki page path>` for each fixed page
- **Reindex step 1:** Run `{search.reindex}`

If this extension is removed, core workflows fall back to scanning `index.md`.

## Configuration

| Option | Default | Description |
|--------|---------|-------------|
| Embedding model | `paraphrase-multilingual-MiniLM-L12-v2` | Multilingual model supporting Korean, English, and more |
| Index path | `search-index/` | Local ChromaDB storage (gitignored) |
| Similarity metric | Cosine | HNSW space configuration |
