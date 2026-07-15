import json
import os
import subprocess
import sys
import threading
import time
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from tools.connected_wikis import (
    DEFAULT_CONFIG, CONFIG_VERSION,
    load_config, save_config,
    with_global_lock, acquire_per_wiki_lock, release_per_wiki_lock,
    validate_id, IdError,
    request_decision, DecisionPending, parse_decisions,
)


# --- Test fixtures ---

def _setup_repo(tmp_path, monkeypatch, with_wiki=True):
    """Common test fixture: monkey-patch module paths to tmp_path."""
    from tools import connected_wikis as cw
    if with_wiki:
        (tmp_path / "wiki").mkdir(exist_ok=True)
    monkeypatch.setattr(cw, "_REPO_ROOT", tmp_path)
    monkeypatch.setattr(cw, "CONFIG_PATH", tmp_path / "connected-wikis.json")
    monkeypatch.setattr(cw, "CONNECTED_DIR", tmp_path / "connected-wikis")
    monkeypatch.setattr(cw, "LOCK_DIR", tmp_path / "connected-wikis" / ".locks")
    monkeypatch.setattr(cw, "GLOBAL_LOCK", tmp_path / "connected-wikis.lock")
    monkeypatch.setattr(cw, "INDEX_PATH", str(tmp_path / "search-index"))
    return cw


def _make_fake_remote(tmp_path: Path, branch: str = "main") -> Path:
    """Create a local git repo that can be cloned. Returns path."""
    repo = tmp_path / f"fake-remote-{branch}"
    repo.mkdir()
    subprocess.run(["git", "init", "-b", branch], cwd=repo, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.email", "t@t"], cwd=repo, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.name", "t"], cwd=repo, check=True, capture_output=True)
    (repo / "wiki").mkdir()
    (repo / "wiki" / "p.md").write_text("---\ntitle: P\ntags: []\n---\nBody", encoding="utf-8")
    (repo / "README.md").write_text("Trust me", encoding="utf-8")
    subprocess.run(["git", "add", "."], cwd=repo, check=True, capture_output=True)
    subprocess.run(["git", "commit", "-m", "init"], cwd=repo, check=True, capture_output=True)
    return repo


# --- Task 2.1: skeleton + JSON helpers ---

def test_load_config_missing_returns_default(tmp_path):
    cfg = load_config(tmp_path / "connected-wikis.json")
    assert cfg == DEFAULT_CONFIG
    assert cfg["schema_version"] == CONFIG_VERSION


def test_save_then_load_roundtrip(tmp_path):
    p = tmp_path / "connected-wikis.json"
    cfg = {"schema_version": 1, "wikis": [{"id": "foo", "name": "Foo", "enabled": True,
            "source_type": "git", "source": "https://x", "status": "ok",
            "added": "2026-04-29",
            "embedding_backend": None, "embedding_model": None}]}
    save_config(p, cfg)
    assert load_config(p) == cfg


def test_save_is_atomic(tmp_path):
    p = tmp_path / "connected-wikis.json"
    save_config(p, {"schema_version": 1, "wikis": []})
    leftover = list(tmp_path.glob("*.tmp*"))
    assert leftover == []


# --- Task 2.2: locks ---

def test_global_lock_serializes_writes(tmp_path):
    cfg_path = tmp_path / "cfg.json"
    lock_path = tmp_path / "cfg.lock"
    save_config(cfg_path, {"schema_version": 1, "wikis": []})

    barrier = threading.Barrier(2)
    errors: list[Exception] = []

    def worker(wiki_id: str):
        try:
            barrier.wait()
            with with_global_lock(lock_path):
                cfg = load_config(cfg_path)
                cfg["wikis"].append({"id": wiki_id, "name": wiki_id, "enabled": True,
                                     "source_type": "local", "source": "/x",
                                     "status": "ok", "added": "2026-04-29",
                                     "embedding_backend": None, "embedding_model": None})
                save_config(cfg_path, cfg)
        except Exception as e:
            errors.append(e)

    t1 = threading.Thread(target=worker, args=("a",))
    t2 = threading.Thread(target=worker, args=("b",))
    t1.start(); t2.start(); t1.join(); t2.join()

    assert errors == []
    final = load_config(cfg_path)
    ids = {w["id"] for w in final["wikis"]}
    assert ids == {"a", "b"}


def test_per_wiki_lock_blocks_concurrent_acquire(tmp_path):
    lock_dir = tmp_path / ".locks"
    lock_dir.mkdir()

    fd1 = acquire_per_wiki_lock(lock_dir, "foo", blocking=False)
    assert fd1 is not None
    fd2 = acquire_per_wiki_lock(lock_dir, "foo", blocking=False)
    assert fd2 is None
    os.close(fd1)


# --- Task 2.3: id validation ---

def test_validate_id_format():
    assert validate_id("spain-travel", []) is None
    assert validate_id("a", []) is None
    assert validate_id("a1b2", []) is None
    with pytest.raises(IdError):
        validate_id("Spain", [])
    with pytest.raises(IdError):
        validate_id("spain-", [])
    with pytest.raises(IdError):
        validate_id("-spain", [])
    with pytest.raises(IdError):
        validate_id("sp--ain", [])
    with pytest.raises(IdError):
        validate_id("a" * 32, [])
    for r in ("wiki", "local", "ext", "default"):
        with pytest.raises(IdError):
            validate_id(r, [])
    existing = [{"id": "spain-travel"}]
    with pytest.raises(IdError):
        validate_id("spain-travel", existing)


# --- Task 2.4: migration backfill ---

def test_load_config_backfills_status(tmp_path):
    p = tmp_path / "cfg.json"
    p.write_text(json.dumps({
        "schema_version": 1,
        "wikis": [{"id": "x", "name": "X", "source_type": "local", "source": "/x",
                   "enabled": True, "added": "2026-04-29"}]
    }), encoding="utf-8")

    cfg = load_config(p)
    assert cfg["wikis"][0]["status"] == "ok"


def test_load_config_backfills_embedding_fields_when_print_model_succeeds(tmp_path, monkeypatch):
    from tools import connected_wikis as cw
    monkeypatch.setattr(cw, "_resolve_active_model_or_none",
                        lambda: ("search-chromadb", "paraphrase-multilingual-MiniLM-L12-v2"))
    p = tmp_path / "cfg.json"
    p.write_text(json.dumps({
        "schema_version": 1,
        "wikis": [{"id": "x", "name": "X", "source_type": "local", "source": "/x",
                   "enabled": True, "added": "2026-04-29", "status": "ok"}]
    }), encoding="utf-8")

    cfg = cw.load_config(p)
    assert cfg["wikis"][0]["embedding_backend"] == "search-chromadb"
    assert cfg["wikis"][0]["embedding_model"] == "paraphrase-multilingual-MiniLM-L12-v2"


def test_load_config_backfills_to_null_when_print_model_fails(tmp_path, monkeypatch):
    from tools import connected_wikis as cw
    monkeypatch.setattr(cw, "_resolve_active_model_or_none", lambda: (None, None))
    p = tmp_path / "cfg.json"
    p.write_text(json.dumps({
        "schema_version": 1,
        "wikis": [{"id": "x", "name": "X", "source_type": "local", "source": "/x",
                   "enabled": True, "added": "2026-04-29", "status": "ok"}]
    }), encoding="utf-8")

    cfg = cw.load_config(p)
    assert cfg["wikis"][0]["embedding_backend"] is None
    assert cfg["wikis"][0]["embedding_model"] is None


# --- Task 2.5: init ---

def test_init_aborts_without_wiki_dir(tmp_path, monkeypatch):
    cw = _setup_repo(tmp_path, monkeypatch, with_wiki=False)
    rc = cw.cmd_init()
    assert rc == 1


def test_init_creates_config_and_gitignore(tmp_path, monkeypatch):
    cw = _setup_repo(tmp_path, monkeypatch)
    (tmp_path / ".gitignore").write_text("# existing\n", encoding="utf-8")

    rc = cw.cmd_init()
    assert rc == 0
    assert (tmp_path / "connected-wikis.json").exists()
    cfg = json.loads((tmp_path / "connected-wikis.json").read_text())
    assert cfg == {"schema_version": 1, "wikis": []}
    gi = (tmp_path / ".gitignore").read_text()
    assert "connected-wikis/" in gi
    assert "connected-wikis.lock" in gi


def test_init_idempotent(tmp_path, monkeypatch):
    cw = _setup_repo(tmp_path, monkeypatch)
    (tmp_path / ".gitignore").write_text("connected-wikis/\nconnected-wikis.lock\n", encoding="utf-8")
    (tmp_path / "connected-wikis.json").write_text(
        json.dumps({"schema_version": 1, "wikis": []}), encoding="utf-8")

    rc = cw.cmd_init()
    assert rc == 0
    gi_lines = (tmp_path / ".gitignore").read_text().split("\n")
    assert gi_lines.count("connected-wikis/") == 1
    assert gi_lines.count("connected-wikis.lock") == 1


# --- Task 2.6: list ---

def test_list_empty(tmp_path, monkeypatch, capsys):
    cw = _setup_repo(tmp_path, monkeypatch)
    cw.cmd_init()
    rc = cw.cmd_list()
    out = capsys.readouterr().out
    assert rc == 0
    assert "| id |" in out
    assert "no connected wikis" in out.lower() or "0 wikis" in out.lower()


def test_list_renders_table_with_pages(tmp_path, monkeypatch, capsys):
    cw = _setup_repo(tmp_path, monkeypatch)
    import chromadb as _ch
    idx = tmp_path / "search-index"
    client = _ch.PersistentClient(path=str(idx))
    coll = client.get_or_create_collection("wiki-ext-spain", metadata={"hnsw:space": "cosine"})
    coll.upsert(ids=["a"], embeddings=[[0.1] * 384], documents=["x"], metadatas=[{"path": "a"}])
    del client
    import gc; gc.collect()

    save_config(cw.CONFIG_PATH, {"schema_version": 1, "wikis": [
        {"id": "spain", "name": "Spain", "source_type": "git", "source": "https://x",
         "enabled": True, "status": "ok", "added": "2026-04-29",
         "embedding_backend": "search-chromadb",
         "embedding_model": "paraphrase-multilingual-MiniLM-L12-v2",
         "last_pulled": "2026-04-29"}
    ]})

    rc = cw.cmd_list()
    out = capsys.readouterr().out
    assert rc == 0
    assert "spain" in out
    lines = [l for l in out.split("\n") if "spain" in l and "|" in l]
    assert len(lines) >= 1


# --- Task 2.7: toggle ---

def test_toggle_flips_enabled(tmp_path, monkeypatch):
    cw = _setup_repo(tmp_path, monkeypatch)
    cw.cmd_init()
    save_config(cw.CONFIG_PATH, {"schema_version": 1, "wikis": [
        {"id": "x", "name": "X", "source_type": "local", "source": "/x",
         "enabled": True, "status": "ok", "added": "2026-04-29",
         "embedding_backend": None, "embedding_model": None}
    ]})

    rc = cw.cmd_toggle("x", "off")
    assert rc == 0
    cfg = cw.load_config(cw.CONFIG_PATH)
    assert cfg["wikis"][0]["enabled"] is False

    rc = cw.cmd_toggle("x", "on")
    cfg = cw.load_config(cw.CONFIG_PATH)
    assert cfg["wikis"][0]["enabled"] is True


def test_toggle_unknown_id_returns_1(tmp_path, monkeypatch):
    cw = _setup_repo(tmp_path, monkeypatch)
    cw.cmd_init()
    rc = cw.cmd_toggle("nope", "on")
    assert rc == 1


# --- Task 2.8: interaction protocol ---

def test_request_decision_exits_4_when_not_tty(monkeypatch, capsys):
    monkeypatch.setattr(sys.stdin, "isatty", lambda: False)
    with pytest.raises(DecisionPending):
        request_decision(prompt_key="consent",
                         question="Trust this wiki?",
                         options=["accept", "reject"],
                         decisions={})
    out = capsys.readouterr().out
    assert "PROMPT: consent | Trust this wiki?" in out
    assert "OPTIONS: accept reject" in out


def test_request_decision_returns_value_from_decisions():
    val = request_decision(prompt_key="consent",
                           question="Trust?",
                           options=["accept", "reject"],
                           decisions={"consent": "accept"})
    assert val == "accept"


def test_request_decision_rejects_invalid_value():
    with pytest.raises(ValueError):
        request_decision(prompt_key="consent",
                         question="?",
                         options=["accept", "reject"],
                         decisions={"consent": "maybe"})


def test_parse_decisions():
    assert parse_decisions(["consent=accept", "mismatch=update"]) == \
        {"consent": "accept", "mismatch": "update"}
    assert parse_decisions(None) == {}
    assert parse_decisions([]) == {}
    with pytest.raises(ValueError):
        parse_decisions(["nope"])


# --- Task 2.9: connect local ---

def _stub_resolve_model(cw, monkeypatch, backend="search-chromadb",
                        model="paraphrase-multilingual-MiniLM-L12-v2"):
    monkeypatch.setattr(cw, "_resolve_active_model_or_none", lambda: (backend, model))


def _make_fake_reindex_factory(cw, ids=("x",)):
    def _fake_reindex(wiki_path, coll):
        import chromadb as _ch
        client = _ch.PersistentClient(path=cw.INDEX_PATH)
        c = client.get_or_create_collection(coll, metadata={"hnsw:space": "cosine"})
        c.upsert(ids=list(ids), embeddings=[[0.1] * 384] * len(ids),
                 documents=["d"] * len(ids), metadatas=[{"path": i} for i in ids])

        class R:
            returncode = 0
            stdout = f"Reindex complete: {len(ids)} pages indexed, 0 skipped"
            stderr = ""

        return R()
    return _fake_reindex


def test_connect_local_happy_path(tmp_path, monkeypatch):
    cw = _setup_repo(tmp_path, monkeypatch)
    cw.cmd_init()

    ext = tmp_path / "ext"
    (ext / "wiki").mkdir(parents=True)
    (ext / "wiki" / "page.md").write_text("---\ntitle: Page\ntags: []\n---\nBody",
                                          encoding="utf-8")
    (ext / "README.md").write_text("Trust me", encoding="utf-8")

    _stub_resolve_model(cw, monkeypatch)
    monkeypatch.setattr(cw, "_run_reindex", _make_fake_reindex_factory(cw))

    rc = cw.cmd_connect(source=str(ext), wiki_id="myext", name=None,
                        source_type="local", decisions={"consent": "accept"})
    assert rc == 0
    cfg = cw.load_config(cw.CONFIG_PATH)
    assert len(cfg["wikis"]) == 1
    w = cfg["wikis"][0]
    assert w["id"] == "myext"
    assert w["source_type"] == "local"
    assert w["status"] == "ok"
    assert w["enabled"] is True
    assert w["embedding_backend"] == "search-chromadb"


def test_connect_local_path_missing(tmp_path, monkeypatch):
    cw = _setup_repo(tmp_path, monkeypatch)
    cw.cmd_init()
    rc = cw.cmd_connect(source="/nonexistent/path", wiki_id="x",
                        name=None, source_type="local", decisions={"consent": "accept"})
    assert rc == 1
    assert cw.load_config(cw.CONFIG_PATH)["wikis"] == []


def test_connect_local_no_wiki_subdir(tmp_path, monkeypatch):
    cw = _setup_repo(tmp_path, monkeypatch)
    cw.cmd_init()
    bad = tmp_path / "bad"
    bad.mkdir()
    rc = cw.cmd_connect(source=str(bad), wiki_id="x",
                        name=None, source_type="local", decisions={"consent": "accept"})
    assert rc == 1
    assert cw.load_config(cw.CONFIG_PATH)["wikis"] == []


def test_connect_consent_required_emits_prompt(tmp_path, monkeypatch, capsys):
    cw = _setup_repo(tmp_path, monkeypatch)
    cw.cmd_init()
    ext = tmp_path / "ext"
    (ext / "wiki").mkdir(parents=True)
    (ext / "wiki" / "p.md").write_text("---\ntitle: P\ntags: []\n---\nBody", encoding="utf-8")
    monkeypatch.setattr(sys.stdin, "isatty", lambda: False)

    with pytest.raises(SystemExit) as exc:
        cw.cmd_connect(source=str(ext), wiki_id="x",
                       name=None, source_type="local", decisions={})
    assert exc.value.code == 4
    out = capsys.readouterr().out
    assert "PROMPT: consent" in out


# --- Task 2.10: connect git ---

def test_connect_git_happy_path(tmp_path, monkeypatch):
    cw = _setup_repo(tmp_path, monkeypatch)
    cw.cmd_init()
    remote = _make_fake_remote(tmp_path)

    _stub_resolve_model(cw, monkeypatch)
    monkeypatch.setattr(cw, "_run_reindex", _make_fake_reindex_factory(cw))

    rc = cw.cmd_connect(source=str(remote), wiki_id="g", name=None,
                        source_type="git", decisions={"consent": "accept"})
    assert rc == 0
    assert (tmp_path / "connected-wikis" / "g" / "wiki" / "p.md").exists()
    cfg = cw.load_config(cw.CONFIG_PATH)
    assert cfg["wikis"][0]["status"] == "ok"
    assert "commit" in cfg["wikis"][0]


@pytest.mark.parametrize("branch", ["main", "master", "trunk"])
def test_connect_git_default_branch_detection(tmp_path, monkeypatch, branch):
    cw = _setup_repo(tmp_path, monkeypatch)
    cw.cmd_init()
    remote = _make_fake_remote(tmp_path, branch=branch)

    _stub_resolve_model(cw, monkeypatch)

    def _fake_reindex(wp, coll):
        class R:
            returncode = 0
            stdout = "Reindex complete: 0 pages indexed, 0 skipped"
            stderr = ""

        return R()
    monkeypatch.setattr(cw, "_run_reindex", _fake_reindex)

    rc = cw.cmd_connect(source=str(remote), wiki_id=f"g{branch}", name=None,
                        source_type="git", decisions={"consent": "accept"})
    assert rc == 0
    detected = cw._detect_default_branch(tmp_path / "connected-wikis" / f"g{branch}")
    assert detected == branch


def test_connect_git_rollback_on_reindex_failure(tmp_path, monkeypatch):
    cw = _setup_repo(tmp_path, monkeypatch)
    cw.cmd_init()
    remote = _make_fake_remote(tmp_path)

    _stub_resolve_model(cw, monkeypatch)

    def _fail_reindex(wiki_path, coll):
        class R:
            returncode = 1
            stdout = ""
            stderr = "boom"

        return R()
    monkeypatch.setattr(cw, "_run_reindex", _fail_reindex)

    rc = cw.cmd_connect(source=str(remote), wiki_id="g", name=None,
                        source_type="git", decisions={"consent": "accept"})
    assert rc == 1
    assert cw.load_config(cw.CONFIG_PATH)["wikis"] == []
    assert not (tmp_path / "connected-wikis" / "g").exists()


# --- Task 2.11: two-phase reservation race ---

def test_two_phase_reservation_collision(tmp_path, monkeypatch):
    cw = _setup_repo(tmp_path, monkeypatch)
    cw.cmd_init()

    ext_a = tmp_path / "a"; (ext_a / "wiki").mkdir(parents=True)
    (ext_a / "wiki" / "p.md").write_text("---\ntitle: P\ntags: []\n---\n", encoding="utf-8")
    ext_b = tmp_path / "b"; (ext_b / "wiki").mkdir(parents=True)
    (ext_b / "wiki" / "p.md").write_text("---\ntitle: P\ntags: []\n---\n", encoding="utf-8")

    _stub_resolve_model(cw, monkeypatch, model="model-x")
    monkeypatch.setattr(cw, "_run_reindex", _make_fake_reindex_factory(cw))

    barrier = threading.Barrier(2)
    results = {}

    def worker(label, source):
        barrier.wait()
        rc = cw.cmd_connect(source=source, wiki_id="dup",
                            name=None, source_type="local",
                            decisions={"consent": "accept"})
        results[label] = rc

    t1 = threading.Thread(target=worker, args=("a", str(ext_a)))
    t2 = threading.Thread(target=worker, args=("b", str(ext_b)))
    t1.start(); t2.start(); t1.join(); t2.join()

    rcs = sorted(results.values())
    assert rcs == [0, 1]
    cfg = cw.load_config(cw.CONFIG_PATH)
    assert len(cfg["wikis"]) == 1
    assert cfg["wikis"][0]["id"] == "dup"


# --- Task 2.12: disconnect ---

def test_disconnect_unknown_id_warns_no_op(tmp_path, monkeypatch, capsys):
    cw = _setup_repo(tmp_path, monkeypatch)
    cw.cmd_init()
    rc = cw.cmd_disconnect("nope", decisions={})
    assert rc == 0
    assert "not found" in capsys.readouterr().err.lower()


def test_disconnect_grep_finds_references(tmp_path, monkeypatch, capsys):
    cw = _setup_repo(tmp_path, monkeypatch)
    cw.cmd_init()
    save_config(cw.CONFIG_PATH, {"schema_version": 1, "wikis": [
        {"id": "es", "name": "ES", "source_type": "local", "source": "/x",
         "enabled": True, "status": "ok", "added": "2026-04-29",
         "embedding_backend": "search-chromadb", "embedding_model": "m"}
    ]})
    syn = tmp_path / "wiki" / "synthesis"
    syn.mkdir(parents=True)
    (syn / "trip.md").write_text(
        "---\ntitle: Trip\ntags: []\n---\nMadrid is fun (출처: es).\n", encoding="utf-8")

    rc = cw.cmd_disconnect("es", decisions={"disconnect-grep": "proceed"})
    assert rc == 0
    captured = capsys.readouterr()
    combined = captured.out + captured.err
    assert "trip.md" in combined


def test_disconnect_cleans_collection_and_dir(tmp_path, monkeypatch):
    cw = _setup_repo(tmp_path, monkeypatch)
    cw.cmd_init()
    import chromadb as _ch
    client = _ch.PersistentClient(path=cw.INDEX_PATH)
    client.get_or_create_collection("wiki-ext-es", metadata={"hnsw:space": "cosine"})
    del client
    import gc; gc.collect()
    clone = tmp_path / "connected-wikis" / "es"
    clone.mkdir(parents=True)
    (clone / "marker").write_text("x", encoding="utf-8")

    save_config(cw.CONFIG_PATH, {"schema_version": 1, "wikis": [
        {"id": "es", "name": "ES", "source_type": "git", "source": "https://x",
         "enabled": True, "status": "ok", "added": "2026-04-29",
         "embedding_backend": "search-chromadb", "embedding_model": "m"}
    ]})

    rc = cw.cmd_disconnect("es", decisions={"disconnect-grep": "proceed"})
    assert rc == 0
    assert not clone.exists()
    cfg = cw.load_config(cw.CONFIG_PATH)
    assert cfg["wikis"] == []
    client = _ch.PersistentClient(path=cw.INDEX_PATH)
    with pytest.raises(Exception):
        client.get_collection("wiki-ext-es")


def test_disconnect_lock_held_aborts(tmp_path, monkeypatch):
    cw = _setup_repo(tmp_path, monkeypatch)
    cw.cmd_init()
    save_config(cw.CONFIG_PATH, {"schema_version": 1, "wikis": [
        {"id": "es", "name": "ES", "source_type": "local", "source": "/x",
         "enabled": True, "status": "ok", "added": "2026-04-29",
         "embedding_backend": None, "embedding_model": None}
    ]})

    fd = cw.acquire_per_wiki_lock(cw.LOCK_DIR, "es", blocking=True)
    try:
        rc = cw.cmd_disconnect("es", decisions={"disconnect-grep": "proceed"})
        assert rc == 1
    finally:
        cw.release_per_wiki_lock(fd)


def test_disconnect_does_not_disturb_in_flight_pull(tmp_path, monkeypatch):
    cw = _setup_repo(tmp_path, monkeypatch)
    cw.cmd_init()
    src = tmp_path / "src"
    (src / "wiki").mkdir(parents=True)
    (src / "wiki" / "p.md").write_text("---\ntitle: P\ntags: []\n---\n", encoding="utf-8")
    save_config(cw.CONFIG_PATH, {"schema_version": 1, "wikis": [
        {"id": "es", "name": "ES", "source_type": "local", "source": str(src),
         "enabled": True, "status": "ok", "added": "2026-04-29",
         "embedding_backend": "search-chromadb", "embedding_model": "m",
         "last_pulled": "2026-01-01"}
    ]})

    pull_done = threading.Event()
    add_calls: list[str] = []

    def _slow_add(f, c, wiki_root=None):
        time.sleep(0.3)
        add_calls.append(str(f))

        class R:
            returncode = 0
            stdout = ""
            stderr = ""

        return R()
    monkeypatch.setattr(cw, "_run_add_page", _slow_add)

    def run_pull():
        cw.cmd_pull(decisions={})
        pull_done.set()

    pull_thread = threading.Thread(target=run_pull)
    pull_thread.start()
    time.sleep(0.05)

    rc = cw.cmd_disconnect("es", decisions={"disconnect-grep": "proceed"})
    assert rc == 1
    pull_thread.join(timeout=5)
    assert pull_done.is_set()
    assert any("p.md" in c for c in add_calls)
    cfg = cw.load_config(cw.CONFIG_PATH)
    assert any(w["id"] == "es" for w in cfg["wikis"])


# --- Task 2.13: pull (git diff + local mtime) ---

def test_pull_git_partial_reindex_on_diff(tmp_path, monkeypatch):
    cw = _setup_repo(tmp_path, monkeypatch)
    cw.cmd_init()
    remote = _make_fake_remote(tmp_path)

    _stub_resolve_model(cw, monkeypatch, model="model-v1")

    add_calls: list[tuple[str, str]] = []

    def _fake_add_page(file, coll, wiki_root=None):
        add_calls.append((str(file), coll))

        class R:
            returncode = 0
            stdout = ""
            stderr = ""

        return R()

    def _fake_reindex(wp, coll):
        import chromadb as _ch
        client = _ch.PersistentClient(path=cw.INDEX_PATH)
        client.get_or_create_collection(coll, metadata={"hnsw:space": "cosine"})

        class R:
            returncode = 0
            stdout = "Reindex complete: 0 pages indexed, 0 skipped"
            stderr = ""

        return R()
    monkeypatch.setattr(cw, "_run_reindex", _fake_reindex)
    monkeypatch.setattr(cw, "_run_add_page", _fake_add_page)

    rc = cw.cmd_connect(source=str(remote), wiki_id="g", name=None,
                        source_type="git", decisions={"consent": "accept"})
    assert rc == 0
    cfg = cw.load_config(cw.CONFIG_PATH)
    initial_commit = cfg["wikis"][0]["commit"]

    (remote / "wiki" / "new.md").write_text(
        "---\ntitle: New\ntags: []\n---\nfresh", encoding="utf-8")
    subprocess.run(["git", "add", "."], cwd=remote, check=True, capture_output=True)
    subprocess.run(["git", "commit", "-m", "add new"], cwd=remote, check=True, capture_output=True)

    add_calls.clear()
    rc = cw.cmd_pull(decisions={})
    assert rc == 0
    cfg = cw.load_config(cw.CONFIG_PATH)
    assert cfg["wikis"][0]["commit"] != initial_commit
    new_md_calls = [c for c in add_calls if c[0].endswith("new.md")]
    assert len(new_md_calls) == 1


def test_pull_unreachable_preserves_enabled(tmp_path, monkeypatch):
    cw = _setup_repo(tmp_path, monkeypatch)
    cw.cmd_init()
    save_config(cw.CONFIG_PATH, {"schema_version": 1, "wikis": [
        {"id": "g", "name": "G", "source_type": "local",
         "source": "/no/such/path",
         "enabled": True, "status": "ok", "added": "2026-04-29",
         "embedding_backend": "search-chromadb", "embedding_model": "m",
         "last_pulled": "2026-04-29"}
    ]})
    rc = cw.cmd_pull(decisions={})
    assert rc == 0
    cfg = cw.load_config(cw.CONFIG_PATH)
    w = cfg["wikis"][0]
    assert w["enabled"] is True
    assert w["status"] == "unreachable"


def test_pull_local_mtime_based(tmp_path, monkeypatch):
    cw = _setup_repo(tmp_path, monkeypatch)
    cw.cmd_init()
    src = tmp_path / "loc"
    (src / "wiki").mkdir(parents=True)
    p1 = src / "wiki" / "old.md"
    p1.write_text("---\ntitle: O\ntags: []\n---\nold", encoding="utf-8")
    save_config(cw.CONFIG_PATH, {"schema_version": 1, "wikis": [
        {"id": "loc", "name": "L", "source_type": "local", "source": str(src),
         "enabled": True, "status": "ok", "added": "2026-04-29",
         "embedding_backend": "search-chromadb", "embedding_model": "m",
         "last_pulled": "2026-01-01"}
    ]})

    add_calls: list[str] = []

    def _stub_add(f, c, wiki_root=None):
        add_calls.append(str(f))

        class R:
            returncode = 0
            stdout = ""
            stderr = ""

        return R()
    monkeypatch.setattr(cw, "_run_add_page", _stub_add)

    rc = cw.cmd_pull(decisions={})
    assert rc == 0
    assert any("old.md" in c for c in add_calls)


# --- Task 2.14: pull partial failure ---

def test_pull_partial_failure_summary(tmp_path, monkeypatch, capsys):
    cw = _setup_repo(tmp_path, monkeypatch)
    cw.cmd_init()
    src_ok = tmp_path / "ok"; (src_ok / "wiki").mkdir(parents=True)
    save_config(cw.CONFIG_PATH, {"schema_version": 1, "wikis": [
        {"id": "ok", "name": "OK", "source_type": "local", "source": str(src_ok),
         "enabled": True, "status": "ok", "added": "2026-04-29",
         "embedding_backend": "search-chromadb", "embedding_model": "m",
         "last_pulled": "2026-04-29"},
        {"id": "bad", "name": "B", "source_type": "local", "source": "/no/such/path",
         "enabled": True, "status": "ok", "added": "2026-04-29",
         "embedding_backend": "search-chromadb", "embedding_model": "m",
         "last_pulled": "2026-04-29"}
    ]})

    def _stub_add(f, c, wiki_root=None):
        class R:
            returncode = 0
            stdout = ""
            stderr = ""

        return R()
    monkeypatch.setattr(cw, "_run_add_page", _stub_add)

    rc = cw.cmd_pull(decisions={})
    assert rc == 0
    cfg = cw.load_config(cw.CONFIG_PATH)
    by_id = {w["id"]: w for w in cfg["wikis"]}
    assert by_id["ok"]["status"] == "ok"
    assert by_id["bad"]["status"] == "unreachable"
    assert by_id["bad"]["enabled"] is True
    out = capsys.readouterr().out
    assert "1 success / 1 failed" in out


def test_pull_no_meta_change_no_commit(tmp_path, monkeypatch, capsys):
    cw = _setup_repo(tmp_path, monkeypatch)
    cw.cmd_init()
    save_config(cw.CONFIG_PATH, {"schema_version": 1, "wikis": [
        {"id": "g", "name": "G", "source_type": "local", "source": "/no/such",
         "enabled": True, "status": "unreachable", "added": "2026-04-29",
         "embedding_backend": None, "embedding_model": None,
         "last_pulled": "2026-04-29"}
    ]})

    rc = cw.cmd_pull(decisions={})
    assert rc == 0
    out = capsys.readouterr().out
    assert "no changes" in out


# --- Task 2.15: pull mismatch decision ---

def test_pull_mismatch_decision_required(tmp_path, monkeypatch):
    cw = _setup_repo(tmp_path, monkeypatch)
    cw.cmd_init()
    remote = _make_fake_remote(tmp_path, branch="main")
    save_config(cw.CONFIG_PATH, {"schema_version": 1, "wikis": [
        {"id": "g", "name": "G", "source_type": "git", "source": str(remote),
         "enabled": True, "status": "ok", "added": "2026-04-29",
         "embedding_backend": "search-chromadb", "embedding_model": "OLD-MODEL",
         "last_pulled": "2026-04-29", "commit": "abc1234"}
    ]})
    subprocess.run(["git", "clone", str(remote), str(tmp_path / "connected-wikis" / "g")],
                   check=True, capture_output=True)

    _stub_resolve_model(cw, monkeypatch, model="NEW-MODEL")
    monkeypatch.setattr(sys.stdin, "isatty", lambda: False)

    with pytest.raises(SystemExit) as exc:
        cw.cmd_pull(decisions={})
    assert exc.value.code == 4

    def _stub_reindex(wp, c):
        class R:
            returncode = 0
            stdout = ""
            stderr = ""

        return R()
    monkeypatch.setattr(cw, "_run_reindex", _stub_reindex)
    rc = cw.cmd_pull(decisions={"mismatch": "update"})
    assert rc == 0
    cfg = cw.load_config(cw.CONFIG_PATH)
    assert cfg["wikis"][0]["embedding_model"] == "NEW-MODEL"


# --- Task 2.16: smoke ---

def _cli_run(args: list[str], cwd: Path) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, "tools/connected_wikis.py"] + args,
        capture_output=True, text=True, cwd=str(cwd),
    )


def test_cli_help_shows_all_subcommands():
    repo_root = Path(__file__).parent.parent
    r = _cli_run(["--help"], repo_root)
    assert r.returncode == 0
    for cmd in ("init", "list", "connect", "toggle", "disconnect", "pull"):
        assert cmd in r.stdout


# --- Task 2.17b: name/added auto-fill ---

def test_infer_name_from_git_url():
    from tools.connected_wikis import _infer_name
    assert _infer_name("https://github.com/friend/spain-travel-wiki", "git") == "spain-travel-wiki"
    assert _infer_name("https://github.com/friend/spain-travel-wiki.git", "git") == "spain-travel-wiki"
    assert _infer_name("git@github.com:friend/foo.git", "git") == "foo"


def test_infer_name_from_local_path():
    from tools.connected_wikis import _infer_name
    assert _infer_name("/Users/me/some-wiki", "local") == "some-wiki"


def test_connect_fills_added_date_and_name(tmp_path, monkeypatch):
    cw = _setup_repo(tmp_path, monkeypatch)
    cw.cmd_init()
    src = tmp_path / "myname-source"
    (src / "wiki").mkdir(parents=True)
    (src / "wiki" / "p.md").write_text("---\ntitle: P\ntags: []\n---\n", encoding="utf-8")

    _stub_resolve_model(cw, monkeypatch, model="m")
    monkeypatch.setattr(cw, "_run_reindex", _make_fake_reindex_factory(cw))

    rc = cw.cmd_connect(source=str(src), wiki_id="myid", name=None,
                        source_type="local", decisions={"consent": "accept"})
    assert rc == 0
    w = cw.load_config(cw.CONFIG_PATH)["wikis"][0]
    assert w["name"] == "myname-source"
    from datetime import date as _date
    assert w["added"] == _date.today().isoformat()


def test_connect_explicit_name_overrides_inference(tmp_path, monkeypatch):
    cw = _setup_repo(tmp_path, monkeypatch)
    cw.cmd_init()
    src = tmp_path / "raw-folder"
    (src / "wiki").mkdir(parents=True)
    (src / "wiki" / "p.md").write_text("---\ntitle: P\ntags: []\n---\n", encoding="utf-8")

    _stub_resolve_model(cw, monkeypatch, model="m")
    monkeypatch.setattr(cw, "_run_reindex", _make_fake_reindex_factory(cw))

    rc = cw.cmd_connect(source=str(src), wiki_id="myid",
                        name="Friendly Display Name",
                        source_type="local", decisions={"consent": "accept"})
    assert rc == 0
    w = cw.load_config(cw.CONFIG_PATH)["wikis"][0]
    assert w["name"] == "Friendly Display Name"


# --- Task 2.18: print-model failure abort ---

def test_connect_aborts_when_print_model_fails(tmp_path, monkeypatch):
    cw = _setup_repo(tmp_path, monkeypatch)
    cw.cmd_init()
    ext = tmp_path / "ext"; (ext / "wiki").mkdir(parents=True)
    (ext / "wiki" / "p.md").write_text("---\ntitle: P\ntags: []\n---\n", encoding="utf-8")

    monkeypatch.setattr(cw, "_resolve_active_model_or_none", lambda: (None, None))

    rc = cw.cmd_connect(source=str(ext), wiki_id="x", name=None,
                        source_type="local", decisions={"consent": "accept"})
    assert rc == 1
    assert cw.load_config(cw.CONFIG_PATH)["wikis"] == []


# --- Review fixes ---

def test_connect_accepts_wiki_with_pages_only_in_subdirs(tmp_path, monkeypatch):
    """Canonical seojae layout: pages live under wiki/concepts/, wiki/entities/, etc."""
    cw = _setup_repo(tmp_path, monkeypatch)
    cw.cmd_init()
    ext = tmp_path / "subdir-wiki"
    (ext / "wiki" / "concepts").mkdir(parents=True)
    (ext / "wiki" / "concepts" / "thing.md").write_text(
        "---\ntitle: T\ntags: []\n---\nbody", encoding="utf-8")
    # No top-level wiki/*.md — only wiki/concepts/*.md

    _stub_resolve_model(cw, monkeypatch, model="m")
    monkeypatch.setattr(cw, "_run_reindex", _make_fake_reindex_factory(cw))

    rc = cw.cmd_connect(source=str(ext), wiki_id="sub", name=None,
                        source_type="local", decisions={"consent": "accept"})
    assert rc == 0
    assert cw.load_config(cw.CONFIG_PATH)["wikis"][0]["status"] == "ok"


def test_connect_resumes_after_decision_pending(tmp_path, monkeypatch):
    """First call (no decision) leaves status=connecting and exits 4.
    Second call with --decision must complete rather than collide on id."""
    cw = _setup_repo(tmp_path, monkeypatch)
    cw.cmd_init()
    ext = tmp_path / "src"; (ext / "wiki").mkdir(parents=True)
    (ext / "wiki" / "p.md").write_text("---\ntitle: P\ntags: []\n---\n", encoding="utf-8")
    monkeypatch.setattr(sys.stdin, "isatty", lambda: False)

    # Call 1: no decision → exits 4 with reservation persisted
    with pytest.raises(SystemExit) as exc:
        cw.cmd_connect(source=str(ext), wiki_id="resume", name=None,
                       source_type="local", decisions={})
    assert exc.value.code == 4
    cfg = cw.load_config(cw.CONFIG_PATH)
    assert len(cfg["wikis"]) == 1
    assert cfg["wikis"][0]["id"] == "resume"
    assert cfg["wikis"][0]["status"] == "connecting"

    # Call 2: decision provided → resumes, completes
    _stub_resolve_model(cw, monkeypatch, model="m")
    monkeypatch.setattr(cw, "_run_reindex", _make_fake_reindex_factory(cw))
    rc = cw.cmd_connect(source=str(ext), wiki_id="resume", name=None,
                        source_type="local", decisions={"consent": "accept"})
    assert rc == 0
    cfg = cw.load_config(cw.CONFIG_PATH)
    assert len(cfg["wikis"]) == 1
    assert cfg["wikis"][0]["status"] == "ok"


def test_connect_rejects_resume_with_different_source(tmp_path, monkeypatch):
    """A status=connecting entry should not resume if the user supplies a different source."""
    cw = _setup_repo(tmp_path, monkeypatch)
    cw.cmd_init()
    save_config(cw.CONFIG_PATH, {"schema_version": 1, "wikis": [
        {"id": "x", "name": "X", "source_type": "local", "source": "/orig",
         "enabled": True, "status": "connecting", "added": "2026-04-29",
         "embedding_backend": None, "embedding_model": None}
    ]})
    rc = cw.cmd_connect(source="/different", wiki_id="x", name=None,
                        source_type="local", decisions={"consent": "accept"})
    assert rc == 1


def test_connect_rejects_overwriting_ok_entry(tmp_path, monkeypatch):
    """Resume only applies to status=connecting; a status=ok entry blocks reconnection."""
    cw = _setup_repo(tmp_path, monkeypatch)
    cw.cmd_init()
    save_config(cw.CONFIG_PATH, {"schema_version": 1, "wikis": [
        {"id": "x", "name": "X", "source_type": "local", "source": "/x",
         "enabled": True, "status": "ok", "added": "2026-04-29",
         "embedding_backend": "search-chromadb", "embedding_model": "m"}
    ]})
    rc = cw.cmd_connect(source="/x", wiki_id="x", name=None,
                        source_type="local", decisions={"consent": "accept"})
    assert rc == 1


def test_pull_mismatch_decision_resolved_before_reset(tmp_path, monkeypatch):
    """When DecisionPending fires for mismatch, clone state must be untouched
    so the next invocation sees a consistent old_commit/HEAD pair."""
    cw = _setup_repo(tmp_path, monkeypatch)
    cw.cmd_init()
    remote = _make_fake_remote(tmp_path)
    save_config(cw.CONFIG_PATH, {"schema_version": 1, "wikis": [
        {"id": "g", "name": "G", "source_type": "git", "source": str(remote),
         "enabled": True, "status": "ok", "added": "2026-04-29",
         "embedding_backend": "search-chromadb", "embedding_model": "OLD-MODEL",
         "last_pulled": "2026-04-29", "commit": "abc1234"}
    ]})
    subprocess.run(["git", "clone", str(remote), str(tmp_path / "connected-wikis" / "g")],
                   check=True, capture_output=True)
    head_before = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=str(tmp_path / "connected-wikis" / "g"),
        capture_output=True, text=True,
    ).stdout.strip()

    # Advance remote so a fetch+reset would change HEAD
    (remote / "wiki" / "new.md").write_text(
        "---\ntitle: N\ntags: []\n---\nfresh", encoding="utf-8")
    subprocess.run(["git", "add", "."], cwd=remote, check=True, capture_output=True)
    subprocess.run(["git", "commit", "-m", "advance"], cwd=remote, check=True, capture_output=True)

    _stub_resolve_model(cw, monkeypatch, model="NEW-MODEL")
    monkeypatch.setattr(sys.stdin, "isatty", lambda: False)

    with pytest.raises(SystemExit) as exc:
        cw.cmd_pull(decisions={})
    assert exc.value.code == 4

    # Local clone must NOT have been advanced — fix verifies mismatch resolves first
    head_after = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=str(tmp_path / "connected-wikis" / "g"),
        capture_output=True, text=True,
    ).stdout.strip()
    assert head_after == head_before


def test_pull_subprocess_failure_is_logged(tmp_path, monkeypatch, capsys):
    """A failed _run_add_page must surface a stderr warning, not silently swallow."""
    cw = _setup_repo(tmp_path, monkeypatch)
    cw.cmd_init()
    src = tmp_path / "loc"; (src / "wiki").mkdir(parents=True)
    (src / "wiki" / "old.md").write_text("---\ntitle: O\ntags: []\n---\nold", encoding="utf-8")
    save_config(cw.CONFIG_PATH, {"schema_version": 1, "wikis": [
        {"id": "loc", "name": "L", "source_type": "local", "source": str(src),
         "enabled": True, "status": "ok", "added": "2026-04-29",
         "embedding_backend": "search-chromadb", "embedding_model": "m",
         "last_pulled": "2026-01-01"}
    ]})

    def _failing_add(f, c, wiki_root=None):
        class R:
            returncode = 1
            stdout = ""
            stderr = "boom"

        return R()
    monkeypatch.setattr(cw, "_run_add_page", _failing_add)

    rc = cw.cmd_pull(decisions={})
    assert rc == 0
    err = capsys.readouterr().err
    assert "add_page failed" in err
    assert "loc:" in err
    assert "boom" in err


def test_init_commits_on_first_bootstrap(tmp_path, monkeypatch):
    """Init must run _git_commit('extension: enable connected-wikis') on first setup."""
    cw = _setup_repo(tmp_path, monkeypatch)
    commits: list[str] = []
    monkeypatch.setattr(cw, "_git_commit", lambda msg: commits.append(msg))

    rc = cw.cmd_init()
    assert rc == 0
    assert "extension: enable connected-wikis" in commits


def test_init_idempotent_no_extra_commit(tmp_path, monkeypatch):
    """Subsequent init calls must not re-commit."""
    cw = _setup_repo(tmp_path, monkeypatch)
    (tmp_path / ".gitignore").write_text("connected-wikis/\nconnected-wikis.lock\n", encoding="utf-8")
    save_config(cw.CONFIG_PATH, {"schema_version": 1, "wikis": []})

    commits: list[str] = []
    monkeypatch.setattr(cw, "_git_commit", lambda msg: commits.append(msg))
    rc = cw.cmd_init()
    assert rc == 0
    assert commits == []


# --- Review fixes (iteration 2) ---

def test_load_config_corrupt_json_raises_clear_error(tmp_path):
    from tools.connected_wikis import load_config, ConfigCorrupt
    p = tmp_path / "cfg.json"
    p.write_text("not json {{{", encoding="utf-8")
    with pytest.raises(ConfigCorrupt) as exc:
        load_config(p)
    assert "not valid JSON" in str(exc.value)


def test_load_config_non_dict_raises_clear_error(tmp_path):
    from tools.connected_wikis import load_config, ConfigCorrupt
    p = tmp_path / "cfg.json"
    p.write_text("[1, 2, 3]", encoding="utf-8")
    with pytest.raises(ConfigCorrupt):
        load_config(p)


def test_load_config_wikis_not_list_raises(tmp_path):
    from tools.connected_wikis import load_config, ConfigCorrupt
    p = tmp_path / "cfg.json"
    p.write_text(json.dumps({"schema_version": 1, "wikis": {}}), encoding="utf-8")
    with pytest.raises(ConfigCorrupt):
        load_config(p)


def test_connect_resume_rejects_source_type_mismatch(tmp_path, monkeypatch, capsys):
    """status=connecting + same id but different source_type → reject, not silently retry."""
    cw = _setup_repo(tmp_path, monkeypatch)
    cw.cmd_init()
    save_config(cw.CONFIG_PATH, {"schema_version": 1, "wikis": [
        {"id": "x", "name": "X", "source_type": "local", "source": "/orig",
         "enabled": True, "status": "connecting", "added": "2026-04-29",
         "embedding_backend": None, "embedding_model": None}
    ]})
    rc = cw.cmd_connect(source="/orig", wiki_id="x", name=None,
                        source_type="git", decisions={"consent": "accept"})
    assert rc == 1
    err = capsys.readouterr().err
    assert "mid-connect" in err.lower() or "different" in err.lower()


def test_connect_resume_uses_today_for_last_pulled_not_added_date(tmp_path, monkeypatch):
    """Resumed connect should keep original `added` date but write today's date as last_pulled."""
    cw = _setup_repo(tmp_path, monkeypatch)
    cw.cmd_init()
    src = tmp_path / "src"; (src / "wiki").mkdir(parents=True)
    (src / "wiki" / "p.md").write_text("---\ntitle: P\ntags: []\n---\n", encoding="utf-8")
    save_config(cw.CONFIG_PATH, {"schema_version": 1, "wikis": [
        {"id": "r", "name": "R", "source_type": "local", "source": str(src),
         "enabled": True, "status": "connecting", "added": "2024-01-01",
         "embedding_backend": None, "embedding_model": None}
    ]})

    _stub_resolve_model(cw, monkeypatch, model="m")
    monkeypatch.setattr(cw, "_run_reindex", _make_fake_reindex_factory(cw))

    rc = cw.cmd_connect(source=str(src), wiki_id="r", name=None,
                        source_type="local", decisions={"consent": "accept"})
    assert rc == 0
    w = cw.load_config(cw.CONFIG_PATH)["wikis"][0]
    from datetime import date as _date
    assert w["added"] == "2024-01-01"  # preserved
    assert w["last_pulled"] == _date.today().isoformat()  # today, not 2024-01-01


def test_pull_does_not_clobber_concurrent_toggle(tmp_path, monkeypatch):
    """Concurrent toggle during cmd_pull must survive — pull merges instead of overwriting."""
    cw = _setup_repo(tmp_path, monkeypatch)
    cw.cmd_init()
    src1 = tmp_path / "s1"; (src1 / "wiki").mkdir(parents=True)
    src2 = tmp_path / "s2"; (src2 / "wiki").mkdir(parents=True)
    save_config(cw.CONFIG_PATH, {"schema_version": 1, "wikis": [
        {"id": "a", "name": "A", "source_type": "local", "source": str(src1),
         "enabled": True, "status": "ok", "added": "2026-04-29",
         "embedding_backend": "search-chromadb", "embedding_model": "m",
         "last_pulled": "2026-04-29"},
        {"id": "b", "name": "B", "source_type": "local", "source": str(src2),
         "enabled": True, "status": "ok", "added": "2026-04-29",
         "embedding_backend": "search-chromadb", "embedding_model": "m",
         "last_pulled": "2026-04-29"},
    ]})

    monkeypatch.setattr(cw, "_run_add_page",
                        lambda f, c: type("R", (), {"returncode": 0, "stdout":"", "stderr":""})())

    # Hook _pull_local to flip "b" off in the JSON mid-loop, simulating a concurrent toggle.
    orig_pull_local = cw._pull_local

    def _toggle_b_then_pull(w, today, backend, model):
        result = orig_pull_local(w, today, backend, model)
        if w["id"] == "a":
            cfg = cw.load_config(cw.CONFIG_PATH)
            for x in cfg["wikis"]:
                if x["id"] == "b":
                    x["enabled"] = False
            save_config(cw.CONFIG_PATH, cfg)
        return result
    monkeypatch.setattr(cw, "_pull_local", _toggle_b_then_pull)

    rc = cw.cmd_pull(decisions={})
    assert rc == 0
    cfg = cw.load_config(cw.CONFIG_PATH)
    by_id = {w["id"]: w for w in cfg["wikis"]}
    # The concurrent toggle of b must have survived
    assert by_id["b"]["enabled"] is False
    # Pull's own mutations should also be present on both
    assert by_id["a"]["status"] == "ok"
    assert by_id["b"]["status"] == "ok"


# --- Review pass 3 ---

def test_load_config_rejects_invalid_id(tmp_path):
    from tools.connected_wikis import ConfigCorrupt
    p = tmp_path / "connected-wikis.json"
    p.write_text(json.dumps({"schema_version": 1, "wikis": [
        {"id": "../evil", "name": "E", "source_type": "local", "source": "/x",
         "enabled": True, "status": "ok", "added": "2026-04-29",
         "embedding_backend": None, "embedding_model": None}
    ]}), encoding="utf-8")
    with pytest.raises(ConfigCorrupt):
        load_config(p)


def test_load_config_rejects_non_dict_entry(tmp_path):
    from tools.connected_wikis import ConfigCorrupt
    p = tmp_path / "connected-wikis.json"
    p.write_text(json.dumps({"schema_version": 1, "wikis": ["not-a-dict"]}),
                 encoding="utf-8")
    with pytest.raises(ConfigCorrupt):
        load_config(p)


def test_git_commit_pathspec_ignores_unrelated_staged_files(tmp_path, monkeypatch):
    """_git_commit must never sweep user-staged files into automated commits."""
    from tools import connected_wikis as cw
    repo = tmp_path / "repo"
    repo.mkdir()
    subprocess.run(["git", "init", "-b", "main"], cwd=repo, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.email", "t@t"], cwd=repo, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.name", "t"], cwd=repo, check=True, capture_output=True)
    (repo / "base.txt").write_text("base", encoding="utf-8")
    subprocess.run(["git", "add", "."], cwd=repo, check=True, capture_output=True)
    subprocess.run(["git", "commit", "-m", "base"], cwd=repo, check=True, capture_output=True)

    (repo / "connected-wikis.json").write_text("{}", encoding="utf-8")
    (repo / "log.md").write_text("# log", encoding="utf-8")
    (repo / "unrelated.txt").write_text("user work in progress", encoding="utf-8")
    subprocess.run(["git", "add", "unrelated.txt"], cwd=repo, check=True, capture_output=True)

    monkeypatch.setattr(cw, "_REPO_ROOT", repo)
    cw._git_commit("connect: test")

    shown = subprocess.run(["git", "show", "--name-only", "--format=%s", "HEAD"],
                           cwd=repo, capture_output=True, text=True).stdout
    assert "connect: test" in shown
    assert "connected-wikis.json" in shown
    assert "unrelated.txt" not in shown


def _connect_git_fixture(tmp_path, monkeypatch, wiki_id="g"):
    """Connect a fake git remote and return (cw, remote, add_calls, reindex_calls)."""
    cw = _setup_repo(tmp_path, monkeypatch)
    cw.cmd_init()
    remote = _make_fake_remote(tmp_path)
    _stub_resolve_model(cw, monkeypatch, model="model-v1")

    add_calls: list[str] = []
    reindex_calls: list[str] = []

    def _fake_add_page(f, c, wiki_root=None):
        add_calls.append(str(f))

        class R:
            returncode = 0
            stdout = ""
            stderr = ""
        return R()

    def _fake_reindex(wp, coll):
        import chromadb as _ch
        client = _ch.PersistentClient(path=cw.INDEX_PATH)
        client.get_or_create_collection(coll, metadata={"hnsw:space": "cosine"})
        reindex_calls.append(str(wp))

        class R:
            returncode = 0
            stdout = "Reindex complete: 1 pages indexed, 0 skipped"
            stderr = ""
        return R()

    monkeypatch.setattr(cw, "_run_add_page", _fake_add_page)
    monkeypatch.setattr(cw, "_run_reindex", _fake_reindex)
    rc = cw.cmd_connect(source=str(remote), wiki_id=wiki_id, name=None,
                        source_type="git", decisions={"consent": "accept"})
    assert rc == 0
    add_calls.clear()
    reindex_calls.clear()
    return cw, remote, add_calls, reindex_calls


def test_pull_git_reindex_on_deletion(tmp_path, monkeypatch):
    """Upstream deletions must trigger a full reindex — incremental --add can't remove."""
    cw, remote, add_calls, reindex_calls = _connect_git_fixture(tmp_path, monkeypatch)

    subprocess.run(["git", "rm", "wiki/p.md"], cwd=remote, check=True, capture_output=True)
    subprocess.run(["git", "commit", "-m", "delete page"], cwd=remote, check=True, capture_output=True)

    rc = cw.cmd_pull(decisions={})
    assert rc == 0
    assert len(reindex_calls) == 1
    assert add_calls == []


def test_pull_git_reindex_on_rename(tmp_path, monkeypatch):
    """A rename removes the old path — must also take the reindex path."""
    cw, remote, add_calls, reindex_calls = _connect_git_fixture(tmp_path, monkeypatch)

    subprocess.run(["git", "mv", "wiki/p.md", "wiki/renamed.md"],
                   cwd=remote, check=True, capture_output=True)
    subprocess.run(["git", "commit", "-m", "rename page"], cwd=remote, check=True, capture_output=True)

    rc = cw.cmd_pull(decisions={})
    assert rc == 0
    assert len(reindex_calls) == 1
    assert add_calls == []


def test_pull_git_reindex_when_many_changes(tmp_path, monkeypatch):
    """Above _INCREMENTAL_ADD_LIMIT changed files, one reindex beats N model loads."""
    cw, remote, add_calls, reindex_calls = _connect_git_fixture(tmp_path, monkeypatch)

    for i in range(cw._INCREMENTAL_ADD_LIMIT + 1):
        (remote / "wiki" / f"bulk{i}.md").write_text(
            f"---\ntitle: B{i}\ntags: []\n---\nbody", encoding="utf-8")
    subprocess.run(["git", "add", "."], cwd=remote, check=True, capture_output=True)
    subprocess.run(["git", "commit", "-m", "bulk add"], cwd=remote, check=True, capture_output=True)

    rc = cw.cmd_pull(decisions={})
    assert rc == 0
    assert len(reindex_calls) == 1
    assert add_calls == []


def test_pull_git_reindex_when_no_stored_commit(tmp_path, monkeypatch):
    """A config entry with no stored commit has no diff base — full reindex."""
    cw, remote, add_calls, reindex_calls = _connect_git_fixture(tmp_path, monkeypatch)

    cfg = cw.load_config(cw.CONFIG_PATH)
    cfg["wikis"][0].pop("commit", None)
    save_config(cw.CONFIG_PATH, cfg)

    rc = cw.cmd_pull(decisions={})
    assert rc == 0
    assert len(reindex_calls) == 1
    assert add_calls == []


def test_pull_git_incremental_add_passes_wiki_root(tmp_path, monkeypatch):
    """Incremental adds must carry wiki_root so metafile exclusion matches reindex."""
    cw = _setup_repo(tmp_path, monkeypatch)
    cw.cmd_init()
    remote = _make_fake_remote(tmp_path)
    _stub_resolve_model(cw, monkeypatch, model="model-v1")

    roots: list[str] = []

    def _fake_add_page(f, c, wiki_root=None):
        roots.append(wiki_root)

        class R:
            returncode = 0
            stdout = ""
            stderr = ""
        return R()

    monkeypatch.setattr(cw, "_run_add_page", _fake_add_page)
    monkeypatch.setattr(cw, "_run_reindex", _make_fake_reindex_factory(cw))
    rc = cw.cmd_connect(source=str(remote), wiki_id="g", name=None,
                        source_type="git", decisions={"consent": "accept"})
    assert rc == 0

    (remote / "wiki" / "new.md").write_text("---\ntitle: N\ntags: []\n---\nx", encoding="utf-8")
    subprocess.run(["git", "add", "."], cwd=remote, check=True, capture_output=True)
    subprocess.run(["git", "commit", "-m", "new"], cwd=remote, check=True, capture_output=True)

    roots.clear()
    rc = cw.cmd_pull(decisions={})
    assert rc == 0
    assert len(roots) == 1
    assert roots[0] is not None and roots[0].endswith("wiki")


def test_pull_local_reindex_when_indexed_file_missing(tmp_path, monkeypatch):
    """Stale indexed entries (source file gone) must force a local reindex."""
    cw = _setup_repo(tmp_path, monkeypatch)
    cw.cmd_init()
    src = tmp_path / "loc"
    (src / "wiki").mkdir(parents=True)
    (src / "wiki" / "keep.md").write_text("---\ntitle: K\ntags: []\n---\nk", encoding="utf-8")
    save_config(cw.CONFIG_PATH, {"schema_version": 1, "wikis": [
        {"id": "loc", "name": "L", "source_type": "local", "source": str(src),
         "enabled": True, "status": "ok", "added": "2026-04-29",
         "embedding_backend": "search-chromadb", "embedding_model": "m",
         "last_pulled": "2026-01-01"}
    ]})

    monkeypatch.setattr(cw, "_indexed_files_missing", lambda ip, c: True)
    add_calls: list[str] = []
    reindex_calls: list[str] = []

    def _stub_add(f, c, wiki_root=None):
        add_calls.append(str(f))

        class R:
            returncode = 0
            stdout = ""
            stderr = ""
        return R()

    def _stub_reindex(wp, coll):
        reindex_calls.append(str(wp))

        class R:
            returncode = 0
            stdout = "Reindex complete: 1 pages indexed, 0 skipped"
            stderr = ""
        return R()

    monkeypatch.setattr(cw, "_run_add_page", _stub_add)
    monkeypatch.setattr(cw, "_run_reindex", _stub_reindex)

    rc = cw.cmd_pull(decisions={})
    assert rc == 0
    assert len(reindex_calls) == 1
    assert add_calls == []


def test_indexed_files_missing_detects_stale(tmp_path, monkeypatch):
    from tools import connected_wikis as cw
    import chromadb as _ch
    index = str(tmp_path / "idx")
    client = _ch.PersistentClient(path=index)
    coll = client.get_or_create_collection("wiki-ext-t", metadata={"hnsw:space": "cosine"})

    existing = tmp_path / "real.md"
    existing.write_text("x", encoding="utf-8")
    coll.upsert(ids=[str(existing)], embeddings=[[0.1] * 384],
                documents=["d"], metadatas=[{"path": str(existing)}])
    assert cw._indexed_files_missing(index, "wiki-ext-t") is False

    coll.upsert(ids=[str(tmp_path / "gone.md")], embeddings=[[0.2] * 384],
                documents=["d"], metadatas=[{"path": "gone"}])
    assert cw._indexed_files_missing(index, "wiki-ext-t") is True
    # Missing collection → False (no signal)
    assert cw._indexed_files_missing(index, "no-such-collection") is False


def test_pull_mismatch_reindex_decision(tmp_path, monkeypatch):
    """decision=reindex must reindex once, update embedding fields, and skip per-file adds."""
    cw, remote, add_calls, reindex_calls = _connect_git_fixture(tmp_path, monkeypatch)

    # Recorded model differs from active model → mismatch prompt fires.
    cfg = cw.load_config(cw.CONFIG_PATH)
    cfg["wikis"][0]["embedding_model"] = "old-model"
    save_config(cw.CONFIG_PATH, cfg)

    (remote / "wiki" / "new.md").write_text("---\ntitle: N\ntags: []\n---\nx", encoding="utf-8")
    subprocess.run(["git", "add", "."], cwd=remote, check=True, capture_output=True)
    subprocess.run(["git", "commit", "-m", "new"], cwd=remote, check=True, capture_output=True)

    rc = cw.cmd_pull(decisions={"mismatch": "reindex"})
    assert rc == 0
    assert len(reindex_calls) == 1  # full reindex, not per-file adds
    assert add_calls == []
    cfg = cw.load_config(cw.CONFIG_PATH)
    assert cfg["wikis"][0]["embedding_model"] == "model-v1"


def test_connect_symlink_wiki_rejected(tmp_path, monkeypatch):
    """A cloned repo whose wiki/ is a symlink must be refused (local file indexing)."""
    cw = _setup_repo(tmp_path, monkeypatch)
    cw.cmd_init()

    outside = tmp_path / "outside-wiki"
    outside.mkdir()
    (outside / "leak.md").write_text("---\ntitle: L\ntags: []\n---\nsecret", encoding="utf-8")

    repo = tmp_path / "evil-remote"
    repo.mkdir()
    subprocess.run(["git", "init", "-b", "main"], cwd=repo, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.email", "t@t"], cwd=repo, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.name", "t"], cwd=repo, check=True, capture_output=True)
    os.symlink(str(outside), str(repo / "wiki"))
    (repo / "README.md").write_text("innocent", encoding="utf-8")
    subprocess.run(["git", "add", "."], cwd=repo, check=True, capture_output=True)
    subprocess.run(["git", "commit", "-m", "evil"], cwd=repo, check=True, capture_output=True)

    _stub_resolve_model(cw, monkeypatch)
    rc = cw.cmd_connect(source=str(repo), wiki_id="evil", name=None,
                        source_type="git", decisions={"consent": "accept"})
    assert rc == 1
    assert cw.load_config(cw.CONFIG_PATH)["wikis"] == []


def test_safe_preview_rejects_symlinked_readme(tmp_path):
    from tools.connected_wikis import _safe_preview
    secret = tmp_path / "secret.txt"
    secret.write_text("do not leak", encoding="utf-8")
    root = tmp_path / "src"
    (root / "wiki").mkdir(parents=True)
    os.symlink(str(secret), str(root / "README.md"))

    name, preview = _safe_preview(root, root / "wiki")
    assert "do not leak" not in preview


def test_safe_preview_strips_control_chars(tmp_path):
    from tools.connected_wikis import _safe_preview
    root = tmp_path / "src"
    (root / "wiki").mkdir(parents=True)
    (root / "README.md").write_text("hi\x1b[31mred\x07bell\nnew line\ttab", encoding="utf-8")

    name, preview = _safe_preview(root, root / "wiki")
    assert name == "README.md"
    assert "\x1b" not in preview and "\x07" not in preview
    assert "\n" in preview and "\t" in preview  # legitimate whitespace kept


def test_safe_preview_reads_at_most_2000_chars(tmp_path):
    from tools.connected_wikis import _safe_preview
    root = tmp_path / "src"
    (root / "wiki").mkdir(parents=True)
    (root / "README.md").write_text("A" * 10000, encoding="utf-8")
    _, preview = _safe_preview(root, root / "wiki")
    assert len(preview) == 2000


@pytest.mark.parametrize("source,expected", [
    ("https://github.com/a/b.git", "git"),
    ("http://example.com/a/b", "git"),
    ("git@github.com:a/b.git", "git"),
    ("ssh://git@host/a/b.git", "git"),
    ("git://host/a/b.git", "git"),
    ("/local/path/to/wiki", "local"),
    ("relative/path", "local"),
])
def test_infer_source_type(source, expected):
    from tools.connected_wikis import _infer_source_type
    assert _infer_source_type(source) == expected


def test_connect_git_option_injection_guarded(tmp_path, monkeypatch):
    """A source starting with -- must be treated as a path, never a git option."""
    cw = _setup_repo(tmp_path, monkeypatch)
    cw.cmd_init()
    _stub_resolve_model(cw, monkeypatch)
    sentinel = tmp_path / "pwned"

    rc = cw.cmd_connect(source=f"--upload-pack=touch {sentinel}", wiki_id="evil",
                        name=None, source_type="git", decisions={"consent": "accept"})
    assert rc == 1
    assert not sentinel.exists()
    assert cw.load_config(cw.CONFIG_PATH)["wikis"] == []


def test_grep_references_all_patterns(tmp_path, monkeypatch):
    """All three citation forms (Korean, English, path) must be detected."""
    cw = _setup_repo(tmp_path, monkeypatch)
    syn = tmp_path / "wiki" / "synthesis"
    syn.mkdir(parents=True)
    (syn / "a.md").write_text("주장 (출처: eng)", encoding="utf-8")
    (syn / "b.md").write_text("claim (source: eng)", encoding="utf-8")
    (syn / "c.md").write_text("see connected-wikis/eng/wiki/p.md", encoding="utf-8")
    (syn / "d.md").write_text("unrelated (source: other)", encoding="utf-8")

    refs = cw._grep_references("eng")
    assert len(refs) == 3
    files = {r[0] for r in refs}
    assert files == {"wiki/synthesis/a.md", "wiki/synthesis/b.md", "wiki/synthesis/c.md"}


def test_request_decision_tty_eof_falls_through(monkeypatch, capsys):
    monkeypatch.setattr(sys.stdin, "isatty", lambda: True)

    def _eof(prompt):
        raise EOFError
    monkeypatch.setattr("builtins.input", _eof)

    with pytest.raises(SystemExit) as exc:
        request_decision(prompt_key="consent", question="Trust?",
                         options=["accept", "reject"], decisions={})
    assert exc.value.code == 4
    assert "PROMPT: consent" in capsys.readouterr().out


def test_request_decision_tty_invalid_then_valid(monkeypatch):
    monkeypatch.setattr(sys.stdin, "isatty", lambda: True)
    answers = iter(["bogus", "accept"])
    monkeypatch.setattr("builtins.input", lambda prompt: next(answers))

    assert request_decision(prompt_key="consent", question="Trust?",
                            options=["accept", "reject"], decisions={}) == "accept"


def test_validate_id_empty_string():
    with pytest.raises(IdError):
        validate_id("", [])


def test_connect_warns_on_credentialed_url(tmp_path, monkeypatch, capsys):
    cw = _setup_repo(tmp_path, monkeypatch)
    cw.cmd_init()
    _stub_resolve_model(cw, monkeypatch)

    rc = cw.cmd_connect(source="https://user:token@example.invalid/a/b.git",
                        wiki_id="cred", name=None, source_type="git",
                        decisions={"consent": "accept"})
    assert rc == 1  # clone fails (invalid host) — the warning must fire regardless
    assert "credentials" in capsys.readouterr().err
