# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [1.0.0] - 2026-07-16

Initial public release.

### Added

- **WIKI_SCHEMA.md** — tool-agnostic wiki schema defining the 3-tier
  architecture (raw sources → wiki → schema) and 5 core workflows:
  Ingest, Query, Check-New, Lint, Reindex
- **Multi-tool support** — pre-configured rule files for Claude Code
  (`CLAUDE.md`), Codex CLI (`AGENTS.md`), and Gemini CLI (`GEMINI.md`)
- **Extension system** — drop-in `.md` files in `extensions/` with
  capability ownership (`provides`/`overrides`) and dependency declarations
- **search-chromadb extension** — semantic search over wiki pages using
  ChromaDB and sentence-transformers (`tools/search.py`)
- **obsidian extension** — Obsidian vault integration
- **connected-wikis extension** — connect external Seojae wikis as
  read-only extended knowledge sources with consent gating
  (`tools/connected_wikis.py`)
- **Example content** — Andrej Karpathy-themed raw sources and generated
  wiki pages (Software 2.0, Vibe Coding, Intro to LLMs)
- **Bilingual documentation** — English and Korean README, CONTRIBUTING,
  and guides
- **Landing page** (`landing/index.html`)
- **Test suite** — 130+ tests covering search and connected-wikis tools

[Unreleased]: https://github.com/VibeVista/seojae/compare/v1.0.0...HEAD
[1.0.0]: https://github.com/VibeVista/seojae/releases/tag/v1.0.0
