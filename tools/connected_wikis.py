"""Connected Knowledge Bases — manage external seojae wikis as toggleable sources.

See docs/connected-knowledge-bases.md for the canonical design.
"""

from __future__ import annotations

import argparse
import contextlib
import fcntl
import json
import os
import re
import shutil
import subprocess
import sys
from datetime import date, datetime
from pathlib import Path

CONFIG_VERSION = 1
DEFAULT_CONFIG: dict = {"schema_version": CONFIG_VERSION, "wikis": []}

_REPO_ROOT = Path(__file__).parent.parent
CONFIG_PATH = _REPO_ROOT / "connected-wikis.json"
CONNECTED_DIR = _REPO_ROOT / "connected-wikis"
LOCK_DIR = CONNECTED_DIR / ".locks"
GLOBAL_LOCK = _REPO_ROOT / "connected-wikis.lock"
INDEX_PATH = str(_REPO_ROOT / "search-index")

EXIT_DECISION_PENDING = 4

_ID_RE = re.compile(r"^[a-z0-9]([a-z0-9-]{0,29}[a-z0-9])?$")
_RESERVED_IDS = frozenset({"wiki", "local", "ext", "default"})


# --- Errors ---

class IdError(ValueError):
    pass


class DecisionPending(SystemExit):
    """Raised when CLI needs an interactive decision; encoded as exit 4."""

    def __init__(self):
        super().__init__(EXIT_DECISION_PENDING)


class _PullUnreachable(Exception):
    pass


# --- Config I/O ---

class ConfigCorrupt(RuntimeError):
    """Raised when connected-wikis.json is unreadable or structurally invalid."""


def load_config(path: Path) -> dict:
    """Read connected-wikis.json. Returns DEFAULT_CONFIG if missing.

    Performs in-memory field backfill (status, embedding_*) but does NOT write back —
    the next save_config() call persists backfilled values.

    Raises ConfigCorrupt with a recovery hint if the file exists but is invalid JSON
    or has the wrong shape.
    """
    if not path.exists():
        return dict(DEFAULT_CONFIG, wikis=[])

    try:
        with path.open("r", encoding="utf-8") as f:
            cfg = json.load(f)
    except json.JSONDecodeError as e:
        raise ConfigCorrupt(
            f"{path} is not valid JSON: {e}. "
            f"Restore from git history or delete to reset."
        ) from e

    if not isinstance(cfg, dict):
        raise ConfigCorrupt(
            f"{path} top-level value is {type(cfg).__name__}, expected object. "
            f"Restore from git history or delete to reset."
        )

    cfg.setdefault("schema_version", CONFIG_VERSION)
    cfg.setdefault("wikis", [])
    if not isinstance(cfg["wikis"], list):
        raise ConfigCorrupt(
            f"{path} 'wikis' field is {type(cfg['wikis']).__name__}, expected list."
        )

    for w in cfg["wikis"]:
        if isinstance(w, dict):
            _backfill_wiki(w)
    return cfg


def _backfill_wiki(w: dict) -> None:
    """Add missing fields (status, embedding_backend, embedding_model)."""
    w.setdefault("status", "ok")
    if "embedding_backend" not in w or "embedding_model" not in w:
        backend, model = _resolve_active_model_or_none()
        w.setdefault("embedding_backend", backend)
        w.setdefault("embedding_model", model)


def _resolve_active_model_or_none() -> tuple[str | None, str | None]:
    """Return (backend, model) by calling tools/search.py --print-model. (None, None) on failure."""
    try:
        r = subprocess.run(
            [sys.executable, str(_REPO_ROOT / "tools" / "search.py"), "--print-model"],
            capture_output=True, text=True, timeout=10,
        )
    except Exception:
        return (None, None)
    if r.returncode != 0:
        return (None, None)
    backend = model = None
    for line in r.stdout.strip().split("\n"):
        if line.startswith("backend="):
            backend = line[len("backend="):]
        elif line.startswith("model="):
            model = line[len("model="):]
    return (backend, model)


def save_config(path: Path, cfg: dict) -> None:
    """Atomic write: tmp file + fsync + os.replace."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with tmp.open("w", encoding="utf-8") as f:
        json.dump(cfg, f, indent=2, ensure_ascii=False)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, path)


# --- Locks (POSIX flock) ---

@contextlib.contextmanager
def with_global_lock(lock_path: Path):
    """Hold an exclusive flock on lock_path for the duration of the with-block.

    Used for short read-modify-write sections on connected-wikis.json.
    POSIX-only (Windows not supported in v1).
    """
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(str(lock_path), os.O_RDWR | os.O_CREAT, 0o644)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX)
        yield
    finally:
        try:
            fcntl.flock(fd, fcntl.LOCK_UN)
        finally:
            os.close(fd)


def acquire_per_wiki_lock(lock_dir: Path, wiki_id: str, blocking: bool = True) -> int | None:
    """Acquire <lock_dir>/<wiki_id>.lock (LOCK_EX). Returns fd or None on failure (non-blocking)."""
    lock_dir.mkdir(parents=True, exist_ok=True)
    lock_path = lock_dir / f"{wiki_id}.lock"
    fd = os.open(str(lock_path), os.O_RDWR | os.O_CREAT, 0o644)
    flags = fcntl.LOCK_EX | (0 if blocking else fcntl.LOCK_NB)
    try:
        fcntl.flock(fd, flags)
        return fd
    except BlockingIOError:
        os.close(fd)
        return None


def release_per_wiki_lock(fd: int) -> None:
    try:
        fcntl.flock(fd, fcntl.LOCK_UN)
    finally:
        os.close(fd)


# --- Validation ---

def validate_id(wiki_id: str, existing_wikis: list[dict]) -> None:
    """Raise IdError on invalid id. Otherwise return None."""
    if not _ID_RE.match(wiki_id):
        raise IdError(
            f"invalid id '{wiki_id}': must match ^[a-z0-9]([a-z0-9-]{{0,29}}[a-z0-9])?$ "
            "(lowercase alphanumeric, hyphens allowed in middle, max 31 chars)"
        )
    if "--" in wiki_id:
        raise IdError(f"invalid id '{wiki_id}': consecutive hyphens not allowed")
    if wiki_id in _RESERVED_IDS:
        raise IdError(f"invalid id '{wiki_id}': reserved word")
    if any(w["id"] == wiki_id for w in existing_wikis):
        raise IdError(f"invalid id '{wiki_id}': already exists")


# --- Decision protocol ---

def request_decision(*, prompt_key: str, question: str, options: list[str],
                     decisions: dict[str, str]) -> str:
    """Resolve an interactive decision.

    Three paths:
    1. decisions[prompt_key] present → validate against options, return.
    2. stdin is TTY → prompt with input(), return user's choice.
    3. else → print PROMPT/OPTIONS and raise DecisionPending (exit 4).
    """
    if prompt_key in decisions:
        val = decisions[prompt_key]
        if val not in options:
            raise ValueError(f"invalid decision for '{prompt_key}': '{val}' not in {options}")
        return val

    if sys.stdin.isatty():
        prompt = f"{question} [{'/'.join(options)}]: "
        while True:
            try:
                ans = input(prompt).strip()
            except EOFError:
                # PTY wrapper or piped EOF — fall through to PROMPT/exit-4 protocol.
                break
            if ans in options:
                return ans
            print(f"Invalid. Choose: {options}")

    print(f"PROMPT: {prompt_key} | {question}")
    print(f"OPTIONS: {' '.join(options)}")
    raise DecisionPending()


def parse_decisions(raw: list[str] | None) -> dict[str, str]:
    """Parse --decision key=value pairs into a dict."""
    out: dict[str, str] = {}
    if not raw:
        return out
    for entry in raw:
        if "=" not in entry:
            raise ValueError(f"--decision must be key=value, got '{entry}'")
        k, v = entry.split("=", 1)
        out[k.strip()] = v.strip()
    return out


# --- Helpers (subprocess, git, chromadb, log, commit) ---

def _run_reindex(wiki_path: str, collection: str):
    """Run tools/search.py --reindex --collection <collection>. Override-able for tests."""
    return subprocess.run(
        [sys.executable, str(_REPO_ROOT / "tools" / "search.py"),
         "--reindex", "--wiki-path", wiki_path, "--collection", collection],
        capture_output=True, text=True,
    )


def _run_add_page(filepath: str, collection: str):
    """Run tools/search.py --add <file> --collection <coll>. Override-able for tests."""
    return subprocess.run(
        [sys.executable, str(_REPO_ROOT / "tools" / "search.py"),
         "--add", filepath, "--collection", collection],
        capture_output=True, text=True,
    )


def _delete_collection(name: str) -> None:
    import chromadb
    import gc
    client = None
    try:
        client = chromadb.PersistentClient(path=INDEX_PATH)
        client.delete_collection(name)
    except Exception:
        pass
    finally:
        # Drop the client reference so SQLite handles get freed promptly,
        # avoiding lock contention with subsequent ChromaDB operations
        # (same pattern the test suite uses defensively).
        del client
        gc.collect()


def _collection_count(index_path: str, collection_name: str) -> int | None:
    """Return collection count or None if missing."""
    import chromadb
    import gc
    client = None
    try:
        client = chromadb.PersistentClient(path=index_path)
        return client.get_collection(collection_name).count()
    except Exception:
        return None
    finally:
        del client
        gc.collect()


def _detect_default_branch(repo_dir: Path) -> str:
    """Detect via `git symbolic-ref refs/remotes/origin/HEAD`. Falls back to `main`."""
    for attempt in range(2):
        r = subprocess.run(["git", "symbolic-ref", "refs/remotes/origin/HEAD"],
                           cwd=str(repo_dir), capture_output=True, text=True)
        if r.returncode == 0:
            ref = r.stdout.strip()
            return ref.removeprefix("refs/remotes/origin/")
        if attempt == 0:
            subprocess.run(["git", "remote", "set-head", "origin", "--auto"],
                           cwd=str(repo_dir), capture_output=True)
    return "main"


def _git_head_sha(repo_dir: Path) -> str:
    r = subprocess.run(["git", "rev-parse", "HEAD"], cwd=str(repo_dir),
                       capture_output=True, text=True)
    return r.stdout.strip()[:7] if r.returncode == 0 else ""


def _append_log(line: str) -> None:
    """Append `## [YYYY-MM-DD] <action> | ...` to log.md if it exists."""
    log_path = _REPO_ROOT / "log.md"
    if not log_path.exists():
        return
    with log_path.open("a", encoding="utf-8") as f:
        f.write(f"\n## [{date.today().isoformat()}] {line}\n")


def _git_commit(message: str) -> None:
    """Stage tracked changes and commit. Best-effort — silent on failure."""
    try:
        subprocess.run(["git", "add", "connected-wikis.json", "log.md", ".gitignore"],
                       cwd=str(_REPO_ROOT), capture_output=True, check=False)
        subprocess.run(["git", "commit", "-m", message],
                       cwd=str(_REPO_ROOT), capture_output=True, check=False)
    except FileNotFoundError:
        pass


def _infer_source_type(source: str) -> str:
    if source.startswith(("http://", "https://", "git@", "ssh://", "git://")):
        return "git"
    return "local"


def _infer_name(source: str, source_type: str) -> str:
    if source_type == "git":
        slug = source.rstrip("/").split("/")[-1]
        if "@" in slug and ":" in slug:
            slug = slug.split(":")[-1]
        return slug[:-4] if slug.endswith(".git") else slug
    return Path(source).name


def _grep_references(wiki_id: str) -> list[tuple[str, int, str]]:
    """Search wiki/{synthesis,concepts,entities,sources} for citation patterns."""
    patterns = [
        re.compile(rf"\(출처:\s*{re.escape(wiki_id)}\s*\)"),
        re.compile(rf"\(source:\s*{re.escape(wiki_id)}\s*\)"),
        re.compile(rf"connected-wikis/{re.escape(wiki_id)}/"),
    ]
    matches: list[tuple[str, int, str]] = []
    for sub in ("synthesis", "concepts", "entities", "sources"):
        d = _REPO_ROOT / "wiki" / sub
        if not d.exists():
            continue
        for md in d.rglob("*.md"):
            try:
                for i, line in enumerate(md.read_text(encoding="utf-8").split("\n"), start=1):
                    if any(p.search(line) for p in patterns):
                        matches.append((str(md.relative_to(_REPO_ROOT)), i, line))
            except Exception:
                continue
    return matches


# --- Subcommands ---

def cmd_init() -> int:
    """Lazy bootstrap. Idempotent. Commits extension activation on first setup."""
    wiki_dir = _REPO_ROOT / "wiki"
    if not wiki_dir.exists():
        print("Error: wiki/ directory not found. Run project init first.", file=sys.stderr)
        return 1

    bootstrapped = False
    if not CONFIG_PATH.exists():
        with with_global_lock(GLOBAL_LOCK):
            if not CONFIG_PATH.exists():
                save_config(CONFIG_PATH, dict(DEFAULT_CONFIG, wikis=[]))
                bootstrapped = True

    gi_path = _REPO_ROOT / ".gitignore"
    needed = ["connected-wikis/", "connected-wikis.lock"]
    if gi_path.exists():
        existing = set(gi_path.read_text(encoding="utf-8").split("\n"))
    else:
        existing = set()
    missing = [n for n in needed if n not in existing]
    if missing:
        with gi_path.open("a", encoding="utf-8") as f:
            for n in missing:
                f.write(f"{n}\n")
        bootstrapped = True

    if bootstrapped:
        _git_commit("extension: enable connected-wikis")

    print("connected-wikis initialized")
    return 0


def cmd_list() -> int:
    cmd_init()

    cfg = load_config(CONFIG_PATH)
    wikis = cfg["wikis"]

    if not wikis:
        print("| id | name | source_type | enabled | status | last_pulled | embedding_model | pages |")
        print("no connected wikis (0 wikis)")
        _print_help_examples()
        return 0

    cols = ["id", "name", "source_type", "enabled", "status",
            "last_pulled", "embedding_model", "pages"]
    print("| " + " | ".join(cols) + " |")
    print("|" + "|".join(["---"] * len(cols)) + "|")
    for w in wikis:
        count = _collection_count(INDEX_PATH, f"wiki-ext-{w['id']}")
        pages = "N/A" if count is None else str(count)
        row = [
            w["id"],
            w.get("name", ""),
            w.get("source_type", ""),
            "true" if w.get("enabled") else "false",
            w.get("status", ""),
            w.get("last_pulled", "—"),
            w.get("embedding_model") or "—",
            pages,
        ]
        print("| " + " | ".join(row) + " |")

    _print_help_examples()
    return 0


def _print_help_examples() -> None:
    print()
    print("Examples:")
    print('  connect <url-or-path> --id <id>')
    print('  toggle <id> on|off')
    print('  pull')
    print('  disconnect <id>')


def cmd_toggle(wiki_id: str, state: str) -> int:
    cmd_init()
    with with_global_lock(GLOBAL_LOCK):
        cfg = load_config(CONFIG_PATH)
        for w in cfg["wikis"]:
            if w["id"] == wiki_id:
                w["enabled"] = (state == "on")
                save_config(CONFIG_PATH, cfg)
                _append_log(f"toggle | {wiki_id} {state}")
                _git_commit(f"config: toggle {wiki_id}")
                print(f"{wiki_id}: enabled={w['enabled']}")
                return 0
        print(f"Error: wiki '{wiki_id}' not found", file=sys.stderr)
        return 1


def _rollback_connect(wiki_id: str, coll_name: str, clone_dir: Path, source_type: str) -> None:
    """Idempotent rollback (spec 'common abort policy')."""
    try:
        _delete_collection(coll_name)
    except Exception as e:
        print(f"Rollback: collection delete failed: {e}", file=sys.stderr)
    if source_type == "git":
        try:
            if clone_dir.exists():
                shutil.rmtree(clone_dir)
        except Exception as e:
            print(f"Rollback: clone dir delete failed: {e}", file=sys.stderr)
    try:
        with with_global_lock(GLOBAL_LOCK):
            cfg = load_config(CONFIG_PATH)
            cfg["wikis"] = [w for w in cfg["wikis"] if w["id"] != wiki_id]
            save_config(CONFIG_PATH, cfg)
    except Exception as e:
        print(f"Rollback: JSON cleanup failed: {e}", file=sys.stderr)
    try:
        (LOCK_DIR / f"{wiki_id}.lock").unlink(missing_ok=True)
    except Exception:
        pass


def cmd_connect(source: str, wiki_id: str, name: str | None,
                source_type: str | None, decisions: dict[str, str]) -> int:
    cmd_init()

    if source_type is None:
        source_type = _infer_source_type(source)
    if name is None:
        name = _infer_name(source, source_type)
    today = date.today().isoformat()
    coll_name = f"wiki-ext-{wiki_id}"
    clone_dir = CONNECTED_DIR / wiki_id

    # Resume-on-re-invocation: a prior call that exited via DecisionPending
    # leaves a status="connecting" entry. Same source AND source_type → resume.
    cfg = load_config(CONFIG_PATH)
    existing = next((w for w in cfg["wikis"] if w["id"] == wiki_id), None)
    added_date = today
    if existing is not None:
        if (existing.get("status") == "connecting"
                and existing.get("source") == source
                and existing.get("source_type") == source_type):
            added_date = existing.get("added", today)
            name = existing.get("name", name)
        elif existing.get("status") == "connecting":
            print(
                f"Error: id '{wiki_id}' is mid-connect with different "
                f"source/source_type (reserved as {existing.get('source_type')}:{existing.get('source')!r}); "
                "either retry with the original args or run disconnect to clear.",
                file=sys.stderr,
            )
            return 1
        else:
            print(f"Error: id '{wiki_id}' already exists (status={existing.get('status')})",
                  file=sys.stderr)
            return 1
    else:
        try:
            validate_id(wiki_id, cfg["wikis"])
        except IdError as e:
            print(f"Error: {e}", file=sys.stderr)
            return 1

        with with_global_lock(GLOBAL_LOCK):
            cfg = load_config(CONFIG_PATH)
            if any(w["id"] == wiki_id for w in cfg["wikis"]):
                print(f"Error: id '{wiki_id}' already reserved", file=sys.stderr)
                return 1
            cfg["wikis"].append({
                "id": wiki_id, "name": name, "source_type": source_type, "source": source,
                "enabled": True, "status": "connecting", "added": added_date,
                "embedding_backend": None, "embedding_model": None,
            })
            save_config(CONFIG_PATH, cfg)

    lock_fd = acquire_per_wiki_lock(LOCK_DIR, wiki_id, blocking=True)
    try:
        if source_type == "git":
            if clone_dir.exists():
                # resume: prior call already cloned
                wiki_subdir = clone_dir / "wiki"
            else:
                clone_dir.parent.mkdir(parents=True, exist_ok=True)
                # `--` prevents `source` strings starting with `--` from being
                # parsed as git options (e.g., --upload-pack=evil-cmd).
                r = subprocess.run(["git", "clone", "--", source, str(clone_dir)],
                                   capture_output=True, text=True)
                if r.returncode != 0:
                    _rollback_connect(wiki_id, coll_name, clone_dir, source_type)
                    print(f"Error: git clone failed: {r.stderr}", file=sys.stderr)
                    return 1
                wiki_subdir = clone_dir / "wiki"
        else:
            if not Path(source).exists():
                _rollback_connect(wiki_id, coll_name, clone_dir, source_type)
                print(f"Error: local path not found: {source}", file=sys.stderr)
                return 1
            wiki_subdir = Path(source) / "wiki"

        if not wiki_subdir.exists() or not any(wiki_subdir.rglob("*.md")):
            _rollback_connect(wiki_id, coll_name, clone_dir, source_type)
            print(f"Error: source has no wiki/**/*.md: {wiki_subdir}", file=sys.stderr)
            return 1

        readme_root = clone_dir if source_type == "git" else Path(source)
        readme = (readme_root / "README.md") if (readme_root / "README.md").exists() \
                 else (wiki_subdir / "index.md") if (wiki_subdir / "index.md").exists() \
                 else None
        readme_preview = readme.read_text(encoding="utf-8")[:2000] if readme else "(no README/index.md)"
        print(f"--- {readme.name if readme else 'preview'} ---\n{readme_preview}\n--- end ---")
        decision = request_decision(
            prompt_key="consent",
            question=f"Trust external wiki '{wiki_id}' content? It will be indexed as data, not executed.",
            options=["accept", "reject"],
            decisions=decisions,
        )
        if decision != "accept":
            _rollback_connect(wiki_id, coll_name, clone_dir, source_type)
            print("Connect aborted: consent rejected", file=sys.stderr)
            return 1

        backend, model = _resolve_active_model_or_none()
        if backend is None or model is None:
            _rollback_connect(wiki_id, coll_name, clone_dir, source_type)
            print("Error: no active search-backend extension. "
                  "Enable extensions/search-chromadb.md or another search-backend provider.",
                  file=sys.stderr)
            return 1

        r = _run_reindex(str(wiki_subdir), coll_name)
        if r.returncode != 0:
            _rollback_connect(wiki_id, coll_name, clone_dir, source_type)
            print(f"Error: reindex failed: {r.stderr}", file=sys.stderr)
            return 1
        m = re.search(r"(\d+) pages indexed, (\d+) skipped", r.stdout)
        if m and int(m.group(2)) > 0:
            print(f"Note: {m.group(2)} pages skipped during reindex", file=sys.stderr)

        commit_hash = _git_head_sha(clone_dir) if source_type == "git" else None
        with with_global_lock(GLOBAL_LOCK):
            cfg = load_config(CONFIG_PATH)
            for w in cfg["wikis"]:
                if w["id"] == wiki_id:
                    w["status"] = "ok"
                    w["embedding_backend"] = backend
                    w["embedding_model"] = model
                    w["last_pulled"] = today
                    if commit_hash:
                        w["commit"] = commit_hash
            save_config(CONFIG_PATH, cfg)

        _append_log(f"connect | {wiki_id}")
        _git_commit(f"connect: {wiki_id}")
        print(f"Connected: {wiki_id}")
        return 0
    finally:
        release_per_wiki_lock(lock_fd)


def cmd_disconnect(wiki_id: str, decisions: dict[str, str]) -> int:
    cmd_init()
    cfg = load_config(CONFIG_PATH)
    if not any(w["id"] == wiki_id for w in cfg["wikis"]):
        print(f"Warning: wiki '{wiki_id}' not found, no-op", file=sys.stderr)
        return 0

    lock_fd = acquire_per_wiki_lock(LOCK_DIR, wiki_id, blocking=False)
    if lock_fd is None:
        print(f"Error: '{wiki_id}' is locked by another operation. Try again later.",
              file=sys.stderr)
        return 1

    try:
        refs = _grep_references(wiki_id)
        if refs:
            print(f"Found {len(refs)} reference(s) to '{wiki_id}':")
            for path, line_no, line in refs[:20]:
                print(f"  {path}:{line_no}: {line.strip()}")
            decision = request_decision(
                prompt_key="disconnect-grep",
                question=f"Proceed with disconnect? Local pages reference '{wiki_id}'.",
                options=["proceed", "abort"],
                decisions=decisions,
            )
            if decision == "abort":
                print("Disconnect aborted.", file=sys.stderr)
                return 1

        with with_global_lock(GLOBAL_LOCK):
            cfg = load_config(CONFIG_PATH)
            cfg["wikis"] = [w for w in cfg["wikis"] if w["id"] != wiki_id]
            save_config(CONFIG_PATH, cfg)

        # JSON entry already removed — best-effort cleanup of remaining artifacts.
        # Failures here would orphan files but the user has no JSON handle to retry,
        # so log loudly and proceed.
        try:
            _delete_collection(f"wiki-ext-{wiki_id}")
        except Exception as e:
            print(f"Warning: could not delete collection 'wiki-ext-{wiki_id}': {e}",
                  file=sys.stderr)

        clone_dir = CONNECTED_DIR / wiki_id
        if clone_dir.exists():
            try:
                shutil.rmtree(clone_dir)
            except Exception as e:
                print(f"Warning: could not remove {clone_dir}: {e}", file=sys.stderr)

        _append_log(f"disconnect | {wiki_id}")
        _git_commit(f"disconnect: {wiki_id}")
        print(f"Disconnected: {wiki_id}")
        return 0
    finally:
        release_per_wiki_lock(lock_fd)
        try:
            (LOCK_DIR / f"{wiki_id}.lock").unlink(missing_ok=True)
        except Exception:
            pass


def _checked_add_page(filepath: str, collection: str, wiki_id: str) -> None:
    """Run _run_add_page and log non-zero exit to stderr (best-effort)."""
    r = _run_add_page(filepath, collection)
    if r.returncode != 0:
        print(f"Warning: add_page failed for {wiki_id}:{filepath}: {r.stderr.strip()}",
              file=sys.stderr)


def _checked_reindex(wiki_path: str, collection: str, wiki_id: str) -> None:
    """Run _run_reindex and log non-zero exit to stderr (best-effort)."""
    r = _run_reindex(wiki_path, collection)
    if r.returncode != 0:
        print(f"Warning: reindex failed for {wiki_id}: {r.stderr.strip()}",
              file=sys.stderr)


def _pull_git(w: dict, today: str, backend: str | None, model: str | None,
              decisions: dict[str, str]) -> bool:
    """Mutates w in place. Raises _PullUnreachable on access failure.

    Embedding-model mismatch is resolved BEFORE any clone-state mutation, so
    DecisionPending leaves disk and JSON consistent for resume.
    """
    clone_dir = CONNECTED_DIR / w["id"]
    if not clone_dir.exists():
        clone_dir.parent.mkdir(parents=True, exist_ok=True)
        r = subprocess.run(["git", "clone", "--", w["source"], str(clone_dir)],
                           capture_output=True, text=True)
        if r.returncode != 0:
            raise _PullUnreachable(r.stderr)

    # Resolve mismatch decision FIRST — must not mutate clone state before this,
    # because DecisionPending exits with the disk untouched and JSON re-readable.
    mismatch_decision: str | None = None
    if backend and model and (w.get("embedding_backend") != backend
                              or w.get("embedding_model") != model):
        mismatch_decision = request_decision(
            prompt_key="mismatch",
            question=f"'{w['id']}' embedding model differs (was {w.get('embedding_model')}, now {model}). Update field only or reindex?",
            options=["update", "reindex"],
            decisions=decisions,
        )

    branch = _detect_default_branch(clone_dir)

    r = subprocess.run(["git", "fetch", "origin", branch],
                       cwd=str(clone_dir), capture_output=True, text=True)
    if r.returncode != 0:
        raise _PullUnreachable(r.stderr)

    old_commit = w.get("commit")
    subprocess.run(["git", "reset", "--hard", f"origin/{branch}"],
                   cwd=str(clone_dir), capture_output=True, check=False)
    new_commit = _git_head_sha(clone_dir)

    coll = f"wiki-ext-{w['id']}"

    if mismatch_decision == "reindex":
        _checked_reindex(str(clone_dir / "wiki"), coll, w["id"])
    if mismatch_decision is not None:
        w["embedding_backend"] = backend
        w["embedding_model"] = model

    # If we already did a full reindex above, skip the diff/full-reindex pass below.
    if mismatch_decision != "reindex":
        if old_commit:
            d = subprocess.run(["git", "diff", "--name-only", old_commit, "HEAD"],
                               cwd=str(clone_dir), capture_output=True, text=True)
            if d.returncode == 0:
                for fname in d.stdout.strip().split("\n"):
                    if not fname or not fname.startswith("wiki/") or not fname.endswith(".md"):
                        continue
                    _checked_add_page(str(clone_dir / fname), coll, w["id"])
            else:
                _checked_reindex(str(clone_dir / "wiki"), coll, w["id"])
        else:
            _checked_reindex(str(clone_dir / "wiki"), coll, w["id"])

    w["last_pulled"] = today
    w["commit"] = new_commit
    if w.get("status") != "ok":
        w["status"] = "ok"
    return True


def _pull_local(w: dict, today: str, backend: str | None, model: str | None) -> bool:
    src = Path(w["source"])
    if not src.exists():
        raise _PullUnreachable(f"local path missing: {src}")

    last_pulled = w.get("last_pulled", "1970-01-01")
    # Note: last_pulled is date-only (YYYY-MM-DD); midnight-local granularity is
    # acceptable per spec — same-day double pull may skip files modified mid-day.
    threshold = datetime.fromisoformat(last_pulled).timestamp()

    wiki_subdir = src / "wiki"
    if not wiki_subdir.exists():
        raise _PullUnreachable(f"no wiki/ in {src}")

    coll = f"wiki-ext-{w['id']}"
    for md in wiki_subdir.rglob("*.md"):
        if md.stat().st_mtime > threshold:
            _checked_add_page(str(md), coll, w["id"])

    if backend and model:
        w["embedding_backend"] = backend
        w["embedding_model"] = model
    w["last_pulled"] = today
    if w.get("status") != "ok":
        w["status"] = "ok"
    return True


_PULL_MUTABLE_FIELDS = (
    "status", "last_pulled", "commit", "embedding_backend", "embedding_model",
)


def cmd_pull(decisions: dict[str, str]) -> int:
    cmd_init()

    cfg = load_config(CONFIG_PATH)
    today = date.today().isoformat()
    success_n = 0
    fail_n = 0
    meta_changed = False
    became_unreachable = 0

    backend, model = _resolve_active_model_or_none()

    # Track per-wiki updates separately so we can merge them on top of a fresh
    # config snapshot at the end — protects against concurrent toggle/connect
    # writes that happened during the (potentially long) per-wiki git fetches.
    updates: dict[str, dict] = {}

    for w in cfg["wikis"]:
        wid = w["id"]
        lock_fd = acquire_per_wiki_lock(LOCK_DIR, wid, blocking=True)
        try:
            try:
                if w["source_type"] == "git":
                    _pull_git(w, today, backend, model, decisions)
                else:
                    _pull_local(w, today, backend, model)
                meta_changed = True
                success_n += 1
            except _PullUnreachable:
                fail_n += 1
                if w.get("status") != "unreachable":
                    w["status"] = "unreachable"
                    meta_changed = True
                    became_unreachable += 1
            updates[wid] = {k: w[k] for k in _PULL_MUTABLE_FIELDS if k in w}
        finally:
            release_per_wiki_lock(lock_fd)

    if meta_changed:
        with with_global_lock(GLOBAL_LOCK):
            # Re-read under the lock and merge the per-wiki updates so we don't
            # clobber concurrent toggle/connect writes that happened mid-loop.
            current = load_config(CONFIG_PATH)
            for w in current["wikis"]:
                if w["id"] in updates:
                    w.update(updates[w["id"]])
            save_config(CONFIG_PATH, current)
        if success_n > 0:
            msg = f"pull: {success_n} wikis updated"
        else:
            msg = f"pull: 0 fresh updates ({became_unreachable} became unreachable)"
        _append_log(f"pull | {success_n} success / {fail_n} failed")
        _git_commit(msg)
    else:
        print("pull: no changes")

    print(f"Pull summary: {success_n} success / {fail_n} failed")
    return 0


# --- CLI ---

def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="connected_wikis", description="Manage connected wikis")
    sub = parser.add_subparsers(dest="cmd", required=True)
    sub.add_parser("init", help="Initialize connected-wikis.json + .gitignore")
    sub.add_parser("list", help="List connected wikis")

    p_tog = sub.add_parser("toggle", help="Enable/disable a wiki")
    p_tog.add_argument("wiki_id")
    p_tog.add_argument("state", choices=["on", "off"])

    p_conn = sub.add_parser("connect", help="Connect an external wiki")
    p_conn.add_argument("source", help="Git URL or local path")
    p_conn.add_argument("--id", dest="wiki_id", required=True)
    p_conn.add_argument("--name", default=None)
    p_conn.add_argument("--source-type", choices=["git", "local"], default=None,
                        help="Auto-detected from source (https://* → git, else local)")
    p_conn.add_argument("--decision", action="append", dest="decisions", default=[])

    p_dis = sub.add_parser("disconnect", help="Disconnect an external wiki")
    p_dis.add_argument("wiki_id")
    p_dis.add_argument("--decision", action="append", dest="decisions", default=[])

    p_pull = sub.add_parser("pull", help="Update all connected wikis")
    p_pull.add_argument("--decision", action="append", dest="decisions", default=[])

    args = parser.parse_args(argv)

    if args.cmd == "init":
        return cmd_init()
    if args.cmd == "list":
        return cmd_list()
    if args.cmd == "toggle":
        return cmd_toggle(args.wiki_id, args.state)
    if args.cmd == "connect":
        return cmd_connect(args.source, args.wiki_id, args.name,
                           args.source_type, parse_decisions(args.decisions))
    if args.cmd == "disconnect":
        return cmd_disconnect(args.wiki_id, parse_decisions(args.decisions))
    if args.cmd == "pull":
        return cmd_pull(parse_decisions(args.decisions))
    return 2


if __name__ == "__main__":
    sys.exit(main())
