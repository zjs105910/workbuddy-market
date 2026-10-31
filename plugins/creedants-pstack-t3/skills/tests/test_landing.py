import ast
import contextlib
import inspect
import json
import os
import re
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import time
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "t3/added/landing/scripts/land.py"
sys.path.insert(0, str(SCRIPT.parent))

import land  # noqa: E402

REVIEWER = "codex/gpt-6.1-sol"
ADMIN = ("--owner", ".admin/@1")


def stamp_in(hours):
    return (datetime.now(timezone.utc) + timedelta(hours=hours)).isoformat()


def git_env():
    """Identity for fixture commits. LC_ALL=C keeps git diagnostics in English."""
    return {**os.environ, "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@t",
            "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@t",
            "LC_ALL": "C"}


def sh(*args, cwd):
    result = subprocess.run(args, cwd=cwd, capture_output=True, text=True, env=git_env())
    if result.returncode != 0:
        raise AssertionError(f"{args} failed: {result.stderr}")
    return result.stdout.strip()


def paused_child(case, args):
    """Run land.py with its first transaction held until <case>/proceed exists, as a command started before a recovery."""
    case = Path(case)
    original = land.Store.tx

    def paused_tx(self):
        (case / "paused").touch()
        deadline = time.monotonic() + 60
        while not (case / "proceed").exists() and time.monotonic() < deadline:
            time.sleep(0.01)
        return original(self)

    land.Store.tx = paused_tx
    sys.exit(land.main(args))


class LandingTest(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.base = Path(self.temporary.name)
        self.env = mock.patch.dict(os.environ, {"XDG_STATE_HOME": str(self.base / "state")})
        self.env.start()
        sh("git", "init", "-q", "--bare", "-b", "main", "origin.git", cwd=self.base)
        sh("git", "clone", "-q", "origin.git", "work", cwd=self.base)
        self.work = self.base / "work"
        sh("git", "checkout", "-q", "-b", "main", cwd=self.work)
        for name in ("a.txt", "b.txt", "lib/x.py"):
            (self.work / name).parent.mkdir(exist_ok=True)
            (self.work / name).write_text(f"{name}\n")
        (self.work / "check.sh").write_text("#!/bin/sh\n! grep -rq BROKEN --include=*.txt .\n")
        (self.work / "check.sh").chmod(0o755)
        self.commit("init")
        sh("git", "push", "-q", "origin", "main", cwd=self.work)
        self.install_github_remote()

    def install_github_remote(self):
        """Point origin at https://github.com/o/r.git and send transport commands to the bare repo.

        git remote get-url still prints the GitHub URL. push, fetch, ls-remote, and pull
        rewrite that URL to origin.git, so a test never contacts GitHub.
        """
        real = shutil.which("git")
        bindir = self.base / "git-wrap"
        bindir.mkdir()
        origin = str(self.base / "origin.git")
        script = bindir / "git"
        script.write_text(
            "#!" + sys.executable + "\n"
            "import os, subprocess, sys\n"
            f"real = {real!r}\n"
            f"origin = {origin!r}\n"
            "args = sys.argv[1:]\n"
            "if len(args) >= 2 and args[0] == 'remote' and args[1] == 'get-url':\n"
            "    os.execv(real, [real, *args])\n"
            "if args and args[0] in ('push', 'fetch', 'ls-remote', 'pull'):\n"
            "    probed = subprocess.run([real, 'remote', 'get-url', 'origin'], capture_output=True, text=True)\n"
            "    url = probed.stdout.strip()\n"
            "    if probed.returncode == 0 and url.startswith('https://github.com/'):\n"
            "        os.execv(real, [real, '-c', 'url.' + origin + '/.insteadOf=' + url, *args])\n"
            "os.execv(real, [real, *args])\n"
        )
        script.chmod(0o755)
        os.environ["PATH"] = str(bindir) + os.pathsep + os.environ.get("PATH", "")
        sh("git", "remote", "set-url", "origin", "https://github.com/o/r.git", cwd=self.work)

    def tearDown(self):
        self.env.stop()
        self.temporary.cleanup()

    def commit(self, message, cwd=None):
        sh("git", "add", "-A", cwd=cwd or self.work)
        sh("git", "commit", "-qm", message, cwd=cwd or self.work)
        return sh("git", "rev-parse", "HEAD", cwd=cwd or self.work)

    def git_raw(self, *args, cwd):
        return subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True, env=git_env())

    def land(self, *args, ok=True):
        result = subprocess.run([sys.executable, str(SCRIPT), "--repo", str(self.work), *args],
                                capture_output=True, text=True, env=os.environ.copy())
        self.assertEqual(result.returncode == 0, ok, result.stdout + result.stderr)
        return (result.stdout if ok else result.stderr).strip()

    def init(self, mode="auto", batch=1, **extra):
        args = ["init", "--trunk", extra.get("trunk", "main"), "--mode", mode, "--check", "./check.sh", "--batch", str(batch)]
        if "merge_method" in extra:
            args += ["--merge-method", extra["merge_method"]]
        if "base" in extra:
            args += ["--base", extra["base"]]
        return self.land(*args)

    def worker(self, name, edits, base="origin/main"):
        """A worker branch in its own worktree with one commit. Returns its SHA."""
        path = self.base / name
        sh("git", "worktree", "add", "-q", "-b", name, str(path), base, cwd=self.work)
        for file, text in edits.items():
            (path / file).parent.mkdir(parents=True, exist_ok=True)
            (path / file).write_text(text)
        return self.commit(name, cwd=path)

    def origin_log(self):
        return sh("git", "log", "--format=%s", "main", cwd=self.base / "origin.git").splitlines()

    def ref_exists(self, ref, cwd):
        return subprocess.run(["git", "rev-parse", "--verify", "--quiet", ref], cwd=cwd, capture_output=True).returncode == 0

    def install_racing_branch_delete(self):
        """While git push --delete runs, another deleter holds the ref lock and removes the ref.

        git 2.55 then rejects the push with "File exists" and "reference already exists".
        That stderr does not contain "does not exist", and ls-remote shows the ref gone.
        """
        hook = self.base / "origin.git" / "hooks" / "pre-receive"
        marker = self.base / "race-deleted"
        hook.write_text(f"""#!/bin/sh
marker={marker}
while read old new ref; do
  if [ "$new" = "0000000000000000000000000000000000000000" ]; then
    path=$(git rev-parse --git-path "$ref")
    echo x > "$path.lock"
    rm -f "$path"
    echo "$ref" >> "$marker"
  fi
done
exit 0
""")
        hook.chmod(0o755)

    def record_pushes(self):
        """Log each git push while later commands run. The real git stays behind the wrapper."""
        log = self.base / "git-pushes"
        bindir = self.base / "bin"
        bindir.mkdir(exist_ok=True)
        real = subprocess.run(["which", "git"], capture_output=True, text=True, check=True).stdout.strip()
        script = bindir / "git"
        script.write_text(
            "#!/bin/sh\n"
            "if [ \"$1\" = push ]; then\n"
            f"  printf '%s\\n' \"$*\" >> '{log}'\n"
            "fi\n"
            f"exec '{real}' \"$@\"\n"
        )
        script.chmod(0o755)
        self._push_path = os.environ.get("PATH", "")
        os.environ["PATH"] = str(bindir) + os.pathsep + self._push_path
        return log

    def stop_recording_pushes(self):
        os.environ["PATH"] = self._push_path

    def assert_pushes_stay_on_their_refs(self, log):
        lines = log.read_text().splitlines()
        self.assertTrue(lines)
        for line in lines:
            self.assertTrue(line.startswith("push --no-follow-tags "), line)
            self.assertNotIn("--dry-run", line)
            self.assertFalse(any(part.startswith(":") for part in line.split()), line)

    def merged_queue_branch(self):
        """Save the queue head, then mark the PR merged at that head."""
        remote = self.base / "origin.git"
        sha = sh("git", "rev-parse", "refs/heads/landing/e1", cwd=remote)
        (self.base / "pr-state").write_text(
            f"MERGED {sha} 1111111111111111111111111111111111111111")
        return sha

    def test_status_refuses_a_q_number(self):
        self.init()
        self.assertEqual(self.queue_one(), "E1")
        self.assertIn("'Q1' is not an entry id such as E3", self.land("status", "Q1", ok=False))
        named = self.land("status", "E1")
        self.assertEqual(self.land("status", "1"), named)
        self.assertTrue(named.startswith("E1 queued"), named)

    def test_leases_refuse_overlap_including_aliases_and_the_whole_repo(self):
        self.init()
        self.assertEqual(self.land("lease", "claim", "--holder", "perf/D1", "--paths", "lib"), "L1")
        self.assertIn("L1 held by perf/D1 on lib", self.land("lease", "claim", "--holder", "bugs/D1", "--paths", "a.txt/../lib/x.py", ok=False))
        self.assertIn("L1 held by perf/D1", self.land("lease", "claim", "--holder", "bugs/D1", "--paths", ".", ok=False))
        self.assertIn("leaves the repository", self.land("lease", "claim", "--holder", "bugs/D1", "--paths", "../etc", ok=False))
        self.assertEqual(self.land("lease", "claim", "--holder", "bugs/D1", "--paths", "lib2,a.txt"), "L2")

    def claim(self, holder, paths, *extra, ok=True):
        return self.land("lease", "claim", "--holder", holder, "--paths", paths, *extra, ok=ok)

    def test_the_cap_refuses_a_claim_naming_the_holders_and_frees_on_release(self):
        self.land("init", "--trunk", "main", "--mode", "push", "--check", "./check.sh", "--cap", "2")
        self.assertEqual(self.claim("a/D1", "a.txt"), "L1")
        self.assertEqual(self.claim("b/D1", "b.txt"), "L2")
        self.assertEqual(self.claim("c/D1", "lib", ok=False), "land: repository at its cap: 2 of 2 changes in flight (a/D1, b/D1)")
        self.assertEqual(self.land("lease", "release", "L1"), "L1 released")
        self.assertEqual(self.claim("c/D1", "lib"), "L3")

    def test_the_cap_is_set_and_cleared_on_its_own_and_shown_in_status(self):
        self.init()
        self.assertNotIn("changes in flight", self.land("status"))
        self.assertEqual(self.land("cap", "4"), "repository cap is now 4 changes in flight")
        self.claim("a/D1", "a.txt")
        self.assertEqual(self.land("status"), "push mode onto refs/remotes/origin/main. leases held: 1, changes in flight: 1 of 4.")
        self.assertEqual(self.land("cap", "0"), "repository cap cleared")
        self.assertEqual(self.land("status"), "push mode onto refs/remotes/origin/main. leases held: 1.")
        self.assertIn("negative", self.land("cap", "-1", ok=False))

    def test_ten_concurrent_claims_under_a_cap_of_three_make_exactly_three_leases(self):
        self.init()
        self.land("cap", "3")
        claims = [subprocess.Popen([sys.executable, str(SCRIPT), "--repo", str(self.work), "lease", "claim",
                                    "--holder", f"r/D{n}", "--paths", f"p{n}.txt"],
                                   stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, env=os.environ.copy())
                  for n in range(10)]
        results = [(claim.wait(), *claim.communicate()) for claim in claims]
        self.assertEqual(sorted(out.strip() for code, out, _ in results if code == 0), ["L1", "L2", "L3"])
        refused = [err for code, _, err in results if code != 0]
        self.assertEqual(len(refused), 7)
        self.assertTrue(all("repository at its cap: 3 of 3 changes in flight" in err for err in refused), refused)
        self.assertEqual(len(self.land("lease", "list").splitlines()), 3)

    def test_a_submitted_lease_counts_toward_the_cap_and_a_bounce_keeps_the_count(self):
        self.init()
        self.land("cap", "2")
        self.assertEqual(self.queue_one(text="BROKEN\n"), "E1")
        self.assertEqual(self.claim("r/D2", "b.txt"), "L2")
        self.assertIn("changes in flight: 2 of 2", self.land("status"))
        self.assertEqual(self.claim("r/D3", "lib", ok=False), "land: repository at its cap: 2 of 2 changes in flight (r/D1, r/D2)")
        self.assertIn("bounced E1 (r/D1)", self.land("land"))
        self.assertIn("changes in flight: 2 of 2", self.land("status"))
        self.assertIn("at its cap", self.claim("r/D3", "lib", ok=False))

    def test_an_expired_lease_does_not_count_toward_the_cap(self):
        self.init()
        self.land("cap", "1")
        self.assertEqual(self.claim("a/D1", "a.txt", "--ttl-hours", "0"), "L1")
        self.assertEqual(self.claim("b/D1", "b.txt"), "L2")

    def test_renewing_an_expired_lease_refuses_an_overlap_another_holder_now_has(self):
        self.init()
        self.claim("docs/D9", "a.txt", "--ttl-hours", "0")
        self.assertEqual(self.claim("engine/D9", "a.txt"), "L2")
        self.assertEqual(self.land("lease", "renew", "L1", ok=False),
                         "land: L1 expired and L2 held by engine/D9 now covers a.txt; claim again after it is released")
        listed = self.land("lease", "list").splitlines()
        self.assertEqual([line.split(" until ")[0] for line in listed], ["L2 active engine/D9"])

    def test_renewing_an_expired_lease_refuses_when_the_cap_filled(self):
        self.init()
        self.land("cap", "2")
        self.claim("a/D1", "a.txt", "--ttl-hours", "0")
        self.claim("b/D1", "b.txt")
        self.claim("c/D1", "lib")
        self.assertEqual(self.land("lease", "renew", "L1", ok=False), "land: repository at its cap: 2 of 2 changes in flight (b/D1, c/D1)")
        self.land("lease", "release", "L3")
        self.assertEqual(self.land("lease", "renew", "L1"), "L1 renewed")
        self.assertEqual([line.split(" until ")[0] for line in self.land("lease", "list").splitlines()], ["L1 active a/D1", "L2 active b/D1"])

    def test_renew_if_live_refuses_an_expired_lease_and_renews_a_live_one(self):
        self.init()
        self.claim("a/D1", "a.txt", "--ttl-hours", "0")
        self.claim("b/D1", "b.txt")
        self.assertRegex(self.land("lease", "renew", "L1", "--if-live", ok=False), r"^land: L1 expired at \d{4}-\d\d-\d\dT\d\d:\d\d$")
        self.assertEqual(self.land("lease", "renew", "L2", "--if-live", "--ttl-hours", "48"), "L2 renewed")
        self.assertEqual(self.land("lease", "list").split(" until ")[1][:10], stamp_in(48)[:10])

    def test_renew_names_a_submitted_a_released_and_a_missing_lease(self):
        self.init()
        self.queue_one()
        self.claim("r/D2", "b.txt")
        self.land("lease", "release", "L2")
        self.assertEqual(self.land("lease", "renew", "L1", ok=False), "land: L1 is submitted; the queue holds it")
        self.assertEqual(self.land("lease", "renew", "L2", ok=False), "land: L2 is released")
        self.assertEqual(self.land("lease", "renew", "L9", ok=False), "land: no L9")

    def lease_row(self, number):
        store = land.Store.for_repo(self.work)
        try:
            return tuple(store.db.execute("SELECT * FROM lease WHERE id = ?", (number,)).fetchone())
        finally:
            store.db.close()

    def owner_state(self):
        store = land.Store.for_repo(self.work)
        try:
            return ([tuple(row) for row in store.db.execute("SELECT * FROM owner")],
                    store.db.execute("SELECT count(*) FROM log").fetchone()[0])
        finally:
            store.db.close()

    def test_an_owner_floor_rises_and_never_lowers(self):
        self.init()
        self.assertEqual(self.land("owner", "--prefix", "docs/", "--generation", "2"), "docs/ at generation 2")
        before = self.owner_state()
        self.assertEqual(self.land("owner", "--prefix", "docs/", "--generation", "2"), "docs/ at generation 2")
        self.assertEqual(self.land("owner", "--prefix", "docs/", "--generation", "1", ok=False),
                         "land: docs/ is at generation 2; a floor never lowers")
        self.assertEqual(self.owner_state(), before)
        self.assertEqual(self.land("owner", "--prefix", "docs/", "--generation", "3"), "docs/ at generation 3")

    def test_lease_writes_refuse_an_owner_below_the_floor_and_change_nothing(self):
        self.init()
        self.assertEqual(self.claim("docs/D3", "a.txt", "--owner", "docs/@1"), "L1")
        self.land("lease", "renew", "L1", "--ttl-hours", "0", "--owner", "docs/@1")
        self.land("owner", "--prefix", "docs/", "--generation", "2")
        before = self.lease_row(1)
        stale = "land: owner docs/@1 is stale; docs/ is at generation 2"
        self.assertEqual(self.land("lease", "release", "L1", "--owner", "docs/@1", ok=False), stale)
        self.assertEqual(self.land("lease", "renew", "L1", "--owner", "docs/@1", ok=False), stale)
        self.assertEqual(self.claim("docs/D4", "b.txt", "--owner", "docs/@1", ok=False), stale)
        self.assertEqual(self.lease_row(1), before)
        self.assertEqual(self.land("lease", "renew", "L1", "--owner", "docs/@2"), "L1 renewed")
        self.assertEqual(self.land("lease", "release", "L1", "--owner", "docs/@2"), "L1 released")

    def test_a_floored_prefix_needs_an_owner_that_covers_the_holder(self):
        self.init()
        self.land("owner", "--prefix", "docs/", "--generation", "2")
        self.assertEqual(self.claim("docs/D1", "a.txt", ok=False), "land: docs/D1 is under docs/ at generation 2; pass --owner docs/@2")
        self.assertEqual(self.claim("docs/D1", "a.txt", "--owner", "engine/@2", ok=False),
                         "land: owner engine/@2 does not cover holder docs/D1")
        self.assertEqual(self.claim("docs/D1", "a.txt", "--owner", "docs/@2"), "L1")
        self.assertEqual(self.claim("engine/D1", "b.txt"), "L2")
        self.assertEqual(self.land("lease", "release", "L2"), "L2 released")

    def test_submit_refuses_a_stale_owner_and_queues_for_the_current_one(self):
        self.init()
        sha = self.worker("w1", {"a.txt": "agent\n"})
        lease = self.claim("docs/D1", "a.txt", "--owner", "docs/@1")
        self.land("owner", "--prefix", "docs/", "--generation", "2")
        submit = ("submit", "--holder", "docs/D1", "--branch", "w1", "--sha", sha, "--lease", lease, "--reviewer", REVIEWER)
        self.assertEqual(self.land(*submit, "--owner", "docs/@1", ok=False), "land: owner docs/@1 is stale; docs/ is at generation 2")
        self.assertEqual(self.land("status", "--holder", "docs/D1"), "no entries held by docs/D1")
        self.assertEqual(self.land(*submit, "--owner", "docs/@2"), "E1")

    def lease_check(self, holder, paths):
        result = subprocess.run([sys.executable, str(SCRIPT), "--repo", str(self.work), "lease", "check", "--holder", holder, "--paths", paths],
                                capture_output=True, text=True, env=os.environ.copy())
        return result.returncode, result.stdout.strip()

    def test_lease_check_runs_admission_without_claiming(self):
        self.init()
        self.claim("a/D1", "a.txt")
        self.land("lease", "release", "L1")
        self.assertEqual(self.land("lease", "check", "--holder", "b/D1", "--paths", "a.txt"), "free")
        self.claim("c/D1", "a.txt,b.txt")
        self.assertEqual(self.lease_check("b/D1", "a.txt"), (1, "L2 held by c/D1 on a.txt, b.txt"))
        self.land("cap", "1")
        self.assertEqual(self.lease_check("b/D1", "lib"), (1, "repository at its cap: 1 of 1 changes in flight (c/D1)"))
        self.assertEqual(len(self.land("lease", "list").splitlines()), 1)

    def test_status_holder_lists_one_holder_or_a_prefix(self):
        self.init()
        sha1 = self.worker("w1", {"a.txt": "one\n"})
        sha2 = self.worker("w2", {"b.txt": "two\n"})
        sha3 = self.worker("w3", {"lib/x.py": "three\n"})
        for holder, branch, sha, path in [("engine/D1", "w1", sha1, "a.txt"), ("engine/D2", "w2", sha2, "b.txt"), ("enginex/D1", "w3", sha3, "lib")]:
            lease = self.claim(holder, path)
            self.land("submit", "--holder", holder, "--branch", branch, "--sha", sha, "--lease", lease, "--reviewer", REVIEWER)
        self.assertEqual(self.land("status", "--holder", "engine/D2"), f"E2 queued (engine/D2, {sha2[:12]})")
        self.land("land")
        landed = sh("git", "rev-parse", "main~2", cwd=self.base / "origin.git")
        self.assertEqual(self.land("status", "--holder", "engine/").splitlines(),
                         [f"E1 landed (engine/D1, {sha1[:12]}) as {landed[:12]}",
                          f"E2 landed (engine/D2, {sha2[:12]}) as {sh('git', 'rev-parse', 'main~1', cwd=self.base / 'origin.git')[:12]}"])
        self.assertEqual(self.land("status", "--holder", "docs/D1"), "no entries held by docs/D1")

    def test_status_holder_sha_matches_the_whole_commit(self):
        import sqlite3
        from contextlib import closing
        self.init()
        sha = self.worker("w1", {"a.txt": "one\n"})
        lease = self.claim("engine/D1", "a.txt")
        self.land("submit", "--holder", "engine/D1", "--branch", "w1", "--sha", sha, "--lease", lease, "--reviewer", REVIEWER)
        other = sha[:12] + ("1" if sha[12] == "0" else "0") + sha[13:]
        database = next((self.base / "state").glob("pstack-t3/landing/*/land.db"))
        with closing(sqlite3.connect(database)) as db, db:
            db.execute("INSERT INTO entry (at, holder, branch, sha, base, fingerprint, lease, reviewer, state, note) "
                       "SELECT at, holder, branch, ?, base, fingerprint, lease, reviewer, 'bounced', 'other' FROM entry",
                       (other,))
        self.assertEqual(self.land("status", "--holder", "engine/D1").splitlines(),
                         [f"E1 queued (engine/D1, {sha[:12]})", f"E2 bounced (engine/D1, {sha[:12]}): other"])
        self.assertEqual(self.land("status", "--holder", "engine/D1", "--sha", sha), f"E1 queued (engine/D1, {sha[:12]})")
        self.assertEqual(self.land("status", "--holder", "engine/D1", "--sha", sha.upper()),
                         f"E1 queued (engine/D1, {sha[:12]})")
        self.assertEqual(self.land("status", "--holder", "engine/D1", "--sha", other),
                         f"E2 bounced (engine/D1, {sha[:12]}): other")
        self.assertEqual(self.land("status", "--holder", "engine/D2", "--sha", sha), f"no entries held by engine/D2 at {sha}")

    def test_status_holder_shows_a_bounce_reason(self):
        self.init()
        self.queue_one(text="BROKEN\n")
        self.land("land")
        line = self.land("status", "--holder", "r/D1")
        self.assertRegex(line, r"^E1 bounced \(r/D1, [0-9a-f]{12}\): checks failed: `./check.sh` exited 1")

    def test_the_mode_line_names_the_holders_of_unreleased_leases(self):
        with self.fake_gh():
            self.init(mode="human")
            self.claim("engine/D3", "a.txt")
            self.claim("docs/D1", "b.txt")
            self.claim("old/D1", "lib", "--ttl-hours", "0")
            self.assertEqual(self.land("mode", "merge"), "landing mode is now merge; leases held by docs/D1, engine/D3")
            self.land("lease", "release", "L1")
            self.land("lease", "release", "L2")
            self.assertEqual(self.land("mode", "push"), "landing mode is now push")

    def test_submit_requires_the_holders_own_lease_covering_every_changed_path(self):
        self.init()
        sha = self.worker("w1", {"a.txt": "a2\n", "b.txt": "b2\n"})
        self.land("lease", "claim", "--holder", "perf/D1", "--paths", "a.txt")
        self.land("lease", "claim", "--holder", "perf/D2", "--paths", "b.txt")
        self.assertIn("not an active lease held by bugs/D9",
                      self.land("submit", "--holder", "bugs/D9", "--branch", "w1", "--sha", sha, "--lease", "L1", "--reviewer", REVIEWER, ok=False))
        self.assertIn("outside L1: b.txt",
                      self.land("submit", "--holder", "perf/D1", "--branch", "w1", "--sha", sha, "--lease", "L1", "--reviewer", REVIEWER, ok=False))

    def test_a_batch_lands_in_one_push_and_resubmitting_is_idempotent(self):
        self.init(batch=4)
        shas = [self.worker(f"w{n}", {f: f"{f} v{n}\n"}) for n, f in enumerate(["a.txt", "b.txt", "lib/x.py"], 1)]
        for n, (sha, path) in enumerate(zip(shas, ["a.txt", "b.txt", "lib"]), 1):
            self.land("lease", "claim", "--holder", f"r/D{n}", "--paths", path)
            self.assertEqual(self.land("submit", "--holder", f"r/D{n}", "--branch", f"w{n}", "--sha", sha, "--lease", f"L{n}", "--reviewer", REVIEWER), f"E{n}")
        self.assertEqual(self.land("submit", "--holder", "r/D1", "--branch", "w1", "--sha", shas[0], "--lease", "L1", "--reviewer", REVIEWER), "E1 already queued")
        self.assertEqual(self.land("land"), "landed E1 (r/D1), E2 (r/D2), E3 (r/D3)")
        self.assertEqual(self.origin_log(), ["w3", "w2", "w1", "init"])
        self.assertEqual(self.land("lease", "list"), "no leases held")

    def test_a_failing_batch_lands_the_good_entries_alone_and_bounces_the_bad_one(self):
        self.init(batch=3)
        good1 = self.worker("w1", {"a.txt": "fine\n"})
        bad = self.worker("w2", {"b.txt": "BROKEN\n"})
        good2 = self.worker("w3", {"lib/x.py": "fine\n"})
        for n, (sha, path) in enumerate([(good1, "a.txt"), (bad, "b.txt"), (good2, "lib")], 1):
            self.land("lease", "claim", "--holder", f"r/D{n}", "--paths", path)
            self.land("submit", "--holder", f"r/D{n}", "--branch", f"w{n}", "--sha", sha, "--lease", f"L{n}", "--reviewer", REVIEWER)
        out = self.land("land")
        self.assertIn("landed E1 (r/D1), E3 (r/D3)", out)
        self.assertIn("bounced E2 (r/D2): checks failed: `./check.sh` exited 1", out)
        self.assertEqual(self.origin_log(), ["w3", "w1", "init"])
        self.assertEqual(self.land("lease", "list").split(" until ")[0], "L2 active r/D2")

    def test_a_conflict_bounces_and_the_fixed_resubmission_lands(self):
        self.init()
        first = self.worker("w1", {"a.txt": "one\n"})
        second = self.worker("w2", {"a.txt": "two\n"})
        self.land("lease", "claim", "--holder", "r/D1", "--paths", "a.txt")
        self.land("submit", "--holder", "r/D1", "--branch", "w1", "--sha", first, "--lease", "L1", "--reviewer", REVIEWER)
        self.land("land")
        self.land("lease", "claim", "--holder", "r/D2", "--paths", "a.txt")
        self.land("submit", "--holder", "r/D2", "--branch", "w2", "--sha", second, "--lease", "L2", "--reviewer", REVIEWER)
        self.assertEqual(self.land("land"), "bounced E2 (r/D2): conflict with trunk")
        path = self.base / "w2"
        sh("git", "fetch", "-q", "origin", cwd=path)
        sh("git", "reset", "-q", "--hard", "origin/main", cwd=path)
        (path / "a.txt").write_text("one\ntwo\n")
        fixed = self.commit("w2 fixed", cwd=path)
        self.assertEqual(self.land("submit", "--holder", "r/D2", "--branch", "w2", "--sha", fixed, "--lease", "L2", "--reviewer", REVIEWER), "E3")
        self.assertEqual(self.land("land"), "landed E3 (r/D2)")

    def rebuild_entry_without_autoincrement(self):
        """Rewrite entry as an older database: the same rows, and no AUTOINCREMENT."""
        store = land.Store.for_repo(self.work)
        try:
            rows = [dict(row) for row in store.db.execute("SELECT * FROM entry")]
            store.db.execute("DROP TABLE entry")
            store.db.executescript(land.SCHEMA.replace(" AUTOINCREMENT", ""))
            columns = [info["name"] for info in store.db.execute("PRAGMA table_info(entry)")]
            for row in rows:
                present = [name for name in columns if name in row]
                store.db.execute(
                    f"INSERT INTO entry ({', '.join(present)}) VALUES ({', '.join('?' * len(present))})",
                    [row[name] for name in present])
            if store.db.execute("SELECT 1 FROM sqlite_master WHERE name = 'sqlite_sequence'").fetchone():
                store.db.execute("DELETE FROM sqlite_sequence WHERE name = 'entry'")
        finally:
            store.db.close()

    def test_a_bounced_entry_resubmitted_gets_a_new_id(self):
        self.init()
        sha = self.worker("w1", {"a.txt": "BROKEN\n"})
        self.claim("r/D1", "a.txt")
        submit = ["submit", "--holder", "r/D1", "--branch", "w1", "--sha", sha, "--lease", "L1", "--reviewer", REVIEWER]
        self.assertEqual(self.land(*submit), "E1")
        self.assertIn("bounced E1 (r/D1): checks failed: `./check.sh` exited 1", self.land("land"))
        self.rebuild_entry_without_autoincrement()
        self.assertIn("E1 bounced", self.land("status", "E1"))
        self.assertEqual(self.land(*submit), "E2")
        self.assertEqual(self.land("status", "E1", ok=False), "land: no E1")
        self.assertIn("E2 queued", self.land("status", "E2"))

    def use_non_english_locale(self):
        """Set LANG and LC_ALL to de_DE.UTF-8 for the rest of this test.

        Returns whether git on this machine prints German under that locale.
        When it does not, git on PATH hides the English conflict strings unless
        that process has LC_ALL=C, and records each cherry-pick environment.
        """
        self.git_locale_log = self.base / "git-locale.log"
        translated = False
        try:
            locpath = self.base / "locales"
            locpath.mkdir()
            compiled = subprocess.run(
                ["localedef", "-f", "UTF-8", "-i", "de_DE", str(locpath / "de_DE.UTF-8")],
                capture_output=True)
        except OSError:
            compiled = None
        if compiled is not None and compiled.returncode == 0:
            os.environ["LOCPATH"] = str(locpath)
            env = os.environ.copy()
            env["LANG"] = "de_DE.UTF-8"
            env["LC_ALL"] = "de_DE.UTF-8"
            probe = subprocess.run(["git", "status"], cwd=self.work, capture_output=True, text=True, env=env)
            translated = "Auf Branch" in probe.stdout
        os.environ["LANG"] = "de_DE.UTF-8"
        os.environ["LC_ALL"] = "de_DE.UTF-8"
        if not translated:
            self.install_c_locale_gate()
        return translated

    def install_c_locale_gate(self):
        """Hide English conflict text unless this git process has LC_ALL=C."""
        current = shutil.which("git")
        bindir = self.base / "locale-gate"
        bindir.mkdir()
        script = bindir / "git"
        script.write_text(
            "#!" + sys.executable + "\n"
            "import os, subprocess, sys\n"
            f"real = {current!r}\n"
            f"log = {str(self.git_locale_log)!r}\n"
            "args = sys.argv[1:]\n"
            "if 'cherry-pick' in args:\n"
            "    with open(log, 'a', encoding='utf-8') as handle:\n"
            "        handle.write('cherry-pick LC_ALL=%s\\n' % os.environ.get('LC_ALL', ''))\n"
            "proc = subprocess.run([real, *args], capture_output=True)\n"
            "out, err = proc.stdout, proc.stderr\n"
            "if os.environ.get('LC_ALL') != 'C':\n"
            "    out = out.replace(b'CONFLICT', b'KONFLIKT').replace(b'could not apply', b'nicht anwenden')\n"
            "    err = err.replace(b'CONFLICT', b'KONFLIKT').replace(b'could not apply', b'nicht anwenden')\n"
            "sys.stdout.buffer.write(out)\n"
            "sys.stderr.buffer.write(err)\n"
            "raise SystemExit(proc.returncode)\n"
        )
        script.chmod(0o755)
        os.environ["PATH"] = str(bindir) + os.pathsep + os.environ["PATH"]

    def test_a_conflict_under_a_non_english_locale_bounces(self):
        translated = self.use_non_english_locale()
        self.init()
        first = self.worker("w1", {"a.txt": "one\n"})
        second = self.worker("w2", {"a.txt": "two\n"})
        self.land("lease", "claim", "--holder", "r/D1", "--paths", "a.txt")
        self.land("submit", "--holder", "r/D1", "--branch", "w1", "--sha", first, "--lease", "L1", "--reviewer", REVIEWER)
        self.land("land")
        self.land("lease", "claim", "--holder", "r/D2", "--paths", "a.txt")
        self.land("submit", "--holder", "r/D2", "--branch", "w2", "--sha", second, "--lease", "L2", "--reviewer", REVIEWER)
        self.assertEqual(self.land("land"), "bounced E2 (r/D2): conflict with trunk")
        if not translated:
            recorded = self.git_locale_log.read_text().splitlines()
            self.assertTrue(recorded)
            for line in recorded:
                self.assertEqual(line, "cherry-pick LC_ALL=C")

    def test_a_conflict_rerere_resolved_to_trunk_bounces(self):
        self.init()
        sha = self.worker("w1", {"a.txt": "worker\n"})
        (self.work / "a.txt").write_text("human\n")
        self.commit("human")
        sh("git", "push", "-q", "origin", "main", cwd=self.work)
        self.land("lease", "claim", "--holder", "r/D1", "--paths", "a.txt")
        self.land("submit", "--holder", "r/D1", "--branch", "w1", "--sha", sha, "--lease", "L1", "--reviewer", REVIEWER)
        sh("git", "config", "rerere.enabled", "true", cwd=self.work)
        sh("git", "config", "rerere.autoupdate", "true", cwd=self.work)
        record = self.base / "record"
        sh("git", "worktree", "add", "-q", "--detach", str(record), "origin/main", cwd=self.work)
        conflict = self.git_raw("cherry-pick", sha, cwd=record)
        self.assertNotEqual(conflict.returncode, 0, conflict.stdout + conflict.stderr)
        (record / "a.txt").write_text("human\n")
        sh("git", "rerere", cwd=record)
        sh("git", "add", "a.txt", cwd=record)
        sh("git", "cherry-pick", "--abort", cwd=record)
        replay = self.git_raw("cherry-pick", sha, cwd=record)
        detail = replay.stdout + replay.stderr
        self.assertNotEqual(replay.returncode, 0, detail)
        self.assertIn("CONFLICT", detail)
        self.assertIn("could not apply", detail)
        self.assertEqual(self.git_raw("status", "--porcelain", cwd=record).stdout, "")
        self.assertEqual(self.git_raw("ls-files", "-u", cwd=record).stdout, "")
        sh("git", "cherry-pick", "--abort", cwd=record)
        self.assertEqual(self.land("land"), "bounced E1 (r/D1): conflict with trunk")
        status = self.land("status", "E1")
        self.assertIn("E1 bounced", status)
        self.assertIn("conflict with trunk", status)
        self.assertNotIn("already in trunk", status)
        self.assertEqual(self.land("lease", "list").split(" until ")[0], "L1 active r/D1")
        self.assertEqual(self.origin_log(), ["human", "init"])
        self.assertEqual(sh("git", "show", "main:a.txt", cwd=self.base / "origin.git"), "human")

    def test_landing_uses_the_pinned_sha_even_when_the_branch_moves_on(self):
        self.init()
        reviewed = self.worker("w1", {"a.txt": "reviewed\n"})
        self.land("lease", "claim", "--holder", "r/D1", "--paths", "a.txt")
        self.land("submit", "--holder", "r/D1", "--branch", "w1", "--sha", reviewed, "--lease", "L1", "--reviewer", REVIEWER)
        (self.base / "w1/a.txt").write_text("unreviewed\n")
        self.commit("sneaky", cwd=self.base / "w1")
        self.land("land")
        self.assertEqual(self.origin_log(), ["w1", "init"])
        self.assertEqual(sh("git", "show", "main:a.txt", cwd=self.base / "origin.git"), "reviewed")

    def test_trunk_moved_by_a_human_is_rebased_onto_and_a_rewind_pauses_the_queue(self):
        self.init()
        sha = self.worker("w1", {"a.txt": "agent\n"})
        (self.work / "b.txt").write_text("human\n")
        self.commit("human")
        sh("git", "push", "-q", "origin", "main", cwd=self.work)
        self.land("lease", "claim", "--holder", "r/D1", "--paths", "a.txt")
        self.land("submit", "--holder", "r/D1", "--branch", "w1", "--sha", sha, "--lease", "L1", "--reviewer", REVIEWER)
        self.assertEqual(self.land("land"), "landed E1 (r/D1)")
        self.assertEqual(self.origin_log(), ["w1", "human", "init"])
        sh("git", "push", "-q", "--force", "origin", "HEAD~1:main", cwd=self.work)
        other = self.worker("w2", {"b.txt": "agent2\n"})
        self.land("lease", "claim", "--holder", "r/D2", "--paths", "b.txt")
        self.land("submit", "--holder", "r/D2", "--branch", "w2", "--sha", other, "--lease", "L2", "--reviewer", REVIEWER)
        self.assertIn("queue paused: trunk no longer contains the last landed commit", self.land("land"))
        self.assertIn("queue paused", self.land("land"))
        self.land("resume")
        self.assertEqual(self.land("land"), "landed E2 (r/D2)")

    def test_a_patch_already_on_trunk_lands_without_replaying_it(self):
        self.init()
        sha = self.worker("w1", {"a.txt": "agent\n"})
        (self.work / "a.txt").write_text("agent\n")
        self.commit("human")
        sh("git", "push", "-q", "origin", "main", cwd=self.work)
        self.land("lease", "claim", "--holder", "r/D1", "--paths", "a.txt")
        self.land("submit", "--holder", "r/D1", "--branch", "w1", "--sha", sha, "--lease", "L1", "--reviewer", REVIEWER)
        self.assertEqual(self.land("land"), "landed E1 (r/D1)")
        self.assertEqual(self.origin_log(), ["human", "init"])
        self.assertIn("already in trunk", self.land("status", "E1"))

    def test_a_commit_that_started_empty_pauses_instead_of_landing(self):
        self.init()
        path = self.base / "w1"
        sh("git", "worktree", "add", "-q", "-b", "w1", str(path), "origin/main", cwd=self.work)
        (path / "a.txt").write_text("agent\n")
        self.commit("w1", cwd=path)
        sh("git", "commit", "-q", "--allow-empty", "-m", "empty", cwd=path)
        sha = sh("git", "rev-parse", "HEAD", cwd=path)
        self.land("lease", "claim", "--holder", "r/D1", "--paths", "a.txt")
        self.land("submit", "--holder", "r/D1", "--branch", "w1", "--sha", sha, "--lease", "L1", "--reviewer", REVIEWER)
        paused = self.land("land")
        self.assertIn("queue paused", paused)
        self.assertIn("cherry-pick failed", paused)
        self.assertNotIn("landed", paused)
        self.assertEqual(self.origin_log(), ["init"])

    def test_a_crash_after_the_push_is_recovered_as_landed_without_pushing_again(self):
        self.init()
        sha = self.worker("w1", {"a.txt": "agent\n"})
        self.land("lease", "claim", "--holder", "r/D1", "--paths", "a.txt")
        self.land("submit", "--holder", "r/D1", "--branch", "w1", "--sha", sha, "--lease", "L1", "--reviewer", REVIEWER)
        store = land.Store.for_repo(self.work)
        real = land.publish

        def publish_then_crash(*args):
            real(*args)
            raise KeyboardInterrupt

        with mock.patch.object(land, "publish", publish_then_crash), self.assertRaises(KeyboardInterrupt):
            land.land(store)
        self.assertEqual(self.land("status", "E1").split(" (")[0], "E1 landing")
        self.assertEqual(self.land("land"), "nothing to land")
        self.assertIn("E1 landed", self.land("status", "E1"))
        self.assertIn("recovered after an interrupted run", self.land("status", "E1"))
        self.assertEqual(self.origin_log(), ["w1", "init"])

    def subprocesses_during_land(self):
        """Commands this land run starts while a write transaction is open."""
        store = land.Store.for_repo(self.work)
        depth = {"n": 0}
        hits = []
        original_tx = land.Store.tx
        original_run = land.subprocess.run
        original_popen = land.subprocess.Popen

        @contextlib.contextmanager
        def watching_tx(store_self):
            depth["n"] += 1
            try:
                with original_tx(store_self) as db:
                    yield db
            finally:
                depth["n"] -= 1

        def record(command):
            if isinstance(command, (list, tuple)):
                hits.append(" ".join(str(part) for part in command))
            else:
                hits.append(str(command))

        def watching_run(*args, **kwargs):
            if depth["n"]:
                record(args[0] if args else kwargs.get("args"))
            return original_run(*args, **kwargs)

        def watching_popen(*args, **kwargs):
            # subprocess.run calls Popen for the same command. Record a direct Popen only.
            if depth["n"] and inspect.stack()[1].function != "run":
                record(args[0] if args else kwargs.get("args"))
            return original_popen(*args, **kwargs)

        with mock.patch.object(land.Store, "tx", watching_tx), \
             mock.patch.object(land.subprocess, "run", watching_run), \
             mock.patch.object(land.subprocess, "Popen", watching_popen):
            land.land(store)
        return hits

    def test_a_land_run_runs_no_subprocess_inside_a_write_transaction(self):
        self.init()
        self.queue_one()
        hits = self.subprocesses_during_land()
        self.assertEqual(self.origin_log()[0], "w1")
        self.assertIn("E1 landed", self.land("status", "E1"))
        self.land("mode", "human")
        sh("git", "fetch", "-q", "origin", cwd=self.work)
        sh("git", "merge", "-q", "--ff-only", "origin/main", cwd=self.work)
        sha = self.worker("w2", {"b.txt": "same\n"})
        (self.work / "b.txt").write_text("same\n")
        self.commit("human")
        sh("git", "push", "-q", "origin", "main", cwd=self.work)
        lease = self.land("lease", "claim", "--holder", "r/D2", "--paths", "b.txt")
        self.land("submit", "--holder", "r/D2", "--branch", "w2", "--sha", sha, "--lease", lease, "--reviewer", REVIEWER)
        with self.fake_gh():
            hits += self.subprocesses_during_land()
        self.assertIn("already in trunk", self.land("status", "E2"))
        self.assertEqual(hits, [])

    def test_a_held_queue_lock_reports_busy(self):
        self.init()
        store = land.Store.for_repo(self.work)
        import fcntl
        with open(store.dir / ".queue.lock", "a") as handle:
            fcntl.flock(handle, fcntl.LOCK_EX)
            self.assertIn("queue busy", self.land("land"))

    def test_local_mode_lands_on_a_queue_owned_ref_and_never_moves_a_branch(self):
        self.init(mode="local", trunk="perf", base="main")
        sha = self.worker("w1", {"a.txt": "fast\n"}, base="main")
        self.land("lease", "claim", "--holder", "perf/D1", "--paths", "a.txt")
        self.land("submit", "--holder", "perf/D1", "--branch", "w1", "--sha", sha, "--lease", "L1", "--reviewer", REVIEWER)
        main_before = sh("git", "rev-parse", "main", cwd=self.work)
        self.assertEqual(self.land("land"), "landed E1 (perf/D1)")
        self.assertEqual(sh("git", "show", "refs/landing/perf:a.txt", cwd=self.work), "fast")
        self.assertEqual(sh("git", "rev-parse", "main", cwd=self.work), main_before)
        self.assertEqual(sh("git", "status", "--porcelain", cwd=self.work), "")

    def fake_gh(self):
        """A gh stand-in. PR url lives in pr-url, the poll answer in pr-state. crash-on-create kills land after creating."""
        fake = self.base / "gh"
        fake.write_text(f"""#!{sys.executable}
import json, os, signal, subprocess, sys
from pathlib import Path
base = Path({str(self.base)!r})
args = sys.argv[1:]
with open(base / "gh-calls", "a") as calls:
    print(" ".join(args), file=calls)
if args[:2] == ["repo", "view"]:
    if (base / "repo-view-fails").exists():
        print("repo view failed", file=sys.stderr)
        sys.exit(1)
    requested = ""
    if "--json" in args:
        requested = args[args.index("--json") + 1]
    if "mergeCommitAllowed" in requested.split(","):
        path = base / "repo-merge.json"
        if path.exists():
            print(path.read_text().strip())
        else:
            print(json.dumps({{"mergeCommitAllowed": True, "squashMergeAllowed": True, "rebaseMergeAllowed": True}}))
        sys.exit(0)
    print(json.dumps({{"nameWithOwner": "o/r"}}))
    sys.exit(0)
if args[:1] == ["api"] and any("/branches/" in arg for arg in args):
    endpoint = next(arg for arg in args if "/branches/" in arg)
    branch = endpoint.split("/branches/", 1)[1]
    if (base / "forge-says-missing").exists():
        print("branch-status 404", file=open(base / "gh-calls", "a"))
        print("HTTP/2.0 404 Not Found")
        print()
        print(json.dumps({{"message": "Branch not found", "status": "404"}}))
        sys.exit(1)
    if (base / "branch-query-fails").exists():
        print("branch-status 500", file=open(base / "gh-calls", "a"))
        print("HTTP/2.0 500 Internal Server Error")
        print()
        print(json.dumps({{"message": "unavailable"}}))
        sys.exit(1)
    ref = "refs/heads/" + branch
    exists = subprocess.run(
        ["git", "--git-dir", str(base / "origin.git"), "rev-parse", "--verify", "--quiet", ref],
        capture_output=True).returncode == 0
    status = "200" if exists else "404"
    print("branch-status " + status, file=open(base / "gh-calls", "a"))
    print("HTTP/2.0 " + ("200 OK" if exists else "404 Not Found"))
    print()
    if exists:
        print(json.dumps({{"name": branch}}))
        sys.exit(0)
    print(json.dumps({{"message": "Branch not found", "status": "404"}}))
    sys.exit(1)
if args[:2] == ["pr", "create"]:
    if "--head" in args:
        (base / "pr-head").write_text(args[args.index("--head") + 1])
    number = "9"
    seq = base / "pr-seq"
    if seq.exists():
        number = seq.read_text().strip() or "9"
        seq.write_text(str(int(number) + 1) + "\\n")
    url = "https://github.com/o/r/pull/" + number
    (base / "pr-url").write_text(url)
    if (base / "crash-on-create").exists():
        (base / "crash-on-create").unlink()
        os.kill(os.getppid(), signal.SIGKILL)
    print(url)
elif args[:2] == ["pr", "merge"]:
    print(" ".join(args), file=open(base / "merge-calls", "a"))
    if "--disable-auto" in args:
        if (base / "disable-auto-fails").exists():
            print((base / "disable-auto-fails").read_text() or "API unavailable", file=sys.stderr)
            sys.exit(1)
        sys.exit(0)
    if (base / "merge-refused").exists():
        print("GraphQL: At least 1 approving review is required by reviewers with write access.", file=sys.stderr)
        sys.exit(1)
    if "--auto" in args and (base / "auto-merge-disabled").exists():
        print("GraphQL: Auto merge is not allowed for this repository (enablePullRequestAutoMerge)", file=sys.stderr)
        sys.exit(1)
    if "--auto" not in args and (base / "plain-merge-fails").exists():
        print((base / "plain-merge-fails").read_text().strip() or "merge conflict", file=sys.stderr)
        sys.exit(1)
    if "--auto" in args and not (base / "auto-merges-immediately").exists():
        if not (base / "required-checks").exists():
            print("GraphQL: Pull request is in clean status (enablePullRequestAutoMerge)", file=sys.stderr)
            sys.exit(1)
        sys.exit(0)
    checks_now = (base / "checks").read_text().strip() if (base / "checks").exists() else ""
    if (base / "policy-until-passed").exists() and checks_now != "passed":
        print("X Pull request o/r#9 is not mergeable: the base branch policy prohibits the merge.", file=sys.stderr)
        sys.exit(1)
    import subprocess
    branch = (base / "pr-head").read_text().strip() if (base / "pr-head").exists() else ""
    if not branch:
        branch = "landing/e1"
    head = subprocess.run(["git", "--git-dir", str(base / "origin.git"), "rev-parse", "refs/heads/" + branch],
                          capture_output=True, text=True).stdout.strip()
    (base / "pr-state").write_text(f"MERGED {{head}} 1111111111111111111111111111111111111111")
    if (base / "merge-state-lags").exists():
        (base / "pr-state-after").write_text((base / "pr-state").read_text())
        (base / "pr-state").write_text(f"OPEN {{head}} ")
elif args[:2] == ["pr", "view"] and any("statusCheckRollup" in arg for arg in args):
    if (base / "checks-query-fails").exists():
        print("API unavailable", file=sys.stderr)
        sys.exit(1)
    if (base / "pr-checks.json").exists():
        doc = (base / "pr-checks.json").read_text()
    else:
        kind = (base / "checks").read_text().strip() if (base / "checks").exists() else ""
        review = "REVIEW_REQUIRED" if (base / "merge-refused").exists() else "APPROVED"
        rollup = {{
            "pending": [{{"name": "test", "status": "IN_PROGRESS"}}],
            "failed": [{{"name": "test (3.12)", "status": "COMPLETED", "conclusion": "FAILURE"}}],
            "passed": [
                {{"name": "test (3.10)", "status": "COMPLETED", "conclusion": "SUCCESS"}},
                {{"name": "test (3.12)", "status": "COMPLETED", "conclusion": "SUCCESS"}},
            ],
        }}.get(kind, [])
        doc = json.dumps({{"reviewDecision": review, "statusCheckRollup": rollup}})
    payload = json.loads(doc)
    if "autoMergeRequest" not in payload:
        marker = base / "auto-merge-request.json"
        payload["autoMergeRequest"] = json.loads(marker.read_text()) if marker.exists() else None
        doc = json.dumps(payload)
    query = args[args.index("-q") + 1]
    ran = subprocess.run(["jq", "-r", query], input=doc, capture_output=True, text=True)
    if ran.returncode != 0:
        print(ran.stderr, file=sys.stderr)
        sys.exit(1)
    sys.stdout.write(ran.stdout if ran.stdout.endswith("\\n") else ran.stdout + "\\n")
    flip = base / "checks-flip"
    if flip.exists():
        (base / "checks").write_text(flip.read_text())
        flip.unlink()
        saved = base / "pr-checks.json"
        if saved.exists():
            saved.unlink()
elif args[:2] == ["pr", "view"] and "--json" in args and args[args.index("--json") + 1] == "headRefName":
    head = (base / "pr-head").read_text().strip() if (base / "pr-head").exists() else ""
    print(head or "landing/e1")
elif args[:2] == ["pr", "view"] and "--json" in args and "url" in args[args.index("--json") + 1].split(","):
    if not (base / "pr-url").exists():
        sys.exit(1)
    url = (base / "pr-url").read_text().strip()
    fields = args[args.index("--json") + 1].split(",")
    target = args[2] if len(args) > 2 and not args[2].startswith("-") else ""
    state = "OPEN"
    head_oid = ""
    prior = None
    if target.startswith("landing/q"):
        prior = base / "legacy-pr-state"
    elif target.startswith("landing/e"):
        prior = base / "entry-pr-state"
    if prior is not None and prior.exists():
        parts = prior.read_text().strip().split()
        if parts:
            state = parts[0] or "OPEN"
        if len(parts) > 1:
            head_oid = parts[1]
    doc = {{"url": url}} if "url" in fields else {{}}
    if "state" in fields:
        doc["state"] = state
    if "headRefOid" in fields:
        doc["headRefOid"] = head_oid
    if "-q" not in args:
        print(url)
    else:
        query = args[args.index("-q") + 1]
        ran = subprocess.run(["jq", "-r", query], input=json.dumps(doc), capture_output=True, text=True)
        if ran.returncode != 0:
            print(ran.stderr, file=sys.stderr)
            sys.exit(1)
        sys.stdout.write(ran.stdout if ran.stdout.endswith("\\n") else ran.stdout + "\\n")
elif args[:2] == ["pr", "view"]:
    print((base / "pr-state").read_text() if (base / "pr-state").exists() else "OPEN")
    nxt = base / "pr-state-after"
    if nxt.exists():
        (base / "pr-state").write_text(nxt.read_text())
        nxt.unlink()
""")
        fake.chmod(0o755)
        return mock.patch.dict(os.environ, {"LAND_GH": str(fake)})

    def pause_repo_view(self):
        """Block gh repo view until repo-view-release appears. The waiting file is the barrier."""
        real = os.environ["LAND_GH"]
        wrapper = self.base / "gh-pause-view"
        wrapper.write_text(
            f"""#!{sys.executable}
import os, sys, time
from pathlib import Path
base = Path({str(self.base)!r})
real = {real!r}
args = sys.argv[1:]
if args[:2] == ["repo", "view"] and (base / "pause-repo-view").exists():
    (base / "repo-view-waiting").touch()
    end = time.monotonic() + 30
    while not (base / "repo-view-release").exists() and time.monotonic() < end:
        time.sleep(0.01)
os.execv(real, [real, *args])
"""
        )
        wrapper.chmod(0o755)
        os.environ["LAND_GH"] = str(wrapper)

    def allow_methods(self, merge=False, squash=False, rebase=False):
        (self.base / "repo-merge.json").write_text(json.dumps({
            "mergeCommitAllowed": merge,
            "squashMergeAllowed": squash,
            "rebaseMergeAllowed": rebase,
        }))

    def stored_merge_method(self):
        return land.Store.for_repo(self.work).contract["mergeMethod"]

    def arm_auto_merge(self):
        (self.base / "auto-merge-request.json").write_text(
            '{"authorEmail":null,"commitBody":null,"commitHeadline":null,'
            '"mergeMethod":"SQUASH","enabledAt":"2026-10-05T02:54:42Z",'
            '"enabledBy":{"login":"octocat","id":"U_1","name":"Octo Cat"}}'
        )

    def queue_one(self, path="a.txt", text="agent\n", name="w1", holder="r/D1"):
        sha = self.worker(name, {path: text})
        lease = self.land("lease", "claim", "--holder", holder, "--paths", path)
        return self.land("submit", "--holder", holder, "--branch", name, "--sha", sha, "--lease", lease, "--reviewer", REVIEWER)

    def base_land_script(self):
        """Pre-rename land.py. The fixture replaces git show, which fails in a shallow clone."""
        path = self.base / "land-3678d11.py"
        source = ROOT / "tests/fixtures/land_before_e_rename.py"
        path.write_bytes(source.read_bytes())
        return path

    def use_land_script(self, path):
        global SCRIPT
        previous = SCRIPT
        SCRIPT = path
        return previous

    def restore_land_script(self, previous):
        global SCRIPT
        SCRIPT = previous

    def require_pr_head_on_origin(self):
        """GitHub rejects pr create when the head branch is not on the remote."""
        real = os.environ["LAND_GH"]
        wrapper = self.base / "gh-head"
        wrapper.write_text(
            f"""#!{sys.executable}
import os, subprocess, sys
from pathlib import Path
base = Path({str(self.base)!r})
real = {real!r}
args = sys.argv[1:]
if args[:2] == ["pr", "create"]:
    if (base / "pr-create-fails").exists():
        print("gh: not authenticated", file=sys.stderr)
        sys.exit(1)
    head = args[args.index("--head") + 1]
    present = subprocess.run(
        ["git", "--git-dir", str(base / "origin.git"), "rev-parse", "--verify", "--quiet", "refs/heads/" + head],
        capture_output=True).returncode == 0
    if not present:
        print("pull request create failed: GraphQL: Head ref must be a branch (createPullRequest)", file=sys.stderr)
        sys.exit(1)
os.execv(real, [real, *args])
"""
        )
        wrapper.chmod(0o755)
        os.environ["LAND_GH"] = str(wrapper)

    def record_created_pr_branch(self):
        """A PR is visible to `gh pr view` only for the head `pr create` used."""
        real = os.environ["LAND_GH"]
        wrapper = self.base / "gh-branch"
        wrapper.write_text(
            f"""#!{sys.executable}
import os, sys
from pathlib import Path
base = Path({str(self.base)!r})
args = sys.argv[1:]
if args[:2] == ["pr", "create"] and "--head" in args:
    (base / "pr-head").write_text(args[args.index("--head") + 1])
def asks_url(argv):
    if "--json" not in argv:
        return False
    return "url" in argv[argv.index("--json") + 1].split(",")
if args[:2] == ["pr", "view"] and asks_url(args) and len(args) > 2 and args[2].startswith("landing/"):
    recorded = (base / "pr-head").read_text().strip() if (base / "pr-head").exists() else ""
    if recorded != args[2]:
        sys.exit(1)
os.execv({real!r}, [{real!r}, *args])
"""
        )
        wrapper.chmod(0o755)
        os.environ["LAND_GH"] = str(wrapper)

    def test_a_legacy_push_without_a_pr_opens_the_pr_on_landing_e(self):
        with self.fake_gh():
            self.require_pr_head_on_origin()
            previous = self.use_land_script(self.base_land_script())
            try:
                self.init(mode="human")
                self.queue_one()
                (self.base / "pr-create-fails").write_text("gh: not authenticated\n")
                paused = self.land("land")
                remote = self.base / "origin.git"
                candidate = sh("git", "rev-parse", "refs/heads/landing/q1", cwd=remote)
                self.assertFalse(self.ref_exists("refs/heads/landing/e1", remote))
                (self.base / "pr-create-fails").unlink()
                self.restore_land_script(previous)
                previous = None
                held = self.land("status", "E1")
                self.assertEqual(self.land("resume"), "queue resumed")
                opened = self.land("land")
            finally:
                if previous is not None:
                    self.restore_land_script(previous)
            self.assertIn("queue paused", paused)
            self.assertIn("awaiting-merge", held)
            self.assertNotIn("pull/9", held)
            self.assertNotIn("queue paused", opened)
            self.assertTrue(self.ref_exists("refs/heads/landing/e1", remote), opened)
            self.assertEqual(sh("git", "rev-parse", "refs/heads/landing/e1", cwd=remote), candidate)
            status = self.land("status", "E1")
            self.assertIn("awaiting-merge", status)
            self.assertIn("https://github.com/o/r/pull/9", status)
            self.assertNotIn("Paused", self.land("status"))

    def created_heads(self):
        calls = (self.base / "gh-calls").read_text().splitlines()
        return [line.split("--head ", 1)[1].split(" ", 1)[0]
                for line in calls if line.startswith("pr create ")]

    def crashed_landing_q_pr(self):
        """An older land.py opened the PR on landing/q<n> and died before storing the URL."""
        self.record_created_pr_branch()
        self.require_pr_head_on_origin()
        previous = self.use_land_script(self.base_land_script())
        try:
            self.init(mode="human")
            self.queue_one()
            (self.base / "crash-on-create").write_text("")
            crashed = subprocess.run(
                [sys.executable, str(SCRIPT), "--repo", str(self.work), "land"],
                capture_output=True, text=True, env=os.environ.copy())
            self.assertEqual(crashed.returncode, -9, crashed.stdout + crashed.stderr)
            self.restore_land_script(previous)
            previous = None
        finally:
            if previous is not None:
                self.restore_land_script(previous)
        return sh("git", "rev-parse", "refs/heads/landing/q1", cwd=self.base / "origin.git")

    def pr_views_of_landing_q(self):
        calls = (self.base / "gh-calls").read_text().splitlines()
        return [line for line in calls if line.startswith("pr view landing/q")]

    def test_a_closed_pr_on_landing_q_is_ignored(self):
        self.ignore_non_open_pr_on_landing_q("CLOSED")

    def test_a_merged_pr_on_landing_q_is_ignored(self):
        self.ignore_non_open_pr_on_landing_q("MERGED")

    def ignore_non_open_pr_on_landing_q(self, state):
        """The queue opens its own pull request whatever state the one on landing/q<n> is in."""
        with self.fake_gh():
            (self.base / "pr-seq").write_text("9\n")
            candidate = self.crashed_landing_q_pr()
            (self.base / "legacy-pr-state").write_text(f"{state} 0123456789abcdef0123456789abcdef01234567\n")
            reported = self.land("land")
        self.assertEqual(self.created_heads(), ["landing/q1", "landing/e1"], reported)
        self.assertEqual(self.pr_views_of_landing_q(), [])
        remote = self.base / "origin.git"
        self.assertEqual(sh("git", "rev-parse", "refs/heads/landing/e1", cwd=remote), candidate)
        self.assertNotIn("adopted", reported)
        status = self.land("status", "E1")
        self.assertIn("awaiting-merge", status)
        self.assertIn("https://github.com/o/r/pull/10", status)
        self.assertNotIn("https://github.com/o/r/pull/9", status)

    def test_an_older_queues_open_pr_on_landing_q_stays_open_by_design_and_a_new_pr_on_landing_e_lands(self):
        """Intended. The queue never reads, adopts, or deletes landing/q<n>. The old branch and PR are closed by hand."""
        with self.fake_gh():
            (self.base / "pr-seq").write_text("9\n")
            candidate = self.crashed_landing_q_pr()
            remote = self.base / "origin.git"
            opened = self.land("land")
            self.assertEqual(opened, "opened PRs for E1 (r/D1) https://github.com/o/r/pull/10")
            self.assertEqual(self.created_heads(), ["landing/q1", "landing/e1"])
            self.assertEqual(sh("git", "rev-parse", "refs/heads/landing/e1", cwd=remote), candidate)
            self.assertEqual(sh("git", "rev-parse", "refs/heads/landing/q1", cwd=remote), candidate)
            (self.base / "pr-state").write_text(f"MERGED {candidate} abc123")
            self.assertEqual(self.land("land"), "landed E1 (r/D1)")
            self.assertEqual(self.pr_views_of_landing_q(), [])
            self.assertEqual(sh("git", "rev-parse", "refs/heads/landing/q1", cwd=remote), candidate)
            self.assertFalse(self.ref_exists("refs/heads/landing/e1", remote))
            self.assertIn("landed as abc123", self.land("status", "E1"))
            self.assertEqual(self.land("lease", "list"), "no leases held")

    def open_pr_on_landing_q_with_the_url_stored(self, remote_is_github):
        """An older queue opened the PR on landing/q1 and stored its URL. landing/e1 was never created."""
        if not remote_is_github:
            sh("git", "remote", "set-url", "origin", str(self.base / "origin.git"), cwd=self.work)
        previous = self.use_land_script(self.base_land_script())
        try:
            self.init(mode="human")
            self.queue_one()
            opened = self.land("land")
        finally:
            self.restore_land_script(previous)
        remote = self.base / "origin.git"
        self.assertIn("https://github.com/o/r/pull/9", opened)
        self.assertEqual((self.base / "pr-head").read_text().strip(), "landing/q1")
        self.assertFalse(self.ref_exists("refs/heads/landing/e1", remote))
        return sh("git", "rev-parse", "refs/heads/landing/q1", cwd=remote)

    def test_a_merged_pr_stored_on_landing_q_lands_when_the_remote_is_not_github(self):
        with self.fake_gh():
            candidate = self.open_pr_on_landing_q_with_the_url_stored(remote_is_github=False)
            remote = self.base / "origin.git"
            (self.base / "pr-state").write_text(f"MERGED {candidate} abc123")
            self.assertEqual(self.land("land"), "landed E1 (r/D1)")
            self.assertEqual(sh("git", "rev-parse", "refs/heads/landing/q1", cwd=remote), candidate)
            self.assertFalse(self.ref_exists("refs/heads/landing/e1", remote))
            self.assertIn("landed as abc123", self.land("status", "E1"))
            self.assertEqual(self.land("lease", "list"), "no leases held")
            self.assertEqual(self.created_heads(), ["landing/q1"])

    def test_a_merged_pr_stored_on_landing_q_lands_when_the_remote_is_github(self):
        with self.fake_gh():
            candidate = self.open_pr_on_landing_q_with_the_url_stored(remote_is_github=True)
            remote = self.base / "origin.git"
            (self.base / "pr-state").write_text(f"MERGED {candidate} abc123")
            self.assertEqual(self.land("land"), "landed E1 (r/D1)")
            self.assertEqual(sh("git", "rev-parse", "refs/heads/landing/q1", cwd=remote), candidate)
            self.assertIn("landed as abc123", self.land("status", "E1"))
            self.assertEqual(self.land("lease", "list"), "no leases held")

    def hide_a_landing_e1_the_older_queue_never_made(self, candidate):
        remote = self.base / "origin.git"
        sh("git", "update-ref", "refs/heads/landing/e1", candidate, cwd=remote)
        sh("git", "config", "receive.hideRefs", "refs/heads/landing/e1", cwd=remote)
        (self.base / "pr-state").write_text(f"MERGED {candidate} abc123")
        return remote

    def test_a_merged_pr_stored_on_landing_q_waits_when_the_forge_says_a_hidden_landing_e_exists(self):
        with self.fake_gh():
            candidate = self.open_pr_on_landing_q_with_the_url_stored(remote_is_github=True)
            remote = self.hide_a_landing_e1_the_older_queue_never_made(candidate)
            deletion = self.git_raw("push", "--no-follow-tags", "origin", "--delete", "landing/e1", cwd=self.work)
            self.assertIn("remote ref does not exist", deletion.stderr)
            self.assertEqual(self.land("land"), "nothing to land")
            self.assertTrue(self.ref_exists("refs/heads/landing/e1", remote))
            self.assertIn("awaiting-merge", self.land("status", "E1"))
            self.assertTrue(self.land("lease", "list").startswith("L1 submitted"))
            self.assertIn("branch-status 200", (self.base / "gh-calls").read_text())

    def test_accepted_limit_a_hidden_landing_e_is_left_in_place_and_the_entry_settles_when_the_remote_is_not_github(self):
        """Intended. With no forge to ask, a hidden branch looks missing, and waiting would never end."""
        with self.fake_gh():
            candidate = self.open_pr_on_landing_q_with_the_url_stored(remote_is_github=False)
            remote = self.hide_a_landing_e1_the_older_queue_never_made(candidate)
            self.assertEqual(self.land("land"), "landed E1 (r/D1)")
            self.assertTrue(self.ref_exists("refs/heads/landing/e1", remote))
            self.assertEqual(self.land("lease", "list"), "no leases held")
            self.assertNotIn("branch-status", (self.base / "gh-calls").read_text())

    def test_a_pr_stored_on_landing_q_that_merged_at_another_head_bounces_when_the_remote_is_not_github(self):
        with self.fake_gh():
            candidate = self.open_pr_on_landing_q_with_the_url_stored(remote_is_github=False)
            other = "0123456789abcdef0123456789abcdef01234567"
            (self.base / "pr-state").write_text(f"MERGED {other} abc123")
            settled = self.land("land")
            self.assertTrue(settled.startswith("bounced E1 (r/D1): merged at abc123 with head 0123456789ab"), settled)
            self.assertEqual(sh("git", "rev-parse", "refs/heads/landing/q1", cwd=self.base / "origin.git"), candidate)
            self.assertIn("review what reached trunk", self.land("status", "E1"))

    def test_a_pr_stored_on_landing_q_that_closed_bounces_when_the_remote_is_not_github(self):
        with self.fake_gh():
            candidate = self.open_pr_on_landing_q_with_the_url_stored(remote_is_github=False)
            (self.base / "pr-state").write_text(f"CLOSED {candidate}")
            self.assertEqual(self.land("land"), "bounced E1 (r/D1): PR closed without merging")
            self.assertEqual(sh("git", "rev-parse", "refs/heads/landing/q1", cwd=self.base / "origin.git"), candidate)
            self.assertTrue(self.land("lease", "list").startswith("L1 active"))

    def test_a_merged_pr_on_landing_e_waits_when_git_says_it_is_absent_and_the_remote_is_not_github(self):
        """The PR head is landing/e1, so git's absent line alone does not settle the entry."""
        with self.fake_gh():
            sh("git", "remote", "set-url", "origin", str(self.base / "origin.git"), cwd=self.work)
            self.init(mode="human")
            self.queue_one()
            self.assertEqual(self.land("land"), "opened PRs for E1 (r/D1) https://github.com/o/r/pull/9")
            remote = self.base / "origin.git"
            candidate = sh("git", "rev-parse", "refs/heads/landing/e1", cwd=remote)
            (self.base / "pr-state").write_text(f"MERGED {candidate} abc123")
            sh("git", "update-ref", "-d", "refs/heads/landing/e1", cwd=remote)
            self.assertEqual(self.land("land"), "nothing to land")
            self.assertIn("awaiting-merge", self.land("status", "E1"))
            self.assertTrue(self.land("lease", "list").startswith("L1 submitted"))

    def test_an_older_queues_open_pr_on_landing_q_stays_open_by_design_and_a_closed_pr_on_landing_e_bounces(self):
        """Intended. The old branch and its PR stay when the new PR on landing/e<n> bounces."""
        with self.fake_gh():
            (self.base / "pr-seq").write_text("9\n")
            candidate = self.crashed_landing_q_pr()
            remote = self.base / "origin.git"
            self.assertEqual(self.land("land"), "opened PRs for E1 (r/D1) https://github.com/o/r/pull/10")
            (self.base / "pr-state").write_text(f"CLOSED {candidate}")
            self.assertEqual(self.land("land"), "bounced E1 (r/D1): PR closed without merging")
            self.assertEqual(self.created_heads(), ["landing/q1", "landing/e1"])
            self.assertEqual(self.pr_views_of_landing_q(), [])
            self.assertEqual(sh("git", "rev-parse", "refs/heads/landing/q1", cwd=remote), candidate)
            self.assertIn("PR closed without merging", self.land("status", "E1"))
            self.assertTrue(self.land("lease", "list").startswith("L1 active"))

    def test_a_merged_pr_on_landing_e_at_another_head_is_not_adopted(self):
        """A fresh contract opens its own PR when landing/e1 is an earlier contract's merged PR."""
        with self.fake_gh():
            self.record_created_pr_branch()
            self.require_pr_head_on_origin()
            self.init(mode="human")
            other = "0123456789abcdef0123456789abcdef01234567"
            (self.base / "pr-url").write_text("https://github.com/o/r/pull/9\n")
            (self.base / "pr-head").write_text("landing/e1")
            (self.base / "pr-seq").write_text("10\n")
            (self.base / "entry-pr-state").write_text(f"MERGED {other}\n")
            self.queue_one()
            reported = self.land("land")
        self.assertEqual(self.created_heads(), ["landing/e1"], reported)
        self.assertNotIn("pull/9", reported)
        status = self.land("status", "E1")
        self.assertIn("awaiting-merge", status)
        self.assertIn("https://github.com/o/r/pull/10", status)
        self.assertNotIn("https://github.com/o/r/pull/9", status)
        remote = self.base / "origin.git"
        self.assertNotEqual(sh("git", "rev-parse", "refs/heads/landing/e1", cwd=remote), other)

    def test_human_mode_opens_a_pr_and_marks_landed_when_it_merges(self):
        with self.fake_gh():
            self.init(mode="human")
            self.queue_one()
            self.assertEqual(self.land("land"), "opened PRs for E1 (r/D1) https://github.com/o/r/pull/9")
            candidate = sh("git", "rev-parse", "landing/e1", cwd=self.base / "origin.git")
            self.assertTrue(self.ref_exists("refs/remotes/origin/landing/e1", self.work))
            (self.base / "pr-state").write_text(f"OPEN {candidate} ")
            self.assertEqual(self.land("land"), "nothing to land")
            (self.base / "pr-state").write_text(f"MERGED {candidate} abc123")
            self.assertEqual(self.land("land"), "landed E1 (r/D1)")
            self.assertFalse(self.ref_exists("refs/heads/landing/e1", self.base / "origin.git"))
            self.assertFalse(self.ref_exists("refs/remotes/origin/landing/e1", self.work))
            self.assertEqual(self.land("lease", "list"), "no leases held")

    def leave_awaiting_merge_without_a_pr(self):
        """Push landing/e<n>, mark the entry awaiting merge, and die before gh pr create."""
        store = land.Store.for_repo(self.work)
        with mock.patch.object(land, "ensure_pr", side_effect=KeyboardInterrupt):
            with self.assertRaises(KeyboardInterrupt):
                land.land(store)
        status = self.land("status", "E1")
        self.assertIn("awaiting-merge", status)
        self.assertNotIn("pull/", status)
        self.assertTrue(self.ref_exists("refs/heads/landing/e1", self.base / "origin.git"))

    def test_a_pr_opened_for_an_entry_left_without_one_is_reported(self):
        with self.fake_gh():
            self.init(mode="human")
            self.queue_one()
            self.leave_awaiting_merge_without_a_pr()
            reported = self.land("land")
            self.assertEqual(reported, "opened PRs for E1 (r/D1) https://github.com/o/r/pull/9")
            status = self.land("status", "E1")
            self.assertIn("awaiting-merge", status)
            self.assertIn("https://github.com/o/r/pull/9", status)
            self.assertEqual(self.land("land"), "nothing to land")

    def test_merge_mode_reports_a_pr_opened_for_an_entry_left_without_one(self):
        with self.fake_gh():
            (self.base / "checks").write_text("pending")
            self.init(mode="merge")
            self.queue_one()
            self.leave_awaiting_merge_without_a_pr()
            reported = self.land("land")
            self.assertEqual(
                reported,
                "opened PRs that merge when their checks pass: E1 (r/D1) https://github.com/o/r/pull/9")
            self.assertIn("waiting for required checks", self.land("status", "E1"))
            self.assertEqual(self.land("land"), "nothing to land")

    def test_merge_mode_merges_its_own_pr_when_there_are_no_checks_to_wait_for(self):
        with self.fake_gh():
            self.init(mode="merge")
            self.queue_one()
            self.assertIn("opened PRs that merge when their checks pass: E1 (r/D1)", self.land("land"))
            self.assertEqual(self.land("land"), "landed E1 (r/D1)")
            self.assertEqual((self.base / "merge-calls").read_text().splitlines(),
                             ["pr merge https://github.com/o/r/pull/9 --auto --merge", "pr merge https://github.com/o/r/pull/9 --merge"])
            self.assertFalse(self.ref_exists("refs/heads/landing/e1", self.base / "origin.git"))
            self.assertFalse(self.ref_exists("refs/remotes/origin/landing/e1", self.work))
            self.assertEqual(self.land("lease", "list"), "no leases held")

    def test_merge_mode_lets_github_merge_after_required_checks_and_asks_once(self):
        with self.fake_gh():
            (self.base / "required-checks").write_text("")
            self.init(mode="merge")
            self.queue_one()
            self.assertEqual(self.land("land"), "opened PRs that merge when their checks pass: E1 (r/D1) https://github.com/o/r/pull/9")
            self.assertEqual(self.land("land"), "nothing to land")
            candidate = sh("git", "rev-parse", "landing/e1", cwd=self.base / "origin.git")
            (self.base / "pr-state").write_text(f"MERGED {candidate} abc123")
            self.assertEqual(self.land("land"), "landed E1 (r/D1)")
            self.assertEqual(len((self.base / "merge-calls").read_text().splitlines()), 1)

    def test_merge_mode_waits_for_running_checks_then_merges(self):
        with self.fake_gh():
            (self.base / "checks").write_text("pending")
            self.init(mode="merge", merge_method="squash")
            self.queue_one()
            self.assertEqual(self.land("land"), "opened PRs that merge when their checks pass: E1 (r/D1) https://github.com/o/r/pull/9")
            self.assertIn("waiting for required checks", self.land("status", "E1"))
            self.assertTrue(self.ref_exists("refs/heads/landing/e1", self.base / "origin.git"))
            calls = (self.base / "merge-calls").read_text() if (self.base / "merge-calls").exists() else ""
            self.assertNotIn("pr merge https://github.com/o/r/pull/9 --squash", calls)
            self.assertEqual(self.land("land"), "nothing to land")
            (self.base / "checks").write_text("passed")
            self.assertEqual(self.land("land"), "landed E1 (r/D1)")
            self.assertIn("pr merge https://github.com/o/r/pull/9 --squash", (self.base / "merge-calls").read_text())
            self.assertFalse(self.ref_exists("refs/heads/landing/e1", self.base / "origin.git"))
            self.assertFalse(self.ref_exists("refs/remotes/origin/landing/e1", self.work))

    def test_merge_mode_bounces_a_pr_whose_required_checks_failed(self):
        with self.fake_gh():
            (self.base / "checks").write_text("failed")
            self.init(mode="merge")
            self.queue_one()
            self.assertEqual(self.land("land"), "bounced E1 (r/D1): required checks failed on https://github.com/o/r/pull/9: test (3.12)")
            self.assertTrue(self.land("lease", "list").startswith("L1 active r/D1"))

    def test_merge_mode_does_not_merge_when_auto_would_succeed_with_a_pending_check(self):
        with self.fake_gh():
            (self.base / "checks").write_text("pending")
            (self.base / "auto-merges-immediately").write_text("")
            self.init(mode="merge")
            self.queue_one()
            self.assertEqual(self.land("land"), "opened PRs that merge when their checks pass: E1 (r/D1) https://github.com/o/r/pull/9")
            self.assertIn("waiting for required checks", self.land("status", "E1"))
            self.assertTrue(self.land("lease", "list").startswith("L1 submitted"))
            self.assertFalse((self.base / "merge-calls").exists())
            self.assertTrue(self.ref_exists("refs/heads/landing/e1", self.base / "origin.git"))

    def test_merge_mode_bounces_when_a_check_fails_after_auto_merge_was_enabled(self):
        with self.fake_gh():
            (self.base / "required-checks").write_text("")
            self.init(mode="merge")
            self.queue_one()
            self.assertEqual(self.land("land"), "opened PRs that merge when their checks pass: E1 (r/D1) https://github.com/o/r/pull/9")
            self.assertEqual(self.land("land"), "nothing to land")
            self.assertIn("merge requested by the queue", self.land("status", "E1"))
            (self.base / "checks").write_text("failed")
            self.assertEqual(self.land("land"), "bounced E1 (r/D1): required checks failed on https://github.com/o/r/pull/9: test (3.12)")
            self.assertTrue(self.land("lease", "list").startswith("L1 active r/D1"))
            self.assertTrue(self.ref_exists("refs/heads/landing/e1", self.base / "origin.git"))

    def test_merge_mode_does_not_merge_when_the_check_query_fails(self):
        with self.fake_gh():
            (self.base / "checks").write_text("pending")
            (self.base / "checks-query-fails").write_text("")
            self.init(mode="merge")
            self.queue_one()
            out = self.land("land")
            self.assertIn("could not read checks", out)
            self.assertIn("queue paused", out)
            self.assertNotIn("landed E1", out)
            self.assertIn("awaiting-merge", self.land("status", "E1"))
            self.assertTrue(self.land("lease", "list").startswith("L1 submitted"))
            self.assertFalse((self.base / "merge-calls").exists())

    def absent_marker(self):
        return land.Store.for_repo(self.work).contract.get("absentDrain") or {}

    def test_merge_mode_does_not_merge_a_just_opened_pr_with_zero_posted_checks(self):
        with self.fake_gh():
            (self.base / "pr-checks.json").write_text('{"reviewDecision":"","statusCheckRollup":[]}')
            self.init(mode="merge")
            self.queue_one()
            opened = self.land("land")
            self.assertIn("opened PRs that merge when their checks pass: E1 (r/D1)", opened)
            self.assertNotIn("landed", opened)
            self.assertNotIn("queue paused", opened)
            self.assertIn("waiting for required checks", self.land("status", "E1"))
            self.assertNotIn("Paused", self.land("status"))
            self.assertTrue(self.land("lease", "list").startswith("L1 submitted"))
            self.assertTrue(self.ref_exists("refs/heads/landing/e1", self.base / "origin.git"))
            self.assertFalse((self.base / "merge-calls").exists())
            self.assertEqual(self.land("land"), "landed E1 (r/D1)")
            self.assertEqual((self.base / "merge-calls").read_text().splitlines(),
                             ["pr merge https://github.com/o/r/pull/9 --auto --merge",
                              "pr merge https://github.com/o/r/pull/9 --merge"])
            self.assertFalse(self.ref_exists("refs/heads/landing/e1", self.base / "origin.git"))
            self.assertEqual(self.land("lease", "list"), "no leases held")

    def test_merge_mode_lands_a_merged_pr_when_a_later_check_fails(self):
        with self.fake_gh():
            (self.base / "required-checks").write_text("")
            self.init(mode="merge")
            self.queue_one()
            self.land("land")
            self.assertEqual(self.land("land"), "nothing to land")
            self.assertIn("merge requested by the queue", self.land("status", "E1"))
            candidate = sh("git", "rev-parse", "landing/e1", cwd=self.base / "origin.git")
            (self.base / "pr-state").write_text(f"MERGED {candidate} abc123")
            (self.base / "checks").write_text("failed")
            self.assertEqual(self.land("land"), "landed E1 (r/D1)")
            self.assertFalse(self.ref_exists("refs/heads/landing/e1", self.base / "origin.git"))
            self.assertEqual(self.land("lease", "list"), "no leases held")
            self.assertIn("E1 landed", self.land("status", "E1"))

    def test_merge_mode_pauses_on_a_merge_conflict_when_auto_merge_is_disabled(self):
        with self.fake_gh():
            (self.base / "pr-checks.json").write_text('{"reviewDecision":"","statusCheckRollup":[]}')
            (self.base / "auto-merge-disabled").write_text("")
            (self.base / "plain-merge-fails").write_text("merge conflict")
            self.init(mode="merge")
            self.queue_one()
            opened = self.land("land")
            self.assertIn("opened PRs that merge when their checks pass: E1 (r/D1)", opened)
            self.assertNotIn("queue paused", opened)
            self.assertFalse((self.base / "merge-calls").exists())
            paused = self.land("land")
            self.assertIn("queue paused", paused)
            self.assertIn("merge conflict", paused)
            self.assertNotIn("landed", paused)
            self.assertIn("Paused", self.land("status"))
            self.assertIn("merge conflict", self.land("status"))
            calls = [
                "pr merge https://github.com/o/r/pull/9 --auto --merge",
                "pr merge https://github.com/o/r/pull/9 --merge",
            ]
            self.assertEqual((self.base / "merge-calls").read_text().splitlines(), calls)
            self.assertIn("queue paused", self.land("land"))
            self.assertEqual((self.base / "merge-calls").read_text().splitlines(), calls)

    def test_merge_mode_waits_when_auto_merge_is_disabled_and_policy_refuses(self):
        with self.fake_gh():
            (self.base / "pr-checks.json").write_text('{"reviewDecision":"","statusCheckRollup":[]}')
            (self.base / "auto-merge-disabled").write_text("")
            (self.base / "policy-until-passed").write_text("")
            self.init(mode="merge")
            self.queue_one()
            self.land("land")
            still = self.land("land")
            self.assertNotIn("queue paused", still)
            self.assertNotIn("landed", still)
            self.assertIn("waiting for required checks", self.land("status", "E1"))
            self.assertNotIn("Paused", self.land("status"))
            calls = (self.base / "merge-calls").read_text()
            self.assertIn("pr merge https://github.com/o/r/pull/9 --auto --merge", calls)
            self.assertIn("pr merge https://github.com/o/r/pull/9 --merge", calls)
            (self.base / "pr-checks.json").unlink()
            (self.base / "auto-merge-disabled").unlink()
            (self.base / "checks").write_text("passed")
            self.assertEqual(self.land("land"), "landed E1 (r/D1)")

    def test_merge_mode_waits_when_base_branch_policy_refuses_and_no_check_is_posted(self):
        with self.fake_gh():
            (self.base / "pr-checks.json").write_text('{"reviewDecision":"","statusCheckRollup":[]}')
            (self.base / "policy-until-passed").write_text("")
            self.init(mode="merge")
            self.queue_one()
            self.land("land")
            self.assertFalse((self.base / "auto-merge-disabled").exists())
            still_empty = self.land("land")
            self.assertNotIn("queue paused", still_empty)
            self.assertNotIn("landed", still_empty)
            self.assertIn("waiting for required checks", self.land("status", "E1"))
            (self.base / "pr-checks.json").unlink()
            (self.base / "checks").write_text("passed")
            self.assertEqual(self.land("land"), "landed E1 (r/D1)")

    def test_merge_mode_does_not_merge_when_a_pending_check_appears_between_reads(self):
        with self.fake_gh():
            (self.base / "pr-checks.json").write_text('{"reviewDecision":"APPROVED","statusCheckRollup":[]}')
            (self.base / "checks-flip").write_text("pending")
            self.init(mode="merge")
            self.queue_one()
            opened = self.land("land")
            self.assertNotIn("landed", opened)
            self.assertNotIn("queue paused", opened)
            self.assertFalse((self.base / "merge-calls").exists())
            self.assertIn("waiting for required checks", self.land("status", "E1"))
            self.assertTrue(self.land("lease", "list").startswith("L1 submitted"))

    def test_merge_mode_does_not_merge_when_a_failed_check_appears_between_reads(self):
        with self.fake_gh():
            (self.base / "pr-checks.json").write_text('{"reviewDecision":"APPROVED","statusCheckRollup":[]}')
            (self.base / "checks-flip").write_text("failed")
            self.arm_auto_merge()
            self.init(mode="merge")
            self.queue_one()
            opened = self.land("land")
            self.assertNotIn("landed", opened)
            self.assertEqual((self.base / "merge-calls").read_text().strip(),
                             "pr merge https://github.com/o/r/pull/9 --disable-auto")
            self.assertIn("bounced E1 (r/D1): required checks failed on https://github.com/o/r/pull/9: test (3.12)", opened)
            self.assertTrue(self.land("lease", "list").startswith("L1 active"))

    def test_merge_mode_drops_the_absent_marker_when_the_entry_lands(self):
        with self.fake_gh():
            (self.base / "pr-checks.json").write_text('{"reviewDecision":"","statusCheckRollup":[]}')
            self.init(mode="merge")
            self.queue_one()
            opened = self.land("land")
            self.assertIn("opened PRs that merge when their checks pass: E1 (r/D1)", opened)
            self.assertEqual(self.absent_marker(), {"1": 1})
            self.assertEqual(self.land("land"), "landed E1 (r/D1)")
            self.assertNotIn("1", self.absent_marker())

    def test_merge_mode_drops_the_absent_marker_when_the_entry_bounces(self):
        with self.fake_gh():
            (self.base / "pr-checks.json").write_text('{"reviewDecision":"","statusCheckRollup":[]}')
            self.init(mode="merge")
            self.queue_one()
            self.land("land")
            self.assertEqual(self.absent_marker(), {"1": 1})
            (self.base / "pr-checks.json").unlink()
            (self.base / "checks").write_text("failed")
            self.assertIn("bounced E1 (r/D1): required checks failed on https://github.com/o/r/pull/9: test (3.12)", self.land("land"))
            self.assertNotIn("1", self.absent_marker())
            self.assertTrue(self.land("lease", "list").startswith("L1 active"))

    def test_a_checked_out_queue_branch_is_named_when_land_cannot_delete_it(self):
        with self.fake_gh():
            self.init(mode="human")
            self.queue_one()
            self.land("land")
            candidate = sh("git", "rev-parse", "landing/e1", cwd=self.base / "origin.git")
            sh("git", "branch", "landing/e1", candidate, cwd=self.work)
            sh("git", "checkout", "-q", "landing/e1", cwd=self.work)
            (self.base / "pr-state").write_text(f"MERGED {candidate} abc123")
            out = self.land("land")
            self.assertIn("landed E1 (r/D1)", out)
            self.assertIn("left local landing/e1", out)
            self.assertTrue(self.ref_exists("refs/heads/landing/e1", self.work))
            self.assertFalse(self.ref_exists("refs/heads/landing/e1", self.base / "origin.git"))
            self.assertIn("E1 landed", self.land("status", "E1"))

    def test_merge_mode_lands_when_the_remote_deletes_the_queue_branch_during_push(self):
        with self.fake_gh():
            self.install_racing_branch_delete()
            self.init(mode="merge")
            self.queue_one()
            opened = self.land("land")
            self.assertIn("opened PRs that merge when their checks pass: E1 (r/D1)", opened)
            self.assertEqual(self.land("land"), "landed E1 (r/D1)")
            self.assertIn("refs/heads/landing/e1", (self.base / "race-deleted").read_text())
            self.assertEqual(self.land("lease", "list"), "no leases held")
            self.assertFalse(self.ref_exists("refs/heads/landing/e1", self.base / "origin.git"))
            self.assertFalse(self.ref_exists("refs/remotes/origin/landing/e1", self.work))
            self.assertIn("branch-status 404", (self.base / "gh-calls").read_text())

    def test_merge_mode_leaves_the_entry_when_the_queue_branch_delete_fails(self):
        with self.fake_gh():
            self.init(mode="merge")
            self.queue_one()
            self.land("land")
            sh("git", "config", "receive.denyDeletes", "true", cwd=self.base / "origin.git")
            self.assertEqual(self.land("land"), "nothing to land")
            self.assertIn("awaiting-merge", self.land("status", "E1"))
            self.assertIn("merge requested by the queue", self.land("status", "E1"))
            self.assertTrue(self.ref_exists("refs/heads/landing/e1", self.base / "origin.git"))
            self.assertIn("branch-status 200", (self.base / "gh-calls").read_text())
            sh("git", "config", "--unset", "receive.denyDeletes", cwd=self.base / "origin.git")
            self.assertEqual(self.land("land"), "landed E1 (r/D1)")
            self.assertEqual(self.land("lease", "list"), "no leases held")

    def test_merge_mode_leaves_the_entry_when_a_hidden_ref_refuses_deletion(self):
        with self.fake_gh():
            self.init(mode="merge")
            self.queue_one()
            self.land("land")
            remote = self.base / "origin.git"
            sh("git", "config", "receive.denyDeletes", "true", cwd=remote)
            sh("git", "config", "uploadpack.hideRefs", "refs/heads/landing/e1", cwd=remote)
            listed = subprocess.run(["git", "ls-remote", "origin", "refs/heads/landing/e1"],
                                    cwd=self.work, capture_output=True, text=True)
            self.assertEqual((listed.returncode, listed.stdout.strip()), (0, ""))
            self.assertEqual(self.land("land"), "nothing to land")
            self.assertTrue(self.ref_exists("refs/heads/landing/e1", remote))
            self.assertTrue(self.land("lease", "list").startswith("L1 submitted"))
            self.assertIn("awaiting-merge", self.land("status", "E1"))
            self.assertIn("branch-status 200", (self.base / "gh-calls").read_text())

    def test_merge_mode_leaves_the_entry_when_a_hidden_ref_is_locked(self):
        with self.fake_gh():
            self.init(mode="merge")
            self.queue_one()
            self.land("land")
            remote = self.base / "origin.git"
            sh("git", "config", "uploadpack.hideRefs", "refs/heads/landing/e1", cwd=remote)
            (remote / "refs/heads/landing/e1.lock").write_text("x")
            listed = subprocess.run(["git", "ls-remote", "origin", "refs/heads/landing/e1"],
                                    cwd=self.work, capture_output=True, text=True)
            self.assertEqual((listed.returncode, listed.stdout.strip()), (0, ""))
            self.assertEqual(self.land("land"), "nothing to land")
            self.assertTrue(self.ref_exists("refs/heads/landing/e1", remote))
            self.assertTrue(self.land("lease", "list").startswith("L1 submitted"))
            self.assertIn("awaiting-merge", self.land("status", "E1"))
            self.assertIn("branch-status 200", (self.base / "gh-calls").read_text())

    def test_merge_mode_leaves_the_entry_when_receive_pack_hides_the_queue_branch(self):
        with self.fake_gh():
            self.init(mode="merge")
            self.queue_one()
            self.land("land")
            remote = self.base / "origin.git"
            sh("git", "config", "receive.hideRefs", "refs/heads/landing/e1", cwd=remote)
            self.assertEqual(self.land("land"), "nothing to land")
            self.assertTrue(self.ref_exists("refs/heads/landing/e1", remote))
            self.assertTrue(self.land("lease", "list").startswith("L1 submitted"))
            self.assertIn("awaiting-merge", self.land("status", "E1"))
            self.assertIn("branch-status 200", (self.base / "gh-calls").read_text())

    def test_an_annotated_tag_stays_local_when_the_queue_pushes(self):
        with self.fake_gh():
            self.init(mode="merge")
            self.queue_one()
            sh("git", "tag", "-a", "private-local-tag", "-m", "local tag", cwd=self.work)
            sh("git", "config", "push.followTags", "true", cwd=self.work)
            log = self.record_pushes()
            try:
                self.assertIn("opened PRs that merge when their checks pass: E1 (r/D1)", self.land("land"))
                self.merged_queue_branch()
                self.assertEqual(self.land("land"), "landed E1 (r/D1)")
            finally:
                self.stop_recording_pushes()
            remote = self.base / "origin.git"
            self.assert_pushes_stay_on_their_refs(log)
            self.assertFalse(self.ref_exists("refs/tags/private-local-tag", remote))
            self.assertNotIn("branch-status", (self.base / "gh-calls").read_text())
            self.assertEqual(self.land("lease", "list"), "no leases held")

    def test_push_mode_keeps_an_annotated_tag_local(self):
        self.init(mode="push")
        self.queue_one()
        sh("git", "tag", "-a", "private-local-tag", "-m", "local tag", cwd=self.work)
        sh("git", "config", "push.followTags", "true", cwd=self.work)
        log = self.record_pushes()
        try:
            self.assertEqual(self.land("land"), "landed E1 (r/D1)")
        finally:
            self.stop_recording_pushes()
        self.assert_pushes_stay_on_their_refs(log)
        self.assertFalse(self.ref_exists("refs/tags/private-local-tag", self.base / "origin.git"))

    def test_merge_mode_settles_when_the_forge_reports_the_branch_gone(self):
        with self.fake_gh():
            self.init(mode="merge")
            self.queue_one()
            self.land("land")
            remote = self.base / "origin.git"
            self.merged_queue_branch()
            sh("git", "update-ref", "-d", "refs/heads/landing/e1", cwd=remote)
            sh("git", "tag", "-a", "private-local-tag", "-m", "local tag", cwd=self.work)
            sh("git", "config", "push.followTags", "true", cwd=self.work)
            log = self.record_pushes()
            try:
                self.assertEqual(self.land("land"), "landed E1 (r/D1)")
            finally:
                self.stop_recording_pushes()
            self.assertEqual(
                log.read_text().splitlines(),
                ["push --no-follow-tags origin --delete landing/e1"])
            self.assertFalse(self.ref_exists("refs/tags/private-local-tag", remote))
            self.assertIn("branch-status 404", (self.base / "gh-calls").read_text())
            self.assertIn(
                "api --include repos/{owner}/{repo}/branches/landing/e1",
                (self.base / "gh-calls").read_text())
            self.assertEqual(self.land("lease", "list"), "no leases held")

    def test_merge_mode_leaves_the_entry_when_the_branch_query_fails(self):
        with self.fake_gh():
            self.init(mode="merge")
            self.queue_one()
            self.land("land")
            remote = self.base / "origin.git"
            self.merged_queue_branch()
            sh("git", "update-ref", "-d", "refs/heads/landing/e1", cwd=remote)
            (self.base / "branch-query-fails").write_text("x")
            self.assertEqual(self.land("land"), "nothing to land")
            self.assertIn("branch-status 500", (self.base / "gh-calls").read_text())
            self.assertIn("awaiting-merge", self.land("status", "E1"))
            self.assertTrue(self.land("lease", "list").startswith("L1 submitted"))
            self.assertFalse(self.ref_exists("refs/heads/landing/e1", remote))

    def test_merge_mode_leaves_the_entry_when_another_push_url_dropped_the_branch(self):
        with self.fake_gh():
            self.init(mode="merge")
            self.queue_one()
            self.land("land")
            remote = self.base / "origin.git"
            backup = self.base / "backup.git"
            ref = "refs/heads/landing/e1"
            sha = self.merged_queue_branch()
            sh("git", "checkout", "--detach", "-q", sha, cwd=self.work)
            sh("git", "clone", "--bare", "-q", str(remote), str(backup), cwd=self.base)
            sh("git", "update-ref", "-d", ref, cwd=backup)
            (remote / "refs/heads/landing/e1.lock").write_text("x")
            sh("git", "config", "--add", "remote.origin.pushurl", str(remote), cwd=self.work)
            sh("git", "config", "--add", "remote.origin.pushurl", str(backup), cwd=self.work)
            self.assertEqual(self.land("land"), "nothing to land")
            self.assertTrue(self.ref_exists(ref, remote))
            self.assertFalse(self.ref_exists(ref, backup))
            self.assertNotIn("branches/", (self.base / "gh-calls").read_text())
            self.assertTrue(self.land("lease", "list").startswith("L1 submitted"))
            self.assertIn("awaiting-merge", self.land("status", "E1"))

    def test_merge_mode_leaves_the_entry_when_the_other_push_url_keeps_the_branch(self):
        with self.fake_gh():
            self.init(mode="merge")
            self.queue_one()
            self.land("land")
            origin = self.base / "origin.git"
            backup = self.base / "backup.git"
            ref = "refs/heads/landing/e1"
            sha = self.merged_queue_branch()
            sh("git", "checkout", "--detach", "-q", sha, cwd=self.work)
            sh("git", "clone", "--bare", "-q", str(origin), str(backup), cwd=self.base)
            sh("git", "update-ref", "-d", ref, cwd=origin)
            lock = backup / "refs/heads/landing/e1.lock"
            lock.parent.mkdir(parents=True, exist_ok=True)
            lock.write_text("x")
            sh("git", "config", "--add", "remote.origin.pushurl", str(origin), cwd=self.work)
            sh("git", "config", "--add", "remote.origin.pushurl", str(backup), cwd=self.work)
            self.assertEqual(self.land("land"), "nothing to land")
            self.assertFalse(self.ref_exists(ref, origin))
            self.assertTrue(self.ref_exists(ref, backup))
            self.assertTrue(self.land("lease", "list").startswith("L1 submitted"))
            self.assertIn("awaiting-merge", self.land("status", "E1"))

    def test_merge_mode_leaves_the_entry_when_the_push_url_names_another_repo(self):
        with self.fake_gh():
            self.init(mode="merge")
            self.queue_one()
            self.land("land")
            remote = self.base / "origin.git"
            self.merged_queue_branch()
            sh("git", "remote", "set-url", "origin", "https://github.com/else/where.git", cwd=self.work)
            sh("git", "config", "receive.denyDeletes", "true", cwd=remote)
            (self.base / "forge-says-missing").write_text("x")
            self.assertEqual(self.land("land"), "nothing to land")
            self.assertTrue(self.ref_exists("refs/heads/landing/e1", remote))
            self.assertTrue(self.land("lease", "list").startswith("L1 submitted"))
            self.assertIn("awaiting-merge", self.land("status", "E1"))
            self.assertNotIn("branches/", (self.base / "gh-calls").read_text())

    def test_merge_mode_leaves_the_entry_when_the_forge_repo_cannot_be_read(self):
        with self.fake_gh():
            self.init(mode="merge")
            self.queue_one()
            self.land("land")
            remote = self.base / "origin.git"
            self.merged_queue_branch()
            sh("git", "update-ref", "-d", "refs/heads/landing/e1", cwd=remote)
            (self.base / "repo-view-fails").write_text("x")
            self.assertEqual(self.land("land"), "nothing to land")
            self.assertFalse(self.ref_exists("refs/heads/landing/e1", remote))
            self.assertTrue(self.land("lease", "list").startswith("L1 submitted"))
            self.assertIn("awaiting-merge", self.land("status", "E1"))

    def test_push_mode_settles_a_missing_branch_only_from_gits_absent_line(self):
        with self.fake_gh():
            self.init(mode="merge")
            self.queue_one()
            self.land("land")
            store = land.Store.for_repo(self.work)
            with store.tx() as db:
                db.execute("INSERT OR REPLACE INTO contract VALUES ('mode', ?)", (json.dumps("push"),))
            store = land.Store.for_repo(self.work)
            self.assertEqual(store.contract["mode"], "push")
            remote = self.base / "origin.git"
            self.merged_queue_branch()
            sh("git", "update-ref", "-d", "refs/heads/landing/e1", cwd=remote)
            sh("git", "tag", "-a", "private-local-tag", "-m", "local tag", cwd=self.work)
            sh("git", "config", "push.followTags", "true", cwd=self.work)
            (self.base / "branch-query-fails").write_text("x")
            entry = store.entries("awaiting-merge")[0]
            log = self.record_pushes()
            try:
                landed, bounced = [], []
                self.assertTrue(land.take_pr(store, entry, landed, bounced))
            finally:
                self.stop_recording_pushes()
            self.assertEqual(landed, [entry["id"]])
            self.assertEqual(bounced, [])
            self.assertEqual(
                log.read_text().splitlines(),
                ["push --no-follow-tags origin --delete landing/e1"])
            self.assertNotIn("branches/", (self.base / "gh-calls").read_text())
            self.assertFalse(self.ref_exists("refs/tags/private-local-tag", remote))
            self.assertEqual(self.land("status", "E1").splitlines()[0].split(". ")[0], "E1 landed (r/D1, w1)")
            self.assertEqual(self.land("lease", "list"), "no leases held")

    def test_merge_mode_lands_in_the_run_whose_plain_merge_succeeds(self):
        with self.fake_gh():
            (self.base / "pr-checks.json").write_text('{"reviewDecision":"","statusCheckRollup":[]}')
            (self.base / "merge-state-lags").write_text("")
            self.init(mode="merge", merge_method="squash")
            self.queue_one()
            opened = self.land("land")
            self.assertIn("opened PRs that merge when their checks pass: E1 (r/D1)", opened)
            self.assertNotIn("landed", opened)
            self.assertEqual(self.land("land"), "landed E1 (r/D1)")
            self.assertEqual(self.land("lease", "list"), "no leases held")
            self.assertFalse(self.ref_exists("refs/heads/landing/e1", self.base / "origin.git"))
            self.assertFalse(self.ref_exists("refs/remotes/origin/landing/e1", self.work))
            self.assertIn("pr merge https://github.com/o/r/pull/9 --squash", (self.base / "merge-calls").read_text())

    def test_merge_mode_lands_in_the_run_whose_auto_merge_completes(self):
        with self.fake_gh():
            (self.base / "pr-checks.json").write_text('{"reviewDecision":"","statusCheckRollup":[]}')
            self.init(mode="merge", merge_method="squash")
            self.queue_one()
            self.land("land")
            (self.base / "auto-merges-immediately").write_text("")
            (self.base / "merge-state-lags").write_text("")
            (self.base / "pr-checks.json").unlink()
            (self.base / "checks").write_text("passed")
            self.assertEqual(self.land("land"), "landed E1 (r/D1)")
            self.assertEqual(self.land("lease", "list"), "no leases held")
            self.assertFalse(self.ref_exists("refs/heads/landing/e1", self.base / "origin.git"))
            calls = (self.base / "merge-calls").read_text().splitlines()
            self.assertEqual(calls[-1], "pr merge https://github.com/o/r/pull/9 --auto --squash")

    def test_merge_mode_reports_a_merge_that_lands_after_the_opening_state_read(self):
        with self.fake_gh():
            (self.base / "required-checks").write_text("")
            self.init(mode="merge")
            self.queue_one()
            self.assertIn("opened PRs that merge when their checks pass: E1 (r/D1)", self.land("land"))
            self.assertEqual(self.land("land"), "nothing to land")
            self.assertIn("merge requested by the queue", self.land("status", "E1"))
            candidate = sh("git", "rev-parse", "landing/e1", cwd=self.base / "origin.git")
            (self.base / "pr-state").write_text(f"OPEN {candidate} ")
            (self.base / "pr-state-after").write_text(f"MERGED {candidate} abc123")
            (self.base / "checks").write_text("passed")
            self.assertEqual(self.land("land"), "landed E1 (r/D1)")
            self.assertEqual(self.land("lease", "list"), "no leases held")
            self.assertFalse(self.ref_exists("refs/heads/landing/e1", self.base / "origin.git"))

    def test_merge_mode_pauses_for_review_without_calling_auto_merge(self):
        with self.fake_gh():
            (self.base / "pr-checks.json").write_text(
                '{"reviewDecision":"REVIEW_REQUIRED","statusCheckRollup":'
                '[{"name":"test (3.12)","status":"COMPLETED","conclusion":"SUCCESS"}]}')
            (self.base / "required-checks").write_text("")
            self.init(mode="merge")
            self.queue_one()
            out = self.land("land")
            self.assertIn("queue paused", out)
            self.assertIn("https://github.com/o/r/pull/9", out)
            self.assertIn("approving review", out)
            self.assertNotIn("landed", out)
            calls = (self.base / "merge-calls").read_text() if (self.base / "merge-calls").exists() else ""
            self.assertNotIn("--auto", calls.split())
            self.assertIn("awaiting-merge", self.land("status", "E1"))
            self.assertTrue(self.land("lease", "list").startswith("L1 submitted"))

    def test_merge_mode_pauses_when_changes_are_requested_without_calling_auto_merge(self):
        with self.fake_gh():
            (self.base / "pr-checks.json").write_text(
                '{"reviewDecision":"CHANGES_REQUESTED","statusCheckRollup":[]}')
            (self.base / "required-checks").write_text("")
            self.init(mode="merge")
            self.queue_one()
            out = self.land("land")
            self.assertIn("queue paused", out)
            self.assertIn("https://github.com/o/r/pull/9", out)
            self.assertIn("changes requested", out)
            calls = (self.base / "merge-calls").read_text() if (self.base / "merge-calls").exists() else ""
            self.assertNotIn("--auto", calls.split())

    def test_merge_mode_disables_auto_merge_when_it_bounces_an_open_pr(self):
        with self.fake_gh():
            (self.base / "required-checks").write_text("")
            self.arm_auto_merge()
            self.init(mode="merge")
            self.queue_one()
            self.land("land")
            self.assertEqual(self.land("land"), "nothing to land")
            self.assertIn("merge requested by the queue", self.land("status", "E1"))
            (self.base / "checks").write_text("failed")
            out = self.land("land")
            self.assertIn("bounced E1 (r/D1): required checks failed on https://github.com/o/r/pull/9: test (3.12)", out)
            self.assertIn("pr merge https://github.com/o/r/pull/9 --disable-auto", (self.base / "merge-calls").read_text())
            self.assertNotIn("pr comment", (self.base / "gh-calls").read_text())
            self.assertNotIn("pr close", (self.base / "gh-calls").read_text())
            self.assertTrue(self.land("lease", "list").startswith("L1 active r/D1"))
            self.assertTrue(self.ref_exists("refs/heads/landing/e1", self.base / "origin.git"))

    def test_merge_mode_pauses_when_it_cannot_disable_auto_merge_on_a_failed_pr(self):
        with self.fake_gh():
            (self.base / "required-checks").write_text("")
            (self.base / "disable-auto-fails").write_text("API unavailable")
            self.arm_auto_merge()
            self.init(mode="merge")
            self.queue_one()
            self.land("land")
            self.land("land")
            (self.base / "checks").write_text("failed")
            self.assertEqual(self.land("land"), "queue paused: required checks failed on https://github.com/o/r/pull/9: test (3.12). "
                                                "Auto-merge is still enabled: API unavailable. Turn auto-merge off on https://github.com/o/r/pull/9, "
                                                "then run land.py resume and land.py land")
            self.assertTrue(self.land("status", "E1").startswith("E1 awaiting-merge"))
            self.assertNotIn("pr close", (self.base / "gh-calls").read_text())
            self.assertTrue(self.land("lease", "list").startswith("L1 submitted"))
            (self.base / "auto-merge-request.json").unlink()
            self.land("resume")
            self.assertIn("bounced E1 (r/D1): required checks failed on https://github.com/o/r/pull/9: test (3.12)", self.land("land"))
            self.assertTrue(self.land("lease", "list").startswith("L1 active"))

    def test_merge_mode_skips_disable_auto_when_auto_merge_request_is_null(self):
        with self.fake_gh():
            (self.base / "checks").write_text("failed")
            (self.base / "auto-merge-request.json").write_text("null")
            self.init(mode="merge")
            self.queue_one()
            self.assertEqual(self.land("land"), "bounced E1 (r/D1): required checks failed on https://github.com/o/r/pull/9: test (3.12)")
            calls = (self.base / "merge-calls").read_text() if (self.base / "merge-calls").exists() else ""
            self.assertNotIn("--disable-auto", calls)
            self.assertNotIn("pr close", (self.base / "gh-calls").read_text())
            self.assertNotIn("auto-merge still enabled", self.land("status", "E1"))
            self.assertTrue(self.land("lease", "list").startswith("L1 active"))

    def test_merge_mode_pauses_on_a_disable_auto_failure_when_auto_merge_request_is_set(self):
        with self.fake_gh():
            (self.base / "required-checks").write_text("")
            self.arm_auto_merge()
            (self.base / "disable-auto-fails").write_text("GraphQL: Auto merge is not enabled for this pull request")
            self.init(mode="merge")
            self.queue_one()
            self.land("land")
            self.land("land")
            (self.base / "checks").write_text("failed")
            out = self.land("land")
            self.assertIn("queue paused: required checks failed on https://github.com/o/r/pull/9: test (3.12). "
                          "Auto-merge is still enabled: GraphQL: Auto merge is not enabled for this pull request", out)
            self.assertTrue(self.land("status", "E1").startswith("E1 awaiting-merge"))
            self.assertIn("pr merge https://github.com/o/r/pull/9 --disable-auto", (self.base / "merge-calls").read_text())
            self.assertNotIn("pr close", (self.base / "gh-calls").read_text())

    def test_merge_mode_pauses_when_github_requires_a_human_approval(self):
        with self.fake_gh():
            (self.base / "merge-refused").write_text("")
            self.init(mode="merge")
            self.queue_one()
            out = self.land("land")
            self.assertIn("queue paused: https://github.com/o/r/pull/9 needs an approving review", out)
            calls = (self.base / "merge-calls").read_text() if (self.base / "merge-calls").exists() else ""
            self.assertNotIn("--auto", calls.split())

    def test_init_in_merge_mode_picks_an_allowed_method(self):
        with self.fake_gh():
            self.allow_methods(squash=True)
            self.init(mode="merge")
            self.assertEqual(self.stored_merge_method(), "squash")
            self.assertIn(
                "repo view --json mergeCommitAllowed,squashMergeAllowed,rebaseMergeAllowed",
                (self.base / "gh-calls").read_text(),
            )
            self.allow_methods(rebase=True)
            self.init(mode="merge")
            self.assertEqual(self.stored_merge_method(), "rebase")
            self.allow_methods(squash=True, rebase=True)
            self.init(mode="merge")
            self.assertEqual(self.stored_merge_method(), "squash")
            self.allow_methods(merge=True, squash=True)
            self.init(mode="merge")
            self.assertEqual(self.stored_merge_method(), "merge")
            self.allow_methods(merge=True, squash=True, rebase=True)
            self.init(mode="merge")
            self.assertEqual(self.stored_merge_method(), "merge")
            self.allow_methods(merge=True, rebase=True)
            self.init(mode="merge", merge_method="rebase")
            self.assertEqual(self.stored_merge_method(), "rebase")

    def test_init_outside_merge_mode_does_not_ask_which_methods_are_allowed(self):
        with self.fake_gh():
            self.allow_methods(squash=True)
            self.init(mode="human")
            calls = (self.base / "gh-calls").read_text() if (self.base / "gh-calls").exists() else ""
            self.assertNotIn("mergeCommitAllowed", calls)
            self.assertEqual(self.stored_merge_method(), "merge")

    def test_init_refuses_a_merge_method_the_repository_disallows(self):
        with self.fake_gh():
            self.allow_methods(squash=True, rebase=True)
            self.assertEqual(
                self.land("init", "--trunk", "main", "--mode", "merge", "--check", "./check.sh",
                          "--merge-method", "merge", ok=False),
                "land: repository does not allow merge; allowed: squash, rebase",
            )
            self.assertIn("has no landing contract", self.land("status", ok=False))
            self.allow_methods()
            self.assertEqual(
                self.land("init", "--trunk", "main", "--mode", "merge", "--check", "./check.sh", ok=False),
                "land: repository allows no merge method; allowed: none",
            )

    def test_init_keeps_merge_when_gh_cannot_read_allowed_methods(self):
        with self.fake_gh():
            (self.base / "repo-view-fails").write_text("x")
            self.allow_methods(squash=True)
            self.init(mode="merge")
            self.assertEqual(self.stored_merge_method(), "merge")
            self.init(mode="merge", merge_method="rebase")
            self.assertEqual(self.stored_merge_method(), "rebase")

    def test_a_refused_merge_method_names_the_command_that_changes_it(self):
        refusal = "GraphQL: Merge commits are not allowed on this repository. (mergePullRequest)"
        with self.fake_gh():
            self.allow_methods(merge=True, squash=True, rebase=True)
            self.init(mode="merge")
            self.queue_one()
            self.assertIn("opened PRs that merge when their checks pass: E1 (r/D1)", self.land("land"))
            (self.base / "plain-merge-fails").write_text(refusal)
            self.allow_methods(squash=True)
            self.assertEqual(
                self.land("land"),
                "queue paused: GitHub refused to merge https://github.com/o/r/pull/9: "
                f"{refusal}. Run land.py mode merge --merge-method squash, then land.py resume",
            )
            self.assertEqual(
                self.land("mode", "human", ok=False),
                "land: 1 entry is queued, landing, or awaiting merge; change the mode when the queue is empty",
            )
            self.assertEqual(
                self.land("mode", "merge", "--merge-method", "merge", ok=False),
                "land: repository does not allow merge; allowed: squash",
            )
            self.assertEqual(
                self.land("mode", "merge", "--merge-method", "squash"),
                "landing mode is now merge, merging with --squash; leases held by r/D1",
            )
            (self.base / "plain-merge-fails").unlink()
            self.assertEqual(self.land("resume"), "queue resumed")
            self.assertEqual(self.land("land"), "landed E1 (r/D1)")
            self.assertIn("pr merge https://github.com/o/r/pull/9 --squash", (self.base / "merge-calls").read_text())
            self.assertEqual(self.land("lease", "list"), "no leases held")

    def test_the_merge_method_changes_while_an_entry_is_queued(self):
        with self.fake_gh():
            self.allow_methods(merge=True, squash=True)
            self.init(mode="merge")
            self.queue_one()
            self.assertEqual(
                self.land("mode", "merge", "--merge-method", "squash"),
                "landing mode is now merge, merging with --squash; leases held by r/D1",
            )
            self.assertEqual(self.stored_merge_method(), "squash")
            self.assertEqual(
                self.land("mode", "push", ok=False),
                "land: 1 entry is queued, landing, or awaiting merge; change the mode when the queue is empty",
            )

    def test_a_method_change_paused_in_github_keeps_the_mode_a_second_process_set(self):
        with self.fake_gh():
            self.allow_methods(merge=True, squash=True)
            self.init(mode="merge")
            self.pause_repo_view()
            (self.base / "pause-repo-view").write_text("")
            child = subprocess.Popen(
                [sys.executable, str(SCRIPT), "--repo", str(self.work),
                 "mode", "merge", "--merge-method", "squash"],
                stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, env=os.environ.copy())
            try:
                deadline = time.monotonic() + 10
                while not (self.base / "repo-view-waiting").exists():
                    if child.poll() is not None or time.monotonic() > deadline:
                        out, err = child.communicate()
                        self.fail(f"repo view did not pause: code {child.returncode}\n{out}\n{err}")
                    time.sleep(0.01)
                self.assertEqual(self.land("mode", "human"), "landing mode is now human")
                self.assertEqual(self.queue_one(), "E1")
                (self.base / "repo-view-release").write_text("")
                out, err = child.communicate(timeout=10)
            finally:
                if child.poll() is None:
                    child.kill()
                    child.communicate()
            self.assertEqual(child.returncode, 1, out + err)
            self.assertEqual(
                err.strip(),
                "land: 1 entry is queued, landing, or awaiting merge; change the mode when the queue is empty",
            )
            self.assertEqual(self.stored_merge_method(), "merge")
            status = self.land("status")
            self.assertTrue(status.startswith("human mode onto"), status)
            self.assertIn("queued: 1", status)

    def test_mode_help_separates_a_switch_from_a_method_change(self):
        top = subprocess.run([sys.executable, str(SCRIPT), "--help"], capture_output=True, text=True)
        mode = subprocess.run([sys.executable, str(SCRIPT), "mode", "--help"], capture_output=True, text=True)
        self.assertEqual(top.returncode, 0, top.stderr)
        self.assertEqual(mode.returncode, 0, mode.stderr)
        for text in (top.stdout, mode.stdout):
            shown = " ".join(text.split())
            self.assertIn("when the queue is empty", shown)
            self.assertIn("--merge-method may change while entries are in flight", shown)
            self.assertNotIn("while nothing is in flight", shown)

    def test_one_busy_entry_is_singular_and_two_are_plural(self):
        with self.fake_gh():
            self.init(mode="human")
            self.queue_one()
            self.land("land")
            self.assertEqual(
                self.land("mode", "merge", ok=False),
                "land: 1 entry is queued, landing, or awaiting merge; change the mode when the queue is empty",
            )
            self.queue_one(path="b.txt", name="w2", holder="r/D2")
            self.land("land")
            self.assertEqual(
                self.land("mode", "push", ok=False),
                "land: 2 entries are queued, landing, or awaiting merge; change the mode when the queue is empty",
            )

    def test_the_mode_changes_only_while_nothing_is_in_flight(self):
        with self.fake_gh():
            self.init(mode="human")
            self.queue_one()
            self.land("land")
            self.assertIn("awaiting merge; change the mode when the queue is empty", self.land("mode", "merge", ok=False))
            candidate = sh("git", "rev-parse", "landing/e1", cwd=self.base / "origin.git")
            (self.base / "pr-state").write_text(f"MERGED {candidate} abc123")
            self.land("land")
            self.assertEqual(self.land("mode", "merge", "--merge-method", "squash"), "landing mode is now merge, merging with --squash")
            self.assertTrue(self.land("status").startswith("merge mode onto"))
            self.assertIn("needs a new contract", self.land("mode", "local", ok=False))

    def test_a_contract_written_with_the_old_auto_mode_reads_as_push(self):
        self.init(mode="auto")
        self.assertTrue(self.land("status").startswith("push mode onto"))
        self.assertEqual(self.land("init", "--trunk", "main", "--mode", "push", "--check", "./check.sh").split()[0], "updated")

    def test_human_mode_adopts_the_pr_a_crashed_run_created(self):
        with self.fake_gh():
            self.init(mode="human")
            self.queue_one()
            (self.base / "crash-on-create").write_text("")
            result = subprocess.run([sys.executable, str(SCRIPT), "--repo", str(self.work), "land"], capture_output=True, text=True, env=os.environ.copy())
            self.assertEqual(result.returncode, -9)
            self.assertEqual(self.land("land"), "adopted E1 (r/D1) https://github.com/o/r/pull/9")
            self.assertIn("awaiting-merge (r/D1, w1). https://github.com/o/r/pull/9", self.land("status", "E1"))

    def test_human_mode_bounces_a_pr_merged_with_a_head_the_queue_did_not_check(self):
        with self.fake_gh():
            self.init(mode="human")
            self.queue_one()
            self.land("land")
            (self.base / "pr-state").write_text("MERGED 0123456789abcdef deadbeef")
            self.assertIn("bounced E1 (r/D1): merged at deadbeef with head 0123456789ab", self.land("land"))

    def test_human_mode_pauses_when_trunk_loses_a_landed_commit(self):
        with self.fake_gh():
            self.init(mode="human")
            self.queue_one()
            self.land("land")
            sh("git", "fetch", "-q", "origin", cwd=self.work)
            merged = self.commit_on_origin("human merge")
            (self.base / "pr-state").write_text(f"MERGED {sh('git', 'rev-parse', 'landing/e1', cwd=self.base / 'origin.git')} {merged}")
            self.assertEqual(self.land("land"), "landed E1 (r/D1)")
            sh("git", "push", "-q", "--force", "origin", "HEAD:main", cwd=self.work)
            self.assertIn("queue paused: trunk no longer contains the last landed commit", self.land("land"))

    def commit_on_origin(self, message):
        """Simulate GitHub merging: push a new commit to origin main. Returns its SHA."""
        clone = self.base / "merger"
        if not clone.exists():
            sh("git", "clone", "-q", "origin.git", "merger", cwd=self.base)
        sh("git", "pull", "-q", "origin", "main", cwd=clone)
        (clone / "merged.txt").write_text(message)
        sha = self.commit(message, cwd=clone)
        sh("git", "push", "-q", "origin", "HEAD:main", cwd=clone)
        return sha

    def test_a_failed_pin_leaves_nothing_queued(self):
        self.init()
        wrapper = self.base / "bin"
        wrapper.mkdir()
        real = sh("sh", "-c", "command -v git", cwd=self.base)
        (wrapper / "git").write_text(f'#!/bin/sh\ncase "$*" in *refs/landing/pins/*) exit 1;; esac\nexec {real} "$@"\n')
        (wrapper / "git").chmod(0o755)
        sha = self.worker("w1", {"a.txt": "agent\n"})
        self.land("lease", "claim", "--holder", "r/D1", "--paths", "a.txt")
        with mock.patch.dict(os.environ, {"PATH": f"{wrapper}:{os.environ['PATH']}"}):
            self.land("submit", "--holder", "r/D1", "--branch", "w1", "--sha", sha, "--lease", "L1", "--reviewer", REVIEWER, ok=False)
        self.assertEqual(self.land("status"), "push mode onto refs/remotes/origin/main. leases held: 1.")

    def test_a_policy_rejection_pauses_the_queue_after_one_check_run(self):
        self.land("init", "--trunk", "main", "--mode", "auto", "--check", f"echo run >> {self.base}/runs")
        hook = self.base / "origin.git/hooks/pre-receive"
        hook.write_text("#!/bin/sh\necho rejected by policy >&2\nexit 1\n")
        hook.chmod(0o755)
        self.queue_one()
        self.assertIn("queue paused: push rejected: remote: rejected by policy", self.land("land"))
        self.assertEqual((self.base / "runs").read_text(), "run\n")
        self.assertIn("E1 queued", self.land("status", "E1"))

    def test_a_check_that_escapes_its_group_cannot_hold_the_queue(self):
        script = self.base / "escape.py"
        script.write_text("import os, time\nos.setsid()\ntime.sleep(20)\n")
        self.land("init", "--trunk", "main", "--mode", "auto", "--check", f"{sys.executable} {script}; true", "--timeout", "1")
        self.queue_one()
        started = __import__("time").monotonic()
        self.assertIn("timed out", self.land("land"))
        self.assertLess(__import__("time").monotonic() - started, 12)

    def test_non_utf8_check_output_and_file_contents_land(self):
        self.land("init", "--trunk", "main", "--mode", "auto", "--check", "printf '\\377'")
        self.worker("w1", {"seed.txt": "seed\n"})
        (self.base / "w1/latin.txt").write_bytes(b"caf\xe9\n")
        sha = self.commit("latin", cwd=self.base / "w1")
        self.land("lease", "claim", "--holder", "r/D1", "--paths", "seed.txt,latin.txt")
        self.land("submit", "--holder", "r/D1", "--branch", "w1", "--sha", sha, "--lease", "L1", "--reviewer", REVIEWER)
        self.assertEqual(self.land("land"), "landed E1 (r/D1)")

    def test_non_ascii_file_names_match_their_lease(self):
        self.init()
        self.assertEqual(self.queue_one(path="café.txt"), "E1")
        self.assertEqual(self.land("land"), "landed E1 (r/D1)")

    def test_landing_works_without_a_git_identity(self):
        self.init()
        self.queue_one()
        empty = self.base / "home"
        empty.mkdir()
        bare_env = {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}
        bare_env.update({"HOME": str(empty), "GIT_CONFIG_GLOBAL": "/dev/null", "GIT_CONFIG_SYSTEM": "/dev/null"})
        result = subprocess.run([sys.executable, str(SCRIPT), "--repo", str(self.work), "land"], capture_output=True, text=True, env=bare_env)
        self.assertEqual(result.stdout.strip(), "landed E1 (r/D1)", result.stderr)

    def test_fingerprint_sees_whitespace_and_ignores_line_numbers(self):
        repo = self.work
        base = sh("git", "rev-parse", "HEAD", cwd=repo)
        (repo / "lib/x.py").write_text("lib/x.py\n    return 1\n")
        indented = self.commit("indent")
        sh("git", "reset", "-q", "--hard", base, cwd=repo)
        (repo / "lib/x.py").write_text("lib/x.py\n  return 1\n")
        other = self.commit("indent 2")
        self.assertNotEqual(land.fingerprint(repo, base, indented), land.fingerprint(repo, base, other))
        sh("git", "reset", "-q", "--hard", base, cwd=repo)
        (repo / "lib/x.py").write_text("header\nlib/x.py\n")
        moved = self.commit("header")
        (repo / "lib/x.py").write_text("header\nlib/x.py\n    return 1\n")
        indented_after_header = self.commit("indent after header")
        self.assertEqual(land.fingerprint(repo, base, indented), land.fingerprint(repo, moved, indented_after_header))

    def test_a_check_that_hangs_is_killed_at_the_timeout(self):
        self.land("init", "--trunk", "main", "--mode", "auto", "--check", "sleep 30", "--timeout", "1")
        sha = self.worker("w1", {"a.txt": "agent\n"})
        self.land("lease", "claim", "--holder", "r/D1", "--paths", "a.txt")
        self.land("submit", "--holder", "r/D1", "--branch", "w1", "--sha", sha, "--lease", "L1", "--reviewer", REVIEWER)
        self.assertIn("bounced E1 (r/D1): checks failed: `sleep 30` timed out", self.land("land"))

    def test_the_contract_refuses_a_conflicting_init_and_other_clones(self):
        self.init()
        self.assertIn("already sets trunk='main'", self.land("init", "--trunk", "dev", "--mode", "auto", ok=False))
        sh("git", "clone", "-q", "origin.git", "other", cwd=self.base)
        result = subprocess.run([sys.executable, str(SCRIPT), "--repo", str(self.base / "other"), "status"],
                                capture_output=True, text=True, env=os.environ.copy())
        self.assertIn("has no landing contract", result.stderr)

    def test_an_exclusive_slot_waits_for_every_other_slot_and_refuses_nesting(self):
        import time
        governor = self.base / "state/pstack-t3/governor"
        governor.mkdir(parents=True)
        (governor / "governor.json").write_text(json.dumps({"slots": 2}))
        marks = self.base / "marks"
        # land.py's slot gate reads LAND_SLOT. The queue sets it around this suite, so the
        # subprocesses under test must not inherit it. The nested command still sets it itself.
        env = {key: value for key, value in os.environ.items() if key != "LAND_SLOT"}
        worker = subprocess.Popen([sys.executable, str(SCRIPT), "slot", "--", "sh", "-c", f"echo worker-start >> {marks}; sleep 2; echo worker-end >> {marks}"],
                                  env=env)
        time.sleep(0.5)
        bench = subprocess.run([sys.executable, str(SCRIPT), "slot", "--exclusive", "--", "sh", "-c", f"echo bench >> {marks}"],
                               capture_output=True, text=True, timeout=30, env=env)
        worker.wait(timeout=30)
        self.assertEqual(bench.returncode, 0, bench.stderr)
        self.assertEqual(marks.read_text().split(), ["worker-start", "worker-end", "bench"])
        nested = subprocess.run([sys.executable, str(SCRIPT), "slot", "--", sys.executable, str(SCRIPT), "slot", "--exclusive", "--", "true"],
                                capture_output=True, text=True, timeout=30, env=env)
        self.assertNotEqual(nested.returncode, 0)
        self.assertIn("must be the outermost slot", nested.stderr)

    def test_human_mode_uses_the_submitted_pr_title_and_body(self):
        log = self.base / "gh-log"
        with self.fake_gh():
            fake = self.base / "gh"
            fake.write_text(fake.read_text().replace('if args[:2] == ["pr", "create"]:',
                                                     f'open({str(log)!r}, "a").write(repr(args) + "\\n")\nif args[:2] == ["pr", "create"]:'))
            self.init(mode="human")
            sha = self.worker("w1", {"a.txt": "agent\n"})
            self.land("lease", "claim", "--holder", "r/D1", "--paths", "a.txt")
            body = self.base / "body.md"
            body.write_text("Cuts load time by 300 ms.\n")
            self.land("submit", "--holder", "r/D1", "--branch", "w1", "--sha", sha, "--lease", "L1", "--reviewer", REVIEWER,
                      "--title", "Faster load", "--body-file", str(body))
            self.land("land")
        create = [line for line in log.read_text().splitlines() if "'create'" in line][0]
        self.assertIn("'--title', 'Faster load'", create)
        self.assertIn("'--body', 'Cuts load time by 300 ms.\\n'", create)
        self.assertNotIn("Queued by", create)
        self.assertNotIn("Reviewed by", create)

    def create_args_without_a_submitted_body(self, *message):
        """Land a worker commit with this message and no --body-file. Returns the gh pr create arguments."""
        log = self.base / "gh-log"
        with self.fake_gh():
            fake = self.base / "gh"
            fake.write_text(fake.read_text().replace('if args[:2] == ["pr", "create"]:',
                                                     f'open({str(log)!r}, "a").write(repr(args) + "\\n")\nif args[:2] == ["pr", "create"]:'))
            self.init(mode="human")
            self.worker("w1", {"a.txt": "agent\n"})
            sh("git", "commit", "-q", "--amend", *message, cwd=self.base / "w1")
            sha = sh("git", "rev-parse", "HEAD", cwd=self.base / "w1")
            self.land("lease", "claim", "--holder", "r/D1", "--paths", "a.txt")
            self.land("submit", "--holder", "r/D1", "--branch", "w1", "--sha", sha, "--lease", "L1", "--reviewer", REVIEWER)
            self.land("land")
        return ast.literal_eval([line for line in log.read_text().splitlines() if "'create'" in line][0])

    def test_human_mode_without_a_submitted_body_uses_the_commit_body(self):
        create = self.create_args_without_a_submitted_body("-m", "Faster load", "-m", "Cuts load time by 300 ms.\n\nMeasured on a cold start.")
        self.assertEqual(create[create.index("--title") + 1], "Faster load")
        self.assertEqual(create[create.index("--body") + 1], "Cuts load time by 300 ms.\n\nMeasured on a cold start.")
        self.assertNotIn("Queued by", " ".join(create))
        self.assertNotIn("Reviewed by", " ".join(create))

    def test_human_mode_without_any_body_opens_the_pr_with_an_empty_body(self):
        create = self.create_args_without_a_submitted_body("-m", "Faster load")
        self.assertEqual(create[create.index("--body") + 1], "")
        self.assertNotIn("Queued by", " ".join(create))
        self.assertNotIn("Reviewed by", " ".join(create))

    def test_a_store_from_before_pr_text_columns_is_migrated(self):
        self.init()
        store = land.Store.for_repo(self.work)
        store.db.execute("DROP TABLE entry")
        store.db.executescript(land.SCHEMA)
        self.assertNotIn("title", {row["name"] for row in store.db.execute("PRAGMA table_info(entry)")})
        store.db.close()
        self.assertEqual(self.queue_one(), "E1")
        self.assertEqual(self.land("land"), "landed E1 (r/D1)")

    def test_nested_slots_do_not_deadlock_with_one_slot(self):
        governor = self.base / "state/pstack-t3/governor"
        governor.mkdir(parents=True)
        (governor / "governor.json").write_text(json.dumps({"slots": 1}))
        result = subprocess.run([sys.executable, str(SCRIPT), "slot", "--", sys.executable, str(SCRIPT), "slot", "--", "true"],
                                capture_output=True, text=True, timeout=20, env=os.environ.copy())
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_worker_slots_span_directories_and_leave_landing_capacity(self):
        import signal

        governor = self.base / "state/pstack-t3/governor"
        governor.mkdir(parents=True)
        (governor / "governor.json").write_text(json.dumps({"slots": 2}))
        env = {key: value for key, value in os.environ.items() if key != "LAND_SLOT"}
        directories = [self.base / f"command-{index}" for index in range(3)]
        releases = [self.base / f"release-{index}" for index in range(3)]
        retry = self.base / "retry"
        handles = []
        processes = []

        def wait_for(path):
            deadline = time.monotonic() + 20
            while not path.exists():
                if time.monotonic() >= deadline:
                    self.fail(f"barrier not reached: {path}")
                time.sleep(0.01)

        command = (
            "import os, sys\n"
            "from pathlib import Path\n"
            "release = os.open(sys.argv[1], os.O_RDONLY)\n"
            "Path('started').touch()\n"
            "assert os.read(release, 1) == b'x'\n"
            "os.close(release)\n"
            "Path('finished').touch()\n"
        )
        third = (
            "import os, sys\n"
            "from pathlib import Path\n"
            f"sys.path.insert(0, {str(SCRIPT.parent)!r})\n"
            "import land\n"
            "count = 0\n"
            "def blocked(seconds):\n"
            "    global count\n"
            "    count += 1\n"
            "    gate = os.open(sys.argv[1], os.O_RDONLY)\n"
            "    Path(f'waiting-{count}').touch()\n"
            "    assert os.read(gate, 1) == b'x'\n"
            "    os.close(gate)\n"
            "land.time.sleep = blocked\n"
            "sys.exit(land.main(sys.argv[2:]))\n"
        )
        try:
            for path in [*releases, retry]:
                os.mkfifo(path)
                # Keep both ends open so a barrier write never waits for a reader.
                handles.append(os.open(path, os.O_RDWR | os.O_NONBLOCK))
            for directory in directories:
                directory.mkdir()
            for index in range(2):
                processes.append(subprocess.Popen(
                    [sys.executable, str(SCRIPT), "slot", "--",
                     sys.executable, "-c", command, str(releases[index])],
                    cwd=directories[index], env=env, start_new_session=True,
                    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL))
                wait_for(directories[index] / "started")
            processes.append(subprocess.Popen(
                [sys.executable, "-c", third, str(retry), "slot", "--",
                 sys.executable, "-c", command, str(releases[2])],
                cwd=directories[2], env=env, start_new_session=True,
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL))
            wait_for(directories[2] / "waiting-1")
            self.assertFalse((directories[2] / "started").exists())
            os.write(handles[3], b"x")
            wait_for(directories[2] / "waiting-2")
            self.assertFalse((directories[2] / "started").exists())
            self.assertTrue(all(process.poll() is None for process in processes))

            landing_mark = self.base / "landing-progress"
            probe = (
                "import sys\n"
                "from pathlib import Path\n"
                f"sys.path.insert(0, {str(SCRIPT.parent)!r})\n"
                "import land\n"
                "with land.slot('landing'):\n"
                f"    Path({str(landing_mark)!r}).touch()\n"
            )
            result = subprocess.run([sys.executable, "-c", probe],
                                    env=env, capture_output=True, text=True, timeout=20)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertTrue(landing_mark.exists())
            self.assertFalse((directories[2] / "started").exists())

            os.write(handles[0], b"x")
            self.assertEqual(processes[0].wait(timeout=20), 0)
            self.assertTrue((directories[0] / "finished").exists())
            os.write(handles[3], b"x")
            wait_for(directories[2] / "started")
            self.assertIsNone(processes[1].poll())
            for index in (1, 2):
                os.write(handles[index], b"x")
                self.assertEqual(processes[index].wait(timeout=20), 0)
                self.assertTrue((directories[index] / "finished").exists())
        finally:
            for process in processes:
                if process.poll() is None:
                    os.killpg(process.pid, signal.SIGKILL)
                process.wait(timeout=20)
            for handle in handles:
                os.close(handle)

    def reserve(self, prefix, paths, ruling, *extra, ok=True):
        return self.land("lease", "reserve", "--for", prefix, "--paths", paths, "--ruling", ruling, *ADMIN, *extra, ok=ok)

    def share(self, prefix, count, *extra, ok=True):
        return self.land("share", "--for", prefix, str(count), *ADMIN, *extra, ok=ok)

    def contest(self, *args, ok=True):
        return self.land("contest", *args, *ADMIN, ok=ok)

    def ruling_rows(self, table):
        store = land.Store.for_repo(self.work)
        try:
            return [dict(row) for row in store.db.execute(f"SELECT * FROM {table} ORDER BY 1")]
        finally:
            store.db.close()

    def reserved_until(self, number):
        return next(row for row in self.ruling_rows("reservation") if row["id"] == number)["expires"][:16]

    def listed(self):
        """lease list with each expiry cut out, so lines compare as literals."""
        return [re.sub(r" until \S+:", ":", line) for line in self.land("lease", "list").splitlines()]

    def concurrent(self, *commands):
        procs = [subprocess.Popen([sys.executable, str(SCRIPT), "--repo", str(self.work), *command],
                                  stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, env=os.environ.copy())
                 for command in commands]
        return [(proc.wait(), *(part.strip() for part in proc.communicate())) for proc in procs]

    def test_a_reservation_refuses_another_holders_claim_and_admits_the_winner(self):
        self.init()
        self.assertEqual(self.reserve("docs/", "a.txt,b.txt", "R4"), "S1")
        refusal = self.claim("engine/D3", "a.txt", ok=False)
        self.assertEqual(refusal, f"land: paths reserved for docs/ by ruling R4 until {self.reserved_until(1)}")
        self.assertEqual(self.lease_check("engine/D3", "b.txt"), (1, refusal.removeprefix("land: ")))
        self.assertEqual(self.claim("engine/D3", "lib"), "L1")
        self.assertEqual(self.claim("docs/D7", "a.txt,b.txt"), "L2")
        self.assertEqual(self.listed(), ["L1 active engine/D3: lib", "L2 active docs/D7: a.txt, b.txt"])
        self.assertEqual(self.ruling_rows("reservation")[0]["state"], "claimed")

    def test_a_reservation_refuses_readmitting_another_holders_expired_lease(self):
        self.init()
        self.assertEqual(self.claim("engine/D3", "a.txt", "--ttl-hours", "0"), "L1")
        self.assertEqual(self.reserve("docs/", "a.txt", "R4"), "S1")
        self.assertEqual(self.land("lease", "renew", "L1", ok=False),
                         f"land: paths reserved for docs/ by ruling R4 until {self.reserved_until(1)}")
        self.assertEqual(self.listed(), ["S1 armed docs/ by R4: a.txt"])
        self.assertEqual(self.claim("docs/D7", "a.txt"), "L2")

    def test_a_claim_covering_one_reserved_path_leaves_the_other_and_counts_once(self):
        self.init()
        self.land("cap", "2")
        self.reserve("docs/", "a.txt,b.txt", "R4")
        self.assertIn("changes in flight: 1 of 2", self.land("status"))
        self.assertEqual(self.claim("docs/D7", "a.txt"), "L1")
        self.assertEqual(self.land("status"), "push mode onto refs/remotes/origin/main. leases held: 1, changes in flight: 1 of 2.")
        self.assertEqual(self.listed(), ["L1 active docs/D7: a.txt", "S1 armed docs/ by R4: b.txt"])
        self.assertIn("paths reserved for docs/ by ruling R4", self.claim("engine/D3", "b.txt", ok=False))
        self.assertEqual(self.claim("engine/D3", "lib"), "L2")
        self.assertEqual(self.claim("ops/D1", "c.txt", ok=False), "land: repository at its cap: 2 of 2 changes in flight (docs/D7, engine/D3)")

    def test_a_reservation_waits_to_arm_while_another_holders_live_lease_overlaps(self):
        self.init()
        self.claim("engine/D1", "a.txt")
        self.assertEqual(self.reserve("docs/", "a.txt,b.txt", "R4"), "S1")
        self.assertEqual(self.lease_check("ops/D1", "c.txt"), (0, "free"))
        self.assertEqual(self.listed(), ["L1 active engine/D1: a.txt", "S1 waiting docs/ by R4: a.txt, b.txt"])
        waiting = "paths reserved for docs/ by ruling R4 until 2 hours after it arms"
        self.assertEqual(self.claim("engine/D2", "b.txt", ok=False), f"land: {waiting}")
        self.assertEqual(self.lease_check("engine/D2", "b.txt"), (1, waiting))
        self.assertEqual(self.ruling_rows("reservation")[0]["armed"], "")
        self.land("lease", "release", "L1")
        self.assertEqual(self.listed(), ["S1 armed docs/ by R4: a.txt, b.txt"])
        self.assertEqual(self.lease_check("ops/D1", "c.txt"), (0, "free"))
        self.assertEqual(self.listed(), ["S1 armed docs/ by R4: a.txt, b.txt"])

    def raw_db(self):
        """land.db opened without Store, which upgrades an older schema when it opens one."""
        return contextlib.closing(sqlite3.connect(next((self.base / "state").glob("pstack-t3/landing/*/land.db"))))

    def dumped(self):
        with self.raw_db() as db:
            return "\n".join(db.iterdump())

    def armed_log(self):
        return [row["id"] for row in self.ruling_rows("log") if (row["kind"], row["state"]) == ("reservation", "armed")]

    def check_with_dump_unchanged(self, holder, paths):
        before = self.dumped()
        answer = self.lease_check(holder, paths)
        self.assertEqual(self.dumped(), before)
        return answer

    def assert_reserved_for_two_hours(self, text):
        match = re.fullmatch(r"(?:land: )?paths reserved for docs/ by ruling R4 until (\d{4}-\d\d-\d\dT\d\d:\d\d)", text)
        self.assertIsNotNone(match, text)
        left = datetime.fromisoformat(match[1]).replace(tzinfo=timezone.utc) - datetime.now(timezone.utc)
        self.assertLess(abs(left - timedelta(hours=2)), timedelta(minutes=2))

    def test_lease_check_leaves_a_reservation_waiting_that_a_claim_would_arm(self):
        self.init()
        self.claim("engine/D1", "a.txt")
        self.assertEqual(self.reserve("docs/", "a.txt", "R4"), "S1")
        self.land("lease", "renew", "L1", "--ttl-hours", "0")
        self.assertEqual(self.listed(), ["S1 waiting docs/ by R4: a.txt"])
        for _ in range(2):
            self.assertEqual(self.check_with_dump_unchanged("ops/D2", "d.txt"), (0, "free"))
            code, refusal = self.check_with_dump_unchanged("engine/D9", "a.txt")
            self.assertEqual(code, 1)
            self.assert_reserved_for_two_hours(refusal)
            self.assertEqual(self.check_with_dump_unchanged("docs/D7", "a.txt"), (0, "free"))
        self.assertEqual(self.listed(), ["S1 waiting docs/ by R4: a.txt"])
        self.assertEqual(self.armed_log(), [])

    def test_a_reservations_hold_starts_at_the_first_claim_after_lease_checks(self):
        self.init()
        self.claim("engine/D1", "a.txt")
        self.assertEqual(self.reserve("docs/", "a.txt", "R4"), "S1")
        self.land("lease", "renew", "L1", "--ttl-hours", "0")
        for holder, paths in [("ops/D2", "d.txt"), ("engine/D9", "a.txt"), ("docs/D7", "a.txt")] * 2:
            self.lease_check(holder, paths)
        claimed = datetime.now(timezone.utc)
        self.assertEqual(self.claim("ops/D2", "d.txt"), "L2")
        row = self.ruling_rows("reservation")[0]
        armed = datetime.fromisoformat(row["armed"])
        self.assertGreaterEqual(armed, claimed)
        self.assertEqual(datetime.fromisoformat(row["expires"]) - armed, timedelta(hours=2))
        self.assertEqual(self.listed(), ["L2 active ops/D2: d.txt", "S1 armed docs/ by R4: a.txt"])
        self.assertEqual(self.armed_log(), [1])
        self.assert_reserved_for_two_hours(self.claim("engine/D9", "a.txt", ok=False))

    def test_lease_check_naming_an_overlapping_lease_claims_no_lease_arms_no_reservation_starts_no_hold_and_adds_no_log_row(self):
        self.init()
        self.claim("engine/D1", "a.txt")
        self.claim("ops/D1", "b.txt")
        self.assertEqual(self.reserve("docs/", "a.txt", "R4"), "S1")
        self.land("lease", "renew", "L1", "--ttl-hours", "0")
        self.assertEqual(self.check_with_dump_unchanged("engine/D9", "b.txt"), (1, "L2 held by ops/D1 on b.txt"))
        self.assertEqual(self.listed(), ["L2 active ops/D1: b.txt", "S1 waiting docs/ by R4: a.txt"])

    def test_lease_check_at_the_cap_claims_no_lease_arms_no_reservation_starts_no_hold_and_adds_no_log_row_and_the_refused_claim_arms(self):
        self.init()
        self.land("cap", "1")
        self.claim("ops/D1", "lib")
        self.assertEqual(self.reserve("docs/", "a.txt", "R1"), "S1")
        self.land("lease", "renew", "L1", "--ttl-hours", "0")
        at_cap = "repository at its cap: 1 of 1 changes in flight (S1 for docs/)"
        for _ in range(2):
            self.assertEqual(self.check_with_dump_unchanged("ops/D2", "c.txt"), (1, at_cap))
        self.assertEqual(self.listed(), ["S1 waiting docs/ by R1: a.txt"])
        self.assertEqual(self.claim("ops/D2", "c.txt", ok=False), f"land: {at_cap}")
        self.assertEqual(self.listed(), ["S1 armed docs/ by R1: a.txt"])
        self.assertEqual(self.armed_log(), [1])

    def test_lease_check_at_a_share_claims_no_lease_arms_no_reservation_starts_no_hold_and_adds_no_log_row(self):
        self.init()
        self.land("cap", "4")
        self.share("docs/", 2)
        self.claim("engine/D1", "a.txt")
        self.assertEqual(self.reserve("ops/", "a.txt", "R4"), "S1")
        self.claim("docs/D1", "b.txt")
        self.claim("docs/D2", "c.txt")
        self.land("lease", "renew", "L1", "--ttl-hours", "0")
        self.assertEqual(self.check_with_dump_unchanged("docs/D3", "lib"), (1, "docs/ is at its share: 2 of 2"))
        self.assertEqual(self.listed(), ["L2 active docs/D1: b.txt", "L3 active docs/D2: c.txt", "S1 waiting ops/ by R4: a.txt"])
        self.assertEqual(self.claim("docs/D3", "lib", ok=False), "land: docs/ is at its share: 2 of 2")

    def test_lease_check_answers_free_past_a_reservation_whose_hold_is_zero_hours(self):
        self.init()
        self.claim("engine/D1", "a.txt")
        self.assertEqual(self.reserve("docs/", "a.txt", "R4", "--ttl-hours", "0"), "S1")
        self.land("lease", "renew", "L1", "--ttl-hours", "0")
        self.assertEqual(self.check_with_dump_unchanged("engine/D9", "a.txt"), (0, "free"))
        self.assertEqual(self.claim("engine/D9", "a.txt"), "L2")

    def test_lease_check_on_an_older_store_upgrades_the_schema_and_leaves_lease_reservation_and_log_rows_unchanged(self):
        self.init()
        self.claim("engine/D1", "a.txt")
        self.assertEqual(self.reserve("docs/", "a.txt", "R4"), "S1")
        self.land("lease", "renew", "L1", "--ttl-hours", "0")
        self.rebuild_entry_without_autoincrement()

        def entry_sql():
            with self.raw_db() as db:
                return db.execute("SELECT sql FROM sqlite_master WHERE name = 'entry'").fetchone()[0]

        def rows():
            with self.raw_db() as db:
                return {table: db.execute(f"SELECT * FROM {table} ORDER BY rowid").fetchall()
                        for table in ("contract", "lease", "attempt", "log", "owner", "reservation", "share", "contest")}

        self.assertNotIn("AUTOINCREMENT", entry_sql())
        self.assertNotIn("title", entry_sql())
        before = rows()
        code, refusal = self.lease_check("engine/D9", "a.txt")
        self.assertEqual(code, 1)
        self.assert_reserved_for_two_hours(refusal)
        self.assertIn("AUTOINCREMENT", entry_sql())
        self.assertIn("title", entry_sql())
        self.assertEqual(rows(), before, "rows of every table except entry, which the schema upgrade rebuilds, and sqlite_sequence, which gains an entry row")
        with self.raw_db() as db:
            self.assertEqual(db.execute("SELECT id, holder FROM lease").fetchall(), [(1, "engine/D1")])
            self.assertEqual(db.execute("SELECT armed, expires FROM reservation").fetchall(), [("", "")])
            self.assertEqual(db.execute("SELECT count(*) FROM log WHERE state = 'armed'").fetchall(), [(0,)])

    def test_releasing_one_lease_leaves_a_reservation_waiting_on_another(self):
        self.init()
        self.claim("engine/D1", "a.txt")
        self.claim("ops/D1", "b.txt")
        self.assertEqual(self.reserve("docs/", "a.txt,b.txt", "R4"), "S1")
        self.land("lease", "release", "L1")
        self.assertEqual(self.listed(), [
            "L2 active ops/D1: b.txt",
            "S1 waiting docs/ by R4: a.txt, b.txt",
        ])
        self.land("lease", "release", "L2")
        self.assertEqual(self.listed(), ["S1 armed docs/ by R4: a.txt, b.txt"])

    def test_landing_an_entry_arms_a_reservation_that_was_waiting_on_its_lease(self):
        self.init()
        sha = self.worker("w1", {"a.txt": "landed\n"})
        self.claim("engine/D1", "a.txt")
        self.assertEqual(self.reserve("docs/", "a.txt", "R4"), "S1")
        self.land("submit", "--holder", "engine/D1", "--branch", "w1", "--sha", sha, "--lease", "L1", "--reviewer", REVIEWER)
        self.assertEqual(self.land("land"), "landed E1 (engine/D1)")
        self.assertEqual(self.listed(), ["S1 armed docs/ by R4: a.txt"])
        armed = next(row for row in self.ruling_rows("reservation") if row["id"] == 1)
        left = datetime.fromisoformat(armed["expires"]) - datetime.now(timezone.utc)
        self.assertLess(abs(left - timedelta(hours=2)), timedelta(minutes=1))

    def test_with_a_cap_of_one_two_waiting_reservations_arm_one_at_a_time_oldest_first(self):
        self.init()
        self.land("cap", "1")
        self.claim("ops/D1", "lib")
        self.assertEqual(self.reserve("docs/", "a.txt", "R1"), "S1")
        self.assertEqual(self.reserve("engine/", "b.txt", "R2"), "S2")
        self.assertEqual(self.listed(), ["L1 active ops/D1: lib", "S1 waiting docs/ by R1: a.txt", "S2 waiting engine/ by R2: b.txt"])
        self.land("lease", "release", "L1")
        self.assertEqual(self.lease_check("ops/D2", "c.txt"), (1, "repository at its cap: 1 of 1 changes in flight (S1 for docs/)"))
        self.assertEqual(self.listed(), ["S1 armed docs/ by R1: a.txt", "S2 waiting engine/ by R2: b.txt"])
        self.assertEqual(self.claim("docs/D7", "a.txt"), "L2")
        self.assertEqual(self.listed(), ["L2 active docs/D7: a.txt", "S2 waiting engine/ by R2: b.txt"])
        self.assertEqual(self.claim("engine/D3", "b.txt", ok=False), "land: repository at its cap: 1 of 1 changes in flight (docs/D7)")
        self.land("lease", "release", "L2")
        self.assertEqual(self.claim("engine/D3", "b.txt"), "L3")
        self.assertEqual(self.listed(), ["L3 active engine/D3: b.txt"])

    def test_two_coordinators_claiming_reserved_paths_at_once_leave_only_the_winners_lease(self):
        self.init()
        for n in range(1, 5):
            self.reserve("docs/", f"p{n}.txt", f"R{n}")
            results = self.concurrent(["lease", "claim", "--holder", f"engine/D{n}", "--paths", f"p{n}.txt"],
                                      ["lease", "claim", "--holder", f"docs/D{n}", "--paths", f"p{n}.txt"])
            (engine_code, _, engine_err), (docs_code, docs_out, _) = results
            self.assertEqual((engine_code, docs_code, docs_out), (1, 0, f"L{n}"), results)
            self.assertTrue(engine_err.startswith("land: paths "), engine_err)
        self.assertEqual(self.listed(), [f"L{n} active docs/D{n}: p{n}.txt" for n in range(1, 5)])

    def test_a_reservation_rerun_returns_it_and_an_ended_one_says_how_it_ended(self):
        self.init()
        self.assertEqual(self.reserve("docs/", "a.txt", "R4"), "S1")
        self.assertEqual(self.reserve("docs/", "a.txt", "R4"), "S1")
        self.assertEqual(self.reserve("engine/", "a.txt,b.txt", "R5", ok=False), "land: paths overlap S1 reserved for docs/ by ruling R4 on a.txt")
        self.assertEqual(self.land("lease", "unreserve", "S1", *ADMIN), "S1 lifted")
        self.assertEqual(self.land("lease", "unreserve", "S1", *ADMIN), "S1 lifted")
        self.assertEqual(self.reserve("docs/", "a.txt", "R4", ok=False), "land: S1 for ruling R4 was lifted")
        self.assertEqual(self.claim("engine/D3", "a.txt"), "L1")
        self.assertEqual(self.reserve("docs/", "b.txt", "R6", "--ttl-hours", "0"), "S2")
        self.assertEqual(self.reserve("docs/", "b.txt", "R6", ok=False), "land: S2 for ruling R6 expired")
        self.assertEqual(self.claim("engine/D4", "b.txt"), "L2")
        self.assertRegex(self.land("lease", "unreserve", "S2", *ADMIN), r"^S2 expired at \d{4}-\d\d-\d\dT\d\d:\d\d$")
        self.assertEqual(self.land("lease", "unreserve", "S9", *ADMIN, ok=False), "land: no S9")
        self.assertEqual(self.reserve("docs", "c.txt", "R7", ok=False), "land: 'docs' is not a holder prefix such as docs/")
        self.assertEqual(self.reserve("docs/", "c.txt", "R8"), "S3")
        self.assertEqual(self.claim("docs/D7", "c.txt"), "L3")
        self.assertEqual(self.reserve("docs/", "c.txt", "R8"), "S3 was claimed in full")

    def test_a_reservation_refuses_the_whole_repository(self):
        self.init()
        refusal = "land: a reservation names the contested paths; it cannot hold the whole repository"
        self.assertEqual(self.reserve("docs/", "", "R4", ok=False), refusal)
        self.assertEqual(self.reserve("docs/", "a.txt,.", "R4", ok=False), refusal)
        self.assertEqual(self.claim("engine/D3", "lib"), "L1")
        self.assertEqual(self.listed(), ["L1 active engine/D3: lib"])

    def test_shares_refuse_a_sum_over_the_cap_and_admission_refuses_a_claim_over_a_share(self):
        self.init()
        self.land("cap", "4")
        self.assertEqual(self.share("docs/", 2), "docs/ share is 2")
        self.assertEqual(self.share("engine/", 3, ok=False), "land: shares would add up to 5, over the cap of 4")
        self.assertEqual(self.share("engine/", 2), "engine/ share is 2")
        self.assertEqual(self.share("engine/", 2), "engine/ share is 2")
        self.assertEqual(self.claim("docs/D1", "a.txt"), "L1")
        self.assertEqual(self.claim("docs/D2", "b.txt"), "L2")
        self.assertEqual(self.claim("docs/D3", "lib", ok=False), "land: docs/ is at its share: 2 of 2")
        self.assertEqual(self.lease_check("docs/D3", "lib"), (1, "docs/ is at its share: 2 of 2"))
        self.assertEqual(self.claim("ops/D1", "lib"), "L3")
        self.assertEqual(self.share("docs/", 1, "--clear", ok=False), "land: --clear takes 0")
        self.assertEqual(self.share("docs/", 0, "--clear"), "docs/ share cleared")
        self.assertEqual(self.claim("docs/D3", "c.txt"), "L4")
        self.assertEqual([(row["prefix"], row["count"]) for row in self.ruling_rows("share")], [("engine/", 2)])

    def test_a_cap_below_the_share_sum_is_refused_and_zero_still_clears(self):
        self.init()
        self.land("cap", "4")
        self.share("docs/", 2)
        self.share("engine/", 2)

        def snapshot():
            store = land.Store.for_repo(self.work)
            try:
                shares = [(row["prefix"], row["count"]) for row in store.db.execute(
                    "SELECT prefix, count FROM share ORDER BY prefix")]
                log = [(row["kind"], row["id"], row["state"], row["note"]) for row in store.db.execute(
                    "SELECT kind, id, state, note FROM log ORDER BY at")]
                return store.contract.get("cap"), shares, log
            finally:
                store.db.close()

        before = snapshot()
        refusal = "land: shares add up to 4 (docs/ 2, engine/ 2), over the cap of 3"
        self.assertEqual(self.land("cap", "3", ok=False), refusal)
        self.assertEqual(snapshot(), before)
        self.assertIn("changes in flight: 0 of 4", self.land("status"))
        self.assertEqual(self.land("cap", "4"), "repository cap is now 4 changes in flight")
        self.assertEqual(self.land("cap", "0"), "repository cap cleared")
        cap, shares, _log = snapshot()
        self.assertIsNone(cap)
        self.assertEqual(shares, [("docs/", 2), ("engine/", 2)])
        self.assertNotIn("of ", self.land("status"))
        self.assertEqual(self.land("cap", "3", ok=False), refusal)
        self.assertEqual(self.land("cap", "4"), "repository cap is now 4 changes in flight")

    def test_an_armed_reservation_counts_toward_its_prefixs_share_until_the_winner_claims(self):
        self.init()
        self.share("docs/", 1)
        self.reserve("docs/", "a.txt", "R4")
        self.assertEqual(self.claim("docs/D9", "b.txt", ok=False), "land: docs/ is at its share: 1 of 1")
        self.assertEqual(self.claim("docs/D9", "a.txt"), "L1")
        self.assertEqual(self.claim("docs/D10", "b.txt", ok=False), "land: docs/ is at its share: 1 of 1")

    def reservation_counts_again_after_its_lease_ends(self, end, limit, refused, outsider):
        self.init()
        limit()
        self.assertEqual(self.reserve("docs/", "a.txt,b.txt", "R4"), "S1")
        self.assertEqual(self.claim("docs/D7", "a.txt", *(["--ttl-hours", "0"] if end == "expire" else [])), "L1")
        if end == "release":
            self.assertEqual(self.land("lease", "release", "L1"), "L1 released")
        self.assertEqual(self.listed(), ["S1 armed docs/ by R4: b.txt"])
        self.assertEqual(self.claim(outsider, "lib", ok=False), f"land: {refused}")
        self.assertEqual(self.lease_check(outsider, "lib"), (1, refused))
        self.assertEqual(self.claim("docs/D7", "b.txt"), "L2")
        self.assertEqual(self.listed(), ["L2 active docs/D7: b.txt"])
        self.assertEqual(self.ruling_rows("reservation")[0]["state"], "claimed")

    def test_a_reservation_counts_toward_the_cap_again_after_its_taken_lease_is_released(self):
        self.reservation_counts_again_after_its_lease_ends(
            "release", lambda: self.land("cap", "1"), "repository at its cap: 1 of 1 changes in flight (S1 for docs/)", "engine/D3")
        self.assertEqual(self.land("status"), "push mode onto refs/remotes/origin/main. leases held: 1, changes in flight: 1 of 1.")

    def test_a_reservation_counts_toward_the_cap_again_after_its_taken_lease_expires(self):
        self.reservation_counts_again_after_its_lease_ends(
            "expire", lambda: self.land("cap", "1"), "repository at its cap: 1 of 1 changes in flight (S1 for docs/)", "engine/D3")

    def test_a_reservation_counts_toward_its_share_again_after_its_taken_lease_is_released(self):
        self.reservation_counts_again_after_its_lease_ends(
            "release", lambda: self.share("docs/", 1), "docs/ is at its share: 1 of 1", "docs/D8")

    def test_a_reservation_counts_toward_its_share_again_after_its_taken_lease_expires(self):
        self.reservation_counts_again_after_its_lease_ends(
            "expire", lambda: self.share("docs/", 1), "docs/ is at its share: 1 of 1", "docs/D8")

    def test_a_reservation_stays_out_of_the_count_while_any_lease_taken_from_it_is_live(self):
        self.init()
        self.land("cap", "2")
        self.reserve("docs/", "a.txt,b.txt,c.txt", "R4")
        self.assertEqual(self.claim("docs/D7", "a.txt"), "L1")
        self.assertEqual(self.claim("docs/D7", "b.txt"), "L2")
        self.land("lease", "release", "L1")
        self.assertEqual(self.claim("engine/D3", "lib"), "L3")
        self.land("lease", "release", "L2")
        self.assertEqual(self.claim("ops/D1", "d.txt", ok=False),
                         "land: repository at its cap: 2 of 2 changes in flight (engine/D3, S1 for docs/)")
        self.assertEqual(self.claim("docs/D7", "c.txt"), "L4")
        self.assertEqual(self.listed(), ["L3 active engine/D3: lib", "L4 active docs/D7: c.txt"])

    def test_the_winner_renews_its_expired_lease_taken_from_a_reservation_at_a_full_cap(self):
        self.init()
        self.land("cap", "1")
        self.reserve("docs/", "a.txt,b.txt", "R4")
        self.assertEqual(self.claim("docs/D7", "a.txt", "--ttl-hours", "0"), "L1")
        self.assertEqual(self.land("lease", "renew", "L1"), "L1 renewed")
        self.assertEqual(self.claim("engine/D3", "lib", ok=False), "land: repository at its cap: 1 of 1 changes in flight (docs/D7)")
        self.assertEqual(self.listed(), ["L1 active docs/D7: a.txt", "S1 armed docs/ by R4: b.txt"])

    def contest_holds_both_holders(self, mode, **extra):
        self.init(mode=mode, **extra)
        self.assertEqual(self.queue_one(path="a.txt", name="w1", holder="docs/D7"), "E1")
        self.assertEqual(self.contest("--holders", "docs/D7,engine/D3"), "C1")
        self.assertEqual(self.contest("--holders", "engine/D3,docs/D7"), "C1")
        self.assertEqual(self.queue_one(path="b.txt", name="w2", holder="engine/D3"), "E2")
        self.assertEqual(self.land("land"), "still queued: E1 (held by C1), E2 (held by C1)")
        self.assertEqual(self.land("status", "--holder", "docs/D7").split(" (")[0], "E1 queued")
        self.assertEqual(self.land("status", "--holder", "engine/D3").split(" (")[0], "E2 queued")

    def test_an_open_contest_holds_both_holders_out_of_a_push_mode_batch(self):
        self.contest_holds_both_holders("push", batch=4)
        self.assertEqual(self.queue_one(path="lib/x.py", name="w3", holder="ops/D1"), "E3")
        self.assertEqual(self.land("land"), "landed E3 (ops/D1)\nstill queued: E1 (held by C1), E2 (held by C1)")
        self.assertEqual(self.origin_log(), ["w3", "init"])

    def test_an_open_contest_holds_both_holders_in_local_mode(self):
        self.contest_holds_both_holders("local", trunk="lane", base="main")
        self.assertEqual(sh("git", "rev-parse", "refs/landing/lane", cwd=self.work), sh("git", "rev-parse", "main", cwd=self.work))

    def test_an_open_contest_keeps_both_holders_out_of_pr_opening_in_human_mode(self):
        with self.fake_gh():
            self.contest_holds_both_holders("human")
            calls = (self.base / "gh-calls").read_text() if (self.base / "gh-calls").exists() else ""
            self.assertNotIn("pr create", calls)
            self.assertFalse(self.ref_exists("refs/heads/landing/e1", self.base / "origin.git"))

    def test_an_open_contest_keeps_both_holders_out_of_pr_opening_in_merge_mode(self):
        with self.fake_gh():
            self.contest_holds_both_holders("merge")
            self.assertNotIn("pr create", (self.base / "gh-calls").read_text())
            self.assertFalse((self.base / "merge-calls").exists())

    def test_a_settled_contest_holds_the_second_holder_until_the_first_lands_after_a_bounce(self):
        self.init()
        self.queue_one(path="a.txt", text="BROKEN\n", name="w1", holder="docs/D7")
        self.contest("--holders", "docs/D7,engine/D3")
        self.queue_one(path="b.txt", name="w2", holder="engine/D3")
        settled = "C1: docs/D7 lands first, engine/D3 waits"
        self.assertEqual(self.contest("--settle", "C1", "--first", "docs/D7"), settled)
        self.assertEqual(self.contest("--settle", "C1", "--first", "docs/D7"), settled)
        out = self.land("land")
        self.assertTrue(out.startswith("bounced E1 (docs/D7): checks failed:"), out)
        self.assertTrue(out.endswith("\nstill queued: E2 (held by C1)"), out)
        (self.base / "w1" / "a.txt").write_text("fixed\n")
        fixed = self.commit("fix", cwd=self.base / "w1")
        self.assertEqual(self.land("submit", "--holder", "docs/D7", "--branch", "w1", "--sha", fixed, "--lease", "L1", "--reviewer", REVIEWER), "E3")
        self.assertEqual(self.land("land"), "landed E3 (docs/D7), E2 (engine/D3)")
        self.assertEqual(self.origin_log(), ["w2", "fix", "w1", "init"])
        self.assertEqual(self.contest("--settle", "C1", "--first", "docs/D7"), settled)
        self.assertEqual(self.contest("--settle", "C1", "--first", "engine/D3", ok=False), "land: C1 is done: docs/D7 landed")

    def test_a_contest_settles_again_in_reverse_and_refuses_an_order_that_closes_a_cycle(self):
        self.init()
        self.assertEqual(self.contest("--holders", "docs/D7,engine/D3"), "C1")
        self.contest("--settle", "C1", "--first", "docs/D7")
        self.assertEqual(self.contest("--settle", "C1", "--first", "engine/D3"), "C1: engine/D3 lands first, docs/D7 waits")
        self.assertEqual(self.contest("--holders", "docs/D7,ops/D1"), "C2")
        self.contest("--settle", "C2", "--first", "docs/D7")
        self.assertEqual(self.contest("--holders", "ops/D1,engine/D3"), "C3")
        self.assertEqual(self.contest("--settle", "C3", "--first", "ops/D1", ok=False),
                         "land: C3 cannot order ops/D1 before engine/D3: it closes a cycle with C1, C2")
        self.assertEqual(self.contest("--settle", "C3", "--first", "engine/D3"), "C3: engine/D3 lands first, ops/D1 waits")
        self.assertEqual(self.contest("--cancel", "C1"), "C1 cancelled")
        self.assertEqual(self.contest("--settle", "C3", "--first", "ops/D1"), "C3: ops/D1 lands first, engine/D3 waits")
        self.assertEqual(self.contest("--settle", "C1", "--first", "docs/D7", ok=False), "land: C1 is cancelled")
        self.assertEqual(self.contest("--settle", "C2", "--first", "docs/D9", ok=False), "land: docs/D9 is not a holder in C2")
        self.assertEqual(self.contest("--holders", "docs/D7,docs/D7", ok=False), "land: a contest needs two different holders")
        self.assertEqual(self.contest("--cancel", "C9", ok=False), "land: no C9")

    def test_a_contest_refuses_work_already_landed_and_ignores_a_bounce(self):
        self.init()
        self.queue_one(path="a.txt", name="w1", holder="docs/D7")
        self.queue_one(path="b.txt", text="BROKEN\n", name="w2", holder="engine/D3")
        self.land("land")
        self.assertEqual(self.contest("--holders", "engine/D3,docs/D7", ok=False), "land: docs/D7 has E1 landed; there is nothing left to order")
        self.assertEqual(self.contest("--holders", "engine/D3,ops/D1"), "C1")

    def test_a_contest_waits_for_a_running_land_to_release_the_queue_lock(self):
        import fcntl
        self.init()
        store = land.Store.for_repo(self.work)
        with open(store.dir / ".queue.lock", "a") as handle:
            fcntl.flock(handle, fcntl.LOCK_EX)
            proc = subprocess.Popen([sys.executable, str(SCRIPT), "--repo", str(self.work), "contest", "--holders", "docs/D7,engine/D3", *ADMIN],
                                    stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, env=os.environ.copy())
            time.sleep(1)
            self.assertIsNone(proc.poll())
            self.assertEqual(self.ruling_rows("contest"), [])
        out, err = proc.communicate(timeout=20)
        store.db.close()
        self.assertEqual((proc.returncode, out.strip()), (0, "C1"), err)

    def test_every_ruling_write_needs_an_owner(self):
        self.init()
        for args in (["lease", "reserve", "--for", "docs/", "--paths", "a.txt", "--ruling", "R1"], ["lease", "unreserve", "S1"],
                     ["share", "--for", "docs/", "1"], ["contest", "--holders", "a/D1,b/D1"], ["contest", "--cancel", "C1"]):
            self.assertIn("--owner", self.land(*args, ok=False))

    def test_paused_ruling_writes_from_a_replaced_admin_change_nothing(self):
        self.init()
        self.land("cap", "4")
        self.share("docs/", 1)
        self.contest("--holders", "docs/D7,engine/D3")
        self.contest("--settle", "C1", "--first", "docs/D7")
        tables = ("share", "reservation", "contest")
        before = {table: self.ruling_rows(table) for table in tables}
        commands = [
            ["share", "--for", "docs/", "2", *ADMIN],
            ["lease", "reserve", "--for", "docs/", "--paths", "a.txt", "--ruling", "R9", *ADMIN],
            ["contest", "--settle", "C1", "--first", "engine/D3", *ADMIN],
        ]
        running = []
        for number, args in enumerate(commands):
            case = self.base / f"paused{number}"
            case.mkdir()
            proc = subprocess.Popen([sys.executable, str(Path(__file__).resolve()), "--paused-child", str(case), "--repo", str(self.work), *args],
                                    stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, env=os.environ.copy())
            running.append((case, proc))
        for case, proc in running:
            deadline = time.monotonic() + 20
            while not (case / "paused").exists():
                if proc.poll() is not None or time.monotonic() > deadline:
                    self.fail(f"{case.name} did not pause: {proc.communicate()}")
                time.sleep(0.01)
        self.assertEqual(self.land("owner", "--prefix", ".admin/", "--generation", "2"), ".admin/ at generation 2")
        for case, proc in running:
            (case / "proceed").touch()
            out, err = proc.communicate(timeout=30)
            self.assertEqual((proc.returncode, err.strip()), (1, "land: owner .admin/@1 is stale; .admin/ is at generation 2"), out)
        self.assertEqual({table: self.ruling_rows(table) for table in tables}, before)
        current = ("--owner", ".admin/@2")
        self.assertEqual(self.land("share", "--for", "docs/", "2", *current), "docs/ share is 2")
        self.assertEqual(self.land("lease", "reserve", "--for", "docs/", "--paths", "a.txt", "--ruling", "R9", *current), "S1")
        self.assertEqual(self.land("contest", "--settle", "C1", "--first", "engine/D3", *current), "C1: engine/D3 lands first, docs/D7 waits")
        self.assertEqual(self.land("contest", "--cancel", "C1", *ADMIN, ok=False), "land: owner .admin/@1 is stale; .admin/ is at generation 2")

    def test_mode_merge_after_init_in_human_mode_swaps_a_disallowed_method(self):
        with self.fake_gh():
            self.allow_methods(squash=True)
            self.init(mode="human")
            self.assertEqual(self.stored_merge_method(), "merge")
            self.assertEqual(self.land("mode", "merge"), "landing mode is now merge, merging with --squash")
            self.assertEqual(self.stored_merge_method(), "squash")
            self.assertEqual(self.land("mode", "human", "--merge-method", "merge", ok=False),
                             "land: repository does not allow merge; allowed: squash")
            self.assertEqual(self.stored_merge_method(), "squash")
            self.assertTrue(self.land("status").startswith("merge mode onto"))
            self.assertEqual(self.land("mode", "human", "--merge-method", "squash"), "landing mode is now human, merging with --squash")

    def test_init_in_any_mode_refuses_a_merge_method_the_repository_disallows(self):
        with self.fake_gh():
            self.allow_methods(squash=True)
            self.assertEqual(self.land("init", "--trunk", "main", "--mode", "human", "--check", "./check.sh", "--merge-method", "merge", ok=False),
                             "land: repository does not allow merge; allowed: squash")
            self.assertIn("has no landing contract", self.land("status", ok=False))
            self.init(mode="push", merge_method="squash")
            self.assertEqual(self.stored_merge_method(), "squash")


    def test_a_settled_contest_keeps_its_order_once_the_first_holders_pr_is_open(self):
        with self.fake_gh():
            self.init(mode="human")
            self.queue_one(path="a.txt", name="w1", holder="docs/D7")
            self.contest("--holders", "docs/D7,engine/D3")
            self.queue_one(path="b.txt", name="w2", holder="engine/D3")
            self.contest("--settle", "C1", "--first", "docs/D7")
            self.assertEqual(self.land("land"), "opened PRs for E1 (docs/D7) https://github.com/o/r/pull/9\nstill queued: E2 (held by C1)")
            self.assertEqual(self.contest("--settle", "C1", "--first", "engine/D3", ok=False),
                             "land: C1 cannot put engine/D3 first: docs/D7 has E1 awaiting-merge")
            self.assertEqual(self.contest("--settle", "C1", "--first", "docs/D7"), "C1: docs/D7 lands first, engine/D3 waits")

    def test_mode_merge_checks_the_method_stored_when_it_writes(self):
        with self.fake_gh():
            self.allow_methods(squash=True)
            self.init(mode="human", merge_method="squash")
            self.pause_repo_view()
            (self.base / "pause-repo-view").write_text("")
            child = subprocess.Popen([sys.executable, str(SCRIPT), "--repo", str(self.work), "mode", "merge"],
                                     stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, env=os.environ.copy())
            try:
                deadline = time.monotonic() + 10
                while not (self.base / "repo-view-waiting").exists():
                    if child.poll() is not None or time.monotonic() > deadline:
                        self.fail(f"repo view did not pause: {child.communicate()}")
                    time.sleep(0.01)
                (self.base / "pause-repo-view").unlink()
                self.init(mode="human")
                self.assertEqual(self.stored_merge_method(), "merge")
                (self.base / "repo-view-release").write_text("")
                out, err = child.communicate(timeout=10)
            finally:
                if child.poll() is None:
                    child.kill()
                    child.communicate()
            self.assertEqual((child.returncode, out.strip()), (0, "landing mode is now merge, merging with --squash"), err)
            self.assertEqual(self.stored_merge_method(), "squash")

    def test_mode_local_checks_an_explicit_merge_method(self):
        with self.fake_gh():
            self.allow_methods(squash=True)
            self.init(mode="local", base="main", merge_method="squash")
            self.assertEqual(self.land("mode", "local", "--merge-method", "merge", ok=False),
                             "land: repository does not allow merge; allowed: squash")
            self.assertEqual(self.stored_merge_method(), "squash")

    def test_a_settled_contest_keeps_its_order_while_a_failed_pr_still_has_auto_merge(self):
        with self.fake_gh():
            (self.base / "required-checks").write_text("")
            (self.base / "disable-auto-fails").write_text("API unavailable")
            self.arm_auto_merge()
            self.init(mode="merge")
            self.queue_one(path="a.txt", name="w1", holder="docs/D7")
            self.contest("--holders", "docs/D7,engine/D3")
            self.queue_one(path="b.txt", name="w2", holder="engine/D3")
            self.contest("--settle", "C1", "--first", "docs/D7")
            self.land("land")
            self.land("land")
            (self.base / "checks").write_text("failed")
            self.assertIn("Auto-merge is still enabled: API unavailable", self.land("land"))
            sha = self.land("status", "--holder", "docs/D7").split(", ")[1][:12]
            self.assertEqual(self.land("submit", "--holder", "docs/D7", "--branch", "w1", "--sha", sha, "--lease", "L1", "--reviewer", REVIEWER),
                             "E1 already awaiting-merge")
            self.assertEqual(self.contest("--settle", "C1", "--first", "engine/D3", ok=False),
                             "land: C1 cannot put engine/D3 first: docs/D7 has E1 awaiting-merge")

if __name__ == "__main__":
    if sys.argv[1:2] == ["--paused-child"]:
        paused_child(sys.argv[2], sys.argv[3:])
    unittest.main()
