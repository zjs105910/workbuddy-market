"""One store-resolution vector table, run against EVERY shipped session-catchup.py.

Issue #209 existed because the copies drifted: v3.8.0 replaced the sanitizer in
the canonical script (and everything synced from it) with a character whitelist,
but three unsynced copies kept a manual `.replace()` chain that never folded
'.'. The suite stayed green because each existing test pointed at exactly one
copy, so nothing compared them.

This module discovers the copies instead of listing them, and runs the same
vectors through each, so a future copy or a future divergence fails here.

The surface under test is sanitize plus probe, not path normalization, so the
per-module normalize step is patched to identity exactly as
test_catchup_project_dir.py does. That keeps POSIX vectors meaningful on
Windows, where Path.resolve() would otherwise rewrite '/home/...' to 'C:\\home\\...'.

Folding rules pinned here were measured against 24 real ~/.claude/projects
stores whose recorded `cwd` could be read: Claude Code folds every character
outside [A-Za-z0-9-] to '-', counting UTF-16 code units, so a non-BMP character
costs two dashes. Older stores kept '_'; both spellings are live, so both are
probed.
"""
from __future__ import annotations

import importlib.util
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest import mock

REPO_ROOT = Path(__file__).resolve().parents[1]

# .kiro ships a different program: it reads .kiro/plan/*.md off the filesystem
# and never touches ~/.claude/projects, so it has no resolver to compare.
EXCLUDED_PARTS = {".kiro"}

RESOLVER_NAMES = (
    "get_claude_project_dir",   # canonical (and every copy synced from it)
    "get_project_dir_claude",   # root scripts/ and .hermes
    "get_project_dir",          # .mastracode (returns a Tuple)
)

NORMALIZE_NAMES = ("normalize_path", "normalize_project_path")


def tracked_catchup_scripts() -> list[Path]:
    """Every session-catchup.py tracked by git, minus the .kiro variant."""
    out = subprocess.run(
        ["git", "ls-files", "*session-catchup.py"],
        cwd=REPO_ROOT, capture_output=True, text=True, check=True,
    ).stdout.split()
    paths = []
    for rel in out:
        path = REPO_ROOT / rel
        if EXCLUDED_PARTS & set(Path(rel).parts):
            continue
        if path.is_file():
            paths.append(path)
    return sorted(paths)


def load_module(script_path: Path, alias: str):
    spec = importlib.util.spec_from_file_location(alias, script_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def resolver_for(module):
    """Return (callable, name) for whichever resolver this copy exposes."""
    for name in RESOLVER_NAMES:
        fn = getattr(module, name, None)
        if callable(fn):
            return fn, name
    return None, None


def resolve_name(fn, resolver_name: str, project_path: str) -> str:
    result = fn(project_path)
    if resolver_name == "get_project_dir":
        # .mastracode returns (path, skip_message)
        result = result[0]
    assert result is not None, f"{resolver_name} returned None for {project_path}"
    return Path(result).name


# (label, project path, the directory name Claude Code actually writes)
VECTORS = [
    ("hidden dir (#209)",       "/home/dev/.dotfiles",       "-home-dev--dotfiles"),
    ("nested hidden dir",       "/home/dev/.config/nvim",    "-home-dev--config-nvim"),
    ("dots inside a segment",   "/home/dev/my.app.v2",       "-home-dev-my-app-v2"),
    ("space in a segment",      "/home/dev/My Project",      "-home-dev-My-Project"),
    ("plain path (regression)", "/home/dev/project",         "-home-dev-project"),
    ("underscore kept (old)",   "/home/dev/Ayseu_Visa_2026", "-home-dev-Ayseu_Visa_2026"),
    ("underscore folded (new)", "/home/dev/MORPHOS_SEND",    "-home-dev-MORPHOS-SEND"),
    # A non-BMP character occupies two UTF-16 code units, so it folds to two
    # dashes; the trailing '_' folds too in current versions. Measured against
    # the real store C--Users-...-Teaching-Material----Daily-Sessions.
    ("emoji (UTF-16 width)",    "/home/dev/\U0001F4C5_Daily", "-home-dev----Daily"),
]


class StoreResolutionParityTests(unittest.TestCase):
    def setUp(self):
        self.scripts = tracked_catchup_scripts()

    def test_every_copy_exposes_a_resolver(self):
        """A new copy that resolves stores must be discoverable by this suite."""
        self.assertTrue(self.scripts, "no session-catchup.py copies found")
        for script in self.scripts:
            with self.subTest(script=script.relative_to(REPO_ROOT).as_posix()):
                module = load_module(script, f"pc_{abs(hash(str(script)))}")
                _, name = resolver_for(module)
                self.assertIsNotNone(
                    name,
                    f"{script.relative_to(REPO_ROOT)} reads ~/.claude/projects but "
                    "exposes no known resolver; add it to RESOLVER_NAMES",
                )

    def test_vectors_resolve_identically_in_every_copy(self):
        for script in self.scripts:
            rel = script.relative_to(REPO_ROOT).as_posix()
            module = load_module(script, f"pv_{abs(hash(str(script)))}")
            fn, resolver_name = resolver_for(module)
            if fn is None:
                continue

            for label, project_path, expected in VECTORS:
                with self.subTest(copy=rel, vector=label):
                    self._assert_vector(module, fn, resolver_name, project_path, expected, rel, label)

    def _assert_vector(self, module, fn, resolver_name, project_path, expected, rel, label):
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp)
            projects = home / ".claude" / "projects"
            projects.mkdir(parents=True)
            (projects / expected).mkdir()

            patches = [mock.patch.object(module.Path, "home", return_value=home)]
            for norm in NORMALIZE_NAMES:
                if hasattr(module, norm):
                    patches.append(
                        mock.patch.object(module, norm, side_effect=lambda p: p)
                    )
            for patch in patches:
                patch.start()
            try:
                got = resolve_name(fn, resolver_name, project_path)
            finally:
                for patch in reversed(patches):
                    patch.stop()

            self.assertEqual(
                expected, got,
                f"{rel} [{label}] resolved {project_path!r} to {got!r}, "
                f"but Claude Code writes {expected!r}",
            )

    def test_missing_store_does_not_resolve_to_the_projects_root(self):
        """A missing store must never make the store root itself the answer."""
        for script in self.scripts:
            rel = script.relative_to(REPO_ROOT).as_posix()
            module = load_module(script, f"pe_{abs(hash(str(script)))}")
            fn, resolver_name = resolver_for(module)
            if fn is None:
                continue
            with self.subTest(copy=rel):
                with tempfile.TemporaryDirectory() as tmp:
                    home = Path(tmp)
                    projects = home / ".claude" / "projects"
                    projects.mkdir(parents=True)
                    patches = [mock.patch.object(module.Path, "home", return_value=home)]
                    for norm in NORMALIZE_NAMES:
                        if hasattr(module, norm):
                            patches.append(
                                mock.patch.object(module, norm, side_effect=lambda p: p)
                            )
                    for patch in patches:
                        patch.start()
                    try:
                        result = fn("/home/dev/absent")
                        if resolver_name == "get_project_dir":
                            result = result[0]
                    finally:
                        for patch in reversed(patches):
                            patch.stop()
                    self.assertNotEqual(
                        projects.resolve(), Path(result).resolve(),
                        f"{rel} resolved a missing project to the store root",
                    )


if __name__ == "__main__":
    unittest.main()
