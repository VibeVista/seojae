# Contributing to Seojae

Thank you for your interest in contributing to Seojae! This guide covers
how to get started, what kinds of contributions we accept, and the conventions
we follow.

## How to Contribute

**Issues** — We welcome bug reports, feature requests, and extension ideas.
Please search existing issues before opening a new one.

**Pull Requests** — The standard workflow:

1. Fork the repository
2. Create a feature branch (`git checkout -b my-feature`)
3. Make your changes
4. Push to your fork and open a Pull Request

Please keep PRs focused: one feature or fix per PR. This makes review
faster and keeps the git history readable.

## Development Setup

```bash
# Clone the repository
git clone https://github.com/Laeyoung/seojae.git
cd seojae

# Create a virtual environment
python3 -m venv venv

# Install dependencies
venv/bin/pip install -r requirements.txt

# Run tests (skips tests that require the 470MB embedding model)
SKIP_MODEL_TESTS=true venv/bin/python -m pytest tests/ -v
```

The `SKIP_MODEL_TESTS=true` flag skips tests that require downloading
the `paraphrase-multilingual-MiniLM-L12-v2` embedding model (~470MB).
If you have the model cached or want to run the full suite, omit the flag.

## Adding Tool Support

Seojae is tool-agnostic — it works with any LLM coding tool that reads
markdown instructions (Claude Code, Codex CLI, Gemini CLI, etc.).

To add support for a new tool:

1. **Create a stub rule file** in the repo root (e.g., `MYTOOL.md`).
   - If the tool supports file imports, use import syntax to reference
     `WIKI_SCHEMA.md` and active extensions:
     ```
     @WIKI_SCHEMA.md
     @extensions/search-chromadb.md
     ```
   - If the tool does not support imports, inline the full content of
     `WIKI_SCHEMA.md` and any active extensions into the rule file.
2. **Add the tool** to the Setup section in `WIKI_SCHEMA.md` under
   "### 1. Update your tool's rule file", following the existing pattern
   for Claude Code, Codex CLI, and Gemini CLI.
3. **Document any tool-specific quirks** in the rule file's Environment
   section — for example:
   - Import syntax differences (`@file` vs `@./file`)
   - File size limits (Codex has a 32KB `project_doc_max_bytes` default)
   - Whether `venv` activation persists between commands

## Creating Extensions

Extensions are markdown files in `extensions/` that add capabilities to
the wiki. Use `extensions/search-chromadb.md` as a reference implementation.

### Frontmatter Fields

```yaml
---
name: my-extension
description: One-line summary of what this extension does
provides: capability-name       # Optional — exclusive capability ownership
overrides: other-extension      # Optional — which extension this replaces
requires:
  packages: [package1>=1.0]     # pip packages needed
  scripts: [tools/my-script.py] # Repo scripts needed
  provides: [search-backend]    # Capability dependencies
min_schema_version: "1.0"       # Minimum WIKI_SCHEMA.md version
commands:                        # Named commands for workflow integration
  my-cmd: "venv/bin/python tools/my-script.py --flag"
---
```

### Required Sections

- **`## Setup`** — One-time installation and configuration steps.
- **`## Workflows`** — New workflows or modifications to existing core
  workflows. Reference the step they follow (e.g., "After Ingest step 3,
  also do X").
- **`## Configuration`** — Configurable options and their defaults.

### Capability Model

- Extensions that **replace** a capability declare both `provides:` and
  `overrides:` — only one extension can own a given capability.
- Extensions that **augment** existing workflows (adding steps, integrations)
  do not need `provides:` and are always active.

## Schema Changes

`WIKI_SCHEMA.md` is the core schema that all LLM tools read. Changes to it
have downstream effects:

1. **Update AGENTS.md** — Codex CLI does not support file imports, so
   `AGENTS.md` contains an inlined copy of the schema. Any change to
   `WIKI_SCHEMA.md` must be reflected in `AGENTS.md`.
2. **Check the size budget** — Codex enforces a default
   `project_doc_max_bytes` of 32,768 bytes:
   ```bash
   wc -c AGENTS.md
   ```
   If `AGENTS.md` also inlines extension content, budget accordingly
   to stay under the limit.
3. **Bump `schema_version`** — If your change affects extension
   compatibility, increment the version in the YAML config block at
   the top of `WIKI_SCHEMA.md`.

## Code Style

- **Python**: Follow [PEP 8](https://peps.python.org/pep-0008/) style
  guidelines.
- **Tests required**: Any changes to files in `tools/` must include
  corresponding tests in `tests/`.
- **CI/offline environments**: Use `SKIP_MODEL_TESTS=true` to skip tests
  that require the embedding model download:
  ```bash
  SKIP_MODEL_TESTS=true venv/bin/python -m pytest tests/ -v
  ```
- **Markdown**: Use ATX-style headers (`#`), fenced code blocks, and
  keep lines under 80 characters where practical.
