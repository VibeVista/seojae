# Seojae (서재) — Wiki Schema

> This file defines the rules and workflows for your LLM-powered knowledge wiki.
> Your LLM coding tool reads this file and follows these instructions to manage
> your wiki automatically. It is tool-agnostic — it works with Claude Code,
> Codex CLI, Gemini CLI, or any LLM coding tool that reads markdown instructions.

```yaml
schema_version: "1.0"

# Wiki Configuration
wiki_language: en    # Default language for meta files (index.md, log.md)
                     # Options: en, ko, ja, zh, etc.
                     # Page content follows source language rules below
```

## Project Overview

Seojae is a pattern-based personal knowledge wiki with a 3-tier architecture:

1. **Raw sources** (`raw/`) — Immutable originals. Only the user adds files; the LLM reads only.
2. **Wiki** (`wiki/`) — LLM-generated/maintained markdown pages: summaries, entities, concepts, synthesis.
3. **Schema** (`WIKI_SCHEMA.md`) — This file. Defines wiki rules and workflows.

## Prerequisites

- Python 3.9+ with pip
- Internet access on first run (downloads ~470MB embedding model)
- An LLM coding tool: Claude Code, Codex CLI, Gemini CLI, or similar

If you cannot download the model immediately, you can skip the search
index setup and build it later with the Reindex workflow.

## Setup

When a user asks to initialize this wiki, perform these steps:

### 1. Update your tool's rule file

The repo ships starter stubs. After initialization, update the file
for your tool with environment-specific settings.

**Claude Code (CLAUDE.md):**
```
@WIKI_SCHEMA.md
@extensions/search-chromadb.md
@extensions/obsidian.md

# Environment
- Python: use `venv/bin/python` prefix or `source venv/bin/activate`
- All tools/ scripts require the venv to be active
```

**Codex CLI (AGENTS.md):**
```
(Full WIKI_SCHEMA.md content is already inlined)
(Append active extension contents below)

# Environment
- Python: always use `venv/bin/python` prefix (venv activation
  does not persist between commands in Codex)
```

**Gemini CLI (GEMINI.md):**
```
@./WIKI_SCHEMA.md
@./extensions/search-chromadb.md
@./extensions/obsidian.md

# Environment
- Python: use `venv/bin/python` prefix or `source venv/bin/activate`
```

### 2. Set up Python environment

- Create venv: `python3 -m venv venv`
- Install: `venv/bin/pip install -r requirements.txt`

### 3. Build search index

- Run the search command defined by the active search extension.
- Default (search-chromadb): `venv/bin/python tools/search.py --reindex`
- Note: first run downloads the embedding model (~470MB).

### 4. Verify

- Run a test query: `venv/bin/python tools/search.py --query "test"`
- If results return, setup is complete.

## Directory Rules

| Path | Write | Read | Conflict Risk |
|------|-------|------|---------------|
| `raw/` | User only | LLM + User | None |
| `wiki/` | LLM only | LLM + User | None |
| `index.md`, `log.md` | LLM only | LLM + User | None |
| `WIKI_SCHEMA.md` | User + LLM | LLM | **Possible** |
| `README.md` | User + LLM | User | **Possible** |

**Absolute rules:**
- Never modify files in `raw/`.
- Wiki page creation/modification must follow the rules in this schema.

**Conflict prevention for shared-write files:** Both the user and the LLM may edit `WIKI_SCHEMA.md` and `README.md`. Do not edit these files while the LLM is working. If both sides have uncommitted changes, the LLM will run `git pull --rebase` and ask the user to resolve any conflicts manually.

## Category Classification

- `wiki/entities/` — Things with a proper name (people, tools, companies, models). Examples: "GPT-4", "OpenAI", "Yoshua Bengio"
- `wiki/concepts/` — Abstract concepts without a proper name (attention mechanism, fine-tuning). Examples: "Transformer Architecture", "Reinforcement Learning"
- `wiki/sources/` — One source = one summary page
- `wiki/synthesis/` — Analysis combining 2+ sources or concepts

### Raw Source Subdirectories

- `raw/myself/` — Your own content (blog posts, resume, etc.)
- `raw/articles/` — Web articles
- `raw/papers/` — Academic papers, PDFs
- `raw/videos/` — YouTube/podcast transcripts
- `raw/books/` — Book chapters
- `raw/misc/` — Miscellaneous
- `raw/assets/` — Images, attachments (not subject to ingest)

**Boundary rule:** If it has a proper name, it is an entity; if it is a general concept or method, it is a concept. In ambiguous cases (e.g., "Transformer" — both a paper title and an architecture), prefer concept unless the page is specifically about a particular paper or product.

## Page Format

### Frontmatter

**Parser limitation:** The `parse_frontmatter` function in the search tool is regex-based. A line starting with `---` inside a YAML block scalar may be misidentified as the closing delimiter. This rarely occurs in practice with wiki pages.

```yaml
---
title: "Page Title"
type: concept          # entity | concept | source | synthesis
tags: [tag1, tag2]
sources: ["raw/papers/example.md"]
aliases: []            # Optional — alternative names, e.g., ["attention mechanism"]
created: YYYY-MM-DD
updated: YYYY-MM-DD
---
```

### Body Rules

- Use Obsidian wikilinks: `[[Page Name]]`
- **Filenames**: Always use English kebab-case (e.g., `attention-mechanism.md`), regardless of body language. Non-English concept names go in the `aliases` frontmatter field.
- Filenames must be unique across all `wiki/` subdirectories (compatible with Obsidian "shortest path" wikilinks).

### Language Rules

- **Source summary pages** (`wiki/sources/`): Written in the source's original language.
- **Entity/concept pages** (`wiki/entities/`, `wiki/concepts/`): Written in the language of the source that first created the page. Later sources in different languages add information in the existing page's language.
- **Synthesis pages** (`wiki/synthesis/`): Written in the language the user requests, or the dominant language of the combined sources.
- **Meta files** (`index.md`, `log.md`, `WIKI_SCHEMA.md`, `README.md`): Written in the language specified by `wiki_language` in the configuration block above. Source titles in log entries are kept in their original language.
- **Wikilink names**: Use one canonical name per concept (always `[[Attention Mechanism]]`, never localized variants like `[[어텐션 메커니즘]]`). Add localized names to the frontmatter `aliases` field if needed.

### Raw Source Format

Raw source files are freeform markdown. There is no required frontmatter — this schema does not enforce a format on raw sources. However, sources may include optional metadata at the top for context:

```yaml
---
title: "Source Title"
author: "Author Name"
source: "https://original-url"
date: YYYY-MM-DD
---
```

The body is the original content or a transcript/summary of it. The LLM reads raw sources as input and generates structured wiki pages from them.

## Workflows

### Search Command Resolution

When a workflow references `{search.query}`, `{search.add}`, or `{search.reindex}`, resolve it by reading the `commands` field from whichever extension is active with `provides: search-backend`. If no search extension is active, use the default shown in parentheses after each token. If no default is applicable, skip the step and warn the user.

### Ingest (Source Processing)

Trigger: User specifies a file, e.g., "ingest raw/articles/some-article.md"

1. Read the entire source (for sources with images: read text first, then examine referenced images separately).
2. Discuss key takeaways with the user (what to emphasize, perspective).
3. Create a source summary page at `wiki/sources/<source-name>.md`.
4. Update related entity/concept/synthesis pages (or create new ones).
5. Add cross-reference wikilinks between new and existing pages.
6. Add new page entries to `index.md`.
7. Update the search index for each new/modified wiki page:
   Run `{search.add}` `<wiki page path>`
   (Default: `venv/bin/python tools/search.py --add`)
   Pages without frontmatter are skipped with a warning; missing files cause exit code 1.
8. Append to `log.md`: `## [YYYY-MM-DD] ingest | <source title>`
9. Git commit: `ingest: <source title>`

### Query (Question Answering)

Trigger: User asks a question about wiki content.

1. Run `{search.query}` `"<question>" --top 5`
   (Default: `venv/bin/python tools/search.py --query`)
   - Output format: `<path> [score: X.XX]` (score: cosine similarity, -1.0 to 1.0)
   - If output is empty or the highest score is below 0.5, also scan `index.md` as a fallback and merge results.
   - If the index path (default: `search-index/`) does not exist (exit code 2), fall back to scanning `index.md` and advise the user to run the Reindex workflow.
   - An empty query string causes exit code 1 — ensure the query is non-empty.
2. Read the wiki pages at the returned paths.
3. Synthesize an answer with source citations. The answer format may vary depending on the question — markdown pages, comparison tables, slide decks (Marp), charts (matplotlib), canvas files.
4. **Save valuable answers back to the wiki.** Comparisons, analyses, discovered connections — these should not vanish in chat history. Save as `wiki/synthesis/<topic>.md`. If unsure whether to save, ask the user.
5. (If saved) Update `index.md`, append to `log.md`: `## [YYYY-MM-DD] query | <question summary>`, Git commit: `query: <question summary>`

### Lint (Wiki Maintenance)

Trigger: User asks to check the wiki, or periodically.

**Health checks:**
1. **Orphan pages** — Pages with no inbound links
2. **Broken links** — References to `[[Non-existent Page]]`
3. **Stale information** — Content contradicting recent sources
4. **Missing pages** — Frequently mentioned entities/concepts without their own page
5. **Insufficient cross-references** — Highly related pages with no links between them

**Growth suggestions** (proactively, beyond just fixing problems):
6. **Data gaps** — Information that could be filled by web searches or new sources
7. **New questions to investigate** — Questions that would deepen wiki coverage
8. **New sources to find** — Source recommendations to fill identified gaps

9. Report findings, fix health issues with user approval, present growth suggestions.
10. Update the search index for each modified page:
    Run `{search.add}` `<modified wiki page path>`
    (Default: `venv/bin/python tools/search.py --add`)
11. Append to `log.md`: `## [YYYY-MM-DD] lint | <summary>`
12. Git commit: `lint: <fix summary>`

### Check-New (Batch New Source Detection)

Trigger: User asks to check for new sources and ingest them.

1. Read `log.md` to build a list of already-processed sources (find `## [YYYY-MM-DD] ingest | <title>` headers, extract source file paths from `^- Source: <path>` patterns in entry bodies).
2. Scan all files in `raw/` subdirectories (excluding `raw/assets/`).
3. Difference = unprocessed sources.
4. Report the list of new sources, then proceed to ingest all of them without waiting for approval.
5. Run the full Ingest workflow for each source, with individual `ingest:` commits per source.
6. After all processing, append a summary to `log.md`: `## [YYYY-MM-DD] check-new | N new sources processed`
7. Git commit: `check-new: N sources processed`

### Reindex (Search Index Rebuild)

Trigger: User asks to rebuild the index, or during environment setup.

1. Run `{search.reindex}`
   (Default: `venv/bin/python tools/search.py --reindex`)
   For non-standard paths, add `--index-path <path>` and/or `--wiki-path <path>`.
2. Confirm the completion message and report (output: `Reindex complete: N pages indexed, M skipped`).
3. `search-index/` is a generated artifact included in `.gitignore` — no commit needed.

## index.md Rules

A categorized wiki catalog. Updated after every Ingest, Query save, and Lint.

- One entry per line: `- [[Page Name]] — one-line summary`
- Alphabetical order within each category
- Category headers (in the language specified by `wiki_language`): Entities, Concepts, Sources, Synthesis

## log.md Rules

Chronological, append-only record. Parseable with `grep "^## \[" log.md | tail -5`.

- Header format: `## [YYYY-MM-DD] <action> | <title>`
- Actions: `init`, `ingest`, `query`, `lint`, `check-new`
- Source file paths always use the `- Source: <path>` prefix (the Check-New workflow parses already-processed sources using the `^- Source: ` pattern).
- Entry bodies also record pages created/modified.

## Git Commit Conventions

- `init: project bootstrapped` — Initial bootstrap
- `ingest: <source title>` — Source processing
- `query: <question summary>` — Query result saved to wiki
- `lint: <fix summary>` — Wiki maintenance
- `check-new: <N sources processed>` — Batch new source processing summary (after individual ingest commits)
- `schema: <change description>` — WIKI_SCHEMA.md or README.md changes

### Git Workflow

1. At the start of any workflow: `git pull`
2. After editing files: `git add` -> `git commit` -> `git pull --rebase` -> `git push`
3. On rebase conflict (extremely rare): `git rebase --abort` and ask the user to resolve manually.

## Extensions

Before starting any workflow, scan the `extensions/` directory.
Each `.md` file is an extension module. Read all active extensions
and follow their instructions alongside this core schema.

### Loading Rules

1. Read all `.md` files in `extensions/` (excluding `README.md`).
   - If an extension declares `min_schema_version` higher than this
     schema's `schema_version`, skip it and warn the user to update.
2. Check `provides:` fields for conflicts:
   - `provides:` signals exclusive ownership of a capability
     (e.g., only one `search-backend` can be active).
   - If two extensions declare the same `provides:` value,
     only use the one with an `overrides:` field targeting the other.
   - If neither overrides the other, warn the user and use
     the first one alphabetically.
   - Extensions that augment (not replace) a workflow do NOT
     need a `provides:` value — they are always active.
3. Check `requires.provides:` fields — if an extension declares
   a capability dependency (e.g., `requires.provides: [search-backend]`),
   verify that a provider is active. Warn the user if not.
4. Verify scripts: check each entry in `requires.scripts:` exists
   in the repo. Warn the user if any are missing.
5. Install dependencies: run `venv/bin/pip install <package>` for
   each entry in `requires.packages:` (let pip handle version resolution).
6. Follow each active extension's instructions.

### What Extensions Can Do

- Add new workflows
- Append steps to existing core workflows (reference the step
  they follow, e.g., "After Ingest step 3, also do X")
- Replace a capability by declaring `provides:` + `overrides:`
- Add integrations (Obsidian, Notion, etc.)
- Define new page types or categories
