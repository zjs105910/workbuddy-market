import os
import subprocess
import sys
from pathlib import Path

from autoharness.lib import sidecar


def test_create_and_read_roundtrip(tmp_path):
    sidecar.create("project", "foo", anchor=7, root=tmp_path)
    d = sidecar.read("project", "foo", tmp_path)
    assert d["created_by"] == "agent"
    assert d["anchor"] == 7
    assert d["use"] == 0


def test_bump_use_increments(tmp_path):
    sidecar.create("project", "foo", anchor=0, root=tmp_path)
    assert sidecar.bump_use("project", "foo", tmp_path) == 1
    assert sidecar.bump_use("project", "foo", tmp_path) == 2
    assert sidecar.read("project", "foo", tmp_path)["use"] == 2


def test_is_agent_created(tmp_path):
    assert not sidecar.is_agent_created("project", "foo", tmp_path)  # no sidecar -> False (only touch self-produced)
    sidecar.create("project", "foo", 0, tmp_path)
    assert sidecar.is_agent_created("project", "foo", tmp_path)


def test_missing_sidecar_reads_empty(tmp_path):
    assert sidecar.read("project", "nope", tmp_path) == {}


def test_anchor_preserved_across_call_bumps(tmp_path):
    sidecar.create("global", "g", anchor=42, root=tmp_path)
    sidecar.bump_use("global", "g", tmp_path)
    assert sidecar.read("global", "g", tmp_path)["anchor"] == 42


# --- three-way counters (hermes-parity Phase 10, direction C) ---

def test_create_has_three_counters(tmp_path):
    d = sidecar.create("project", "tri", 0, tmp_path)
    assert d["use"] == 0 and d["view"] == 0 and d["patch"] == 0


def test_bumps_are_independent(tmp_path):
    sidecar.create("project", "tri", 0, tmp_path)
    assert sidecar.bump_use("project", "tri", tmp_path) == 1
    assert sidecar.bump_view("project", "tri", tmp_path) == 1
    assert sidecar.bump_view("project", "tri", tmp_path) == 2
    assert sidecar.bump_patch("project", "tri", tmp_path) == 1
    d = sidecar.read("project", "tri", tmp_path)
    assert (d["use"], d["view"], d["patch"]) == (1, 2, 1)


def test_legacy_calls_migrates_to_use_once(tmp_path):
    sidecar.write("project", "old", {"created_by": "agent", "calls": 7, "anchor": 0}, tmp_path)
    d = sidecar.read("project", "old", tmp_path)
    assert d.get("use", 0) + d.get("calls", 0) == 7  # no double count either way
    sidecar.bump_use("project", "old", tmp_path)
    d = sidecar.read("project", "old", tmp_path)
    assert d["use"] == 8 and "calls" not in d  # migrated once, idempotent


def test_reuse_after_patch_marked_on_first_use(tmp_path):
    sidecar.create("project", "p", 0, tmp_path)
    sidecar.bump_use("project", "p", tmp_path)
    sidecar.bump_patch("project", "p", tmp_path)
    d = sidecar.read("project", "p", tmp_path)
    assert d.get("reused_gen", 0) < d["patch"]  # not yet reused since the patch
    sidecar.bump_use("project", "p", tmp_path)
    d = sidecar.read("project", "p", tmp_path)
    assert d["reused_gen"] == d["patch"]  # first use after patch marks the reuse generation


def test_bumps_preserve_all_counters_across_processes(tmp_path):
    sidecar.create("project", "shared", anchor=42, root=tmp_path)
    code = (
        "import pathlib, sys, time\n"
        "from autoharness.lib import sidecar\n"
        "root = pathlib.Path(sys.argv[1])\n"
        "original_read = sidecar.read\n"
        "def delayed_read(*args, **kwargs):\n"
        "    data = original_read(*args, **kwargs)\n"
        "    time.sleep(0.001)\n"
        "    return data\n"
        "sidecar.read = delayed_read\n"
        "for _ in range(20):\n"
        "    sidecar.bump_use('project', 'shared', root)\n"
        "    sidecar.bump_view('project', 'shared', root)\n"
        "    sidecar.bump_patch('project', 'shared', root)\n"
    )
    env = {**os.environ, "PYTHONPATH": str(Path(sidecar.__file__).parents[2])}
    procs = [subprocess.Popen([sys.executable, "-c", code, str(tmp_path)], env=env)
             for _ in range(4)]
    try:
        assert [p.wait(timeout=30) for p in procs] == [0, 0, 0, 0]
    finally:
        for p in procs:
            if p.poll() is None:
                p.kill()
                p.wait()

    data = sidecar.read("project", "shared", tmp_path)
    assert (data["use"], data["view"], data["patch"]) == (80, 80, 80)
    assert data["anchor"] == 42
    assert data["created_by"] == "agent"
    sidecar.bump_use("project", "shared", tmp_path)
    assert sidecar.read("project", "shared", tmp_path)["reused_gen"] == 80
