# Release Guide

Maintainer process for cutting a new Seojae release.

## Versioning

Seojae follows [Semantic Versioning](https://semver.org/spec/v2.0.0.html):

- **Major** — breaking changes to `WIKI_SCHEMA.md` workflows, the extension
  contract (frontmatter fields, capability model), or CLI interfaces
- **Minor** — new workflows, extensions, or CLI features that are
  backward-compatible
- **Patch** — bug fixes and documentation-only changes

The wiki schema has its own `schema_version` in the YAML block at the top of
`WIKI_SCHEMA.md`. Bump it when a change affects extension compatibility, and
mention the bump in the release notes.

## Release checklist

1. **Verify `main` is green**
   ```bash
   git checkout main && git pull
   SKIP_MODEL_TESTS=true venv/bin/python -m pytest tests/ -v
   ```
   Also check the [CI status](https://github.com/VibeVista/seojae/actions).

2. **Update CHANGELOG.md** — move entries from `[Unreleased]` into a new
   version section with today's date, and update the comparison links at
   the bottom. Commit as `schema: release vX.Y.Z changelog`.

3. **Sync AGENTS.md if the schema changed** — Codex CLI reads an inlined
   copy of `WIKI_SCHEMA.md`. Verify it is current and under the 32KiB limit:
   ```bash
   wc -c AGENTS.md
   ```

4. **Tag and push**
   ```bash
   git tag vX.Y.Z
   git push origin main --tags
   ```

5. **Create the GitHub release**
   ```bash
   gh release create vX.Y.Z --title "vX.Y.Z" \
     --notes "See CHANGELOG.md for details."
   ```
   Paste the CHANGELOG section for the version into the release notes.

6. **Announce** (optional) — blog, X/Twitter, Reddit (r/LocalLLaMA,
   r/ObsidianMD), Hacker News, GeekNews.

## Branch policy

- `main` carries the **framework only** — no personal wiki content.
- Feature work happens on branches and lands via reviewed PRs.
- Releases are tagged from `main` only.
