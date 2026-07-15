---
name: connected-wikis
description: Connect external seojae wikis as toggleable extended knowledge sources
min_schema_version: "1.0"
requires:
  provides: [search-backend]
  packages: []
  scripts: [tools/search.py, tools/connected_wikis.py]
---

## Setup

This extension is initialized lazily — the first `connect`/`pull`/`list` invocation
runs `tools/connected_wikis.py init` automatically, which:

1. Creates `connected-wikis.json` with `{"schema_version": 1, "wikis": []}`.
2. Adds `connected-wikis/` and `connected-wikis.lock` to `.gitignore`.
3. Commits with `extension: enable connected-wikis`.

Manual init: `venv/bin/python tools/connected_wikis.py init`

**Sample wiki for testing:** a public fixture wiki is available at
`https://github.com/Laeyoung/den` (coffee-knowledge pages; suggested id: `den`).
Use it to demo or verify the Connect/Query/Pull/Disconnect workflows end-to-end
— see the walkthrough in `docs/connected-wikis-guide.ko.md` §0.

## Workflows

This extension adds six workflows (`Init`, `Connect`, `Toggle`, `Disconnect`,
`Pull`, `List/Status`) and a hook that augments the core `Query` workflow.

### Init — implicit/lazy

Triggered automatically by Connect/Pull/List on first invocation when
`connected-wikis.json` is missing or `.gitignore` lacks `connected-wikis/`.
Manually: `venv/bin/python tools/connected_wikis.py init`. Aborts if `wiki/`
is missing (run project init first). See Setup section for details.

### Connect — `"<repo-url-or-path>을 <id>로 연결해줘"` / `"connect the <name> wiki"`

1. Run `venv/bin/python tools/connected_wikis.py connect <source> --id <id> [--name <name>]`
2. The CLI may emit `PROMPT: consent | ...` followed by `OPTIONS: accept reject` and exit code 4.
   When this happens, present the prompt to the user, get their answer, and re-invoke the same
   command with `--decision consent=<answer>` appended. CLI is idempotent — reservation persists
   across re-invocations until success or rollback.
3. Re-invoke as needed for additional decisions (e.g., `--decision mismatch=reindex`).
4. On success: external wiki is cloned to `connected-wikis/<id>/`, indexed into ChromaDB
   collection `wiki-ext-<id>`, and registered in `connected-wikis.json` with `enabled=true,
   status=ok`.

### Toggle — `"<id> 켜/꺼"`

`venv/bin/python tools/connected_wikis.py toggle <id> on|off`

Updates `enabled` flag only — no reindex needed.

### Disconnect — `"<id> 연결 해제"`

`venv/bin/python tools/connected_wikis.py disconnect <id> [--decision disconnect-grep=proceed]`

CLI greps `wiki/{synthesis,concepts,entities,sources}/` for `(출처: <id>)` /
`(source: <id>)` / `connected-wikis/<id>/` patterns and reports findings. User must
acknowledge with `disconnect-grep=proceed` to continue. Then deletes the JSON entry,
ChromaDB collection, clone directory, and per-wiki lock file.

### Pull — `"연결된 wiki들 업데이트"`

`venv/bin/python tools/connected_wikis.py pull [--decision mismatch=update|reindex]`

Per-wiki:
- `git`: `git fetch` + `git reset --hard origin/<default-branch>`. Diff-based partial reindex
  via `--add`. fetch failure → `status="unreachable"` (preserves `enabled`).
- `local`: mtime-based partial reindex. Path missing → `status="unreachable"`.

Embedding model mismatch surfaces an interactive `mismatch` prompt
(`update` = update field only / `reindex` = recompute embeddings).

### List/Status — `"연결된 wiki 목록 보여줘"`

`venv/bin/python tools/connected_wikis.py list`

Outputs a markdown table: `id | name | source_type | enabled | status | last_pulled |
embedding_model | pages`. No commit, no log entry — read-only.

### Query Hook (augments core Query workflow)

**After Query step 1 (running `{search.query}`):**

1. Read `connected-wikis.json`.
2. Filter `wikis[]` to those with `enabled == true && status == "ok"`.
   Apply per-query overrides if the user said `"<id>로만"` / `"using only <id>"`
   (whitelist) or `"<id> 빼고"` / `"excluding <id>"` (blacklist) — these do **not**
   mutate `connected-wikis.json`. If both are present, whitelist takes precedence,
   then blacklist is applied to the whitelisted set.
3. For each candidate, compare `embedding_backend`/`embedding_model` to the active
   backend (from `venv/bin/python tools/search.py --print-model`). If they match →
   include in unified `--collections wiki,wiki-ext-<id1>,...` query and merge
   results by score. If they mismatch → run that collection's query separately
   and present its top hits in a labeled section ("출처 모델 불일치 — 점수 비교
   불가"), without merging into the unified ranking. Warn (don't fail).
4. Then proceed to Query step 2 with the merged + segregated result set.

Multi-collection invocation must use `tools/search.py` directly (the `{search.*}`
token resolver does not support `--collection` flags).

#### Citation Format (replaces Query step 3 default when external wiki used)

- **Inline label**: each sentence sourced from an external wiki ends with
  `(출처: <id>)` (or `(source: <id>)` if `wiki_language: en`).
- **Citations block**: if any external wiki was used in the answer, append a
  `## Citations` (or `## 인용` for `wiki_language: ko`) section listing all
  pages cited. Local pages as wikilinks; external pages as full paths
  `connected-wikis/<id>/wiki/...` (NOT wikilinks). For `source_type: git` external
  pages, also include the upstream URL: `https://<host>/<owner>/<repo>/blob/<commit>/wiki/...`.

If 0 external wikis are enabled or no external result was cited, fall back to
the core Query step 3 citation behavior.

## Configuration

| Option | Default | Description |
|--------|---------|-------------|
| Config path | `connected-wikis.json` | Per-machine wiki list (committed) |
| Clone path | `connected-wikis/<id>/` | Where git sources are cloned (gitignored) |
| Lock dir | `connected-wikis/.locks/` | Per-wiki POSIX flocks |
| Global lock | `connected-wikis.lock` | JSON read-modify-write critical section |
| Collection prefix | `wiki-ext-<id>` | ChromaDB collection name format |
| ID format | `^[a-z0-9]([a-z0-9-]{0,29}[a-z0-9])?$` | Reserved: `wiki`, `local`, `ext`, `default` |

## Platform Support

POSIX-only (Linux/macOS). Windows is not supported in v1.
