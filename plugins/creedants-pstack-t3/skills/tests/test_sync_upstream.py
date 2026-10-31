import hashlib
import json
import os
import shutil
import stat
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts/sync_upstream.py"
sys.path.insert(0, str(ROOT / "scripts"))

import build  # noqa: E402
import sync_upstream  # noqa: E402

GIT_ENV = {
    **{name: value for name, value in os.environ.items() if not name.startswith("GIT_")},
    "GIT_CONFIG_GLOBAL": os.devnull,
    "GIT_CONFIG_SYSTEM": os.devnull,
    "GIT_AUTHOR_NAME": "Fixture",
    "GIT_AUTHOR_EMAIL": "fixture@example.invalid",
    "GIT_COMMITTER_NAME": "Fixture",
    "GIT_COMMITTER_EMAIL": "fixture@example.invalid",
    "LC_ALL": "C",
}
PLUGIN = "pstack/.cursor-plugin/plugin.json"
SKILL = "---\nname: fixture\ndescription: A fixture skill.\n---\n\n# Fixture\n\n"
PINNED_TREE = {
    "other/notes.md": "upstream other/notes.md\n",
    PLUGIN: '{"name": "pstack", "version": "1.0.0"}\n',
    "pstack/README.md": "upstream README.md\n",
    "pstack/agents/persona.md": "upstream agents/persona.md\n",
    "pstack/automations/nightly/skills/job.md": "upstream automations job.md\n",
    "pstack/skills/alpha/SKILL.md": SKILL + "upstream alpha/SKILL.md\n",
    "pstack/skills/alpha/both.md": "upstream alpha/both.md\n",
    "pstack/skills/beta/SKILL.md": SKILL + "upstream beta/SKILL.md\n",
    "pstack/skills/beta/old.md": "upstream beta/old.md\n",
    "pstack/skills/gone/deep/file.md": "upstream gone/deep/file.md\n",
    "pstack/skills/gone/kept.md": "upstream gone/kept.md\n",
    "pstack/skills/setup-pstack/SKILL.md": SKILL + "upstream setup-pstack/SKILL.md\n",
}
T3_TREE = {
    "t3/added/alpha/both.md": "t3 added alpha/both.md\n",
    "t3/agents/persona.md": "t3 agents/persona.md\n",
    "t3/overrides/alpha/SKILL.md": SKILL + "t3 overrides alpha/SKILL.md\n",
    "t3/overrides/alpha/both.md": "t3 overrides alpha/both.md\n",
    "t3/overrides/gone/kept.md": "t3 overrides gone/kept.md\n",
    "t3/removed.txt": "# Upstream paths pstack-t3 does not ship.\ngone\n",
    "t3/runtime.md": SKILL + "t3 runtime.md\n",
    "t3/scripts/roles.py": "# t3 scripts/roles.py\n",
    "t3/setup.md": SKILL + "t3 setup.md\n",
}
RENDERED_FROM = {
    "alpha/SKILL.md": "t3/overrides/alpha/SKILL.md",
    "alpha/both.md": "t3/added/alpha/both.md",
    "beta/SKILL.md": "vendor/pstack/skills/beta/SKILL.md",
    "beta/old.md": "vendor/pstack/skills/beta/old.md",
    "gone/deep/file.md": None,
    "gone/kept.md": "t3/overrides/gone/kept.md",
    "setup-pstack/SKILL.md": "t3/setup.md",
}
LAYERS = sync_upstream.Layers(
    hand_ported={"agents/persona.md": "t3/agents/persona.md", "skills/setup-pstack/SKILL.md": "t3/setup.md"},
    added=frozenset({"alpha/both.md", "setup-pstack/SKILL.md"}),
    overrides=frozenset({"alpha/SKILL.md", "alpha/both.md", "gone/kept.md"}),
    removed=frozenset({"gone", "beta/old.md"}),
)
CLASSIFIED = (
    ("pstack/skills/alpha/SKILL.md", ("overridden", "t3/overrides/alpha/SKILL.md")),
    ("pstack/skills/alpha/both.md", ("overridden", "t3/added/alpha/both.md")),
    ("pstack/skills/gone/kept.md", ("overridden", "t3/overrides/gone/kept.md")),
    ("pstack/skills/setup-pstack/SKILL.md", ("overridden", "t3/setup.md")),
    ("pstack/agents/persona.md", ("overridden", "t3/agents/persona.md")),
    ("pstack/skills/gone/deep/file.md", ("dropped", None)),
    ("pstack/skills/beta/old.md", ("dropped", None)),
    ("pstack/skills/beta/SKILL.md", ("unchanged", None)),
    ("pstack/skills/gone-later/file.md", ("unchanged", None)),
    ("pstack/skills/top-level.md", ("unchanged", None)),
    ("pstack/agents/unported.md", ("not-shipped", None)),
    ("pstack/README.md", ("not-shipped", None)),
    ("pstack/automations/nightly/skills/alpha/SKILL.md", ("not-shipped", None)),
    ("pstack/skills/alpha/__pycache__/SKILL.md", ("not-shipped", None)),
    ("pstack/skills", ("not-shipped", None)),
)


def git(directory, *arguments):
    return subprocess.run(
        ("git", *arguments), cwd=directory, env=GIT_ENV, check=True, capture_output=True, text=True
    ).stdout.strip()


def write_tree(base, files):
    for name, text in files.items():
        target = base / name
        if text is None:
            target.unlink()
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text)


def commit(repository, files):
    write_tree(repository, files)
    git(repository, "add", "--all")
    git(repository, "commit", "--quiet", "--message", "change")
    return git(repository, "rev-parse", "HEAD")


def new_upstream(directory):
    repository = Path(directory) / "upstream"
    repository.mkdir()
    git(repository, "init", "--quiet", "--initial-branch", "main")
    return repository, commit(repository, PINNED_TREE)


def new_checkout(directory, repository, pinned):
    root = Path(directory) / "checkout"
    (root / "scripts").mkdir(parents=True)
    shutil.copy(SCRIPT, root / "scripts/sync_upstream.py")
    shutil.copy(ROOT / "scripts/build.py", root / "scripts/build.py")
    write_tree(root, T3_TREE)
    write_tree(root / "vendor", {name: text for name, text in PINNED_TREE.items() if name.startswith("pstack/")})
    meta = {"repository": str(repository), "commit": pinned, "path": "pstack", "version": "1.0.0"}
    (root / "upstream.json").write_text(json.dumps(meta, indent=2) + "\n")
    return root


def snapshot(root):
    return {
        path.relative_to(root).as_posix(): (
            stat.S_IMODE(path.lstat().st_mode),
            hashlib.sha256(path.read_bytes()).hexdigest() if path.is_file() else None,
        )
        for path in root.rglob("*")
    }


def last_line(path):
    return path.read_text().splitlines()[-1]


class CheckoutCase(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.directory = Path(temporary.name)
        self.upstream, self.pinned = new_upstream(self.directory)
        self.root = new_checkout(self.directory, self.upstream, self.pinned)
        self.scratch = self.directory / "scratch"
        self.scratch.mkdir()

    def sync(self, *flags, **environment):
        # PYTHONDONTWRITEBYTECODE in a developer's shell would hide a script that writes __pycache__.
        inherited = {name: value for name, value in GIT_ENV.items() if not name.startswith("PYTHON")}
        return subprocess.run(
            [sys.executable, str(self.root / "scripts/sync_upstream.py"), *flags],
            cwd=self.root,
            env={**inherited, "TMPDIR": str(self.scratch), **environment},
            capture_output=True,
            text=True,
        )


class CheckTest(CheckoutCase):
    def check(self, *flags, **environment):
        return self.sync("--check", *flags, **environment)

    def rows(self, files, version="1.0.0"):
        head = commit(self.upstream, files)
        result = self.check()
        self.assertEqual((result.returncode, result.stderr), (0, ""))
        header, *rows = result.stdout.splitlines()
        self.assertEqual(header, f"upstream main: {self.pinned[:12]} -> {head[:12]}{version and f' ({version})'}")
        return rows

    def failure(self, *flags, **environment):
        result = self.check(*flags, **environment)
        self.assertEqual((result.returncode, result.stdout), (1, ""))
        return result.stderr

    def test_up_to_date(self):
        result = self.check()
        self.assertEqual((result.returncode, result.stdout, result.stderr), (0, f"up to date ({self.pinned[:12]})\n", ""))

    def test_a_changed_overridden_file(self):
        self.assertEqual(
            self.rows({"pstack/skills/alpha/SKILL.md": "edited\n"}),
            ["changed  pstack/skills/alpha/SKILL.md  overridden by t3/overrides/alpha/SKILL.md"],
        )

    def test_a_changed_file_that_ships_unchanged(self):
        self.assertEqual(
            self.rows({"pstack/skills/beta/SKILL.md": "edited\n"}),
            ["changed  pstack/skills/beta/SKILL.md  ships unchanged"],
        )

    def test_an_added_file(self):
        self.assertEqual(
            self.rows({"pstack/skills/beta/new.md": "added\n"}),
            ["added    pstack/skills/beta/new.md  ships unchanged"],
        )

    def test_a_removed_file(self):
        self.assertEqual(
            self.rows({"pstack/skills/beta/old.md": None}),
            ["removed  pstack/skills/beta/old.md  ships unchanged"],
        )

    def test_a_path_under_a_directory_in_removed_txt(self):
        self.assertEqual(
            self.rows({"pstack/skills/gone/deep/file.md": "edited\n", "pstack/skills/gone/new.md": "added\n"}),
            [
                "changed  pstack/skills/gone/deep/file.md  dropped by t3/removed.txt",
                "added    pstack/skills/gone/new.md  dropped by t3/removed.txt",
            ],
        )

    def test_paths_that_never_ship_and_paths_ported_by_hand(self):
        self.assertEqual(
            self.rows(
                {
                    "pstack/README.md": "edited\n",
                    "pstack/agents/persona.md": "edited\n",
                    "pstack/agents/unported.md": "added\n",
                    "pstack/automations/nightly/skills/job.md": "edited\n",
                    "pstack/skills/setup-pstack/SKILL.md": "edited\n",
                }
            ),
            [
                "changed  pstack/README.md  not shipped",
                "changed  pstack/agents/persona.md  overridden by t3/agents/persona.md",
                "added    pstack/agents/unported.md  not shipped",
                "changed  pstack/automations/nightly/skills/job.md  not shipped",
                "changed  pstack/skills/setup-pstack/SKILL.md  overridden by t3/setup.md",
            ],
        )

    def test_each_row_names_the_file_the_build_renders(self):
        commit(self.upstream, {f"pstack/skills/{key}": "edited upstream\n" for key in RENDERED_FROM})
        report = json.loads(self.check("--json").stdout)
        claimed = {
            entry["path"][len("pstack/skills/") :]: {
                "overridden": entry["t3_path"],
                "unchanged": f"vendor/{entry['path']}",
                "dropped": None,
            }[entry["handling"]]
            for entry in report["changes"]
        }
        self.assertEqual(claimed, RENDERED_FROM)
        rendered = self.directory / "rendered"
        subprocess.run(
            [sys.executable, "-B", "-c", "import pathlib, sys, build; build.render(pathlib.Path(sys.argv[1]))", str(rendered)],
            cwd=self.root / "scripts",
            check=True,
        )
        for key, source in RENDERED_FROM.items():
            with self.subTest(path=key):
                if source is None:
                    self.assertFalse((rendered / key).exists())
                else:
                    self.assertEqual(last_line(rendered / key), last_line(self.root / source))

    def test_a_commit_that_leaves_the_prefix_alone(self):
        self.assertEqual(self.rows({"other/notes.md": "edited\n"}), ["no changes under pstack/"])
        report = json.loads(self.check("--json").stdout)
        self.assertEqual((report["up_to_date"], report["changes"]), (False, []))

    def test_a_filename_with_a_space_and_a_newline_stays_one_row(self):
        name = "pstack/skills/beta/odd name\nadded    pstack/skills/alpha/SKILL.md  ships unchanged"
        self.assertEqual(self.rows({name: "added\n"}), [f"added    {json.dumps(name)}  ships unchanged"])
        self.assertEqual(json.loads(self.check("--json").stdout)["changes"][0]["path"], name)

    def test_a_filename_with_a_space_is_quoted(self):
        self.assertEqual(
            self.rows({"pstack/skills/beta/two words.md": "added\n"}),
            ['added    "pstack/skills/beta/two words.md"  ships unchanged'],
        )

    def test_a_fixed_copy_missing_from_t3_overrides_nothing(self):
        (self.root / "t3/setup.md").unlink()
        self.assertEqual(
            self.rows({"pstack/skills/setup-pstack/SKILL.md": "edited\n"}),
            ["changed  pstack/skills/setup-pstack/SKILL.md  ships unchanged"],
        )

    def test_the_header_names_the_new_version_when_upstream_states_one(self):
        self.assertEqual(
            self.rows({PLUGIN: '{"name": "pstack", "version": "1.1.0"}\n'}, version="1.1.0"),
            [f"changed  {PLUGIN}  not shipped"],
        )
        self.assertEqual(self.rows({PLUGIN: None}, version=""), [f"removed  {PLUGIN}  not shipped"])

    def test_json_holds_the_same_report(self):
        up_to_date = {
            "repository": str(self.upstream),
            "ref": "main",
            "pinned": self.pinned,
            "commit": self.pinned,
            "version": "1.0.0",
            "up_to_date": True,
            "changes": [],
        }
        result = self.check("--json")
        self.assertEqual((result.returncode, result.stderr), (0, ""))
        self.assertEqual(json.loads(result.stdout), up_to_date)
        head = commit(
            self.upstream,
            {
                PLUGIN: '{"name": "pstack", "version": "1.1.0"}\n',
                "pstack/skills/alpha/SKILL.md": "edited\n",
                "pstack/skills/beta/new.md": "added\n",
                "pstack/skills/beta/old.md": None,
                "pstack/skills/gone/deep/file.md": "edited\n",
            },
        )
        result = self.check("--json", "--ref", head)
        self.assertEqual((result.returncode, result.stderr), (0, ""))
        self.assertEqual(result.stdout[-2:], "}\n")
        self.assertEqual(
            json.loads(result.stdout),
            {
                **up_to_date,
                "ref": head,
                "commit": head,
                "version": "1.1.0",
                "up_to_date": False,
                "changes": [
                    {"path": PLUGIN, "change": "changed", "handling": "not-shipped", "t3_path": None},
                    {
                        "path": "pstack/skills/alpha/SKILL.md",
                        "change": "changed",
                        "handling": "overridden",
                        "t3_path": "t3/overrides/alpha/SKILL.md",
                    },
                    {"path": "pstack/skills/beta/new.md", "change": "added", "handling": "unchanged", "t3_path": None},
                    {"path": "pstack/skills/beta/old.md", "change": "removed", "handling": "unchanged", "t3_path": None},
                    {
                        "path": "pstack/skills/gone/deep/file.md",
                        "change": "changed",
                        "handling": "dropped",
                        "t3_path": None,
                    },
                ],
            },
        )

    def test_the_repository_flag_replaces_the_one_in_upstream_json(self):
        commit(self.upstream, {"pstack/README.md": "edited\n"})
        elsewhere = self.directory / "elsewhere"
        meta = json.loads((self.root / "upstream.json").read_text())
        (self.root / "upstream.json").write_text(json.dumps({**meta, "repository": str(elsewhere)}))
        self.assertIn(f"repository '{elsewhere}' does not exist", self.failure())
        result = self.check("--repository", str(self.upstream), "--json")
        self.assertEqual(result.returncode, 0, result.stderr)
        report = json.loads(result.stdout)
        self.assertEqual((report["repository"], report["changes"][0]["path"]), (str(self.upstream), "pstack/README.md"))

    def test_an_unknown_ref_exits_1_with_the_git_error(self):
        self.assertEqual(self.failure("--ref", "nope"), "fatal: Needed a single revision\n")

    def test_a_pinned_commit_upstream_lacks_exits_1_with_the_git_error(self):
        commit(self.upstream, {"pstack/README.md": "edited\n"})
        meta = json.loads((self.root / "upstream.json").read_text())
        (self.root / "upstream.json").write_text(json.dumps({**meta, "commit": "1" * 40}))
        self.assertIn(f"fatal: bad object {'1' * 40}", self.failure())

    def test_a_missing_git_exits_1(self):
        empty = self.directory / "empty"
        empty.mkdir()
        self.assertEqual(self.failure(PATH=str(empty)), "[Errno 2] No such file or directory: 'git'\n")

    def test_json_or_repository_without_check_is_a_usage_error_that_syncs_nothing(self):
        commit(self.upstream, {"pstack/README.md": "edited\n"})
        before = snapshot(self.root)
        for flags in (("--json",), ("--repository", str(self.upstream))):
            with self.subTest(flags=flags):
                result = self.sync(*flags)
                self.assertEqual(result.returncode, 2)
                self.assertIn("--json and --repository need --check", result.stderr)
                self.assertEqual(snapshot(self.root), before)

    def test_writes_nothing(self):
        commit(self.upstream, {"pstack/skills/alpha/SKILL.md": "edited\n"})
        git(self.root, "init", "--quiet")
        git(self.root, "add", "--all")
        git(self.root, "commit", "--quiet", "--message", "checkout")
        before = snapshot(self.root)
        self.assertEqual(self.check().returncode, 0)
        self.assertEqual(self.check("--json").returncode, 0)
        self.assertEqual(self.check("--ref", self.pinned).returncode, 0)
        self.assertEqual(self.check("--ref", "nope").returncode, 1)
        self.assertEqual(snapshot(self.root), before)
        self.assertEqual(list(self.root.rglob("__pycache__")), [])
        self.assertEqual(list(self.scratch.iterdir()), [])
        self.assertEqual(git(self.root, "status", "--porcelain", "--ignored"), "")


class SyncTest(CheckoutCase):
    def test_without_check_the_sync_still_replaces_vendor_and_moves_the_pin(self):
        head = commit(
            self.upstream,
            {
                PLUGIN: '{"name": "pstack", "version": "1.1.0"}\n',
                "pstack/skills/beta/SKILL.md": "edited\n",
                "pstack/skills/beta/old.md": None,
            },
        )
        result = self.sync()
        self.assertEqual(result.stdout.splitlines()[0], f"vendor/pstack: {self.pinned[:12]} -> {head[:12]} (1.1.0)")
        self.assertEqual(result.returncode, 1)
        self.assertIn("override drift", result.stdout)
        meta = json.loads((self.root / "upstream.json").read_text())
        self.assertEqual(
            meta, {"repository": str(self.upstream), "commit": head, "path": "pstack", "version": "1.1.0"}
        )
        expected = {name[len("pstack/") :]: text for name, text in PINNED_TREE.items() if name.startswith("pstack/")}
        expected[".cursor-plugin/plugin.json"] = '{"name": "pstack", "version": "1.1.0"}\n'
        expected["skills/beta/SKILL.md"] = "edited\n"
        del expected["skills/beta/old.md"]
        vendor = self.root / "vendor/pstack"
        self.assertEqual(
            {path.relative_to(vendor).as_posix(): path.read_text() for path in vendor.rglob("*") if path.is_file()},
            expected,
        )


class ClassifyTest(unittest.TestCase):
    def test_each_path_gets_the_layer_the_build_ships(self):
        for path, expected in CLASSIFIED:
            with self.subTest(path=path):
                self.assertEqual(sync_upstream.classify(path, "pstack", LAYERS), expected)

    def test_the_prefix_can_be_nested(self):
        self.assertEqual(
            sync_upstream.classify("plugins/pstack/skills/alpha/SKILL.md", "plugins/pstack", LAYERS),
            ("overridden", "t3/overrides/alpha/SKILL.md"),
        )

    def test_agrees_with_the_real_build(self):
        layers = sync_upstream.load_layers()
        skills = ROOT / "vendor/pstack/skills"
        seen = set()
        with tempfile.TemporaryDirectory() as directory:
            rendered = Path(directory)
            build.render(rendered)
            for rel in build.relative_files(skills):
                handling, t3_path = sync_upstream.classify(f"pstack/skills/{rel.as_posix()}", "pstack", layers)
                seen.add(handling)
                with self.subTest(path=rel.as_posix()):
                    self.assertIn(handling, ("overridden", "unchanged", "dropped"))
                    self.assertEqual((rendered / rel).is_file(), handling != "dropped")
                    if handling == "dropped" or (len(rel.parts) == 2 and rel.name == "SKILL.md"):
                        continue
                    source = ROOT / t3_path if handling == "overridden" else skills / rel
                    self.assertEqual((rendered / rel).read_bytes(), source.read_bytes())
        self.assertLessEqual({"overridden", "unchanged"}, seen)


class UpstreamChangesTest(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.upstream, self.pinned = new_upstream(temporary.name)
        environment = mock.patch.dict(os.environ, GIT_ENV, clear=True)
        environment.start()
        self.addCleanup(environment.stop)

    def changes(self, repository=None, ref="main", prefix="pstack"):
        return sync_upstream.upstream_changes(repository or str(self.upstream), ref, self.pinned, prefix)

    def test_the_pinned_commit_has_no_changes(self):
        self.assertEqual(self.changes(), (self.pinned, "1.0.0", []))

    def test_lists_what_changed_under_the_prefix_since_the_pinned_commit(self):
        head = commit(
            self.upstream,
            {
                "other/notes.md": "edited outside the prefix\n",
                "pstack-extra/skills/alpha/SKILL.md": "a sibling that shares the prefix's first letters\n",
                PLUGIN: '{"name": "pstack", "version": "1.1.0"}\n',
                "pstack/skills/alpha/SKILL.md": "edited\n",
                "pstack/skills/beta/odd name\n.md": "added\n",
                "pstack/skills/beta/old.md": None,
            },
        )
        self.assertEqual(
            self.changes(),
            (
                head,
                "1.1.0",
                [
                    ("changed", PLUGIN),
                    ("changed", "pstack/skills/alpha/SKILL.md"),
                    ("added", "pstack/skills/beta/odd name\n.md"),
                    ("removed", "pstack/skills/beta/old.md"),
                ],
            ),
        )

    def test_a_rename_is_one_removed_path_and_one_added_path(self):
        head = commit(
            self.upstream,
            {"pstack/skills/beta/old.md": None, "pstack/skills/beta/renamed.md": PINNED_TREE["pstack/skills/beta/old.md"]},
        )
        self.assertEqual(
            self.changes(),
            (head, "1.0.0", [("removed", "pstack/skills/beta/old.md"), ("added", "pstack/skills/beta/renamed.md")]),
        )

    def test_a_commit_that_leaves_the_prefix_alone_has_no_changes(self):
        head = commit(self.upstream, {"other/notes.md": "edited outside the prefix\n"})
        self.assertEqual(self.changes(), (head, "1.0.0", []))

    def test_a_glob_character_in_the_prefix_matches_only_itself(self):
        head = commit(self.upstream, {"p*/skills/alpha/SKILL.md": "added\n", "pstack/README.md": "edited\n"})
        self.assertEqual(self.changes(prefix="p*"), (head, None, [("added", "p*/skills/alpha/SKILL.md")]))

    def test_a_tag_and_a_commit_resolve_like_a_branch(self):
        head = commit(self.upstream, {"pstack/README.md": "edited\n"})
        git(self.upstream, "tag", "--annotate", "--message", "release", "v2")
        commit(self.upstream, {"pstack/README.md": "edited again\n"})
        expected = (head, "1.0.0", [("changed", "pstack/README.md")])
        self.assertEqual(self.changes(ref="v2"), expected)
        self.assertEqual(self.changes(ref=head), expected)

    def test_a_blobless_clone_still_reads_the_version(self):
        git(self.upstream, "config", "uploadpack.allowFilter", "true")
        head = commit(self.upstream, {PLUGIN: '{"name": "pstack", "version": "2.0.0"}\n'})
        self.assertEqual(self.changes(repository=self.upstream.as_uri()), (head, "2.0.0", [("changed", PLUGIN)]))

    def test_an_unreadable_version_is_none(self):
        for text, change in (("not json\n", "changed"), ("[]\n", "changed"), ('{"version": 2}\n', "changed"), (None, "removed")):
            with self.subTest(plugin=text):
                head = commit(self.upstream, {PLUGIN: text})
                self.assertEqual(self.changes(), (head, None, [(change, PLUGIN)]))


if __name__ == "__main__":
    unittest.main()
