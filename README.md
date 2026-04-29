# Seojae (서재)

Seojae is an LLM-powered knowledge wiki framework. Feed it raw sources — articles,
papers, videos, notes — and your LLM coding tool automatically builds a structured,
cross-referenced wiki.

```
                  You add files             LLM builds wiki
                +-----------+             +-------------+
  articles  --> |           |   ingest    |             |
  papers    --> |  raw/     | ----------> |  wiki/      |
  videos    --> |           |             |             |
  notes     --> +-----------+             +-------------+
                                                |
                            governed by         |
                          +-------------------+ |
                          | WIKI_SCHEMA.md    |<+
                          | (rules & prompts) |
                          +-------------------+
```

The schema file (`WIKI_SCHEMA.md`) tells the LLM how to organize pages, maintain
cross-references, and run workflows. It is tool-agnostic — it works with Claude Code,
Codex CLI, Gemini CLI, or any LLM coding tool that reads markdown instructions.

## Features

**5 core workflows** — all triggered by natural language:

| Workflow | What it does |
|----------|-------------|
| **Ingest** | Process a raw source into wiki pages (summaries, entities, concepts, synthesis) |
| **Query** | Answer questions using wiki content with semantic search |
| **Check-New** | Detect and batch-ingest new raw sources |
| **Lint** | Health-check the wiki: find orphan pages, broken links, suggest growth |
| **Reindex** | Rebuild the semantic search index |

**Modular extension system** — drop a `.md` file into `extensions/` to enable a
capability; remove it to disable. Extensions can add workflows, integrate with
external tools, or replace built-in components.

**Built-in extensions:**
- `search-chromadb` — Semantic search powered by ChromaDB and sentence-transformers
- `obsidian` — Obsidian vault integration for viewing and navigating the wiki

## Prerequisites

- **Python 3.9+** with pip
- **~470MB disk space** for the embedding model (downloaded automatically on first run)
- **An LLM coding tool** — one of:
  - [Claude Code](https://docs.anthropic.com/en/docs/claude-code)
  - [Codex CLI](https://github.com/openai/codex)
  - [Gemini CLI](https://github.com/google-gemini/gemini-cli)

## Supported Tools

| Tool | Rule file | How it reads rules | Import syntax | Notes |
|------|-----------|-------------------|---------------|-------|
| **Claude Code** | `CLAUDE.md` | Auto-reads on session start | `@WIKI_SCHEMA.md` | Restart session after first setup |
| **Codex CLI** | `AGENTS.md` | Auto-reads on session start | No import (32KiB limit); full content inlined | Works immediately |
| **Gemini CLI** | `GEMINI.md` | Auto-reads on session start | `@./WIKI_SCHEMA.md` | Restart session after first setup |

Each tool ships with a pre-configured rule file in the repo. The rule file imports
(or inlines) `WIKI_SCHEMA.md` and active extensions, so the LLM knows how to manage
your wiki from the moment you start a session.

## Quick Start

```bash
# 1. Clone the repo
git clone https://github.com/Laeyoung/seojae.git
cd seojae

# 2. Open with your LLM tool (it auto-reads the rule file)
claude          # Claude Code
codex           # Codex CLI
gemini          # Gemini CLI

# 3. Say:
#    "Initialize this wiki"
```

During initialization, the LLM will:
- Create a Python virtual environment (`venv/`)
- Install dependencies from `requirements.txt`
- Build the semantic search index (downloads the ~470MB embedding model on first run)
- Verify the setup with a test query

After that, drop files into `raw/` and say "check for new sources" to start building
your wiki.

## Example

The repo includes 3 example raw sources by Andrej Karpathy:

| Raw source | Wiki pages generated |
|-----------|---------------------|
| `raw/articles/software-2.0.md` | Source summary + entity + concept pages |
| `raw/articles/vibe-coding.md` | Source summary + concept page |
| `raw/videos/intro-to-llms.md` | Source summary |

These produce 7 wiki pages total (3 source summaries, 1 entity, 2 concepts,
1 synthesis), demonstrating how Seojae cross-references related content.

See [docs/getting-started.md](docs/getting-started.md) for a detailed walkthrough.

## CLI Reference

`tools/search.py` is the only component usable without an LLM tool.
It requires the Python venv to be active.

```bash
# Semantic search
venv/bin/python tools/search.py --query "attention mechanism" --top 5

# Add/update a page in the index
venv/bin/python tools/search.py --add wiki/concepts/attention-mechanism.md

# Rebuild the full index
venv/bin/python tools/search.py --reindex
```

| Argument | Default | Description |
|----------|---------|-------------|
| `--query` | -- | Semantic search query |
| `--add` | -- | Add/update a wiki page in the index |
| `--reindex` | -- | Rebuild the full index |
| `--top` | `5` | Number of results |
| `--index-path` | `search-index/` | ChromaDB index directory |
| `--wiki-path` | `wiki/` | Wiki directory (`--reindex` only) |

**Exit codes:**

| Code | Meaning |
|------|---------|
| `0` | Success (includes skipping pages without frontmatter) |
| `1` | Error (empty query, file not found, wiki path not found) |
| `2` | Index not found (run `--reindex` first) |

## Extensions

Extensions are markdown files that add capabilities to Seojae. Each file contains
LLM instructions that are loaded alongside the core schema.

**Using extensions:**
1. Drop a `.md` file into `extensions/`
2. Restart your LLM tool session
3. The extension is now active

**Removing extensions:**
- Delete the `.md` file from `extensions/` and restart your session

**Finding extensions:**
- Search GitHub for the topic [`seojae-extension`](https://github.com/topics/seojae-extension)

**Built-in extensions:**
- `search-chromadb.md` — Semantic search backend (ChromaDB + sentence-transformers)
- `obsidian.md` — Obsidian vault integration
- `connected-wikis.md` — Toggle external seojae wikis as extended knowledge sources

See [extensions/README.md](extensions/README.md) for details on creating your own.

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md).

## License

[MIT](LICENSE)
