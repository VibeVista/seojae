# Getting Started with Seojae

A step-by-step tutorial for first-time users. By the end, you will have
a working wiki with your first ingested source.

---

## 1. Prerequisites

You need two things installed before you begin:

**Python 3.9 or later:**

```bash
python3 --version
# Python 3.12.x  (any 3.9+ is fine)
```

If the command fails, install Python from [python.org](https://www.python.org/)
or through your system package manager.

**An LLM coding tool** (one of the following):

| Tool | Verify | Docs |
|------|--------|------|
| Claude Code | `claude --version` | [claude.ai/code](https://claude.ai/code) |
| Codex CLI | `codex --version` | [github.com/openai/codex](https://github.com/openai/codex) |
| Gemini CLI | `gemini --version` | [github.com/google-gemini/gemini-cli](https://github.com/google-gemini/gemini-cli) |

Any tool that reads markdown instruction files will work, but these
three have pre-configured rule files in the repo.

---

## 2. Clone and Open

```bash
git clone https://github.com/VibeVista/seojae.git
cd seojae
```

Now open the project with your LLM tool:

```bash
# Claude Code
claude

# Codex CLI
codex

# Gemini CLI
gemini
```

Each tool automatically reads its own instruction file on startup:

| Tool | File read | How the schema loads |
|------|-----------|----------------------|
| Claude Code | `CLAUDE.md` | Contains `@WIKI_SCHEMA.md`, which imports the full schema plus extensions |
| Codex CLI | `AGENTS.md` | Full schema is inlined directly (Codex does not support file imports) |
| Gemini CLI | `GEMINI.md` | Contains `@./WIKI_SCHEMA.md`, which imports the full schema plus extensions |

You do not need to configure anything manually -- the tool reads the
rules and knows how to operate the wiki.

---

## 3. Initialize

Type this in your LLM tool's chat:

```
initialize this wiki
```

The tool will perform these steps automatically:

1. **Create a Python virtual environment** -- `python3 -m venv venv`
2. **Install dependencies** -- `venv/bin/pip install -r requirements.txt`
3. **Download the embedding model** -- ~470 MB on first run; this may
   take a few minutes depending on your connection
4. **Build the search index** -- `venv/bin/python tools/search.py --reindex`
5. **Run a verification query** -- confirms the index is working

> **Important:** Claude Code and Gemini CLI users must **restart their
> session** after initialization for extension imports to load correctly.
> Codex CLI users can continue immediately since the full schema is
> already inlined in `AGENTS.md`.

---

## 4. Explore the Examples

The repo ships with Karpathy-themed example content so you can see how
everything fits together before adding your own sources.

### The raw source

Open `raw/articles/vibe-coding.md`. This is what a raw source looks like:

```markdown
---
title: "Vibe Coding"
author: "Andrej Karpathy"
source: "https://x.com/karpathy/status/1886192184808149383"
date: 2025-02-02
---

# Vibe Coding

## Overview

Andrej Karpathy describes "Vibe Coding" as a programming approach
enabled by advanced AI systems...
```

The frontmatter is optional metadata -- title, author, URL, date. The
body is the original content (or a summary of it). Files in `raw/` are
**immutable**: the LLM never modifies them.

### The generated wiki pages

When this source was ingested, the LLM created several wiki pages:

**Source summary** -- `wiki/sources/vibe-coding-karpathy.md`

This page summarizes the raw source. Notice how it:
- Extracts key points into structured sections
- Links to related pages with wikilinks: `[[Andrej Karpathy]]`,
  `[[Software 2.0]]`
- Records the original URL and date in a Source section at the bottom

**Concept page** -- `wiki/concepts/vibe-coding.md`

This page treats "Vibe Coding" as a standalone concept. It:
- Provides a definition independent of any single source
- Compares the concept to related ideas in a Paradigm Comparison table
- Cross-references the source summary: `[[Vibe Coding -- Karpathy]]`
- Lists Korean aliases in the frontmatter (`aliases: ["바이브 코딩"]`)

**Entity page** -- `wiki/entities/andrej-karpathy.md`

The LLM recognized "Andrej Karpathy" as a named entity and created a
page linking back to all sources that mention him.

### How they connect

Open `index.md` to see the full catalog organized by category
(Entities, Concepts, Sources, Synthesis). Every page is reachable
through wikilinks, forming a knowledge graph you can browse in Obsidian
(see step 8).

---

## 5. Add Your First Source

Create a new file in `raw/articles/` (or any `raw/` subdirectory
except `raw/assets/`). Here is a template:

```markdown
---
title: "Your Article Title"
author: "Author Name"
source: "https://example.com/article"
date: 2026-01-15
---

# Your Article Title

Paste or summarize the article content here...
```

Save it as `raw/articles/your-article.md`. The filename should be
descriptive and use kebab-case (e.g., `scaling-laws-openai.md`).

> **Tip:** You can add any text content -- web articles, paper
> summaries, video transcripts, book notes. See `WIKI_SCHEMA.md` for
> the full list of `raw/` subdirectories.

---

## 6. Run Ingest

Tell your LLM tool:

```
ingest raw/articles/your-article.md
```

The tool will:

1. Read your source file in full
2. Discuss key takeaways with you (what to emphasize, your perspective)
3. Create a **source summary** page in `wiki/sources/`
4. Create or update **entity and concept** pages in `wiki/entities/`
   and `wiki/concepts/`
5. Add **cross-reference wikilinks** between new and existing pages
6. Update `index.md` with new entries
7. Append a timestamped entry to `log.md`
8. Update the **search index** so the new content is queryable
9. Create a **git commit**: `ingest: Your Article Title`

After the ingest finishes, check `index.md` to see your new pages
listed, and browse the generated wiki pages to see how the LLM
structured the information.

---

## 7. Query the Wiki

Now that your wiki has content, ask questions:

```
What topics does my wiki cover?
```

The LLM uses **semantic search** to find relevant wiki pages, reads
them, and synthesizes an answer with citations. You might also try:

```
Compare vibe coding with traditional software development
```

```
What are the key ideas from Karpathy's work?
```

When the LLM produces a valuable answer -- a comparison, a synthesis,
a discovered connection -- it will offer to save it as a
`wiki/synthesis/` page so the insight is preserved in your wiki rather
than lost in chat history.

---

## 8. Open in Obsidian (Optional)

If you have [Obsidian](https://obsidian.md/) installed:

1. Open Obsidian and choose **Open folder as vault**
2. Select the `seojae` project directory
3. Open **Graph View** (Ctrl/Cmd + G) to visualize connections between
   pages

The `extensions/obsidian.md` extension handles wikilink conventions so
that `[[Page Name]]` links resolve correctly across the wiki. Pages,
sources, entities, and concepts all appear as connected nodes in the
graph.

> **Note:** The `raw/` directory appears in the vault but its files are
> read-only by convention. The wiki pages in `wiki/` are where the
> structured knowledge lives.

---

## Next Steps

- **Add more sources** -- Drop files into `raw/` and run
  `"check for new sources and ingest them"` to batch-process everything
- **Ask deeper questions** -- The more sources you add, the richer the
  cross-references and synthesis become
- **Run a health check** -- Type `"check the wiki"` to find orphan
  pages, broken links, and growth opportunities
- **Customize** -- Edit `WIKI_SCHEMA.md` to change the wiki language,
  adjust workflows, or add new categories
- **Write extensions** -- Add `.md` files to `extensions/` to extend
  the wiki with new capabilities

For the full schema reference, see
[WIKI_SCHEMA.md](../WIKI_SCHEMA.md). For contribution guidelines, see
[CONTRIBUTING.md](../CONTRIBUTING.md).
