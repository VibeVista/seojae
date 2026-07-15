# Open Source Launch Checklist

Status tracker for officially launching Seojae as an open source project.
Items marked `[x]` are complete; items under "Post-merge (maintainer)" require
actions on `main` after this branch is merged.

## Repository foundation

- [x] Public GitHub repository (`VibeVista/seojae`)
- [x] MIT LICENSE with correct copyright holder
- [x] Repo description and topics set (`llm`, `knowledge-management`, `wiki`, ...)
- [x] `.gitignore` covers generated artifacts (venv, search-index, session data)
- [x] No personal/sensitive information in tracked files (swept 2026-07-16)

## Documentation

- [x] README.md / README.ko.md — features, quick start, CLI reference
- [x] All repo URLs point to `VibeVista/seojae` (was: stale `Laeyoung/seojae`)
- [x] README badges (CI, license, Python version)
- [x] Getting-started tutorial (`docs/getting-started.md`)
- [x] CONTRIBUTING.md / CONTRIBUTING.ko.md
- [x] CHANGELOG.md (Keep a Changelog format)
- [x] RELEASE_GUIDE.md rewritten as an ongoing maintainer release process
  (previous version was a one-time repo-migration guide, now obsolete)

## Community health

- [x] CODE_OF_CONDUCT.md (Contributor Covenant 2.1)
- [x] SECURITY.md (private vulnerability reporting)
- [x] Issue templates (bug report, feature request) + config with discussion link
- [x] Pull request template

## Quality & CI

- [x] Test suite passes locally (`SKIP_MODEL_TESTS=true pytest` — 131 passed)
- [x] GitHub Actions CI on push/PR (Python 3.9 & 3.12 matrix)
- [x] CI green on the launch PR (#9: Python 3.9 & 3.12 both pass)

## Post-merge (maintainer)

- [ ] Merge launch PR into `main` (requires user approval per branch policy)
- [ ] Tag and publish release: `git tag v1.0.0 && git push --tags`, then
  `gh release create v1.0.0` — see RELEASE_GUIDE.md
- [ ] (Optional) Enable GitHub Pages for `landing/` (Settings → Pages)
- [ ] (Optional) Upload a 1280×640 social preview image (Settings → Social preview)
- [ ] (Optional) Enable GitHub Discussions for community Q&A
- [ ] Announce: blog, X/Twitter, Reddit (r/LocalLLaMA, r/ObsidianMD),
  Hacker News (Show HN), GeekNews/Disquiet
