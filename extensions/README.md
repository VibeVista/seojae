# Seojae Extensions

Extensions are markdown files that add capabilities to your Seojae wiki.
Drop a file into this directory to enable it; remove to disable.

## Finding Extensions

Search GitHub for topic `seojae-extension`:
https://github.com/topics/seojae-extension

## Installing an Extension

1. Download the `.md` file from the extension's repository
2. **Review its contents** — extensions are LLM instructions executed
   with your tool's permissions. Treat them like shell scripts.
3. Copy the `.md` file into this `extensions/` directory
4. Restart your LLM tool session (or re-initialize)

## Creating Your Own Extension

Use `search-chromadb.md` in this directory as a reference.

### Required Frontmatter

- `name`: Extension identifier
- `description`: One-line summary

### Optional Frontmatter

- `provides`: Capability this extension exclusively owns (e.g., `search-backend`)
- `overrides`: Name of extension this one replaces
- `requires.packages`: pip packages needed
- `requires.scripts`: Repo scripts needed
- `requires.provides`: Capabilities this extension depends on
- `min_schema_version`: Minimum WIKI_SCHEMA.md version
- `commands`: Named commands this extension provides

### Required Sections

- `## Setup` — One-time installation steps
- `## Workflows` — New or modified workflows
- `## Configuration` — Configurable options

## Publishing

1. Create a GitHub repo for your extension
2. Add the topic `seojae-extension`
3. Include the `.md` file at the repo root
