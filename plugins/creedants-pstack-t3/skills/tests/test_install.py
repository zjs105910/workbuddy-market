"""Installer behavior a fresh home can observe."""

import errno
import fcntl
import hashlib
import json
import os
import re
import shlex
import shutil
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
NAMES = ("alpha", "pstack-runtime", "swarm")
OLD_SHA = "3936df1838da72e64c9870c6c73262929c27f828385be625286018a80039a33d"
KEPT = "kept {n} records whose links no longer point at this checkout; they apply again if the links come back"
ADOPTED = "adopted {n} links an older installer recorded"
UNTRACKED = "links already point at this checkout but are not tracked; uninstall leaves them"
CONTESTED = "kept backup {backup}: {aside} is held for that path and another entry is there now; remove the one that is not the backup and rerun uninstall"

OLD_INSTALLER = r'''#!/usr/bin/env python3
"""Install pstack-t3 skills into every provider skill directory T3 reads.

T3's `$` picker lists each provider's native skills, so pstack-t3 links its
generated skills into each provider's directory. Every link and every entry
moved aside is recorded in a manifest so `uninstall` restores the prior state.
"""

import argparse
import json
import os
import shutil
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SKILLS = ROOT / "skills"
HARNESSES = ("claude", "codex", "grok", "cursor")


def skill_dirs(scope_root, user):
    home = Path(os.environ.get("HOME", str(Path.home())))
    claude = Path(os.environ["CLAUDE_CONFIG_DIR"]) if user and os.environ.get("CLAUDE_CONFIG_DIR") else (home / ".claude" if user else scope_root / ".claude")
    base = home if user else scope_root
    return {
        "claude": claude / "skills",
        "codex": base / ".agents" / "skills",
        "grok": base / ".grok" / "skills",
        "cursor": base / ".cursor" / "skills",
    }


def extra_dirs(scope_root, user):
    """Other directories each provider also reads skills from, where stale copies can compete."""
    home = Path(os.environ.get("HOME", str(Path.home())))
    base = home if user else scope_root
    claude = skill_dirs(scope_root, user)["claude"]
    return {
        "claude": [],
        "codex": [base / ".codex" / "skills"],
        "grok": [],
        "cursor": [base / ".agents" / "skills", base / ".codex" / "skills", claude],
    }


def state_dir(scope_root, user):
    if user:
        config = Path(os.environ.get("XDG_CONFIG_HOME") or Path(os.environ.get("HOME", str(Path.home()))) / ".config")
        return config / "pstack-t3"
    return scope_root / ".pstack"


def ours(path):
    """A link whose target is a skill directory in this checkout. Never follows loops."""
    if not path.is_symlink():
        return False
    target = Path(os.path.normpath(os.path.join(path.parent, os.readlink(path))))
    return target.parent in (SKILLS, Path(os.path.realpath(SKILLS)))


def inside_checkout(path):
    """True when the path is, or resolves into, this checkout's skills tree."""
    real = Path(os.path.realpath(path))
    skills = Path(os.path.realpath(SKILLS))
    return real == skills or skills in real.parents


def describe(path):
    if path.is_symlink():
        return f"link to {os.readlink(path)}"
    return "directory" if path.is_dir() else "file"


def load_manifest(file):
    if file.exists():
        return json.loads(file.read_text())
    return {"links": [], "backups": []}


def save_manifest(file, manifest):
    file.parent.mkdir(parents=True, exist_ok=True)
    temporary = file.with_suffix(".tmp")
    temporary.write_text(json.dumps(manifest, indent=2) + "\n")
    os.replace(temporary, file)


def plan(targets, names):
    """Return (actions, conflicts). Directories sharing a real path are visited once,
    and each action names every harness that shares it."""
    actions, conflicts, seen = [], [], {}
    for harness, directory in targets.items():
        real = Path(os.path.realpath(directory))
        if real in seen:
            seen[real].append(harness)
            continue
        seen[real] = [harness]
        if inside_checkout(directory):
            print(f"{harness}: {directory} already resolves to {SKILLS}; nothing to link")
            continue
        for name in names:
            link = directory / name
            if ours(link):
                continue
            if inside_checkout(link):
                # Moving this aside would move pstack-t3's own skill directory.
                continue
            if link.exists() or link.is_symlink():
                conflicts.append((seen[real], link))
            actions.append((seen[real], link))
    return actions, conflicts


def install(args):
    if not SKILLS.is_dir():
        sys.exit("skills/ is missing; run python3 scripts/build.py first")
    user = args.project is None
    scope = Path(args.project).resolve() if args.project else None
    targets = {h: d for h, d in skill_dirs(scope, user).items() if h in args.harness}
    names = sorted(p.name for p in SKILLS.iterdir() if (p / "SKILL.md").is_file())
    actions, conflicts = plan(targets, names)
    if conflicts and not args.replace:
        lines = [f"  {'/'.join(harnesses)}: {link} ({describe(link)})" for harnesses, link in conflicts]
        sys.exit("these skills already exist; rerun with --replace to move them aside (uninstall restores them):\n" + "\n".join(lines))
    if args.dry_run:
        for harnesses, link in actions:
            print(f"would link {link} -> {SKILLS / link.name}" + (f" (replacing {describe(link)})" if (harnesses, link) in conflicts else ""))
        print(f"{len(actions)} links planned")
        return
    state = state_dir(scope, user)
    manifest_file = state / "install-manifest.json"
    manifest = load_manifest(manifest_file)
    # Create the stamp directory on the first skill that has to be moved aside.
    backup_root = None
    for harnesses, link in actions:
        link.parent.mkdir(parents=True, exist_ok=True)
        if link.exists() or link.is_symlink():
            if backup_root is None:
                (state / "backups").mkdir(parents=True, exist_ok=True)
                backup_root = Path(tempfile.mkdtemp(prefix=time.strftime("%Y%m%dT%H%M%S-"), dir=state / "backups"))
            backup = backup_root / harnesses[0] / link.name
            backup.parent.mkdir(parents=True, exist_ok=True)
            # Record before moving, so a crash mid-move still leaves a restorable entry.
            manifest["backups"].append({"harnesses": harnesses, "original": str(link), "backup": str(backup)})
            save_manifest(manifest_file, manifest)
            shutil.move(str(link), str(backup))
        link.symlink_to(SKILLS / link.name, target_is_directory=True)
        manifest["links"].append({"harnesses": harnesses, "path": str(link)})
        save_manifest(manifest_file, manifest)
    print(f"linked {len(actions)} skills into {', '.join(sorted(set(h for hs, _ in actions for h in hs))) or 'nothing (already installed)'}")
    print(f"manifest: {manifest_file}")


def entry_harnesses(entry):
    """Harnesses that share an entry's directory. Unknown means all of them."""
    if not isinstance(entry, dict):
        return list(HARNESSES)
    if "harnesses" in entry:
        return entry["harnesses"]
    return [entry["harness"]] if "harness" in entry else list(HARNESSES)


def entry_path(entry):
    return Path(entry["path"] if isinstance(entry, dict) else entry)


def uninstall(args):
    user = args.project is None
    scope = Path(args.project).resolve() if args.project else None
    manifest_file = state_dir(scope, user) / "install-manifest.json"
    manifest = load_manifest(manifest_file)
    shared = set()

    def selected(entry):
        # A directory shared by several harnesses goes only when all of them are selected.
        harnesses = entry_harnesses(entry)
        if set(harnesses) <= set(args.harness):
            return True
        if set(harnesses) & set(args.harness):
            shared.add(", ".join(sorted(set(harnesses) - set(args.harness))))
        return False
    removed, kept_links = 0, []
    for entry in manifest["links"]:
        link = entry_path(entry)
        if not selected(entry):
            kept_links.append(entry)
        elif ours(link):
            if not args.dry_run:
                link.unlink()
            removed += 1
    restored, kept_backups = 0, []
    for entry in reversed(manifest["backups"]):
        original, backup = Path(entry["original"]), Path(entry["backup"])
        present = backup.exists() or backup.is_symlink()
        if not selected(entry) or not present:
            if present:
                kept_backups.append(entry)
            continue
        occupied = original.exists() or original.is_symlink()
        # In a dry run our own links are still in place but would be removed first.
        if occupied and not (args.dry_run and ours(original)):
            print(f"kept backup {backup}: {original} is occupied; clear it and rerun uninstall")
            kept_backups.append(entry)
            continue
        if not args.dry_run:
            shutil.move(str(backup), str(original))
        restored += 1
    print(f"would remove {removed} links, would restore {restored} entries" if args.dry_run else f"removed {removed} links, restored {restored} entries")
    for others in sorted(shared):
        print(f"kept entries whose directory is shared with {others}; select those harnesses too to remove them")
    if args.dry_run:
        return 0
    if kept_links or kept_backups:
        save_manifest(manifest_file, {"links": kept_links, "backups": list(reversed(kept_backups))})
    elif manifest_file.exists():
        manifest_file.unlink()
    return 0


def doctor(args):
    user = args.project is None
    scope = Path(args.project).resolve() if args.project else None
    names = sorted(p.name for p in SKILLS.iterdir() if (p / "SKILL.md").is_file()) if SKILLS.is_dir() else []
    healthy = True
    for harness, directory in skill_dirs(scope, user).items():
        if harness not in args.harness:
            continue
        if Path(os.path.realpath(directory)) == Path(os.path.realpath(SKILLS)):
            print(f"{harness:7} {directory}: resolves to the pstack-t3 skills tree itself")
            continue
        if inside_checkout(directory):
            print(f"{harness:7} {directory}: points inside one pstack-t3 skill, so the other skills are invisible")
            healthy = False
            continue
        installed = [n for n in names if ours(directory / n)]
        foreign = [n for n in names if (directory / n).exists() and not ours(directory / n)]
        missing = [n for n in names if not (directory / n).exists()]
        healthy &= not foreign and not missing
        print(f"{harness:7} {directory}: {len(installed)}/{len(names)} pstack-t3" +
              (f", {len(foreign)} taken by other copies ({', '.join(foreign[:5])}{'...' if len(foreign) > 5 else ''})" if foreign else "") +
              (f", {len(missing)} missing" if missing else ""))
        for extra in extra_dirs(scope, user)[harness]:
            stale = [n for n in names if (extra / n).exists() and not ours(extra / n)]
            if stale:
                healthy = False
                print(f"        {extra} also holds other copies of {len(stale)} of these "
                      f"({', '.join(stale[:5])}{'...' if len(stale) > 5 else ''}); {harness} may load those instead")
        if not user:
            # Claude and Grok load the user copy when both scopes define a name.
            user_directory = skill_dirs(None, True)[harness]
            shadowing = [n for n in installed if (user_directory / n).exists() and not ours(user_directory / n)]
            if shadowing:
                healthy = False
                print(f"        user scope {user_directory} has other copies of {len(shadowing)} of these "
                      f"({', '.join(shadowing[:5])}{'...' if len(shadowing) > 5 else ''}); providers that prefer user scope will load those instead")
    return 0 if healthy else 1


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("install", "uninstall", "doctor"), nargs="?", default="install")
    parser.add_argument("--project", help="install into this repository instead of the user's skill directories")
    parser.add_argument("--harness", default="all", help="comma list of " + ",".join(HARNESSES) + ", or all")
    parser.add_argument("--replace", action="store_true", help="move conflicting skills aside; uninstall restores them")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)
    args.harness = HARNESSES if args.harness == "all" else tuple(h.strip() for h in args.harness.split(","))
    unknown = set(args.harness) - set(HARNESSES)
    if unknown:
        parser.error(f"unknown harness {', '.join(sorted(unknown))}")
    return {"install": install, "uninstall": uninstall, "doctor": doctor}[args.command](args) or 0


if __name__ == "__main__":
    sys.exit(main())
'''


def run_install(home, *args):
    return _run(home, ROOT, args)


def _env(home):
    env = os.environ.copy()
    env.pop("XDG_CONFIG_HOME", None)
    env.pop("CLAUDE_CONFIG_DIR", None)
    env["HOME"] = str(home)
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    return env


def _run(home, checkout, args):
    return subprocess.run(
        [sys.executable, str(Path(checkout) / "scripts" / "install.py"), *args],
        env=_env(home),
        cwd=home,
        capture_output=True,
        text=True,
    )


class FreshInstallTest(unittest.TestCase):
    def test_fresh_install_links_every_skill_and_rerun_adds_no_backup(self):
        with tempfile.TemporaryDirectory() as directory:
            home = Path(directory)
            names = sorted(p.name for p in (ROOT / "skills").iterdir() if (p / "SKILL.md").is_file())
            first = run_install(home)
            self.assertEqual(first.returncode, 0, first.stderr)
            for harness in (".claude", ".agents", ".grok", ".cursor"):
                for name in names:
                    link = home / harness / "skills" / name
                    self.assertTrue(link.is_symlink(), link)
                    self.assertEqual(link.resolve(), (ROOT / "skills" / name).resolve(), link)
                    self.assertEqual((link / "SKILL.md").read_bytes(), (ROOT / "skills" / name / "SKILL.md").read_bytes())
            backups = home / ".config/pstack-t3/backups"
            self.assertFalse(backups.exists(), "a fresh install created a backup directory")
            again = run_install(home)
            self.assertEqual(again.returncode, 0, again.stderr)
            self.assertIn("already installed", again.stdout)
            self.assertFalse(backups.exists(), "rerunning install created a backup directory")

    def test_replace_saves_the_old_skill_and_rerun_adds_no_empty_backup(self):
        with tempfile.TemporaryDirectory() as directory:
            home = Path(directory)
            swarm = home / ".grok/skills/swarm"
            swarm.mkdir(parents=True)
            (swarm / "SKILL.md").write_text("foreign-skill\n")
            refused = run_install(home, "--harness", "grok")
            self.assertNotEqual(refused.returncode, 0)
            self.assertFalse((home / ".grok/skills/poteto-mode").exists())
            replaced = run_install(home, "--harness", "grok", "--replace")
            self.assertEqual(replaced.returncode, 0, replaced.stderr)
            saved = list((home / ".config/pstack-t3/backups").rglob("SKILL.md"))
            self.assertEqual([path.read_text() for path in saved], ["foreign-skill\n"])
            stamps = sorted(p.name for p in (home / ".config/pstack-t3/backups").iterdir() if p.is_dir())
            self.assertEqual(len(stamps), 1)
            again = run_install(home, "--harness", "grok")
            self.assertEqual(again.returncode, 0, again.stderr)
            self.assertIn("already installed", again.stdout)
            stamps_after = sorted(p.name for p in (home / ".config/pstack-t3/backups").iterdir() if p.is_dir())
            self.assertEqual(stamps_after, stamps)
            removed = run_install(home, "--harness", "grok", "uninstall")
            self.assertEqual(removed.returncode, 0, removed.stderr)
            self.assertEqual((swarm / "SKILL.md").read_text(), "foreign-skill\n")
            self.assertFalse((home / ".grok/skills/poteto-mode").exists())


def fresh_home():
    wrapper = tempfile.TemporaryDirectory()
    return wrapper, Path(os.path.realpath(wrapper.name))


def provider_link(home, harness, name):
    folder = {"claude": ".claude", "codex": ".agents", "grok": ".grok", "cursor": ".cursor"}[harness]
    return home / folder / "skills" / name


def state_dir(home):
    return home / ".config" / "pstack-t3"


def legacy_file(home):
    return state_dir(home) / "install-manifest.json"


def owner_file(home, checkout):
    digest = hashlib.sha256(str(checkout).encode()).hexdigest()[:16]
    return state_dir(home) / "install-owners" / f"{digest}.json"


def make_checkout(home, name, old=False):
    checkout = home / "checkouts" / name
    (checkout / "scripts").mkdir(parents=True)
    target = checkout / "scripts" / "install.py"
    if old:
        target.write_bytes(OLD_INSTALLER.encode())
    else:
        shutil.copy(ROOT / "scripts" / "install.py", target)
    for skill in NAMES:
        directory = checkout / "skills" / skill
        directory.mkdir(parents=True)
        (directory / "SKILL.md").write_text(f"{name}-{skill}\n")
    return checkout


def upgrade(checkout):
    shutil.copy(ROOT / "scripts" / "install.py", checkout / "scripts" / "install.py")


def run(home, checkout, *args):
    return _run(home, checkout, args)


def snapshot(root):
    records = []
    for dirpath, dirnames, filenames in os.walk(root):
        for name in sorted(dirnames):
            path = Path(dirpath) / name
            rel = str(path.relative_to(root))
            if path.is_symlink():
                records.append((rel, "link", os.readlink(path)))
            else:
                records.append((rel, "dir", None))
        for name in sorted(filenames):
            path = Path(dirpath) / name
            rel = str(path.relative_to(root))
            if path.is_symlink():
                records.append((rel, "link", os.readlink(path)))
            elif path.is_file():
                records.append((rel, "file", path.read_bytes()))
    return tuple(records)


def read_legacy(home):
    return json.loads(legacy_file(home).read_text())


def read_owner(home, checkout):
    file = owner_file(home, checkout)
    if not file.exists():
        return None
    return json.loads(file.read_text())


def grok_paths(home):
    return [str(provider_link(home, "grok", name)) for name in NAMES]


def plant_links(home, checkout, harness="grok"):
    for name in NAMES:
        link = provider_link(home, harness, name)
        link.parent.mkdir(parents=True, exist_ok=True)
        if link.is_symlink() or link.exists():
            link.unlink()
        os.symlink(checkout / "skills" / name, link)


def write_owner(home, checkout, paths, harnesses=("grok",)):
    file = owner_file(home, checkout)
    file.parent.mkdir(parents=True, exist_ok=True)
    links = {path: {"harnesses": list(harnesses)} for path in paths}
    file.write_text(json.dumps({"checkout": str(checkout), "links": links}, indent=2) + "\n")


def write_legacy(home, links, backups):
    file = legacy_file(home)
    file.parent.mkdir(parents=True, exist_ok=True)
    file.write_text(json.dumps({"links": links, "backups": backups}, indent=2) + "\n")


def pause_after_load(home, checkout, args):
    ready = home / f"ready-{checkout.name}"
    go = home / f"go-{checkout.name}"
    wrapper = home / f"pause-{checkout.name}.py"
    installer = str(checkout / "scripts" / "install.py")
    wrapper.write_text(
        "import importlib.util, sys, time\n"
        "from pathlib import Path\n"
        f"spec = importlib.util.spec_from_file_location('installer', {installer!r})\n"
        "module = importlib.util.module_from_spec(spec)\n"
        "sys.modules[spec.name] = module\n"
        "spec.loader.exec_module(module)\n"
        "original = module.load\n"
        "def paused(*args):\n"
        "    result = original(*args)\n"
        f"    Path({str(ready)!r}).touch()\n"
        "    deadline = time.monotonic() + 30\n"
        f"    while not Path({str(go)!r}).exists():\n"
        "        if time.monotonic() > deadline:\n"
        "            raise RuntimeError('barrier timeout')\n"
        "        time.sleep(0.01)\n"
        "    return result\n"
        "module.load = paused\n"
        "sys.exit(module.main())\n"
    )
    proc = subprocess.Popen(
        [sys.executable, str(wrapper), *args],
        env=_env(home),
        cwd=home,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    return proc, ready, go


def squat_uninstall(home, checkout, path, payload, *args):
    wrapper = home / f"squat-{checkout.name}.py"
    installer = str(checkout / "scripts" / "install.py")
    wrapper.write_text(
        "import importlib.util, sys, os\n"
        "from pathlib import Path\n"
        f"spec = importlib.util.spec_from_file_location('installer', {installer!r})\n"
        "module = importlib.util.module_from_spec(spec)\n"
        "sys.modules[spec.name] = module\n"
        "spec.loader.exec_module(module)\n"
        "changed = False\n"
        "def after(original):\n"
        "    def race(target, *args, **kwargs):\n"
        "        global changed\n"
        "        result = original(target, *args, **kwargs)\n"
        f"        if str(target) == {str(path)!r} and not changed:\n"
        "            changed = True\n"
        f"            Path(target).write_bytes({payload!r})\n"
        "        return result\n"
        "    return race\n"
        "os.rename = after(os.rename)\n"
        "os.unlink = after(os.unlink)\n"
        "sys.exit(module.main())\n"
    )
    return subprocess.run(
        [sys.executable, str(wrapper), *args],
        env=_env(home),
        cwd=home,
        capture_output=True,
        text=True,
    )


def run_failing(home, checkout, call, path, *args):
    module, name = call.split(".")
    wrapper = home / f"fail-{checkout.name}.py"
    installer = str(checkout / "scripts" / "install.py")
    wrapper.write_text(
        "import errno, importlib.util, os, shutil, sys\n"
        f"spec = importlib.util.spec_from_file_location('installer', {installer!r})\n"
        "installer = importlib.util.module_from_spec(spec)\n"
        "sys.modules[spec.name] = installer\n"
        "spec.loader.exec_module(installer)\n"
        f"original = getattr({module}, {name!r})\n"
        "def failing(*args, **kwargs):\n"
        f"    if {str(path)!r} in [str(arg) for arg in args]:\n"
        f"        raise PermissionError(errno.EACCES, os.strerror(errno.EACCES), {str(path)!r})\n"
        "    return original(*args, **kwargs)\n"
        f"setattr({module}, {name!r}, failing)\n"
        "sys.exit(installer.main())\n"
    )
    return subprocess.run(
        [sys.executable, str(wrapper), *args],
        env=_env(home),
        cwd=home,
        capture_output=True,
        text=True,
    )


def interleave_removal(home, checkout, paths, call, *args, occupy=None):
    """Run `call` once, just before this installer first moves or deletes any of `paths`, then write `occupy` there."""
    wrapper = home / f"interleave-{checkout.name}.py"
    installer = str(checkout / "scripts" / "install.py")
    wrapper.write_text(
        "import importlib.util, os, subprocess, sys\n"
        f"spec = importlib.util.spec_from_file_location('installer', {installer!r})\n"
        "module = importlib.util.module_from_spec(spec)\n"
        "sys.modules[spec.name] = module\n"
        "spec.loader.exec_module(module)\n"
        "fired = False\n"
        "def before(original):\n"
        "    def hooked(target, *args, **kwargs):\n"
        "        global fired\n"
        f"        if not fired and str(target) in {[str(path) for path in paths]!r}:\n"
        "            fired = True\n"
        f"            child = subprocess.run({[str(part) for part in call]!r}, env=os.environ, capture_output=True, text=True)\n"
        "            assert child.returncode == 0, child.stdout + child.stderr\n"
        "            result = original(target, *args, **kwargs)\n"
        f"            if {occupy!r} is not None:\n"
        f"                open(target, 'wb').write({occupy!r})\n"
        "            return result\n"
        "        return original(target, *args, **kwargs)\n"
        "    return hooked\n"
        "os.rename = before(os.rename)\n"
        "os.unlink = before(os.unlink)\n"
        "status = module.main()\n"
        "assert fired, 'the interleaved call never ran'\n"
        "sys.exit(status)\n"
    )
    return subprocess.run(
        [sys.executable, str(wrapper), *args],
        env=_env(home),
        cwd=home,
        capture_output=True,
        text=True,
    )


def set_aside(path):
    """Entries an uninstall kept aside for `path`, each in its own hidden directory beside it."""
    # Before Python 3.12, Path.glob skips a final symlink that points nowhere, so each holder is checked with lexists.
    return sorted(holder / path.name for holder in path.parent.glob(".pstack-t3-*/") if os.path.lexists(holder / path.name))


def uninstall_hooked(home, checkout, code):
    """Run this checkout's uninstall with `code` run first against the loaded installer, named `module`."""
    wrapper = home / f"hooked-{checkout.name}.py"
    installer = str(checkout / "scripts" / "install.py")
    wrapper.write_text(
        "import importlib.util, os, sys\n"
        "from pathlib import Path\n"
        f"spec = importlib.util.spec_from_file_location('installer', {installer!r})\n"
        "module = importlib.util.module_from_spec(spec)\n"
        "sys.modules[spec.name] = module\n"
        "spec.loader.exec_module(module)\n"
        f"{code}\n"
        "sys.exit(module.main())\n"
    )
    return subprocess.run(
        [sys.executable, str(wrapper), "--harness", "grok", "uninstall"],
        env=_env(home),
        cwd=home,
        capture_output=True,
        text=True,
    )


def install_hooked(home, checkout, code, *args):
    """Run this checkout's installer with `args`, with `code` run first against the loaded installer, named `module`."""
    wrapper = home / f"hooked-install-{checkout.name}.py"
    installer = str(checkout / "scripts" / "install.py")
    wrapper.write_text(
        "import importlib.util, os, sys\n"
        f"spec = importlib.util.spec_from_file_location('installer', {installer!r})\n"
        "module = importlib.util.module_from_spec(spec)\n"
        "sys.modules[spec.name] = module\n"
        "spec.loader.exec_module(module)\n"
        f"{code}\n"
        "sys.exit(module.main())\n"
    )
    return subprocess.run(
        [sys.executable, str(wrapper), *args],
        env=_env(home),
        cwd=home,
        capture_output=True,
        text=True,
    )


def refused_move(path, *first):
    """Hook code that makes `shutil.move` of `path` raise before it copies anything.

    Each statement of `first` runs just before the error, with `destination` naming where the move was going.
    """
    return (
        "import errno, shutil\n"
        "moving = shutil.move\n"
        "def refused(source, destination, *args, **kwargs):\n"
        f"    if str(source) == {str(path)!r}:\n"
        + "".join(f"        {statement}\n" for statement in first)
        + f"        raise PermissionError(errno.EACCES, os.strerror(errno.EACCES), {str(path)!r})\n"
        "    return moving(source, destination, *args, **kwargs)\n"
        "shutil.move = refused\n"
    )


def put_back_race(path, swap, occupy=None, link_error=False, rename=None):
    """Hook code that swaps `path` for a foreign `swap` entry just before the move aside.

    `occupy` arrives at `path` when the put-back calls a rename onto it, after any check for vacancy.
    `rename` takes the no-replace rename away: "platform" runs it as darwin, "symbol" gives it a libc
    without `renameat2`, and "libc" makes loading libc fail. At exit the run records what that rename
    returned on a scratch pair, read back with `noreplace_result`.
    """
    return (
        "import atexit, ctypes, errno, shutil, tempfile\n"
        f"target = {str(path)!r}\n"
        "moved = False\n"
        "def hooked(original):\n"
        "    def call(source, destination, *args, **kwargs):\n"
        "        global moved\n"
        "        if not moved and str(source) == target:\n"
        "            moved = True\n"
        "            os.unlink(target)\n"
        f"            if {swap!r} == 'directory':\n"
        "                os.mkdir(target)\n"
        "                Path(target, 'precious').write_bytes(b'directory bytes\\x00')\n"
        "            else:\n"
        "                os.symlink('/foreign/swarm', target)\n"
        "        elif moved and str(destination) == target:\n"
        f"            if {occupy!r} == 'directory':\n"
        "                os.mkdir(target)\n"
        f"            elif {occupy!r} == 'file':\n"
        "                Path(target).write_bytes(b'occupant\\x00\\xff')\n"
        "        return original(source, destination, *args, **kwargs)\n"
        "    return call\n"
        "os.rename = hooked(os.rename)\n"
        + without_noreplace(hooked="hooked", link_error=link_error, rename=rename)
    )


def without_noreplace(hooked, link_error, rename):
    """Hook code that wraps the no-replace rename in `hooked` and takes it or hard links away, as `put_back_race` describes.

    A platform without that rename has no /proc either, so a hard link from a held descriptor finds nothing there.
    """
    return (
        "noreplace = getattr(module, 'rename_noreplace', None)\n"
        "def record():\n"
        "    scratch = tempfile.mkdtemp(dir=os.getcwd())\n"
        "    Path(scratch, 'source').write_bytes(b'')\n"
        "    source, destination = os.path.join(scratch, 'source'), os.path.join(scratch, 'target')\n"
        "    code = noreplace(source, destination) if noreplace else errno.ENOSYS\n"
        "    Path(os.getcwd(), 'noreplace-result').write_text(str(code))\n"
        "    shutil.rmtree(scratch)\n"
        "atexit.register(record)\n"
        "if noreplace:\n"
        f"    module.rename_noreplace = {hooked}(noreplace)\n"
        f"if {link_error!r}:\n"
        "    def denied(*args, **kwargs):\n"
        "        raise OSError(errno.EPERM, 'hard links prohibited')\n"
        "    os.link = denied\n"
        f"if {rename is not None}:\n"
        "    linking = os.link\n"
        "    def no_proc(source, *args, **kwargs):\n"
        "        if str(source).startswith('/proc/'):\n"
        "            raise FileNotFoundError(errno.ENOENT, os.strerror(errno.ENOENT), source)\n"
        "        return linking(source, *args, **kwargs)\n"
        "    os.link = no_proc\n"
        f"if {rename!r} == 'platform':\n"
        "    sys.platform = 'darwin'\n"
        f"elif {rename!r} == 'symbol':\n"
        "    ctypes.CDLL = lambda *args, **kwargs: object()\n"
        f"elif {rename!r} == 'libc':\n"
        "    def missing(*args, **kwargs):\n"
        "        raise OSError('no libc')\n"
        "    ctypes.CDLL = missing\n"
    )


def restore_race(path, occupy, link_error=False, rename=None):
    """Hook code that fills `path` just before the first call that would write a backup onto it.

    `occupy` is a "file", a "directory", a "link", or a command line to run, such as another checkout's
    installer. `link_error` and `rename` take hard links and the no-replace rename away as in `put_back_race`.
    """
    return (
        "import atexit, ctypes, errno, shutil, subprocess, tempfile\n"
        f"target = {str(path)!r}\n"
        f"occupy = {occupy!r}\n"
        "filled = False\n"
        "def filling(original, hard_link=False):\n"
        "    def call(source, destination, *args, **kwargs):\n"
        "        global filled\n"
        "        entry = os.readlink(source) if str(source).startswith('/proc/self/fd/') else source\n"
        "        # A directory cannot be hard linked, so its occupant arrives at the rename that follows, when there is one.\n"
        f"        directory = hard_link and {rename is None} and os.path.isdir(entry) and not os.path.islink(entry)\n"
        "        if not filled and str(destination) == target and not directory:\n"
        "            filled = True\n"
        "            if occupy == 'file':\n"
        "                Path(target).write_bytes(b'occupant\\x00\\xff')\n"
        "            elif occupy == 'directory':\n"
        "                os.mkdir(target)\n"
        "                Path(target, 'precious').write_bytes(b'directory bytes\\x00')\n"
        "            elif occupy == 'link':\n"
        "                os.symlink('/foreign/occupant', target)\n"
        "            else:\n"
        "                child = subprocess.run(occupy, env=os.environ, capture_output=True, text=True)\n"
        "                assert child.returncode == 0, child.stdout + child.stderr\n"
        "        return original(source, destination, *args, **kwargs)\n"
        "    return call\n"
        "shutil.move = filling(shutil.move)\n"
        "os.rename = filling(os.rename)\n"
        + without_noreplace(hooked="filling", link_error=link_error, rename=rename)
        # The occupant also arrives at a hard link that is then refused.
        + "os.link = filling(os.link, hard_link=True)\n"
        + "atexit.register(lambda: Path(os.getcwd(), 'filled').write_text(str(filled)))\n"
    )


def cross_device(backups, path, occupy=None, rename=None):
    """Hook code that fails every move out of `backups` the way a move onto another filesystem fails.

    A move that stays inside `backups` works. A hard link from a held descriptor counts as a move of the entry it holds.

    `occupy` is a "file" or a "directory" that fills `path` just before the first call that would write
    anything else onto it. `rename` takes the no-replace rename away as in `put_back_race`. At exit the
    run records how many moves it failed, read back with `crossings`.
    """
    return (
        "import atexit, ctypes, errno, shutil, tempfile\n"
        f"backups = {str(backups) + os.sep!r}\n"
        f"target = {str(path)!r}\n"
        f"occupy = {occupy!r}\n"
        "crossed = 0\n"
        "filled = False\n"
        "def crossing(original, raises=False):\n"
        "    def call(source, destination, *args, **kwargs):\n"
        "        global crossed, filled\n"
        "        entry = os.readlink(source) if str(source).startswith('/proc/self/fd/') else str(source)\n"
        "        if entry.startswith(backups) and not str(destination).startswith(backups):\n"
        "            crossed += 1\n"
        "            if raises:\n"
        "                raise OSError(errno.EXDEV, os.strerror(errno.EXDEV))\n"
        "            return errno.EXDEV\n"
        "        if occupy and not filled and str(destination) == target:\n"
        "            filled = True\n"
        "            if occupy == 'file':\n"
        "                Path(target).write_bytes(b'occupant\\x00\\xff')\n"
        "            else:\n"
        "                os.mkdir(target)\n"
        "                Path(target, 'precious').write_bytes(b'directory bytes\\x00')\n"
        "        return original(source, destination, *args, **kwargs)\n"
        "    return call\n"
        "os.link = crossing(os.link, raises=True)\n"
        "os.rename = crossing(os.rename, raises=True)\n"
        + without_noreplace(hooked="crossing", link_error=False, rename=rename)
        + "atexit.register(lambda: Path(os.getcwd(), 'crossed').write_text(str(crossed)))\n"
        + "atexit.register(lambda: Path(os.getcwd(), 'filled').write_text(str(filled)))\n"
    )


def crossings(home):
    """How many moves out of the backups a `cross_device` run failed."""
    return int((home / "crossed").read_text())


def noreplace_result(home):
    """What the installer's no-replace rename returned in a `put_back_race` run: 0 when it renames, else the errno."""
    return int((home / "noreplace-result").read_text())


def backup_race(backup, path, events, foreign="file", proc=True, links=True):
    """Hook code that changes what the backup's path names in the middle of a restore.

    Each event is `(call, role, when, action)`. `call` is "link", "rename", or "noreplace". `role` is "from" for
    the first such call that reads the backup's path, or "onto" for the first that writes `path`. `when` is
    "before" the call, or "after" it once it worked. The "swap" action renames the backup to a `.saved` name
    beside it and puts a `foreign` "file" or "directory" at its path. "squat" puts another file at the backup's
    path. "vanish" deletes the backup's directory. "occupy" puts a file at `path`. Without `proc` a hard link from
    a held descriptor finds nothing, and without `links` every hard link is refused. At exit the run records how
    many events fired, read back with `fired`.
    """
    return (
        "import atexit, errno, shutil\n"
        f"backup, target, saved = {str(backup)!r}, {str(path)!r}, {str(backup) + '.saved'!r}\n"
        f"events = {list(events)!r}\n"
        "fired = []\n"
        "renaming = os.rename\n"
        "def change(action):\n"
        "    if action == 'swap':\n"
        "        if os.path.lexists(backup):\n"
        "            renaming(backup, saved)\n"
        f"        if {foreign!r} == 'directory':\n"
        "            os.mkdir(backup)\n"
        "            Path(backup, 'precious').write_bytes(b'foreign directory\\x00')\n"
        "        else:\n"
        "            Path(backup).write_bytes(b'foreign\\x00\\xff')\n"
        "    elif action == 'squat':\n"
        "        Path(backup).write_bytes(b'squatter\\x00')\n"
        "    elif action == 'vanish':\n"
        "        shutil.rmtree(os.path.dirname(backup))\n"
        "    else:\n"
        "        Path(target).write_bytes(b'occupant\\x00\\xff')\n"
        "def racing(name, original):\n"
        "    def call(source, destination, *args, **kwargs):\n"
        "        due = [\n"
        "            event for event in events\n"
        "            if event not in fired and event[0] == name\n"
        "            and (str(source) == backup if event[1] == 'from' else str(destination) == target)\n"
        "        ]\n"
        "        for event in due:\n"
        "            if event[2] == 'before':\n"
        "                fired.append(event)\n"
        "                change(event[3])\n"
        "        result = original(source, destination, *args, **kwargs)\n"
        "        # A hard link and a rename return nothing. The no-replace rename returns 0 when it worked.\n"
        "        if not result:\n"
        "            for event in due:\n"
        "                if event not in fired:\n"
        "                    fired.append(event)\n"
        "                    change(event[3])\n"
        "        return result\n"
        "    return call\n"
        "linking = os.link\n"
        "def limited(source, *args, **kwargs):\n"
        f"    if not {links!r}:\n"
        "        raise OSError(errno.EPERM, 'hard links prohibited')\n"
        f"    if not {proc!r} and str(source).startswith('/proc/'):\n"
        "        raise FileNotFoundError(errno.ENOENT, os.strerror(errno.ENOENT), source)\n"
        "    return linking(source, *args, **kwargs)\n"
        "os.link = racing('link', limited)\n"
        "os.rename = racing('rename', renaming)\n"
        "module.rename_noreplace = racing('noreplace', module.rename_noreplace)\n"
        "atexit.register(lambda: Path(os.getcwd(), 'fired').write_text(str(len(fired))))\n"
    )


def fired(home):
    """How many events of a `backup_race` run fired."""
    return int((home / "fired").read_text())


def raising(call):
    """Hook code that makes the installer's own `call` raise an I/O error."""
    return (
        "import errno\n"
        "def boom(*args, **kwargs):\n"
        f"    raise OSError(errno.EIO, 'injected {call} failure')\n"
        f"module.{call} = boom\n"
    )


def injected(call):
    """What a `raising` run prints for the error it raised."""
    return f"[Errno {errno.EIO}] injected {call} failure"


SCRAP_LEFT = "an unfinished copy or an already restored backup; delete it by hand"

# Hook code that fails the delete of the swarm entry an uninstall moved aside.
UNLINK_ASIDE = (
    "import errno\n"
    "unlinking = os.unlink\n"
    "def boom(path, *args, **kwargs):\n"
    "    if '.pstack-t3-' in str(path) and str(path).endswith('/swarm'):\n"
    "        raise OSError(errno.EIO, 'injected unlink failure')\n"
    "    return unlinking(path, *args, **kwargs)\n"
    "os.unlink = boom\n"
)

# Hook code that ends the run, as a kill would, once a directory backup has moved aside.
KILLED_ASIDE = "module.place_proven = lambda *args: os._exit(9)\n"

# Hook code that takes away the hard link from a held descriptor, as on a platform without /proc.
NO_PROC = (
    "import errno\n"
    "linking = os.link\n"
    "def no_proc(source, *args, **kwargs):\n"
    "    if str(source).startswith('/proc/'):\n"
    "        raise FileNotFoundError(errno.ENOENT, os.strerror(errno.ENOENT), source)\n"
    "    return linking(source, *args, **kwargs)\n"
    "os.link = no_proc\n"
)


def unlock_failure(state, count):
    """Hook code that fails the unlock of the state lock, then writes to `count` how many descriptors the run still has open on `state`."""
    return (
        "import fcntl\n"
        "locking = fcntl.flock\n"
        "def flock(fd, operation):\n"
        "    if operation == fcntl.LOCK_UN:\n"
        "        raise OSError(5, 'injected unlock failure')\n"
        "    return locking(fd, operation)\n"
        "fcntl.flock = flock\n"
        "def still_open():\n"
        "    found = 0\n"
        "    for fd in os.listdir('/proc/self/fd'):\n"
        "        try:\n"
        f"            found += os.readlink(f'/proc/self/fd/{{fd}}') == {str(state)!r}\n"
        "        except OSError:\n"
        "            pass\n"
        "    return found\n"
        "running = module.main\n"
        "def main(*args):\n"
        "    try:\n"
        "        return running(*args)\n"
        "    except OSError as error:\n"
        "        print(f'unlock raised: {error}')\n"
        f"        Path({str(count)!r}).write_text(str(still_open()))\n"
        "        return 0\n"
        "module.main = main\n"
    )


class OwnershipTest(unittest.TestCase):
    def setUp(self):
        self.use_fresh()

    def use_fresh(self):
        wrapper, self.home = fresh_home()
        self.addCleanup(wrapper.cleanup)

    def ok(self, result, *lines):
        self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
        got = result.stdout.splitlines()
        for line in lines:
            self.assertIn(line, got)

    def skipped(self, result, *lines):
        self.assertEqual(result.returncode, 3, result.stderr + result.stdout)
        got = result.stdout.splitlines()
        for line in lines:
            self.assertIn(line, got)

    def assert_empty_records(self):
        self.assertTrue(legacy_file(self.home).is_file())
        data = read_legacy(self.home)
        self.assertEqual(data["links"], [])
        self.assertEqual(data["backups"], [])
        owners = state_dir(self.home) / "install-owners"
        found = list(owners.glob("*.json")) if owners.is_dir() else []
        self.assertEqual(found, [])

    def assert_claims(self, checkout, paths):
        data = read_owner(self.home, checkout)
        self.assertIsNotNone(data, checkout)
        self.assertEqual(data["checkout"], str(checkout))
        self.assertEqual(set(data["links"]), set(paths))

    def assert_grok_text(self, checkout, names=NAMES):
        for name in names:
            link = provider_link(self.home, "grok", name)
            self.assertEqual(os.readlink(link), str(checkout / "skills" / name), name)
            self.assertEqual((link / "SKILL.md").read_bytes(), (checkout / "skills" / name / "SKILL.md").read_bytes())

    def assert_gone(self, names=NAMES, harness="grok"):
        for name in names:
            self.assertFalse(os.path.lexists(provider_link(self.home, harness, name)))

    def two(self):
        return make_checkout(self.home, "a"), make_checkout(self.home, "b")

    def base(self):
        a, b = self.two()
        self.ok(run(self.home, a, "--harness", "grok"))
        self.ok(run(self.home, b, "--harness", "grok", "--replace"))
        return a, b

    def test_old_installer_matches_397d163(self):
        self.assertEqual(hashlib.sha256(OLD_INSTALLER.encode()).hexdigest(), OLD_SHA)

    def test_row_1_replaced_owner_stays_tracked(self):
        a, b = self.base()
        self.ok(run(self.home, b, "--harness", "grok", "uninstall"), "removed 3 links, restored 3 entries")
        self.assert_claims(a, grok_paths(self.home))
        self.assert_grok_text(a)
        self.ok(run(self.home, a, "--harness", "grok", "uninstall"), "removed 3 links, restored 0 entries")
        self.assert_gone()
        self.assert_empty_records()

    def test_row_1b_owner_withdraws_links_another_checkout_moved_aside(self):
        a, b = self.base()
        self.ok(
            run(self.home, a, "--harness", "grok", "uninstall"),
            "removed 3 links, restored 0 entries",
            "3 of them had been moved aside by another checkout's --replace",
        )
        self.assert_grok_text(b)
        self.assert_claims(b, grok_paths(self.home))
        self.ok(run(self.home, b, "--harness", "grok", "uninstall"), "removed 3 links, restored 0 entries")
        self.assert_gone()
        self.assert_empty_records()

    def repoint_swarm(self, target):
        link = provider_link(self.home, "grok", "swarm")
        link.unlink()
        os.symlink(target, link)
        return str(target)

    def assert_repoint_survives(self, a, text):
        link = provider_link(self.home, "grok", "swarm")
        self.ok(
            run(self.home, a, "--harness", "grok", "uninstall"),
            "removed 2 links, restored 0 entries",
            KEPT.format(n=1),
        )
        self.assertEqual(os.readlink(link), text)
        self.assert_claims(a, [str(link)])
        before = snapshot(self.home)
        self.ok(
            run(self.home, a, "--harness", "grok", "uninstall"),
            "removed 0 links, restored 0 entries",
            KEPT.format(n=1),
        )
        self.assertEqual(snapshot(self.home), before)
        self.assertEqual(os.readlink(link), text)

    def test_row_2_repointed_link_to_an_existing_directory_is_left_alone(self):
        a, b = self.base()
        self.ok(run(self.home, b, "--harness", "grok", "uninstall"), "removed 3 links, restored 3 entries")
        target = self.home / "unrelated-dir"
        target.mkdir()
        text = self.repoint_swarm(target)
        self.assert_repoint_survives(a, text)
        link = provider_link(self.home, "grok", "swarm")
        link.unlink()
        os.symlink(a / "skills" / "swarm", link)
        self.ok(run(self.home, a, "--harness", "grok", "uninstall"), "removed 1 links, restored 0 entries")
        self.assertFalse(os.path.lexists(link))
        self.assert_empty_records()

    def test_row_3_repointed_dangling_link_is_left_alone(self):
        a, b = self.base()
        self.ok(run(self.home, b, "--harness", "grok", "uninstall"), "removed 3 links, restored 3 entries")
        text = self.repoint_swarm(self.home / "missing-target")
        self.assert_repoint_survives(a, text)

    def foreign_then_both_uninstall(self, target):
        a, b = self.two()
        link = provider_link(self.home, "grok", "swarm")
        link.parent.mkdir(parents=True)
        os.symlink(target, link)
        text = str(target)
        self.ok(run(self.home, a, "--harness", "grok", "--replace"))
        self.ok(run(self.home, b, "--harness", "grok", "--replace"))
        self.ok(run(self.home, b, "--harness", "grok", "uninstall"), "removed 3 links, restored 3 entries")
        self.ok(run(self.home, a, "--harness", "grok", "uninstall"), "removed 3 links, restored 1 entries")
        self.assertEqual(os.readlink(link), text)
        self.assertEqual((link / "SKILL.md").read_bytes(), (target / "SKILL.md").read_bytes() if (target / "SKILL.md").exists() else (link / "SKILL.md").read_bytes())
        for name in ("alpha", "pstack-runtime"):
            self.assertFalse(os.path.lexists(provider_link(self.home, "grok", name)))
        self.assert_empty_records()
        before = snapshot(self.home)
        self.ok(run(self.home, a, "--harness", "grok", "uninstall"), "removed 0 links, restored 0 entries")
        self.assertEqual(snapshot(self.home), before)

    def test_row_4_foreign_symlink_comes_back_untracked(self):
        target = self.home / "foreign-target"
        target.mkdir()
        (target / "SKILL.md").write_text("foreign-skill\n")
        self.foreign_then_both_uninstall(target)
        self.assertEqual((provider_link(self.home, "grok", "swarm") / "SKILL.md").read_text(), "foreign-skill\n")

    def test_row_5_repointed_lookalike_link_is_left_alone(self):
        a, b = self.base()
        self.ok(run(self.home, b, "--harness", "grok", "uninstall"), "removed 3 links, restored 3 entries")
        lookalike = self.home / "lookalike"
        (lookalike / "scripts").mkdir(parents=True)
        (lookalike / "scripts" / "install.py").write_text("print('unrelated installer')\n")
        (lookalike / "skills" / "swarm").mkdir(parents=True)
        (lookalike / "skills" / "swarm" / "SKILL.md").write_text("lookalike\n")
        text = self.repoint_swarm(lookalike / "skills" / "swarm")
        self.assert_repoint_survives(a, text)
        self.assertEqual((lookalike / "scripts" / "install.py").read_text(), "print('unrelated installer')\n")
        self.assertEqual((lookalike / "skills" / "swarm" / "SKILL.md").read_text(), "lookalike\n")

    def test_row_6_lookalike_symlink_comes_back_untracked(self):
        lookalike = self.home / "lookalike"
        (lookalike / "scripts").mkdir(parents=True)
        (lookalike / "scripts" / "install.py").write_text("print('unrelated installer')\n")
        (lookalike / "skills" / "swarm").mkdir(parents=True)
        (lookalike / "skills" / "swarm" / "SKILL.md").write_text("lookalike\n")
        self.foreign_then_both_uninstall(lookalike / "skills" / "swarm")
        self.assertEqual((lookalike / "scripts" / "install.py").read_text(), "print('unrelated installer')\n")
        self.assertEqual((provider_link(self.home, "grok", "swarm") / "SKILL.md").read_text(), "lookalike\n")

    def alias_of(self, checkout):
        alias = self.home / "a-alias"
        os.symlink(checkout, alias)
        return alias

    def test_row_7_alias_spelled_link_stays_untracked(self):
        a, b = self.two()
        alias = self.alias_of(a)
        self.ok(run(self.home, a, "--harness", "grok"))
        link = provider_link(self.home, "grok", "swarm")
        link.unlink()
        text = str(alias / "skills" / "swarm")
        os.symlink(text, link)
        self.ok(run(self.home, b, "--harness", "grok", "--replace"))
        self.ok(run(self.home, b, "--harness", "grok", "uninstall"), "removed 3 links, restored 3 entries")
        self.ok(
            run(self.home, alias, "--harness", "grok", "uninstall"),
            "removed 2 links, restored 0 entries",
            KEPT.format(n=1),
        )
        self.assertEqual(os.readlink(link), text)
        self.assertEqual((link / "SKILL.md").read_bytes(), (a / "skills" / "swarm" / "SKILL.md").read_bytes())
        self.assert_claims(a, [str(link)])
        before = snapshot(self.home)
        self.ok(run(self.home, a, "--harness", "grok", "uninstall"), "removed 0 links, restored 0 entries")
        self.assertEqual(snapshot(self.home), before)
        self.assertEqual(os.readlink(link), text)

    def test_row_7u_legacy_rows_do_not_adopt_an_alias_spelling(self):
        a, b = self.two()
        alias = self.alias_of(a)
        self.ok(run(self.home, a, "--harness", "grok"))
        paths = grok_paths(self.home)
        owner = owner_file(self.home, a)
        if owner.exists():
            owner.unlink()
        write_legacy(self.home, [{"harnesses": ["grok"], "path": path} for path in paths], [])
        link = provider_link(self.home, "grok", "swarm")
        link.unlink()
        text = str(alias / "skills" / "swarm")
        os.symlink(text, link)
        self.ok(run(self.home, b, "--harness", "grok", "--replace"))
        self.ok(run(self.home, b, "--harness", "grok", "uninstall"), "removed 3 links, restored 3 entries")
        self.ok(run(self.home, alias, "--harness", "grok", "uninstall"), "removed 2 links, restored 0 entries")
        self.assertEqual(os.readlink(link), text)
        self.assertEqual((link / "SKILL.md").read_bytes(), (a / "skills" / "swarm" / "SKILL.md").read_bytes())
        left = read_legacy(self.home)["links"]
        self.assertEqual(left, [{"harnesses": ["grok"], "path": str(link)}])
        self.ok(run(self.home, a, "--harness", "grok", "uninstall"), "removed 0 links, restored 0 entries")
        self.assertEqual(os.readlink(link), text)
        self.assertEqual(read_legacy(self.home)["links"], [{"harnesses": ["grok"], "path": str(link)}])

    def test_row_8_relative_link_text_is_restored_exactly(self):
        a, b = self.two()
        self.ok(run(self.home, a, "--harness", "grok"))
        expected = {}
        for name in NAMES:
            link = provider_link(self.home, "grok", name)
            relative = os.path.relpath(os.readlink(link), link.parent)
            link.unlink()
            os.symlink(relative, link)
            expected[name] = relative
        self.ok(run(self.home, b, "--harness", "grok", "--replace"))
        self.ok(run(self.home, b, "--harness", "grok", "uninstall"), "removed 3 links, restored 3 entries")
        for name in NAMES:
            link = provider_link(self.home, "grok", name)
            self.assertEqual(os.readlink(link), expected[name])
            self.assertEqual((link / "SKILL.md").read_bytes(), (a / "skills" / name / "SKILL.md").read_bytes())
        self.assert_claims(a, grok_paths(self.home))
        self.ok(run(self.home, a, "--harness", "grok", "uninstall"), "removed 3 links, restored 0 entries")
        self.assert_gone()
        self.assert_empty_records()

    def test_row_9_alias_invocation_records_the_canonical_checkout(self):
        a, b = self.two()
        alias = self.alias_of(a)
        self.ok(run(self.home, alias, "--harness", "grok"))
        self.assert_grok_text(a)
        self.assert_claims(a, grok_paths(self.home))
        self.ok(run(self.home, b, "--harness", "grok", "--replace"))
        self.ok(run(self.home, b, "--harness", "grok", "uninstall"), "removed 3 links, restored 3 entries")
        self.assert_claims(a, grok_paths(self.home))
        self.ok(run(self.home, alias, "--harness", "grok", "uninstall"), "removed 3 links, restored 0 entries")
        self.assert_gone()
        self.assert_empty_records()

    def share_skills(self, source, dest):
        shutil.rmtree(dest / "skills")
        os.symlink(source / "skills", dest / "skills")

    def assert_shared_tree(self, installer, other):
        self.ok(run(self.home, installer, "--harness", "grok"))
        self.ok(run(self.home, other, "--harness", "grok", "uninstall"), "removed 0 links, restored 0 entries")
        self.assert_grok_text(installer)
        self.assert_claims(installer, grok_paths(self.home))
        self.ok(run(self.home, installer, "--harness", "grok", "uninstall"), "removed 3 links, restored 0 entries")
        self.assert_gone()
        self.assert_empty_records()

    def test_row_10_forward_shared_skills_tree(self):
        a, b = self.two()
        self.share_skills(a, b)
        self.assert_shared_tree(b, a)

    def test_row_10_reverse_shared_skills_tree(self):
        a, b = self.two()
        self.share_skills(b, a)
        self.assert_shared_tree(b, a)

    def test_row_11a_deleted_checkout_links_stay_and_the_other_owner_remains(self):
        a, b = self.two()
        later = make_checkout(self.home, "l")
        self.ok(run(self.home, later, "--harness", "codex"))
        self.ok(run(self.home, a, "--harness", "grok"))
        texts = {name: os.readlink(provider_link(self.home, "grok", name)) for name in NAMES}
        shutil.rmtree(a)
        self.ok(run(self.home, b, "uninstall"), "removed 0 links, restored 0 entries")
        for name in NAMES:
            link = provider_link(self.home, "grok", name)
            self.assertTrue(os.path.lexists(link))
            self.assertFalse(os.path.exists(link))
            self.assertEqual(os.readlink(link), texts[name])
        self.assert_claims(a, grok_paths(self.home))
        codex_paths = [str(provider_link(self.home, "codex", name)) for name in NAMES]
        self.assert_claims(later, codex_paths)
        self.ok(run(self.home, later, "--harness", "codex", "uninstall"), "removed 3 links, restored 0 entries")
        for name in NAMES:
            self.assertEqual(os.readlink(provider_link(self.home, "grok", name)), texts[name])
        self.assert_claims(a, grok_paths(self.home))
        tagged = [row for row in read_legacy(self.home)["links"] if row.get("checkout") == str(a)]
        self.assertEqual({row["path"] for row in tagged}, set(grok_paths(self.home)))
        self.assertIsNone(read_owner(self.home, later))

    def test_row_11b_deleted_owner_is_restored_untracked_beside_a_live_owner(self):
        a, b = self.two()
        later = make_checkout(self.home, "l")
        self.ok(run(self.home, a, "--harness", "grok"))
        texts = {name: os.readlink(provider_link(self.home, "grok", name)) for name in NAMES}
        self.ok(run(self.home, later, "--harness", "codex"))
        self.ok(run(self.home, b, "--harness", "grok", "--replace"))
        shutil.rmtree(a)
        self.ok(run(self.home, b, "--harness", "grok", "uninstall"), "removed 3 links, restored 3 entries")
        for name in NAMES:
            link = provider_link(self.home, "grok", name)
            self.assertTrue(os.path.lexists(link))
            self.assertFalse(os.path.exists(link))
            self.assertEqual(os.readlink(link), texts[name])
        self.assert_claims(a, grok_paths(self.home))
        self.assert_claims(later, [str(provider_link(self.home, "codex", name)) for name in NAMES])
        self.ok(run(self.home, later, "--harness", "codex", "uninstall"), "removed 3 links, restored 0 entries")
        for name in NAMES:
            self.assertEqual(os.readlink(provider_link(self.home, "grok", name)), texts[name])
        self.assert_claims(a, grok_paths(self.home))
        self.assert_gone(harness="codex")

    def test_row_12a_dry_run_matches_a_covered_foreign_file(self):
        a, b = self.two()
        self.share_skills(a, b)
        swarm = provider_link(self.home, "grok", "swarm")
        swarm.parent.mkdir(parents=True)
        swarm.write_bytes(b"foreign\x00file\n")
        self.ok(run(self.home, b, "--harness", "grok", "--replace"))
        before = snapshot(self.home)
        dry = run(self.home, a, "--harness", "grok", "uninstall", "--dry-run")
        self.ok(dry, "would remove 0 links, would restore 0 entries")
        self.assertIn(f"{swarm} is occupied; clear it and rerun uninstall", dry.stdout)
        self.assertEqual(snapshot(self.home), before)
        self.ok(run(self.home, a, "--harness", "grok", "uninstall"), "removed 0 links, restored 0 entries")
        self.assertEqual(snapshot(self.home), before)
        self.assert_grok_text(b)
        self.ok(run(self.home, b, "--harness", "grok", "uninstall"), "removed 3 links, restored 1 entries")
        self.assertEqual(swarm.read_bytes(), b"foreign\x00file\n")
        self.assertFalse(swarm.is_symlink())
        self.assert_empty_records()

    def test_row_12b_dry_run_counts_each_path_once(self):
        a, b = self.base()
        before = snapshot(self.home)
        self.ok(
            run(self.home, b, "--harness", "grok", "uninstall", "--dry-run"),
            "would remove 3 links, would restore 3 entries",
        )
        self.assertEqual(snapshot(self.home), before)
        self.assert_grok_text(b)
        self.ok(run(self.home, b, "--harness", "grok", "uninstall"), "removed 3 links, restored 3 entries")
        self.assert_grok_text(a)
        self.assert_claims(a, grok_paths(self.home))

    def test_row_13_three_replace_cycles_keep_one_row_per_path(self):
        a, b = self.two()
        self.ok(run(self.home, a, "--harness", "grok"))
        paths = grok_paths(self.home)
        for _ in range(3):
            self.ok(run(self.home, b, "--harness", "grok", "--replace"))
            self.ok(run(self.home, b, "--harness", "grok", "uninstall"), "removed 3 links, restored 3 entries")
            self.assert_claims(a, paths)
            tagged = [row for row in read_legacy(self.home)["links"] if row.get("checkout") == str(a)]
            self.assertEqual(len(tagged), 3)
            self.assertEqual({row["path"] for row in tagged}, set(paths))
            self.assertIsNone(read_owner(self.home, b))
        self.ok(run(self.home, a, "--harness", "grok", "uninstall"), "removed 3 links, restored 0 entries")
        self.assert_gone()
        self.assert_empty_records()

    def legacy_links(self, shape, paths):
        links = []
        for path in paths:
            if shape == "harnesses":
                row = {"harnesses": ["grok"], "path": path}
            elif shape == "harness":
                row = {"harness": "grok", "path": path}
            else:
                row = path
            links.append(row)
            links.append(json.loads(json.dumps(row)))
        return links

    def plant_legacy(self, shape):
        a = make_checkout(self.home, "a")
        self.ok(run(self.home, a, "--harness", "grok"))
        paths = grok_paths(self.home)
        owner = owner_file(self.home, a)
        if owner.exists():
            owner.unlink()
        write_legacy(self.home, self.legacy_links(shape, paths), [])
        return a, paths

    def legacy_rows(self):
        return read_legacy(self.home)["links"]

    def legacy_shape(self, shape):
        a, paths = self.plant_legacy(shape)
        planted = self.legacy_rows()
        adopted = run(self.home, a, "--harness", "grok")
        self.ok(adopted, "linked 0 skills into nothing (already installed)", ADOPTED.format(n=3))
        self.assertNotIn(UNTRACKED, adopted.stdout)
        self.assertEqual(self.legacy_rows(), planted)
        self.assert_claims(a, paths)
        self.assert_grok_text(a)

        self.use_fresh()
        a, paths = self.plant_legacy(shape)
        b = make_checkout(self.home, "b")
        self.ok(run(self.home, b, "--harness", "grok", "--replace"))
        self.ok(run(self.home, b, "--harness", "grok", "uninstall"), "removed 3 links, restored 3 entries")
        self.assert_grok_text(a)
        self.ok(run(self.home, a, "--harness", "grok", "uninstall"), "removed 3 links, restored 0 entries")
        self.assert_gone()
        self.assertIsNone(read_owner(self.home, a))
        self.assertEqual(len(self.legacy_rows()), 3)
        self.assertEqual(set(self._row_path(row) for row in self.legacy_rows()), set(paths))

        self.use_fresh()
        a, paths = self.plant_legacy(shape)
        b = make_checkout(self.home, "b")
        self.ok(run(self.home, b, "--harness", "grok", "uninstall"), "removed 0 links, restored 0 entries")
        self.assert_grok_text(a)
        self.ok(run(self.home, a, "--harness", "grok", "uninstall"), "removed 3 links, restored 0 entries")
        self.assert_gone()
        self.assertEqual(len(self.legacy_rows()), 3)

    def _row_path(self, row):
        return row["path"] if isinstance(row, dict) else row

    def test_row_14_harnesses_shape(self):
        self.legacy_shape("harnesses")

    def test_row_14_harness_shape(self):
        self.legacy_shape("harness")

    def test_row_14_bare_string_shape(self):
        self.legacy_shape("bare")

    def test_row_14b_legacy_backup_restores_an_untracked_link(self):
        a, b = self.two()
        plant_links(self.home, b)
        backup_dir = state_dir(self.home) / "backups" / "old" / "grok"
        backup_dir.mkdir(parents=True)
        links = []
        backups = []
        for name in NAMES:
            original = str(provider_link(self.home, "grok", name))
            backup = backup_dir / name
            os.symlink(a / "skills" / name, backup)
            links.append({"harnesses": ["grok"], "path": original})
            links.append({"harnesses": ["grok"], "path": original})
            backups.append({"harnesses": ["grok"], "original": original, "backup": str(backup)})
        write_legacy(self.home, links, backups)
        sentinel = self.home / "sentinel.txt"
        sentinel.write_text("keep\n")
        skill_bytes = {
            checkout / "skills" / name / "SKILL.md": (checkout / "skills" / name / "SKILL.md").read_bytes()
            for checkout in (a, b)
            for name in NAMES
        }
        self.ok(run(self.home, b, "--harness", "grok", "uninstall"), "removed 3 links, restored 3 entries")
        self.assert_grok_text(a)
        for path, content in skill_bytes.items():
            self.assertEqual(path.read_bytes(), content)
        self.assertEqual(sentinel.read_text(), "keep\n")
        adopted = run(self.home, a, "--harness", "grok")
        self.ok(adopted, "linked 0 skills into nothing (already installed)", ADOPTED.format(n=3))
        self.assertNotIn(UNTRACKED, adopted.stdout)
        self.assert_claims(a, grok_paths(self.home))
        self.assert_grok_text(a)
        self.ok(run(self.home, a, "--harness", "grok", "uninstall"), "removed 3 links, restored 0 entries")
        self.assert_gone()
        self.assertEqual(sentinel.read_text(), "keep\n")
        for path, content in skill_bytes.items():
            self.assertEqual(path.read_bytes(), content)

    def test_row_14c_old_manifest_file_cannot_erase_current_rows(self):
        a = make_checkout(self.home, "a")
        other = make_checkout(self.home, "c")
        self.ok(run(self.home, a, "--harness", "grok"))
        before = owner_file(self.home, a).read_bytes()
        plant_links(self.home, other, "codex")
        legacy_file(self.home).unlink()
        self.assertEqual(owner_file(self.home, a).read_bytes(), before)
        self.assertFalse(legacy_file(self.home).exists())
        self.ok(run(self.home, a, "--harness", "grok", "uninstall"), "removed 3 links, restored 0 entries")
        self.assert_gone()
        self.assertFalse(legacy_file(self.home).exists())
        self.assertIsNone(read_owner(self.home, a))
        for name in NAMES:
            link = provider_link(self.home, "codex", name)
            self.assertEqual(os.readlink(link), str(other / "skills" / name))
            self.assertEqual((link / "SKILL.md").read_bytes(), (other / "skills" / name / "SKILL.md").read_bytes())

    def test_project_scope_refuses_a_directory_shared_with_user_scope(self):
        a = make_checkout(self.home, "a")
        self.ok(run(self.home, a, "--harness", "grok"))
        before = snapshot(state_dir(self.home))
        project = self.home / "project"
        project_skills = project / ".grok" / "skills"
        project_skills.parent.mkdir(parents=True)
        os.symlink(self.home / ".grok" / "skills", project_skills)
        refusal = f"grok: {project_skills} already resolves to {self.home / '.grok' / 'skills'}; nothing to link"
        self.ok(run(self.home, a, "--project", str(project), "--harness", "grok"), refusal)
        self.assertEqual(snapshot(state_dir(self.home)), before)
        self.assert_grok_text(a)
        self.assertFalse((project / ".pstack").exists())

    def test_project_scope_leaves_holders_in_a_directory_shared_with_user_scope(self):
        a = make_checkout(self.home, "a")
        self.ok(run(self.home, a, "--harness", "grok"))
        shared = self.home / ".grok" / "skills"
        project = self.home / "project"
        (project / ".grok").mkdir(parents=True)
        os.symlink(shared, project / ".grok" / "skills")
        empty = shared / ".pstack-t3-live0000"
        empty.mkdir()
        stray = shared / ".pstack-t3-other000" / "notes"
        stray.parent.mkdir()
        stray.write_bytes(b"stray\x00\xfd")
        for command in ((), ("uninstall",)):
            with self.subTest(command=command):
                result = run(self.home, a, "--project", str(project), "--harness", "grok", *command)
                self.ok(result)
                self.assertNotIn(".pstack-t3-", result.stdout + result.stderr)
                self.assertEqual(os.listdir(empty), [])
                self.assertEqual(stray.read_bytes(), b"stray\x00\xfd")
                self.assertFalse((project / ".pstack").exists())

    def share_cursor_with_agents(self):
        agents = self.home / ".agents" / "skills"
        agents.mkdir(parents=True)
        (agents / "swarm").write_bytes(b"foreign\x00file\n")
        cursor = self.home / ".cursor" / "skills"
        cursor.parent.mkdir(parents=True)
        os.symlink(agents, cursor)
        return agents

    def test_c3_shared_provider_directory_carries_both_harnesses(self):
        a, b = self.two()
        agents = self.share_cursor_with_agents()
        self.ok(run(self.home, a, "--harness", "codex", "--replace"))
        self.ok(run(self.home, b, "--harness", "cursor", "--replace"))
        self.ok(
            run(self.home, a, "--harness", "codex", "uninstall"),
            "removed 0 links, restored 0 entries",
            "kept entries whose directory is shared with cursor; select those harnesses too to remove them",
        )
        self.assertEqual(os.readlink(agents / "swarm"), str(b / "skills" / "swarm"))
        self.ok(
            run(self.home, a, "--harness", "codex,cursor", "uninstall"),
            "removed 3 links, restored 0 entries",
            "3 of them had been moved aside by another checkout's --replace",
        )
        self.assertEqual(os.readlink(agents / "swarm"), str(b / "skills" / "swarm"))
        self.assertEqual((agents / "swarm" / "SKILL.md").read_bytes(), (b / "skills" / "swarm" / "SKILL.md").read_bytes())
        self.ok(run(self.home, b, "--harness", "codex,cursor", "uninstall"), "removed 3 links, restored 1 entries")
        self.assertEqual((agents / "swarm").read_bytes(), b"foreign\x00file\n")
        self.assertFalse((agents / "swarm").is_symlink())
        self.assert_empty_records()

    def test_partial_selection_does_not_restore_over_a_live_link(self):
        a = make_checkout(self.home, "a")
        agents = self.share_cursor_with_agents()
        self.ok(run(self.home, a, "--harness", "codex", "--replace"))
        self.ok(run(self.home, a, "--harness", "cursor"), "linked 0 skills into nothing (already installed)")
        text = os.readlink(agents / "swarm")
        self.assertEqual(text, str(a / "skills" / "swarm"))
        saved = [path.read_bytes() for path in (state_dir(self.home) / "backups").rglob("swarm") if path.is_file()]
        self.assertEqual(saved, [b"foreign\x00file\n"])
        before = snapshot(self.home)
        self.ok(
            run(self.home, a, "--harness", "codex", "uninstall"),
            "removed 0 links, restored 0 entries",
            "kept entries whose directory is shared with cursor; select those harnesses too to remove them",
        )
        self.assertEqual(snapshot(self.home), before)
        self.assertEqual(os.readlink(agents / "swarm"), text)
        saved_after = [path.read_bytes() for path in (state_dir(self.home) / "backups").rglob("swarm") if path.is_file()]
        self.assertEqual(saved_after, [b"foreign\x00file\n"])

    def test_crash_between_action_halves_converges(self):
        a = make_checkout(self.home, "a")
        foreign = provider_link(self.home, "grok", "alpha")
        foreign.parent.mkdir(parents=True)
        foreign.write_bytes(b"keep-me\n")
        swarm = provider_link(self.home, "grok", "swarm")
        write_owner(self.home, a, [str(swarm)])
        self.ok(
            run(self.home, a, "--harness", "grok", "uninstall"),
            "removed 0 links, restored 0 entries",
            KEPT.format(n=1),
        )
        self.assertFalse(os.path.lexists(swarm))
        self.assertEqual(foreign.read_bytes(), b"keep-me\n")
        self.assert_claims(a, [str(swarm)])

        self.use_fresh()
        a = make_checkout(self.home, "a")
        plant_links(self.home, a)
        paths = grok_paths(self.home)
        backups = []
        for name in NAMES:
            link = str(provider_link(self.home, "grok", name))
            backups.append({
                "original": link,
                "harnesses": ["grok"],
                "backup": str(state_dir(self.home) / "backups" / "missing" / name),
            })
        write_owner(self.home, a, paths)
        write_legacy(self.home, [], backups)
        kept = self.home / "kept.txt"
        kept.write_text("kept\n")
        self.ok(run(self.home, a, "--harness", "grok", "uninstall"), "removed 3 links, restored 0 entries")
        self.assert_gone()
        self.assertEqual(kept.read_text(), "kept\n")
        self.assertEqual(len(read_legacy(self.home)["backups"]), 3)
        self.assertIsNone(read_owner(self.home, a))

        self.use_fresh()
        a = make_checkout(self.home, "a")
        plant_links(self.home, a)
        swarm = provider_link(self.home, "grok", "swarm")
        swarm.unlink()
        swarm.write_bytes(b"foreign\x00file\n")
        write_owner(self.home, a, grok_paths(self.home))
        self.ok(
            run(self.home, a, "--harness", "grok", "uninstall"),
            "removed 2 links, restored 0 entries",
            KEPT.format(n=1),
        )
        self.assertEqual(swarm.read_bytes(), b"foreign\x00file\n")
        self.assertFalse(swarm.is_symlink())
        for name in ("alpha", "pstack-runtime"):
            self.assertFalse(os.path.lexists(provider_link(self.home, "grok", name)))
        self.assert_claims(a, [str(swarm)])

        self.use_fresh()
        a, b = self.two()
        plant_links(self.home, b)
        paths = grok_paths(self.home)
        write_owner(self.home, b, paths)
        write_owner(self.home, a, paths)
        backups = []
        for name in NAMES:
            link = str(provider_link(self.home, "grok", name))
            backups.append({
                "original": link,
                "harnesses": ["grok"],
                "backup": str(state_dir(self.home) / "backups" / "gone" / name),
            })
        write_legacy(self.home, [], backups)
        kept = self.home / "kept.txt"
        kept.write_text("kept\n")
        self.ok(run(self.home, a, "--harness", "grok", "uninstall"), "removed 0 links, restored 0 entries")
        self.assert_grok_text(b)
        self.assert_claims(a, paths)
        self.assert_claims(b, paths)
        self.ok(run(self.home, b, "--harness", "grok", "uninstall"), "removed 3 links, restored 0 entries")
        self.assert_gone()
        self.assertEqual(kept.read_text(), "kept\n")
        self.assert_claims(a, paths)
        self.assertIsNone(read_owner(self.home, b))
        self.assertEqual(len(read_legacy(self.home)["backups"]), 3)

        self.use_fresh()
        a = make_checkout(self.home, "a")
        swarm = provider_link(self.home, "grok", "swarm")
        swarm.parent.mkdir(parents=True)
        swarm.write_bytes(b"foreign\x00file\n")
        write_legacy(self.home, [], [{
            "original": str(swarm),
            "harnesses": ["grok"],
            "backup": str(state_dir(self.home) / "backups" / "gone" / "swarm"),
            "note": "keep",
        }])
        self.ok(run(self.home, a, "--harness", "grok", "uninstall"), "removed 0 links, restored 0 entries")
        self.assertEqual(swarm.read_bytes(), b"foreign\x00file\n")
        self.assertEqual(read_legacy(self.home)["backups"][0]["note"], "keep")

        self.use_fresh()
        a = make_checkout(self.home, "a")
        plant_links(self.home, a)
        paths = grok_paths(self.home)
        backups = []
        for name in NAMES:
            link = str(provider_link(self.home, "grok", name))
            backups.append({
                "original": link,
                "harnesses": ["grok"],
                "backup": str(state_dir(self.home) / "backups" / "gone" / name),
                "note": "keep",
            })
        write_owner(self.home, a, paths)
        write_legacy(self.home, [], backups)
        kept = self.home / "kept.txt"
        kept.write_text("kept\n")
        self.ok(run(self.home, a, "--harness", "grok", "uninstall"), "removed 3 links, restored 0 entries")
        self.assert_gone()
        self.assertEqual(kept.read_text(), "kept\n")
        self.assertEqual([row["note"] for row in read_legacy(self.home)["backups"]], ["keep", "keep", "keep"])
        self.assertIsNone(read_owner(self.home, a))

    def resume(self, proc, ready, go, during):
        try:
            deadline = time.monotonic() + 30
            while not ready.exists():
                if proc.poll() is not None:
                    out, err = proc.communicate()
                    self.fail(f"paused install exited early\n{out}\n{err}")
                if time.monotonic() > deadline:
                    self.fail("paused install did not reach load")
                time.sleep(0.01)
            during()
            go.touch()
            out, err = proc.communicate(timeout=30)
        finally:
            if proc.poll() is None:
                proc.kill()
                proc.communicate()
        self.assertEqual(proc.returncode, 0, err + out)
        return out

    def test_f1a_paused_noop_race_when_legacy_is_created(self):
        a = make_checkout(self.home, "a")
        c = make_checkout(self.home, "c", old=True)
        self.ok(run(self.home, a, "--harness", "grok"))
        proc, ready, go = pause_after_load(self.home, a, ["--harness", "grok"])
        out = self.resume(proc, ready, go, lambda: self.ok(run(self.home, c, "--harness", "codex")))
        self.assertIn("already installed", out)
        self.ok(run(self.home, c, "--harness", "codex", "uninstall"), "removed 3 links, restored 0 entries")
        self.assert_gone(harness="codex")
        self.assert_grok_text(a)
        self.ok(run(self.home, a, "--harness", "grok", "uninstall"), "removed 3 links, restored 0 entries")
        self.assert_gone()

    def test_f1a_paused_noop_race_when_legacy_already_exists(self):
        a = make_checkout(self.home, "a", old=True)
        c = make_checkout(self.home, "c", old=True)
        self.ok(run(self.home, a, "--harness", "grok"))
        self.assertTrue(legacy_file(self.home).is_file())
        upgrade(a)
        proc, ready, go = pause_after_load(self.home, a, ["--harness", "grok"])
        out = self.resume(proc, ready, go, lambda: self.ok(run(self.home, c, "--harness", "codex")))
        self.assertIn("already installed", out)
        self.ok(run(self.home, c, "--harness", "codex", "uninstall"), "removed 3 links, restored 0 entries")
        self.assert_gone(harness="codex")
        self.assert_grok_text(a)
        upgrade(a)
        self.ok(run(self.home, a, "--harness", "grok", "uninstall"), "removed 3 links, restored 0 entries")
        self.assert_gone()

    def test_f1b_older_operator_still_uninstalls(self):
        a = make_checkout(self.home, "a", old=True)
        b = make_checkout(self.home, "b")
        swarm = provider_link(self.home, "grok", "swarm")
        swarm.parent.mkdir(parents=True)
        swarm.write_bytes(b"operator foreign\x00bytes")
        self.ok(run(self.home, a, "--harness", "grok", "--replace"))
        self.ok(run(self.home, b, "--harness", "codex"))
        self.ok(run(self.home, b, "--harness", "codex", "uninstall"), "removed 3 links, restored 0 entries")
        self.assert_gone(harness="codex")
        self.ok(run(self.home, a, "--harness", "grok", "uninstall"), "removed 3 links, restored 1 entries")
        self.assertEqual(swarm.read_bytes(), b"operator foreign\x00bytes")
        self.assertFalse(swarm.is_symlink())
        self.assert_gone(("alpha", "pstack-runtime"))

    def test_f1c_mixed_replacement_keeps_the_first_owner(self):
        a = make_checkout(self.home, "a")
        b = make_checkout(self.home, "b", old=True)
        c = make_checkout(self.home, "c")
        self.ok(run(self.home, a, "--harness", "grok"))
        self.ok(run(self.home, b, "--harness", "grok", "--replace"))
        self.ok(run(self.home, c, "--harness", "codex"))
        upgrade(b)
        self.ok(run(self.home, b, "--harness", "grok", "uninstall"), "removed 3 links, restored 3 entries")
        self.assert_grok_text(a)
        self.ok(run(self.home, a, "--harness", "grok", "uninstall"), "removed 3 links, restored 0 entries")
        self.assert_gone()
        self.ok(run(self.home, c, "--harness", "codex", "uninstall"), "removed 3 links, restored 0 entries")
        self.assert_gone(harness="codex")
        self.assert_empty_records()

    def test_f1d_mixed_replacement_restores_the_newer_layer(self):
        a = make_checkout(self.home, "a")
        b = make_checkout(self.home, "b", old=True)
        c = make_checkout(self.home, "c")
        swarm = provider_link(self.home, "grok", "swarm")
        swarm.parent.mkdir(parents=True)
        swarm.write_bytes(b"initial foreign\x00")
        self.ok(run(self.home, a, "--harness", "grok", "--replace"))
        self.ok(run(self.home, b, "--harness", "grok", "--replace"))
        self.ok(run(self.home, c, "--harness", "codex"))
        upgrade(b)
        self.ok(run(self.home, b, "--harness", "grok", "uninstall"), "removed 3 links, restored 3 entries")
        self.assert_grok_text(a)
        self.ok(run(self.home, a, "--harness", "grok", "uninstall"), "removed 3 links, restored 1 entries")
        self.assertEqual(swarm.read_bytes(), b"initial foreign\x00")
        self.assertFalse(swarm.is_symlink())
        self.assert_gone(("alpha", "pstack-runtime"))

    def _pruned(self):
        a = make_checkout(self.home, "a", old=True)
        c = make_checkout(self.home, "c")
        shutil.rmtree(a / "skills" / "pstack-runtime")
        self.ok(run(self.home, a, "--harness", "grok"), "linked 2 skills into grok")
        self.ok(run(self.home, c, "--harness", "codex"))
        return a, c

    def test_f1e_pruned_old_tree_uninstalls(self):
        a, c = self._pruned()
        self.ok(run(self.home, a, "--harness", "grok", "uninstall"), "removed 2 links, restored 0 entries")
        self.assert_gone(("alpha", "swarm"))
        self.assertEqual((a / "skills" / "swarm" / "SKILL.md").read_text(), "a-swarm\n")
        for name in NAMES:
            link = provider_link(self.home, "codex", name)
            self.assertEqual(os.readlink(link), str(c / "skills" / name))
        self.ok(run(self.home, c, "--harness", "codex", "uninstall"), "removed 3 links, restored 0 entries")
        self.assert_gone(harness="codex")

    def test_f1e_pruned_old_tree_uninstalls_after_upgrade(self):
        a, c = self._pruned()
        upgrade(a)
        self.ok(run(self.home, a, "--harness", "grok", "uninstall"), "removed 2 links, restored 0 entries")
        self.assert_gone(("alpha", "swarm"))
        for name in NAMES:
            link = provider_link(self.home, "codex", name)
            self.assertEqual(os.readlink(link), str(c / "skills" / name))
            self.assertEqual((link / "SKILL.md").read_bytes(), (c / "skills" / name / "SKILL.md").read_bytes())
        self.ok(run(self.home, c, "--harness", "codex", "uninstall"), "removed 3 links, restored 0 entries")
        self.assert_gone(harness="codex")

    def test_f2a_blocked_restore_keeps_the_backup(self):
        b = make_checkout(self.home, "b")
        swarm = provider_link(self.home, "grok", "swarm")
        swarm.parent.mkdir(parents=True)
        swarm.write_bytes(b"original foreign\x00bytes")
        self.ok(run(self.home, b, "--harness", "grok", "--replace"))
        blocked = squat_uninstall(self.home, b, swarm, b"new occupant\x00bytes", "--harness", "grok", "uninstall")
        self.skipped(blocked, "removed 3 links, restored 0 entries")
        self.assertIn("skipped restore", blocked.stdout)
        self.assertEqual(swarm.read_bytes(), b"new occupant\x00bytes")
        swarm.unlink()
        self.ok(run(self.home, b, "--harness", "grok", "uninstall"), "removed 0 links, restored 1 entries")
        self.assertEqual(swarm.read_bytes(), b"original foreign\x00bytes")
        self.assertFalse(swarm.is_symlink())

    def test_f2b_blocked_restore_keeps_the_displaced_owner(self):
        a, b = self.two()
        self.ok(run(self.home, a, "--harness", "grok"))
        self.ok(run(self.home, b, "--harness", "grok", "--replace"))
        swarm = provider_link(self.home, "grok", "swarm")
        blocked = squat_uninstall(self.home, b, swarm, b"new occupant", "--harness", "grok", "uninstall")
        self.skipped(blocked, "removed 3 links, restored 2 entries")
        self.assertIn("skipped restore", blocked.stdout)
        self.assertEqual(swarm.read_bytes(), b"new occupant")
        self.ok(
            run(self.home, a, "--harness", "grok", "uninstall"),
            "removed 3 links, restored 0 entries",
            "1 of them had been moved aside by another checkout's --replace",
        )
        self.assertEqual(swarm.read_bytes(), b"new occupant")
        self.assertFalse(swarm.is_symlink())
        self.assert_gone(("alpha", "pstack-runtime"))
        before = swarm.read_bytes()
        self.ok(run(self.home, a, "--harness", "grok", "uninstall"), "removed 0 links, restored 0 entries")
        self.assertEqual(swarm.read_bytes(), before)

    def test_f3a_provider_directory_move_keeps_ownership(self):
        a = make_checkout(self.home, "a")
        b = make_checkout(self.home, "b")
        self.ok(run(self.home, a, "--harness", "grok"))
        skills = self.home / ".grok" / "skills"
        dest = self.home / "relocated-skills"
        skills.rename(dest)
        skills.symlink_to(dest)
        self.assert_grok_text(a)
        self.ok(run(self.home, b, "--harness", "codex", "uninstall"), "removed 0 links, restored 0 entries")
        self.ok(run(self.home, a, "--harness", "grok", "uninstall"), "removed 3 links, restored 0 entries")
        self.assert_gone()

    def test_f3b_dotfiles_move_restores_at_the_current_path(self):
        a = make_checkout(self.home, "a")
        dots1 = self.home / "dots1" / "grok"
        (dots1 / "skills" / "swarm").mkdir(parents=True)
        (dots1 / "skills" / "swarm" / "SKILL.md").write_bytes(b"user directory\x00bytes")
        (self.home / ".grok").symlink_to(dots1)
        self.ok(run(self.home, a, "--harness", "grok", "--replace"))
        (self.home / "dots1").rename(self.home / "dots2")
        (self.home / ".grok").unlink()
        (self.home / ".grok").symlink_to(self.home / "dots2" / "grok")
        doctor = run(self.home, a, "--harness", "grok", "doctor")
        self.assertEqual(doctor.returncode, 0, doctor.stdout + doctor.stderr)
        self.assertIn("3/3 pstack-t3", doctor.stdout)
        self.ok(run(self.home, a, "--harness", "grok", "uninstall"), "removed 3 links, restored 1 entries")
        swarm = self.home / ".grok" / "skills" / "swarm"
        self.assertEqual((swarm / "SKILL.md").read_bytes(), b"user directory\x00bytes")
        self.assertFalse(swarm.is_symlink())
        self.assertFalse((self.home / "dots1").exists())
        self.assert_gone(("alpha", "pstack-runtime"))

    def test_f4a_temporary_absence_keeps_ownership(self):
        a = make_checkout(self.home, "a")
        c = make_checkout(self.home, "c")
        self.ok(run(self.home, a, "--harness", "grok"))
        away = self.home / "a-away"
        a.rename(away)
        self.ok(run(self.home, c, "--harness", "claude"))
        away.rename(a)
        self.ok(run(self.home, a, "--harness", "grok", "uninstall"), "removed 3 links, restored 0 entries")
        self.assert_gone()
        for name in NAMES:
            link = provider_link(self.home, "claude", name)
            self.assertEqual(os.readlink(link), str(c / "skills" / name))
        self.ok(run(self.home, c, "--harness", "claude", "uninstall"), "removed 3 links, restored 0 entries")
        self.assert_gone(harness="claude")

    def test_f4b_displaced_owner_survives_temporary_absence(self):
        a, b = self.two()
        c = make_checkout(self.home, "c")
        self.ok(run(self.home, a, "--harness", "grok"))
        self.ok(run(self.home, b, "--harness", "grok", "--replace"))
        away = self.home / "a-away"
        a.rename(away)
        self.ok(run(self.home, c, "--harness", "claude"))
        self.ok(run(self.home, c, "--harness", "claude", "uninstall"), "removed 3 links, restored 0 entries")
        away.rename(a)
        self.ok(
            run(self.home, a, "--harness", "grok", "uninstall"),
            "removed 3 links, restored 0 entries",
            "3 of them had been moved aside by another checkout's --replace",
        )
        self.assert_grok_text(b)
        self.ok(run(self.home, b, "--harness", "grok", "uninstall"), "removed 3 links, restored 0 entries")
        self.assert_gone()
        self.assert_empty_records()

    def test_f4b_absent_owner_is_restored_by_the_covering_checkout(self):
        a, b = self.two()
        c = make_checkout(self.home, "c")
        self.ok(run(self.home, a, "--harness", "grok"))
        self.ok(run(self.home, b, "--harness", "grok", "--replace"))
        away = self.home / "a-away"
        a.rename(away)
        self.ok(run(self.home, c, "--harness", "claude"))
        self.ok(run(self.home, c, "--harness", "claude", "uninstall"), "removed 3 links, restored 0 entries")
        away.rename(a)
        self.ok(run(self.home, b, "--harness", "grok", "uninstall"), "removed 3 links, restored 3 entries")
        self.assert_grok_text(a)
        self.ok(run(self.home, a, "--harness", "grok", "uninstall"), "removed 3 links, restored 0 entries")
        self.assert_gone()
        self.assert_empty_records()

    def _chain(self, foreign=False):
        a = make_checkout(self.home, "a")
        b = make_checkout(self.home, "b")
        c = make_checkout(self.home, "c", old=True)
        if foreign:
            swarm = provider_link(self.home, "grok", "swarm")
            swarm.parent.mkdir(parents=True)
            swarm.write_bytes(b"stack foreign\x00")
        for owner in (a, b, c):
            self.ok(run(self.home, owner, "--harness", "grok", "--replace"))
        return a, b, c

    def test_f5a_mixed_generation_chain_restores_the_top_layer(self):
        a, b, c = self._chain()
        upgrade(c)
        self.ok(run(self.home, c, "--harness", "grok", "uninstall"), "removed 3 links, restored 3 entries")
        self.assert_grok_text(b)
        self.ok(
            run(self.home, a, "--harness", "grok", "uninstall"),
            "removed 3 links, restored 0 entries",
            "3 of them had been moved aside by another checkout's --replace",
        )
        self.assert_grok_text(b)
        self.ok(run(self.home, b, "--harness", "grok", "uninstall"), "removed 3 links, restored 0 entries")
        self.assert_gone()
        self.assert_empty_records()

    def test_f5b_old_uninstall_in_the_chain_still_cleans_up(self):
        a, b, c = self._chain()
        self.ok(run(self.home, c, "--harness", "grok", "uninstall"), "removed 3 links, restored 3 entries")
        self.assert_grok_text(b)
        self.ok(run(self.home, b, "--harness", "grok", "uninstall"), "removed 3 links, restored 3 entries")
        self.assert_grok_text(a)
        self.ok(run(self.home, a, "--harness", "grok", "uninstall"), "removed 3 links, restored 0 entries")
        self.assert_gone()
        self.assert_empty_records()

    def test_f5c_foreign_bytes_survive_the_mixed_chain(self):
        a, b, c = self._chain(foreign=True)
        upgrade(c)
        swarm = provider_link(self.home, "grok", "swarm")
        self.ok(run(self.home, c, "--harness", "grok", "uninstall"), "removed 3 links, restored 3 entries")
        self.assert_grok_text(b)
        self.ok(run(self.home, a, "--harness", "grok", "uninstall"), "removed 3 links, restored 0 entries")
        self.assert_grok_text(b)
        self.ok(run(self.home, b, "--harness", "grok", "uninstall"), "removed 3 links, restored 1 entries")
        self.assertEqual(swarm.read_bytes(), b"stack foreign\x00")
        self.assertFalse(swarm.is_symlink())
        self.assert_gone(("alpha", "pstack-runtime"))

    def backup_dir(self, harness="grok"):
        found = sorted((state_dir(self.home) / "backups").glob(f"*/{harness}"))
        self.assertEqual(len(found), 1, found)
        return found[0]

    def test_failed_withdraw_keeps_the_claim_for_the_next_uninstall(self):
        a, b = self.base()
        for name in NAMES:
            provider_link(self.home, "grok", name).unlink()
        self.ok(run(self.home, a, "--harness", "grok"), "linked 3 skills into grok")
        layer = self.backup_dir()
        layer.chmod(0o555)
        self.addCleanup(lambda: layer.exists() and layer.chmod(0o755))
        failed = run(self.home, a, "--harness", "grok", "uninstall")
        self.skipped(failed, "removed 3 links, restored 0 entries", KEPT.format(n=3))
        self.assertIn("skipped withdraw", failed.stdout)
        self.assert_claims(a, grok_paths(self.home))
        layer.chmod(0o755)
        self.ok(run(self.home, a, "--harness", "grok", "uninstall"), "removed 3 links, restored 0 entries")
        self.assert_gone()
        self.assertIsNone(read_owner(self.home, a))
        data = read_legacy(self.home)
        self.assertEqual(data["backups"], [])
        self.assertEqual([row for row in data["links"] if row.get("checkout") == str(a)], [])

    def test_withdraw_beneath_a_repointed_link_keeps_its_claim(self):
        a, b = self.base()
        self.ok(run(self.home, a, "--harness", "grok", "--replace"), "linked 3 skills into grok")
        foreign = self.home / "foreign-dir"
        foreign.mkdir()
        self.repoint_swarm(foreign)
        swarm = provider_link(self.home, "grok", "swarm")
        self.ok(
            run(self.home, a, "--harness", "grok", "uninstall"),
            "removed 5 links, restored 2 entries",
            KEPT.format(n=1),
        )
        self.assert_claims(a, [str(swarm)])
        self.assertEqual(os.readlink(swarm), str(foreign))
        swarm.unlink()
        os.symlink(a / "skills" / "swarm", swarm)
        self.ok(run(self.home, a, "--harness", "grok", "uninstall"), "removed 1 links, restored 1 entries")
        self.assertIsNone(read_owner(self.home, a))
        self.assert_grok_text(b)
        self.ok(run(self.home, b, "--harness", "grok", "uninstall"), "removed 3 links, restored 0 entries")
        self.assert_gone()
        self.assert_empty_records()

    def test_withdraw_through_a_backup_keeps_the_covering_old_rows(self):
        a = make_checkout(self.home, "a")
        c = make_checkout(self.home, "c", old=True)
        d = make_checkout(self.home, "d", old=True)
        self.ok(run(self.home, a, "--harness", "grok"))
        self.ok(run(self.home, d, "uninstall"), "removed 0 links, restored 0 entries")
        self.ok(run(self.home, c, "--harness", "grok", "--replace"))
        self.ok(
            run(self.home, a, "--harness", "grok", "uninstall"),
            "removed 3 links, restored 0 entries",
            "3 of them had been moved aside by another checkout's --replace",
        )
        self.assertIsNone(read_owner(self.home, a))
        self.assert_grok_text(c)
        self.ok(run(self.home, c, "--harness", "grok", "uninstall"), "removed 3 links, restored 0 entries")
        self.assert_gone()

    def test_failed_move_leaves_no_backup_row(self):
        b = make_checkout(self.home, "b")
        swarm = provider_link(self.home, "grok", "swarm")
        swarm.parent.mkdir(parents=True)
        swarm.write_bytes(b"foreign\x00bytes")
        failed = run_failing(self.home, b, "shutil.move", swarm, "--harness", "grok", "--replace")
        self.skipped(
            failed,
            "linked 2 skills into grok",
            f"skipped move {swarm}: [Errno 13] Permission denied: '{swarm}'",
        )
        self.assertEqual(read_legacy(self.home)["backups"], [])
        self.assertEqual(swarm.read_bytes(), b"foreign\x00bytes")
        alpha, runtime = (str(provider_link(self.home, "grok", name)) for name in ("alpha", "pstack-runtime"))
        self.assert_claims(b, [alpha, runtime])

    def test_failed_link_leaves_no_claim_or_row(self):
        b = make_checkout(self.home, "b")
        swarm = provider_link(self.home, "grok", "swarm")
        failed = run_failing(self.home, b, "os.symlink", swarm, "--harness", "grok")
        self.skipped(
            failed,
            "linked 2 skills into grok",
            f"skipped link {swarm}: [Errno 13] Permission denied: '{swarm}'",
        )
        alpha, runtime = (str(provider_link(self.home, "grok", name)) for name in ("alpha", "pstack-runtime"))
        self.assert_claims(b, [alpha, runtime])
        self.assertEqual(sorted(row["path"] for row in read_legacy(self.home)["links"]), [alpha, runtime])

    def assert_refused(self, result, file):
        self.assertNotEqual(result.returncode, 0)
        lines = result.stderr.strip().splitlines()
        self.assertEqual(len(lines), 1, result.stderr)
        self.assertIn(str(file), lines[0])

    def test_legacy_file_that_is_not_an_object_is_refused_unchanged(self):
        a = make_checkout(self.home, "a")
        for text in ('["kept"]\n', '{"links": {"kept": 1}}\n', "{not json\n"):
            legacy_file(self.home).parent.mkdir(parents=True, exist_ok=True)
            legacy_file(self.home).write_text(text)
            self.assert_refused(run(self.home, a, "--harness", "grok"), legacy_file(self.home))
            self.assertEqual(legacy_file(self.home).read_text(), text)
            self.assert_gone()

    def test_owner_file_that_is_not_json_is_refused_unchanged(self):
        a = make_checkout(self.home, "a")
        owner = owner_file(self.home, a)
        owner.parent.mkdir(parents=True)
        owner.write_text("{not json\n")
        self.assert_refused(run(self.home, a, "--harness", "grok"), owner)
        self.assertEqual(owner.read_text(), "{not json\n")
        self.assert_gone()

    def test_backup_row_without_harnesses_matches_its_directory(self):
        a = make_checkout(self.home, "a")
        swarm = provider_link(self.home, "grok", "swarm")
        swarm.parent.mkdir(parents=True)
        saved = state_dir(self.home) / "backups" / "old" / "grok" / "swarm"
        saved.mkdir(parents=True)
        (saved / "SKILL.md").write_text("saved\n")
        write_legacy(self.home, [], [{"original": str(swarm), "backup": str(saved)}])
        self.ok(run(self.home, a, "--harness", "grok", "uninstall"), "removed 0 links, restored 1 entries")
        self.assertEqual((swarm / "SKILL.md").read_text(), "saved\n")

    def test_partial_move_keeps_the_row_for_its_copy(self):
        b = make_checkout(self.home, "b")
        skills = provider_link(self.home, "grok", "swarm").parent
        swarm = skills / "swarm"
        swarm.mkdir(parents=True)
        (swarm / "SKILL.md").write_text("precious\n")
        skills.chmod(0o555)
        self.addCleanup(skills.chmod, 0o755)
        self.skipped(run(self.home, b, "--harness", "grok", "--replace"), "linked 0 skills into grok")
        rows = read_legacy(self.home)["backups"]
        self.assertEqual([row["original"] for row in rows], [str(swarm)])
        self.assertEqual((Path(rows[0]["backup"]) / "SKILL.md").read_text(), "precious\n")
        stamp = Path(rows[0]["backup"]).parent.parent.name
        self.assertEqual(self.under_backups(), [stamp, f"{stamp}/grok", f"{stamp}/grok/swarm", f"{stamp}/grok/swarm/SKILL.md"])

    def test_old_replace_before_a_removal_keeps_its_link_and_our_claim(self):
        a = make_checkout(self.home, "a")
        b = make_checkout(self.home, "b", old=True)
        self.ok(run(self.home, a, "--harness", "grok"))
        replace = [sys.executable, b / "scripts" / "install.py", "--harness", "grok", "--replace"]
        raced = interleave_removal(self.home, a, grok_paths(self.home), replace, "--harness", "grok", "uninstall")
        self.skipped(raced, "removed 0 links, restored 0 entries", KEPT.format(n=3))
        self.assert_grok_text(b)
        self.assert_claims(a, grok_paths(self.home))
        self.ok(run(self.home, b, "--harness", "grok", "uninstall"), "removed 3 links, restored 3 entries")
        self.assert_grok_text(a)
        self.ok(run(self.home, a, "--harness", "grok", "uninstall"), "removed 3 links, restored 0 entries")
        self.assert_gone()
        self.assertIsNone(read_owner(self.home, a))
        self.assertEqual(sorted(os.listdir(provider_link(self.home, "grok", "swarm").parent)), [])

    def test_old_replace_and_a_new_occupant_keep_the_moved_link_aside(self):
        a = make_checkout(self.home, "a")
        b = make_checkout(self.home, "b", old=True)
        self.ok(run(self.home, a, "--harness", "grok"))
        alpha = provider_link(self.home, "grok", "alpha")
        replace = [sys.executable, b / "scripts" / "install.py", "--harness", "grok", "--replace"]
        raced = interleave_removal(self.home, a, [alpha], replace, "--harness", "grok", "uninstall", occupy=b"occupant\x00")
        self.skipped(raced, "removed 0 links, restored 0 entries", KEPT.format(n=3))
        aside = set_aside(alpha)
        self.assertEqual(len(aside), 1, aside)
        self.assertIn(
            f"skipped unlink {alpha}: the link no longer matches the recorded checkout and {alpha} was taken again; "
            f"it is kept at {aside[0]}",
            raced.stdout.splitlines(),
        )
        self.assertEqual(os.readlink(aside[0]), str(b / "skills" / "alpha"))
        self.assertEqual(alpha.read_bytes(), b"occupant\x00")
        self.assert_grok_text(b, ("pstack-runtime", "swarm"))
        self.assert_claims(a, grok_paths(self.home))

    def test_entry_moved_into_a_backup_during_uninstall_keeps_its_claim(self):
        a = make_checkout(self.home, "a")
        b = make_checkout(self.home, "b", old=True)
        self.ok(run(self.home, a, "--harness", "grok"))
        self.ok(run(self.home, b, "--harness", "grok", "--replace"))
        for name in NAMES:
            provider_link(self.home, "grok", name).unlink()
        relink_then_replace = (
            "import os, subprocess, sys\n"
            f"for name in {list(NAMES)!r}:\n"
            f"    os.symlink(os.path.join({str(a / 'skills')!r}, name), os.path.join({str(provider_link(self.home, 'grok', 'x').parent)!r}, name))\n"
            f"subprocess.run([sys.executable, {str(b / 'scripts' / 'install.py')!r}, '--harness', 'grok', '--replace'], check=True)\n"
        )
        layer = str(self.backup_dir())
        withdrawn = [os.path.join(layer, name) for name in NAMES]
        raced = interleave_removal(
            self.home, a, withdrawn, [sys.executable, "-c", relink_then_replace], "--harness", "grok", "uninstall"
        )
        self.ok(raced, "removed 3 links, restored 0 entries", KEPT.format(n=3))
        self.assert_grok_text(b)
        self.assert_claims(a, grok_paths(self.home))
        self.ok(run(self.home, b, "--harness", "grok", "uninstall"), "removed 3 links, restored 3 entries")
        self.assert_grok_text(a)
        self.ok(run(self.home, a, "--harness", "grok", "uninstall"), "removed 3 links, restored 0 entries")
        self.assert_gone()
        self.assertIsNone(read_owner(self.home, a))

    def test_a_hidden_entry_present_before_uninstall_survives_every_move_aside(self):
        for kind in ("file", "link"):
            with self.subTest(kind=kind):
                self.use_fresh()
                a = make_checkout(self.home, "a")
                self.ok(run(self.home, a, "--harness", "grok"))
                parent = provider_link(self.home, "grok", "swarm").parent
                # Every hidden name an uninstall could pick first is already taken by an entry it did not create.
                plant = (
                    "import secrets, tempfile\n"
                    "secrets.token_hex = lambda n: 'deadbeef'\n"
                    "candidates = tempfile._get_candidate_names\n"
                    "def colliding():\n"
                    "    yield 'deadbeef'\n"
                    "    yield from candidates()\n"
                    "tempfile._get_candidate_names = colliding\n"
                    f"for name in ['.swarm.pstack-t3-%d-deadbeef' % os.getpid(), '.pstack-t3-deadbeef']:\n"
                    f"    hidden = os.path.join({str(parent)!r}, name)\n"
                    f"    if {kind!r} == 'file':\n"
                    "        Path(hidden).write_bytes(b'hidden\\x00\\xff')\n"
                    "    else:\n"
                    "        os.symlink('/foreign/hidden', hidden)\n"
                )
                raced = uninstall_hooked(self.home, a, plant)
                self.ok(raced, "removed 3 links, restored 0 entries")
                self.assert_gone()
                hidden = sorted(name for name in os.listdir(parent))
                self.assertEqual(len(hidden), 2, hidden)
                self.assertEqual(hidden[0], ".pstack-t3-deadbeef")
                self.assertRegex(hidden[1], r"^\.swarm\.pstack-t3-\d+-deadbeef$")
                for name in hidden:
                    if kind == "file":
                        self.assertEqual((parent / name).read_bytes(), b"hidden\x00\xff")
                    else:
                        self.assertEqual(os.readlink(parent / name), "/foreign/hidden")
                self.assertIsNone(read_owner(self.home, a))

    def noreplace(self, rename):
        """What the no-replace rename returned in the last hooked run. A forced `rename` must have taken it away."""
        code = noreplace_result(self.home)
        if rename is not None:
            self.assertEqual(code, errno.ENOSYS)
        return code

    def test_a_directory_put_back_never_replaces_a_directory_that_took_the_path(self):
        for rename in (None, "platform", "symbol"):
            with self.subTest(rename=rename):
                self.use_fresh()
                a = make_checkout(self.home, "a")
                self.ok(run(self.home, a, "--harness", "grok"))
                swarm = provider_link(self.home, "grok", "swarm")
                hook = put_back_race(swarm, "directory", occupy="directory", rename=rename)
                raced = uninstall_hooked(self.home, a, hook)
                code = self.noreplace(rename)
                self.assertEqual(os.listdir(swarm), [])
                aside = set_aside(swarm)
                self.assertEqual(len(aside), 1, aside)
                if code == 0:
                    reason = f"{swarm} was taken again"
                else:
                    reason = f"{swarm} cannot be refilled without risking an overwrite ({os.strerror(code)})"
                self.skipped(
                    raced,
                    "removed 2 links, restored 0 entries",
                    f"skipped unlink {swarm}: the link no longer matches the recorded checkout and {reason}; "
                    f"it is kept at {aside[0]}",
                )
                self.assertEqual((aside[0] / "precious").read_bytes(), b"directory bytes\x00")
                self.assert_claims(a, [str(swarm)])

    def test_a_foreign_directory_moved_aside_goes_back_to_its_empty_path(self):
        for rename in (None, "platform", "symbol"):
            with self.subTest(rename=rename):
                self.use_fresh()
                a = make_checkout(self.home, "a")
                self.ok(run(self.home, a, "--harness", "grok"))
                swarm = provider_link(self.home, "grok", "swarm")
                raced = uninstall_hooked(self.home, a, put_back_race(swarm, "directory", rename=rename))
                code = self.noreplace(rename)
                if code == 0:
                    self.skipped(
                        raced,
                        "removed 2 links, restored 0 entries",
                        f"skipped unlink {swarm}: the link no longer matches the recorded checkout",
                    )
                    self.assertEqual((swarm / "precious").read_bytes(), b"directory bytes\x00")
                    self.assertEqual(os.listdir(swarm.parent), ["swarm"])
                else:
                    self.assertFalse(os.path.lexists(swarm))
                    aside = set_aside(swarm)
                    self.assertEqual(len(aside), 1, aside)
                    self.skipped(
                        raced,
                        "removed 2 links, restored 0 entries",
                        f"skipped unlink {swarm}: the link no longer matches the recorded checkout and {swarm} cannot be "
                        f"refilled without risking an overwrite ({os.strerror(code)}); it is kept at {aside[0]}",
                    )
                    self.assertEqual((aside[0] / "precious").read_bytes(), b"directory bytes\x00")
                    self.assertEqual(os.listdir(swarm.parent), [aside[0].parent.name])
                self.assert_claims(a, [str(swarm)])

    def test_a_put_back_without_hard_links_never_replaces_a_file_that_took_the_path(self):
        for rename in (None, "platform", "symbol"):
            with self.subTest(rename=rename):
                self.use_fresh()
                a = make_checkout(self.home, "a")
                self.ok(run(self.home, a, "--harness", "grok"))
                swarm = provider_link(self.home, "grok", "swarm")
                hook = put_back_race(swarm, "link", occupy="file", link_error=True, rename=rename)
                raced = uninstall_hooked(self.home, a, hook)
                code = self.noreplace(rename)
                self.assertFalse(swarm.is_symlink())
                self.assertEqual(swarm.read_bytes(), b"occupant\x00\xff")
                aside = set_aside(swarm)
                self.assertEqual(len(aside), 1, aside)
                if code == 0:
                    reason = f"{swarm} was taken again"
                else:
                    reason = f"{swarm} cannot be refilled without risking an overwrite ({os.strerror(code)})"
                self.skipped(
                    raced,
                    "removed 2 links, restored 0 entries",
                    f"skipped unlink {swarm}: the link no longer matches the recorded checkout and {reason}; "
                    f"it is kept at {aside[0]}",
                )
                self.assertEqual(os.readlink(aside[0]), "/foreign/swarm")
                self.assert_claims(a, [str(swarm)])

    def test_a_put_back_with_no_safe_rename_keeps_the_entry_aside(self):
        a = make_checkout(self.home, "a")
        self.ok(run(self.home, a, "--harness", "grok"))
        swarm = provider_link(self.home, "grok", "swarm")
        raced = uninstall_hooked(self.home, a, put_back_race(swarm, "link", link_error=True, rename="libc"))
        self.noreplace("libc")
        self.assertFalse(os.path.lexists(swarm))
        aside = set_aside(swarm)
        self.assertEqual(len(aside), 1, aside)
        self.skipped(
            raced,
            "removed 2 links, restored 0 entries",
            f"skipped unlink {swarm}: the link no longer matches the recorded checkout and {swarm} cannot be refilled "
            f"without risking an overwrite ({os.strerror(errno.ENOSYS)}); it is kept at {aside[0]}",
        )
        self.assertEqual(os.readlink(aside[0]), "/foreign/swarm")
        self.assert_claims(a, [str(swarm)])

    def displaced_by(self, kind):
        """Checkout a after `--replace` moved a foreign `kind` entry at swarm aside, with swarm and its one backup row."""
        a = make_checkout(self.home, "a")
        swarm = provider_link(self.home, "grok", "swarm")
        swarm.parent.mkdir(parents=True)
        if kind == "directory":
            swarm.mkdir()
            (swarm / "SKILL.md").write_bytes(b"displaced\x00\xfe")
        elif kind == "link":
            os.symlink("/foreign/displaced", swarm)
        else:
            swarm.write_bytes(b"displaced\x00\xfe")
        self.ok(run(self.home, a, "--harness", "grok", "--replace"), "linked 3 skills into grok")
        rows = read_legacy(self.home)["backups"]
        self.assertEqual([row["original"] for row in rows], [str(swarm)])
        return a, swarm, rows

    def assert_displaced(self, path, kind):
        if kind == "directory":
            self.assertEqual(os.listdir(path), ["SKILL.md"])
            self.assertEqual((path / "SKILL.md").read_bytes(), b"displaced\x00\xfe")
        elif kind == "link":
            self.assertEqual(os.readlink(path), "/foreign/displaced")
        else:
            self.assertFalse(path.is_symlink())
            self.assertEqual(path.read_bytes(), b"displaced\x00\xfe")

    def assert_restore_kept(self, raced, swarm, rows, kind, reason, tried=True):
        """The raced restore wrote nothing at swarm and kept the backup and its row where they were."""
        self.assertEqual((self.home / "filled").read_text(), str(tried))
        backup = Path(rows[0]["backup"])
        self.skipped(raced, "removed 3 links, restored 0 entries", f"skipped restore {backup}: {reason}")
        self.assert_displaced(backup, kind)
        self.assertEqual(os.listdir(backup.parent), [backup.name])
        self.assertEqual(read_legacy(self.home)["backups"], rows)
        self.assertEqual(set_aside(swarm), [])

    def restore_reason(self, swarm, kind, link_error, rename):
        """Why a put-back onto a taken swarm declined: a hard link sees the occupant, else the no-replace rename decides."""
        code = self.noreplace(rename)
        if (kind != "directory" and not link_error) or code == 0:
            return f"{swarm} was taken again"
        return f"{swarm} cannot be refilled without risking an overwrite ({os.strerror(code)})"

    def restore_tried(self, kind, link_error, rename):
        """Whether the restore reached a call that writes swarm, which is when the occupant arrives.

        A platform with no safe rename has no held descriptor to link either. It gives up on a directory, and on a
        file it cannot hard link, before any such call.
        """
        return not (rename == "platform" and (kind == "directory" or link_error))

    def test_a_restore_never_replaces_an_entry_that_took_the_path(self):
        cases = (
            ("file", "file", False),
            ("file", "file", True),
            ("file", "link", False),
            ("file", "directory", False),
            ("directory", "directory", False),
            ("directory", "file", False),
        )
        for kind, occupy, link_error in cases:
            for rename in (None, "platform", "symbol"):
                with self.subTest(kind=kind, occupy=occupy, link_error=link_error, rename=rename):
                    self.use_fresh()
                    a, swarm, rows = self.displaced_by(kind)
                    raced = uninstall_hooked(self.home, a, restore_race(swarm, occupy, link_error=link_error, rename=rename))
                    reason = self.restore_reason(swarm, kind, link_error, rename)
                    tried = self.restore_tried(kind, link_error, rename)
                    self.assert_restore_kept(raced, swarm, rows, kind, reason, tried)
                    if not tried:
                        self.assertFalse(os.path.lexists(swarm))
                    elif occupy == "file":
                        self.assertEqual(swarm.read_bytes(), b"occupant\x00\xff")
                        swarm.unlink()
                    elif occupy == "link":
                        self.assertEqual(os.readlink(swarm), "/foreign/occupant")
                        swarm.unlink()
                    else:
                        self.assertEqual(os.listdir(swarm), ["precious"])
                        self.assertEqual((swarm / "precious").read_bytes(), b"directory bytes\x00")
                        shutil.rmtree(swarm)
                    self.ok(run(self.home, a, "--harness", "grok", "uninstall"), "removed 0 links, restored 1 entries")
                    self.assert_displaced(swarm, kind)
                    self.assert_empty_records()

    def test_a_restore_never_writes_into_another_checkout_that_took_the_path(self):
        cases = (("file", False), ("file", True), ("directory", False))
        for kind, link_error in cases:
            for rename in (None, "platform", "symbol"):
                with self.subTest(kind=kind, link_error=link_error, rename=rename):
                    self.use_fresh()
                    a, swarm, rows = self.displaced_by(kind)
                    b = make_checkout(self.home, "b", old=True)
                    tree = snapshot(b / "skills")
                    install_b = [sys.executable, str(b / "scripts" / "install.py"), "--harness", "grok"]
                    hook = restore_race(swarm, install_b, link_error=link_error, rename=rename)
                    raced = uninstall_hooked(self.home, a, hook)
                    reason = self.restore_reason(swarm, kind, link_error, rename)
                    tried = self.restore_tried(kind, link_error, rename)
                    self.assert_restore_kept(raced, swarm, rows, kind, reason, tried)
                    if not tried:
                        self.assertFalse(os.path.lexists(swarm))
                        continue
                    self.assertEqual(snapshot(b / "skills"), tree)
                    self.assert_grok_text(b)
                    self.ok(run(self.home, b, "--harness", "grok", "uninstall"), "removed 3 links, restored 1 entries")
                    self.assertEqual(snapshot(b / "skills"), tree)
                    self.assert_displaced(swarm, kind)
                    self.ok(run(self.home, a, "--harness", "grok", "uninstall"), "removed 0 links, restored 0 entries")
                    self.assert_displaced(swarm, kind)
                    self.assertFalse(legacy_file(self.home).exists())

    def test_a_backup_swapped_during_uninstall_is_not_restored(self):
        a, swarm, rows = self.displaced_by("file")
        backup = rows[0]["backup"]
        alpha = str(provider_link(self.home, "grok", "alpha"))
        hook = (
            "swapped = False\n"
            "def swapping(original):\n"
            "    def call(source, destination, *args, **kwargs):\n"
            "        global swapped\n"
            f"        if not swapped and str(source) == {alpha!r}:\n"
            "            swapped = True\n"
            f"            os.unlink({backup!r})\n"
            f"            Path({backup!r}).write_bytes(b'swapped\\x00')\n"
            "        return original(source, destination, *args, **kwargs)\n"
            "    return call\n"
            "os.rename = swapping(os.rename)\n"
        )
        self.skipped(
            uninstall_hooked(self.home, a, hook),
            "removed 3 links, restored 0 entries",
            f"skipped restore {backup}: the backup is no longer the entry uninstall read",
        )
        self.assertFalse(os.path.lexists(swarm))
        self.assertEqual(Path(backup).read_bytes(), b"swapped\x00")
        self.assertEqual(read_legacy(self.home)["backups"], rows)

    def test_a_swapped_backup_that_reuses_the_inode_number_and_change_time_is_not_restored(self):
        """A filesystem may give a freed inode's numbers to the next new entry. Here every freed one is reused."""
        a, swarm, rows = self.displaced_by("file")
        backup = rows[0]["backup"]
        alpha = str(provider_link(self.home, "grok", "alpha"))
        held = self.home / "held-after-uninstall"
        hook = (
            "import types\n"
            f"backup = {backup!r}\n"
            "planned = os.lstat(backup)\n"
            "real_lstat = os.lstat\n"
            "def in_use():\n"
            "    for fd in range(1024):\n"
            "        try:\n"
            "            stat = os.fstat(fd)\n"
            "        except OSError:\n"
            "            continue\n"
            "        if (stat.st_dev, stat.st_ino) == (planned.st_dev, planned.st_ino):\n"
            "            return True\n"
            "    return False\n"
            "def lstat(path, *args, **kwargs):\n"
            "    stat = real_lstat(path, *args, **kwargs)\n"
            "    if str(path) != backup or (stat.st_dev, stat.st_ino) == (planned.st_dev, planned.st_ino) or in_use():\n"
            "        return stat\n"
            "    fields = {name: getattr(stat, name) for name in dir(stat) if name.startswith('st_')}\n"
            "    fields.update(st_dev=planned.st_dev, st_ino=planned.st_ino, st_ctime_ns=planned.st_ctime_ns)\n"
            "    return types.SimpleNamespace(**fields)\n"
            "swapped = False\n"
            "def swapping(original):\n"
            "    def call(source, destination, *args, **kwargs):\n"
            "        global swapped\n"
            f"        if not swapped and str(source) == {alpha!r}:\n"
            "            swapped = True\n"
            "            os.unlink(backup)\n"
            "            Path(backup).write_bytes(b'swapped\\x00')\n"
            "            os.lstat = lstat\n"
            "        return original(source, destination, *args, **kwargs)\n"
            "    return call\n"
            "os.rename = swapping(os.rename)\n"
            "planned_uninstall = module.uninstall\n"
            "def uninstall(args):\n"
            "    code = planned_uninstall(args)\n"
            f"    Path({str(held)!r}).write_text(str(in_use()))\n"
            "    return code\n"
            "module.uninstall = uninstall\n"
        )
        self.skipped(
            uninstall_hooked(self.home, a, hook),
            "removed 3 links, restored 0 entries",
            f"skipped restore {backup}: the backup is no longer the entry uninstall read",
        )
        self.assertFalse(os.path.lexists(swarm))
        self.assertEqual(Path(backup).read_bytes(), b"swapped\x00")
        self.assertEqual(read_legacy(self.home)["backups"], rows)
        self.assertEqual(held.read_text(), "False")

    def test_a_backup_that_cannot_be_held_open_is_not_restored(self):
        a, swarm, rows = self.displaced_by("file")
        backup = rows[0]["backup"]
        hook = (
            "import errno\n"
            "real_open = os.open\n"
            "def refusing(path, *args, **kwargs):\n"
            f"    if str(path) == {backup!r}:\n"
            "        raise PermissionError(errno.EACCES, os.strerror(errno.EACCES), path)\n"
            "    return real_open(path, *args, **kwargs)\n"
            "os.open = refusing\n"
        )
        self.skipped(
            uninstall_hooked(self.home, a, hook),
            "removed 3 links, restored 0 entries",
            f"skipped restore {backup}: the backup could not be held open to prove it is the entry uninstall read "
            f"({os.strerror(errno.EACCES)})",
        )
        self.assertFalse(os.path.lexists(swarm))
        self.assertEqual(read_legacy(self.home)["backups"], rows)
        self.ok(run(self.home, a, "--harness", "grok", "uninstall"), "removed 0 links, restored 1 entries")
        self.assert_displaced(swarm, "file")
        self.assert_empty_records()

    def cross_device_uninstall(self, swarm, a, occupy=None, rename=None, crossed=True):
        hook = cross_device(state_dir(self.home) / "backups", swarm, occupy=occupy, rename=rename)
        raced = uninstall_hooked(self.home, a, hook)
        if crossed:
            self.assertGreater(crossings(self.home), 0, raced.stdout + raced.stderr)
        return raced

    def assert_no_copy_left(self, swarm):
        self.assertEqual(list(swarm.parent.glob(".pstack-t3-*")), [])

    def test_a_restore_across_filesystems_copies_the_backup_into_place(self):
        times = (1_500_000_000_123_456_789, 1_600_000_000_123_456_789)
        for kind in ("file", "link", "directory"):
            with self.subTest(kind=kind):
                self.use_fresh()
                a, swarm, rows = self.displaced_by(kind)
                backup = Path(rows[0]["backup"])
                if kind == "file":
                    os.chmod(backup, 0o604)
                    os.utime(backup, ns=times)
                    # A filesystem with whole-second timestamps keeps only the seconds.
                    stored = backup.stat().st_mtime_ns
                elif kind == "directory":
                    os.symlink("SKILL.md", backup / "alias")
                    os.symlink("/foreign/dangling", backup / "dangling")
                    os.chmod(backup / "SKILL.md", 0o604)
                    os.utime(backup / "SKILL.md", ns=times)
                    stored = (backup / "SKILL.md").stat().st_mtime_ns
                raced = self.cross_device_uninstall(swarm, a)
                self.ok(raced, "removed 3 links, restored 1 entries")
                if kind == "file":
                    self.assert_displaced(swarm, kind)
                    self.assertEqual(swarm.stat().st_mode & 0o777, 0o604)
                    self.assertEqual(swarm.stat().st_mtime_ns, stored)
                elif kind == "link":
                    self.assert_displaced(swarm, kind)
                else:
                    self.assertFalse(swarm.is_symlink())
                    self.assertEqual(sorted(os.listdir(swarm)), ["SKILL.md", "alias", "dangling"])
                    self.assertEqual((swarm / "SKILL.md").read_bytes(), b"displaced\x00\xfe")
                    self.assertEqual((swarm / "SKILL.md").stat().st_mode & 0o777, 0o604)
                    self.assertEqual((swarm / "SKILL.md").stat().st_mtime_ns, stored)
                    self.assertEqual(os.readlink(swarm / "alias"), "SKILL.md")
                    self.assertEqual(os.readlink(swarm / "dangling"), "/foreign/dangling")
                self.assertFalse(os.path.lexists(backup))
                self.assert_no_copy_left(swarm)
                self.assert_empty_records()

    def test_a_restore_across_filesystems_never_replaces_an_entry_that_took_the_path(self):
        for kind in ("file", "link", "directory"):
            for occupy in ("file", "directory"):
                with self.subTest(kind=kind, occupy=occupy):
                    self.use_fresh()
                    a, swarm, rows = self.displaced_by(kind)
                    backup = Path(rows[0]["backup"])
                    raced = self.cross_device_uninstall(swarm, a, occupy=occupy)
                    self.assert_restore_kept(raced, swarm, rows, kind, f"{swarm} was taken again")
                    self.assert_no_copy_left(swarm)
                    if occupy == "file":
                        self.assertEqual(swarm.read_bytes(), b"occupant\x00\xff")
                        swarm.unlink()
                    else:
                        self.assertEqual(os.listdir(swarm), ["precious"])
                        self.assertEqual((swarm / "precious").read_bytes(), b"directory bytes\x00")
                        shutil.rmtree(swarm)
                    self.ok(self.cross_device_uninstall(swarm, a), "removed 0 links, restored 1 entries")
                    self.assert_displaced(swarm, kind)
                    self.assertFalse(os.path.lexists(backup))
                    self.assert_no_copy_left(swarm)
                    self.assert_empty_records()

    def test_a_restore_across_filesystems_with_no_safe_rename_keeps_the_backup(self):
        for rename in ("platform", "symbol"):
            with self.subTest(rename=rename):
                self.use_fresh()
                a, swarm, rows = self.displaced_by("directory")
                backup = Path(rows[0]["backup"])
                # With no safe rename the directory never leaves its place, so no move is tried.
                raced = self.cross_device_uninstall(swarm, a, rename=rename, crossed=False)
                self.assertEqual(crossings(self.home), 0)
                code = self.noreplace(rename)
                self.skipped(
                    raced,
                    "removed 3 links, restored 0 entries",
                    f"skipped restore {backup}: {swarm} cannot be refilled without risking an overwrite ({os.strerror(code)})",
                )
                self.assertFalse(os.path.lexists(swarm))
                self.assert_displaced(backup, "directory")
                self.assertEqual(read_legacy(self.home)["backups"], rows)
                self.assert_no_copy_left(swarm)

    def backup_race_uninstall(self, a, swarm, backup, *events, crossing=False, **options):
        """Uninstall with every event fired against the one backup. `crossing` puts the backups on another filesystem."""
        hook = backup_race(backup, swarm, events, **options)
        if crossing:
            hook = cross_device(state_dir(self.home) / "backups", swarm) + hook
        raced = uninstall_hooked(self.home, a, hook)
        self.assertEqual(fired(self.home), len(events), raced.stdout + raced.stderr)
        if crossing:
            self.assertGreater(crossings(self.home), 0, raced.stdout + raced.stderr)
            self.assert_no_copy_left(swarm)
        return raced

    def assert_foreign(self, path, foreign="file"):
        if foreign == "directory":
            self.assertEqual(os.listdir(path), ["precious"])
            self.assertEqual((path / "precious").read_bytes(), b"foreign directory\x00")
        else:
            self.assertFalse(path.is_symlink())
            self.assertEqual(path.read_bytes(), b"foreign\x00\xff")

    def assert_swap_refused(self, raced, swarm, rows, kind, foreign="file"):
        """The restore moved nothing. The foreign entry is at the backup's path, the backup is where the swap saved it, and the row stays."""
        backup = Path(rows[0]["backup"])
        self.skipped(
            raced,
            "removed 3 links, restored 0 entries",
            f"skipped restore {backup}: the backup is no longer the entry uninstall read",
        )
        self.assertFalse(os.path.lexists(swarm))
        self.assert_foreign(backup, foreign)
        self.assert_displaced(Path(f"{backup}.saved"), kind)
        self.assertEqual(sorted(os.listdir(backup.parent)), [backup.name, f"{backup.name}.saved"])
        self.assertEqual(read_legacy(self.home)["backups"], rows)

    def assert_swap_survived(self, raced, a, swarm, rows, kind, foreign="file", saved=True, noted=True):
        """The restore put the backup uninstall read at swarm. The foreign entry is still at the backup's path, and the row is gone."""
        backup = Path(rows[0]["backup"])
        self.ok(raced, "removed 3 links, restored 1 entries")
        note = f"kept {backup}: it is not the backup uninstall restored to {swarm}"
        self.assertEqual(note in raced.stdout.splitlines(), noted, raced.stdout)
        self.assert_displaced(swarm, kind)
        self.assert_foreign(backup, foreign)
        names = [backup.name]
        if saved:
            self.assert_displaced(Path(f"{backup}.saved"), kind)
            names.append(f"{backup.name}.saved")
        self.assertEqual(sorted(os.listdir(backup.parent)), names)
        self.assert_empty_records()
        self.ok(run(self.home, a, "--harness", "grok", "uninstall"), "removed 0 links, restored 0 entries")
        self.assert_displaced(swarm, kind)
        self.assert_foreign(backup, foreign)

    def test_an_entry_that_takes_the_backups_path_around_the_hard_link_is_never_moved_or_deleted(self):
        for kind in ("file", "link"):
            for when in ("before", "after"):
                with self.subTest(kind=kind, when=when):
                    self.use_fresh()
                    a, swarm, rows = self.displaced_by(kind)
                    raced = self.backup_race_uninstall(a, swarm, rows[0]["backup"], ("link", "onto", when, "swap"))
                    self.assert_swap_survived(raced, a, swarm, rows, kind)

    def test_an_entry_that_takes_the_backups_path_is_never_restored_without_proc(self):
        for kind in ("file", "link"):
            with self.subTest(kind=kind, when="before the private name"):
                self.use_fresh()
                a, swarm, rows = self.displaced_by(kind)
                raced = self.backup_race_uninstall(a, swarm, rows[0]["backup"], ("link", "from", "before", "swap"), proc=False)
                self.assert_swap_refused(raced, swarm, rows, kind)
            for event in (("link", "from", "after", "swap"), ("link", "onto", "after", "swap")):
                with self.subTest(kind=kind, event=event):
                    self.use_fresh()
                    a, swarm, rows = self.displaced_by(kind)
                    raced = self.backup_race_uninstall(a, swarm, rows[0]["backup"], event, proc=False)
                    self.assert_swap_survived(raced, a, swarm, rows, kind)

    def test_an_entry_that_takes_a_directory_backups_path_is_put_back(self):
        for foreign in ("directory", "file"):
            with self.subTest(foreign=foreign):
                self.use_fresh()
                a, swarm, rows = self.displaced_by("directory")
                event = ("noreplace", "from", "before", "swap")
                raced = self.backup_race_uninstall(a, swarm, rows[0]["backup"], event, foreign=foreign)
                self.assert_swap_refused(raced, swarm, rows, "directory", foreign)

    def test_an_entry_that_takes_a_backups_path_is_put_back_without_hard_links(self):
        a, swarm, rows = self.displaced_by("file")
        event = ("noreplace", "from", "before", "swap")
        raced = self.backup_race_uninstall(a, swarm, rows[0]["backup"], event, links=False)
        self.assert_swap_refused(raced, swarm, rows, "file")

    def test_an_entry_that_arrives_after_a_directory_backup_left_is_never_touched(self):
        a, swarm, rows = self.displaced_by("directory")
        event = ("noreplace", "from", "after", "swap")
        raced = self.backup_race_uninstall(a, swarm, rows[0]["backup"], event, foreign="directory")
        # The backup's path was empty when the entry arrived, so the restore never looks at it again.
        self.assert_swap_survived(raced, a, swarm, rows, "directory", "directory", saved=False, noted=False)

    def test_a_directory_backup_that_can_go_neither_way_is_kept_aside(self):
        a, swarm, rows = self.displaced_by("directory")
        backup = Path(rows[0]["backup"])
        events = (("noreplace", "onto", "before", "swap"), ("noreplace", "onto", "before", "occupy"))
        raced = self.backup_race_uninstall(a, swarm, backup, *events)
        aside = set_aside(backup)
        self.assertEqual(len(aside), 1, aside)
        self.skipped(
            raced,
            "removed 3 links, restored 0 entries",
            f"skipped restore {backup}: {swarm} was taken again and {backup} was taken again; it is kept at {aside[0]}",
        )
        self.assert_displaced(aside[0], "directory")
        self.assert_foreign(backup)
        self.assertEqual(swarm.read_bytes(), b"occupant\x00\xff")
        self.assertEqual(read_legacy(self.home)["backups"], rows)

    def test_an_entry_that_cannot_go_back_to_the_backups_path_is_kept_aside(self):
        a, swarm, rows = self.displaced_by("file")
        backup = Path(rows[0]["backup"])
        events = (("link", "onto", "after", "swap"), ("rename", "from", "after", "squat"))
        raced = self.backup_race_uninstall(a, swarm, backup, *events)
        aside = set_aside(backup)
        self.assertEqual(len(aside), 1, raced.stdout + raced.stderr)
        self.ok(
            raced,
            "removed 3 links, restored 1 entries",
            f"kept {aside[0]}: it took the place of the backup uninstall restored to {swarm} and {backup} was taken again",
        )
        self.assert_displaced(swarm, "file")
        self.assert_displaced(Path(f"{backup}.saved"), "file")
        self.assert_foreign(aside[0])
        self.assertEqual(backup.read_bytes(), b"squatter\x00")
        self.assert_empty_records()

    def test_a_backup_whose_directory_vanishes_after_the_hard_link_is_restored(self):
        a, swarm, rows = self.displaced_by("file")
        backup = Path(rows[0]["backup"])
        raced = self.backup_race_uninstall(a, swarm, backup, ("link", "onto", "after", "vanish"))
        self.ok(raced, "removed 3 links, restored 1 entries")
        self.assert_displaced(swarm, "file")
        self.assertFalse(os.path.lexists(backup.parent))
        self.assert_empty_records()

    def test_a_copy_across_filesystems_that_fails_keeps_the_backup_at_its_path(self):
        for kind in ("file", "link", "directory"):
            with self.subTest(kind=kind):
                self.use_fresh()
                a, swarm, rows = self.displaced_by(kind)
                backup = Path(rows[0]["backup"])
                full = (
                    "def full(*args, **kwargs):\n"
                    "    raise OSError(errno.ENOSPC, os.strerror(errno.ENOSPC))\n"
                    "shutil.copytree = shutil.copy2 = full\n"
                )
                hook = cross_device(state_dir(self.home) / "backups", swarm) + full
                raced = uninstall_hooked(self.home, a, hook)
                self.assertGreater(crossings(self.home), 0, raced.stdout + raced.stderr)
                self.skipped(
                    raced,
                    "removed 3 links, restored 0 entries",
                    f"skipped restore {backup}: [Errno {errno.ENOSPC}] {os.strerror(errno.ENOSPC)}",
                )
                self.assertFalse(os.path.lexists(swarm))
                self.assert_displaced(backup, kind)
                self.assertEqual(os.listdir(backup.parent), [backup.name])
                self.assertEqual(read_legacy(self.home)["backups"], rows)
                self.assert_no_copy_left(swarm)
                self.ok(self.cross_device_uninstall(swarm, a), "removed 0 links, restored 1 entries")
                self.assert_displaced(swarm, kind)
                self.assert_empty_records()

    def test_an_entry_that_takes_the_backups_path_before_a_copy_across_filesystems_is_never_copied(self):
        for kind, event, foreign in (
            ("file", ("link", "from", "before", "swap"), "file"),
            ("link", ("link", "from", "before", "swap"), "file"),
            ("directory", ("noreplace", "from", "before", "swap"), "directory"),
        ):
            with self.subTest(kind=kind):
                self.use_fresh()
                a, swarm, rows = self.displaced_by(kind)
                raced = self.backup_race_uninstall(a, swarm, rows[0]["backup"], event, crossing=True, foreign=foreign)
                self.assert_swap_refused(raced, swarm, rows, kind, foreign)

    def test_an_entry_that_takes_the_backups_path_after_a_copy_across_filesystems_is_never_discarded(self):
        for kind in ("file", "link"):
            with self.subTest(kind=kind):
                self.use_fresh()
                a, swarm, rows = self.displaced_by(kind)
                event = ("link", "onto", "after", "swap")
                raced = self.backup_race_uninstall(a, swarm, rows[0]["backup"], event, crossing=True)
                self.assert_swap_survived(raced, a, swarm, rows, kind)
        with self.subTest(kind="directory"):
            self.use_fresh()
            a, swarm, rows = self.displaced_by("directory")
            event = ("noreplace", "onto", "after", "swap")
            raced = self.backup_race_uninstall(a, swarm, rows[0]["backup"], event, crossing=True, foreign="directory")
            # The directory was already out of its path when the entry arrived, so only the proven directory is discarded.
            self.assert_swap_survived(raced, a, swarm, rows, "directory", "directory", saved=False, noted=False)

    def test_an_entry_that_takes_a_withdrawn_backups_path_is_never_deleted(self):
        a, b = self.base()
        rows = read_legacy(self.home)["backups"]
        swarm = provider_link(self.home, "grok", "swarm")
        backup = Path(next(row["backup"] for row in rows if row["original"] == str(swarm)))
        raced = uninstall_hooked(self.home, a, put_back_race(backup, "link"))
        self.skipped(
            raced,
            "removed 2 links, restored 0 entries",
            f"skipped withdraw {backup}: the backup no longer matches the recorded checkout",
        )
        self.assertEqual(os.readlink(backup), "/foreign/swarm")
        self.assertEqual(os.listdir(backup.parent), [backup.name])
        self.assertEqual(read_legacy(self.home)["backups"], [row for row in rows if row["backup"] == str(backup)])
        self.assert_claims(a, [str(swarm)])
        self.assert_grok_text(b)

    def holders(self):
        """Every hidden directory an installer made to move an entry through, anywhere under the home."""
        return sorted(str(path) for path in self.home.rglob(".pstack-t3-*"))

    def strand_backup(self, hook, kind="directory"):
        """Checkout a's uninstall, stopped by `hook` with the backup of a displaced swarm left aside."""
        a, swarm, rows = self.displaced_by(kind)
        backup = Path(rows[0]["backup"])
        raced = uninstall_hooked(self.home, a, hook)
        aside = set_aside(backup)
        self.assertEqual(len(aside), 1, raced.stdout + raced.stderr)
        self.assert_displaced(aside[0], kind)
        return a, swarm, backup, raced, aside[0]

    def strand_link(self):
        """Checkout a's uninstall, stopped with its own swarm link left aside and the claim still recorded."""
        a = make_checkout(self.home, "a")
        self.ok(run(self.home, a, "--harness", "grok"))
        swarm = provider_link(self.home, "grok", "swarm")
        raced = uninstall_hooked(self.home, a, UNLINK_ASIDE)
        aside = set_aside(swarm)
        self.assertEqual(len(aside), 1, raced.stdout + raced.stderr)
        self.assertEqual(os.readlink(aside[0]), str(a / "skills" / "swarm"))
        self.assert_claims(a, [str(swarm)])
        return a, swarm, raced, aside[0]

    def strand_copied_backup(self):
        """Checkout a's uninstall across filesystems, stopped after the copy landed at swarm and before the backup was deleted."""
        a, swarm, rows = self.displaced_by("directory")
        backup = Path(rows[0]["backup"])
        hook = cross_device(state_dir(self.home) / "backups", swarm) + raising("discard")
        raced = uninstall_hooked(self.home, a, hook)
        self.assertGreater(crossings(self.home), 0, raced.stdout + raced.stderr)
        aside = set_aside(backup)
        self.assertEqual(len(aside), 1, raced.stdout + raced.stderr)
        self.assert_displaced(aside[0], "directory")
        self.assert_displaced(swarm, "directory")
        return a, swarm, backup, raced, aside[0]

    def plant(self, beside, holder=".pstack-t3-unproven"):
        """A file in a holder beside `beside` that no installer put there."""
        stray = beside.parent / holder / beside.name
        stray.parent.mkdir(parents=True)
        stray.write_bytes(b"stray\x00\xfd")
        return stray

    def test_a_restore_that_raises_names_where_the_backup_is_kept(self):
        with self.subTest(stage="directory moved aside"):
            a, swarm, backup, raced, aside = self.strand_backup(raising("same_entry"))
            self.skipped(
                raced,
                "removed 3 links, restored 0 entries",
                f"skipped restore {backup}: {injected('same_entry')}; it is kept at {aside}",
            )
            self.assertFalse(os.path.lexists(swarm))
        with self.subTest(stage="backup already linked to its path"):
            self.use_fresh()
            a, swarm, backup, raced, aside = self.strand_backup(raising("same_entry"), kind="file")
            self.skipped(
                raced,
                "removed 3 links, restored 0 entries",
                f"skipped restore {backup}: {injected('same_entry')}; it is kept at {aside}",
            )
            self.assert_displaced(swarm, "file")

    def test_a_put_back_that_raises_names_where_the_entry_is_kept(self):
        a = make_checkout(self.home, "a")
        self.ok(run(self.home, a, "--harness", "grok"))
        swarm = provider_link(self.home, "grok", "swarm")
        raced = uninstall_hooked(self.home, a, put_back_race(swarm, "link") + raising("put_back"))
        aside = set_aside(swarm)
        self.assertEqual(len(aside), 1, raced.stdout + raced.stderr)
        self.skipped(
            raced,
            "removed 2 links, restored 0 entries",
            f"skipped unlink {swarm}: {injected('put_back')}; it is kept at {aside[0]}",
        )
        self.assertEqual(os.readlink(aside[0]), "/foreign/swarm")
        self.assertFalse(os.path.lexists(swarm))

    def test_a_discard_that_raises_after_a_copy_landed_names_where_the_backup_is_kept(self):
        a, swarm, backup, raced, aside = self.strand_copied_backup()
        self.skipped(
            raced,
            "removed 3 links, restored 0 entries",
            f"skipped restore {backup}: {injected('discard')}; it is kept at {aside}",
        )

    def test_a_link_removal_that_raises_names_where_the_link_is_kept(self):
        a, swarm, raced, aside = self.strand_link()
        self.skipped(
            raced,
            "removed 2 links, restored 0 entries",
            f"skipped unlink {swarm}: {injected('unlink')}; it is kept at {aside}",
        )

    def test_a_later_uninstall_restores_a_backup_left_in_a_holder(self):
        for stopped, hook in (("error", raising("same_entry")), ("kill", KILLED_ASIDE)):
            with self.subTest(stopped=stopped):
                self.use_fresh()
                a, swarm, backup, raced, aside = self.strand_backup(hook)
                self.assertEqual(raced.returncode, 9 if stopped == "kill" else 3, raced.stdout + raced.stderr)
                self.ok(
                    run(self.home, a, "--harness", "grok", "uninstall"),
                    f"recovered {backup} from {aside}",
                    "removed 0 links, restored 1 entries",
                )
                self.assert_displaced(swarm, "directory")
                self.assertFalse(os.path.lexists(backup))
                self.assert_empty_records()
                self.assertEqual(self.holders(), [])

    def test_a_later_install_returns_a_backup_left_in_a_holder_before_it_links(self):
        a, swarm, backup, raced, aside = self.strand_backup(raising("same_entry"))
        self.ok(
            run(self.home, a, "--harness", "grok"),
            f"recovered {backup} from {aside}",
            "linked 3 skills into grok",
        )
        self.assert_displaced(backup, "directory")
        self.assert_grok_text(a)
        self.assertEqual(self.holders(), [])
        self.ok(run(self.home, a, "--harness", "grok", "uninstall"), "removed 3 links, restored 1 entries")
        self.assert_displaced(swarm, "directory")
        self.assert_empty_records()

    def test_a_later_uninstall_returns_this_checkouts_link_left_in_a_holder(self):
        a, swarm, raced, aside = self.strand_link()
        self.ok(
            run(self.home, a, "--harness", "grok", "uninstall"),
            f"recovered {swarm} from {aside}",
            "removed 1 links, restored 0 entries",
        )
        self.assert_gone()
        self.assert_empty_records()
        self.assertEqual(self.holders(), [])

    def test_a_later_install_returns_this_checkouts_link_left_in_a_holder(self):
        a, swarm, raced, aside = self.strand_link()
        self.ok(
            run(self.home, a, "--harness", "grok"),
            f"recovered {swarm} from {aside}",
            "linked 2 skills into grok",
        )
        self.assert_grok_text(a)
        self.assert_claims(a, grok_paths(self.home))
        self.assertEqual([row["path"] for row in read_legacy(self.home)["links"]].count(str(swarm)), 1)
        self.assertEqual(self.holders(), [])

    def test_an_entry_no_record_proves_is_left_and_reported_on_every_run(self):
        a, swarm, rows = self.displaced_by("file")
        backup = Path(rows[0]["backup"])
        beside_skill = self.plant(swarm.parent / "notes")
        beside_backup = self.plant(backup.parent / "notes")
        lines = (
            f"left {beside_skill}: it is not a link this checkout recorded at {swarm.parent / 'notes'}",
            f"left {beside_backup}: no backup record names {backup.parent / 'notes'}",
        )
        self.ok(run(self.home, a, "--harness", "grok"), "linked 0 skills into nothing (already installed)", *lines)
        self.ok(run(self.home, a, "--harness", "grok"), "linked 0 skills into nothing (already installed)", *lines)
        self.ok(run(self.home, a, "--harness", "grok", "uninstall"), "removed 3 links, restored 1 entries", *lines)
        self.ok(run(self.home, a, "--harness", "grok", "uninstall"), "removed 0 links, restored 0 entries", *lines)
        self.assertEqual(beside_skill.read_bytes(), b"stray\x00\xfd")
        self.assertEqual(beside_backup.read_bytes(), b"stray\x00\xfd")
        self.assertFalse(os.path.lexists(swarm.parent / "notes"))
        self.assertFalse(os.path.lexists(backup.parent / "notes"))

    def test_an_entry_whose_recorded_path_is_taken_is_never_placed_over_the_occupant(self):
        a, swarm, backup, raced, aside = self.strand_backup(raising("same_entry"))
        backup.write_bytes(b"occupant\x00\xff")
        line = f"left {aside}: {backup} is the recorded backup of {swarm} and another entry is there now"
        self.ok(run(self.home, a, "--harness", "grok"), line, "linked 3 skills into grok")
        self.ok(run(self.home, a, "--harness", "grok"), line, "linked 0 skills into nothing (already installed)")
        self.assert_displaced(aside, "directory")
        self.assertEqual(backup.read_bytes(), b"occupant\x00\xff")

    def test_empty_holders_are_removed_without_a_line(self):
        a, swarm, rows = self.displaced_by("file")
        backup = Path(rows[0]["backup"])
        for parent in (swarm.parent, backup.parent):
            (parent / ".pstack-t3-empty000").mkdir()
            (parent / ".pstack-t3-scrap-empty000").mkdir()
        result = run(self.home, a, "--harness", "grok")
        self.ok(result)
        self.assertEqual(
            result.stdout.splitlines(),
            ["linked 0 skills into nothing (already installed)", f"manifest: {legacy_file(self.home)}"],
        )
        self.assertEqual(self.holders(), [])
        self.assert_displaced(backup, "file")
        self.assert_grok_text(a)

    def test_a_copy_in_a_scrap_holder_is_never_placed(self):
        for copy in ("directory", "link"):
            with self.subTest(copy=copy):
                self.use_fresh()
                a, swarm, rows = self.displaced_by("directory")
                os.unlink(swarm)
                scrap = swarm.parent / ".pstack-t3-scrap-partial0" / "swarm"
                scrap.parent.mkdir()
                if copy == "directory":
                    scrap.mkdir()
                    (scrap / "SKILL.md").write_bytes(b"partial\x00")
                else:
                    os.symlink(a / "skills" / "swarm", scrap)
                self.assert_claims(a, grok_paths(self.home))
                self.assertEqual(read_legacy(self.home)["backups"], rows)
                line = f"left {scrap}: {SCRAP_LEFT}"
                self.ok(run(self.home, a, "--harness", "grok"), line, "linked 1 skills into grok")
                self.assert_grok_text(a)
                self.ok(run(self.home, a, "--harness", "grok", "uninstall"), line, "removed 3 links, restored 1 entries")
                self.assert_displaced(swarm, "directory")
                if copy == "directory":
                    self.assertEqual(os.listdir(scrap), ["SKILL.md"])
                    self.assertEqual((scrap / "SKILL.md").read_bytes(), b"partial\x00")
                else:
                    self.assertEqual(os.readlink(scrap), str(a / "skills" / "swarm"))

    def test_what_is_left_of_a_copied_backup_is_never_returned_to_the_backups_path(self):
        a, swarm, backup, raced, aside = self.strand_copied_backup()
        line = f"left {aside}: {SCRAP_LEFT}"
        self.ok(run(self.home, a, "--harness", "grok", "uninstall"), line, "removed 0 links, restored 0 entries")
        self.assertFalse(os.path.lexists(backup))
        self.assert_displaced(aside, "directory")
        self.assert_displaced(swarm, "directory")
        swarm.rename(swarm.parent / "kept")
        self.ok(run(self.home, a, "--harness", "grok"), line, "linked 3 skills into grok")
        self.assertFalse(os.path.lexists(backup))
        self.assert_displaced(aside, "directory")
        self.assert_grok_text(a)

    def test_a_second_name_of_a_backup_left_in_a_holder_is_removed(self):
        a, swarm, backup, raced, aside = self.strand_backup(NO_PROC + raising("same_entry"), kind="file")
        self.assertTrue(os.path.samefile(aside, backup))
        rows = read_legacy(self.home)["backups"]
        self.ok(
            run(self.home, a, "--harness", "grok"),
            f"removed {aside}: it was a second name for {backup}",
            "linked 3 skills into grok",
        )
        self.assert_displaced(backup, "file")
        self.assertEqual(backup.stat().st_nlink, 1)
        self.assertEqual(read_legacy(self.home)["backups"], rows)
        self.assertEqual(self.holders(), [])

    def test_a_second_name_of_a_restored_entry_left_in_a_holder_is_removed_with_its_row(self):
        a, swarm, backup, raced, aside = self.strand_backup(raising("same_entry"), kind="file")
        self.assertTrue(os.path.samefile(aside, swarm))
        self.assertEqual([row["backup"] for row in read_legacy(self.home)["backups"]], [str(backup)])
        self.ok(
            run(self.home, a, "--harness", "grok", "uninstall"),
            f"removed {aside}: it was a second name for {swarm}",
            "removed 0 links, restored 0 entries",
        )
        self.assert_displaced(swarm, "file")
        self.assertEqual(swarm.stat().st_nlink, 1)
        self.assert_empty_records()
        self.assertEqual(self.holders(), [])

    def test_a_foreign_entry_in_a_holder_beside_a_path_this_checkout_claims_is_left(self):
        a = make_checkout(self.home, "a")
        self.ok(run(self.home, a, "--harness", "grok"))
        swarm = provider_link(self.home, "grok", "swarm")
        self.assert_claims(a, grok_paths(self.home))
        stray = self.plant(swarm)
        line = f"left {stray}: it is not a link this checkout recorded at {swarm}"
        self.ok(run(self.home, a, "--harness", "grok"), "linked 0 skills into nothing (already installed)", line)
        self.assertEqual(os.readlink(swarm), str(a / "skills" / "swarm"))
        self.ok(run(self.home, a, "--harness", "grok", "uninstall"), "removed 3 links, restored 0 entries", line)
        self.assertEqual(stray.read_bytes(), b"stray\x00\xfd")
        self.assertFalse(os.path.lexists(swarm))

    def test_this_checkouts_link_in_a_holder_whose_path_is_taken_is_removed(self):
        a, swarm, raced, aside = self.strand_link()
        swarm.write_bytes(b"occupant\x00\xff")
        self.ok(
            run(self.home, a, "--harness", "grok", "uninstall"),
            f"removed {aside}: it is this checkout's link and {swarm} is taken",
        )
        self.assertFalse(swarm.is_symlink())
        self.assertEqual(swarm.read_bytes(), b"occupant\x00\xff")
        self.assertEqual(self.holders(), [])

    def test_a_link_in_a_holder_that_no_record_of_this_checkout_names_is_left(self):
        a = make_checkout(self.home, "a")
        swarm = provider_link(self.home, "grok", "swarm")
        aside = swarm.parent / ".pstack-t3-unnamed0" / "swarm"
        aside.parent.mkdir(parents=True)
        os.symlink(a / "skills" / "swarm", aside)
        line = f"left {aside}: it is not a link this checkout recorded at {swarm}"
        self.ok(run(self.home, a, "--harness", "grok", "uninstall"), line, "removed 0 links, restored 0 entries")
        self.ok(run(self.home, a, "--harness", "grok", "uninstall"), line, "removed 0 links, restored 0 entries")
        self.assertEqual(os.readlink(aside), str(a / "skills" / "swarm"))
        self.assertFalse(os.path.lexists(swarm))

    def test_a_dry_run_reports_holders_and_changes_nothing(self):
        a, swarm, raced, aside = self.strand_link()
        stray = self.plant(swarm.parent / "notes")
        before = snapshot(self.home)
        lines = (
            f"would recover {swarm} from {aside}",
            f"left {stray}: it is not a link this checkout recorded at {swarm.parent / 'notes'}",
        )
        self.ok(run(self.home, a, "--harness", "grok", "uninstall", "--dry-run"), "would remove 0 links, would restore 0 entries", *lines)
        self.ok(run(self.home, a, "--harness", "grok", "--dry-run"), "3 links planned", *lines)
        self.assertEqual(snapshot(self.home), before)

    def test_a_dry_run_that_finds_a_holder_creates_no_state_directory(self):
        a = make_checkout(self.home, "a")
        stray = self.plant(provider_link(self.home, "grok", "notes"))
        line = f"left {stray}: it is not a link this checkout recorded at {provider_link(self.home, 'grok', 'notes')}"
        self.ok(run(self.home, a, "--harness", "grok", "uninstall", "--dry-run"), line)
        self.ok(run(self.home, a, "--harness", "grok", "--dry-run"), line)
        self.assertFalse(state_dir(self.home).exists())
        self.assertEqual(stray.read_bytes(), b"stray\x00\xfd")

    def test_a_run_with_no_holders_and_no_steps_creates_no_state_directory(self):
        a = make_checkout(self.home, "a")
        provider_link(self.home, "grok", "swarm").parent.mkdir(parents=True)
        self.ok(run(self.home, a, "--harness", "grok", "uninstall"), "removed 0 links, restored 0 entries")
        self.assertFalse(state_dir(self.home).exists())

    def test_the_state_lock_descriptor_is_closed_when_the_unlock_raises(self):
        a = make_checkout(self.home, "a")
        self.ok(run(self.home, a, "--harness", "grok"))
        count = self.home / "descriptors"
        raced = uninstall_hooked(self.home, a, unlock_failure(state_dir(self.home), count))
        self.ok(raced, "removed 3 links, restored 0 entries", f"unlock raised: [Errno {errno.EIO}] injected unlock failure")
        self.assertEqual(count.read_text(), "0")

    def test_an_older_uninstall_restores_a_backup_the_new_installer_returned(self):
        a, swarm, backup, raced, aside = self.strand_backup(KILLED_ASIDE)
        b = make_checkout(self.home, "b", old=True)
        swarm.write_bytes(b"occupant")
        self.ok(
            run(self.home, a, "--harness", "grok", "uninstall"),
            f"recovered {backup} from {aside}",
            "removed 0 links, restored 0 entries",
        )
        swarm.unlink()
        self.assert_displaced(backup, "directory")
        self.ok(run(self.home, b, "--harness", "grok", "uninstall"), "removed 0 links, restored 1 entries")
        self.assert_displaced(swarm, "directory")
        self.assertFalse(os.path.lexists(backup))

    def test_a_holder_beside_a_skills_directory_does_not_stop_an_older_installer(self):
        b = make_checkout(self.home, "b", old=True)
        stray = self.plant(provider_link(self.home, "grok", "swarm"))
        self.ok(run(self.home, b, "--harness", "grok"), "linked 3 skills into grok")
        self.assert_grok_text(b)
        self.ok(run(self.home, b, "--harness", "grok", "uninstall"), "removed 3 links, restored 0 entries")
        self.assert_gone()
        self.assertEqual(stray.read_bytes(), b"stray\x00\xfd")

    def test_a_run_for_one_harness_leaves_a_backup_of_another_harness_in_its_holder(self):
        a, swarm, backup, raced, aside = self.strand_backup(raising("same_entry"))
        other = run(self.home, a, "--harness", "claude", "uninstall")
        self.ok(other)
        self.assertEqual(other.stdout.splitlines(), ["removed 0 links, restored 0 entries"])
        self.assertFalse(os.path.lexists(backup))
        self.assert_displaced(aside, "directory")
        self.ok(
            run(self.home, a, "--harness", "grok", "uninstall"),
            f"recovered {backup} from {aside}",
            "removed 0 links, restored 1 entries",
        )
        self.assert_displaced(swarm, "directory")
        self.assertEqual(self.holders(), [])

    def test_a_run_for_one_harness_leaves_the_holders_in_the_skills_directory_of_another(self):
        a = make_checkout(self.home, "a")
        notes = provider_link(self.home, "grok", "notes")
        stray = self.plant(notes)
        empty = notes.parent / ".pstack-t3-empty000"
        empty.mkdir()
        removed = run(self.home, a, "--harness", "claude", "uninstall")
        self.ok(removed)
        self.assertEqual(removed.stdout.splitlines(), ["removed 0 links, restored 0 entries"])
        linked = run(self.home, a, "--harness", "claude")
        self.ok(linked)
        self.assertEqual(linked.stdout.splitlines(), ["linked 3 skills into claude", f"manifest: {legacy_file(self.home)}"])
        self.assertEqual(self.holders(), [str(empty), str(stray.parent)])
        self.assertEqual(stray.read_bytes(), b"stray\x00\xfd")
        self.ok(
            run(self.home, a, "--harness", "grok", "uninstall"),
            f"left {stray}: it is not a link this checkout recorded at {notes}",
            "removed 0 links, restored 0 entries",
        )
        self.assertEqual(self.holders(), [str(stray.parent)])

    def test_a_run_for_one_harness_of_a_shared_directory_returns_a_backup_filed_under_the_other(self):
        a = make_checkout(self.home, "a")
        agents = self.share_cursor_with_agents()
        self.ok(run(self.home, a, "--harness", "cursor", "--replace"), "linked 3 skills into codex, cursor")
        backup = Path(read_legacy(self.home)["backups"][0]["backup"])
        self.assertEqual(backup.parent.name, "codex")
        aside = backup.parent / ".pstack-t3-held0000" / "swarm"
        aside.parent.mkdir()
        backup.rename(aside)
        other = run(self.home, a, "--harness", "claude", "uninstall")
        self.ok(other)
        self.assertEqual(other.stdout.splitlines(), ["removed 0 links, restored 0 entries"])
        self.assertEqual(aside.read_bytes(), b"foreign\x00file\n")
        self.ok(
            run(self.home, a, "--harness", "cursor", "uninstall"),
            f"recovered {backup} from {aside}",
            "removed 0 links, restored 0 entries",
            "kept entries whose directory is shared with codex; select those harnesses too to remove them",
        )
        self.assertEqual(backup.read_bytes(), b"foreign\x00file\n")
        self.assertEqual(os.readlink(agents / "swarm"), str(a / "skills" / "swarm"))
        self.assertEqual(self.holders(), [])

    def test_an_install_refused_for_a_taken_path_reports_only_the_entries_it_leaves_in_holders(self):
        with self.subTest(held="an entry no record proves"):
            a = make_checkout(self.home, "a")
            swarm = provider_link(self.home, "grok", "swarm")
            stray = self.plant(swarm.parent / "notes")
            swarm.write_bytes(b"occupant\x00\xff")
            before = snapshot(self.home)
            refused = run(self.home, a, "--harness", "grok")
            self.assertEqual(refused.returncode, 1, refused.stdout + refused.stderr)
            self.assertEqual(
                refused.stdout.splitlines(),
                [f"left {stray}: it is not a link this checkout recorded at {swarm.parent / 'notes'}"],
            )
            self.assertIn("these skills already exist", refused.stderr)
            self.assertEqual(snapshot(self.home), before)
            self.assertFalse(state_dir(self.home).exists())
        with self.subTest(held="this checkout's link"):
            self.use_fresh()
            a, swarm, raced, aside = self.strand_link()
            provider_link(self.home, "grok", "alpha").write_bytes(b"occupant\x00\xff")
            before = snapshot(self.home)
            refused = run(self.home, a, "--harness", "grok")
            self.assertEqual(refused.returncode, 1, refused.stdout + refused.stderr)
            self.assertEqual(refused.stdout, "")
            self.assertIn("these skills already exist", refused.stderr)
            self.assertEqual(snapshot(self.home), before)
            self.assertEqual(os.readlink(aside), str(a / "skills" / "swarm"))

    def test_a_run_that_only_leaves_entries_creates_no_state_directory(self):
        a = make_checkout(self.home, "a")
        notes = provider_link(self.home, "grok", "notes")
        stray = self.plant(notes)
        line = f"left {stray}: it is not a link this checkout recorded at {notes}"
        removed = run(self.home, a, "--harness", "grok", "uninstall")
        self.ok(removed)
        self.assertEqual(removed.stdout.splitlines(), [line, "removed 0 links, restored 0 entries"])
        self.assertFalse(state_dir(self.home).exists())
        plant_links(self.home, a)
        linked = run(self.home, a, "--harness", "grok")
        self.ok(linked)
        self.assertEqual(
            linked.stdout.splitlines(),
            [line, "linked 0 skills into nothing (already installed)", f"3 {UNTRACKED}", f"manifest: {legacy_file(self.home)}"],
        )
        self.assertFalse(state_dir(self.home).exists())
        self.assertEqual(stray.read_bytes(), b"stray\x00\xfd")

    def test_a_run_that_only_leaves_entries_waits_for_the_lock_of_a_state_directory_that_exists(self):
        a = make_checkout(self.home, "a")
        notes = provider_link(self.home, "grok", "notes")
        stray = self.plant(notes)
        state_dir(self.home).mkdir(parents=True)
        lock = os.open(state_dir(self.home), os.O_RDONLY)
        self.addCleanup(os.close, lock)
        fcntl.flock(lock, fcntl.LOCK_EX)
        waiting = subprocess.Popen(
            [sys.executable, str(a / "scripts" / "install.py"), "--harness", "grok", "uninstall"],
            env=_env(self.home),
            cwd=self.home,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        self.addCleanup(waiting.kill)
        with self.assertRaises(subprocess.TimeoutExpired):
            waiting.communicate(timeout=1)
        fcntl.flock(lock, fcntl.LOCK_UN)
        stdout, stderr = waiting.communicate(timeout=30)
        self.assertEqual(waiting.returncode, 0, stderr + stdout)
        self.assertEqual(
            stdout.splitlines(),
            [f"left {stray}: it is not a link this checkout recorded at {notes}", "removed 0 links, restored 0 entries"],
        )
        self.assertEqual(stray.read_bytes(), b"stray\x00\xfd")

    def test_an_entry_at_the_path_of_a_backup_left_in_a_holder_is_not_restored_in_its_place(self):
        a, swarm, backup, raced, aside = self.strand_backup(raising("same_entry"))
        backup.write_bytes(b"occupant\x00\xff")
        self.ok(run(self.home, a, "--harness", "grok"), "linked 3 skills into grok")
        rows = read_legacy(self.home)["backups"]
        lines = [
            f"left {aside}: {backup} is the recorded backup of {swarm} and another entry is there now",
            CONTESTED.format(backup=backup, aside=aside),
        ]
        planned = run(self.home, a, "--harness", "grok", "uninstall", "--dry-run")
        self.ok(planned)
        self.assertEqual(planned.stdout.splitlines(), lines + ["would remove 3 links, would restore 0 entries"])
        removed = run(self.home, a, "--harness", "grok", "uninstall")
        self.ok(removed)
        self.assertEqual(removed.stdout.splitlines(), lines + ["removed 3 links, restored 0 entries"])
        self.assertFalse(os.path.lexists(swarm))
        self.assertEqual(backup.read_bytes(), b"occupant\x00\xff")
        self.assert_displaced(aside, "directory")
        self.assertEqual(read_legacy(self.home)["backups"], rows)
        backup.unlink()
        self.ok(
            run(self.home, a, "--harness", "grok", "uninstall"),
            f"recovered {backup} from {aside}",
            "removed 0 links, restored 1 entries",
        )
        self.assert_displaced(swarm, "directory")
        self.assert_empty_records()
        self.assertEqual(self.holders(), [])

    def test_this_checkouts_link_at_the_path_of_a_backup_left_in_a_holder_is_not_withdrawn(self):
        a, swarm, backup, raced, aside = self.strand_backup(raising("same_entry"))
        os.symlink(a / "skills" / "swarm", backup)
        self.ok(run(self.home, a, "--harness", "grok"), "linked 3 skills into grok")
        rows = read_legacy(self.home)["backups"]
        self.ok(
            run(self.home, a, "--harness", "grok", "uninstall"),
            f"left {aside}: {backup} is the recorded backup of {swarm} and another entry is there now",
            CONTESTED.format(backup=backup, aside=aside),
            "removed 3 links, restored 0 entries",
        )
        self.assertFalse(os.path.lexists(swarm))
        self.assertEqual(os.readlink(backup), str(a / "skills" / "swarm"))
        self.assert_displaced(aside, "directory")
        self.assertEqual(read_legacy(self.home)["backups"], rows)

    def test_an_entry_at_the_path_of_a_copied_backup_left_in_a_scrap_holder_is_not_restored(self):
        a, swarm, backup, raced, aside = self.strand_copied_backup()
        rows = read_legacy(self.home)["backups"]
        self.assertEqual([row["backup"] for row in rows], [str(backup)])
        backup.write_bytes(b"occupant\x00\xff")
        shutil.rmtree(swarm)
        removed = run(self.home, a, "--harness", "grok", "uninstall")
        self.ok(removed)
        self.assertEqual(
            removed.stdout.splitlines(),
            [f"left {aside}: {SCRAP_LEFT}", CONTESTED.format(backup=backup, aside=aside), "removed 0 links, restored 0 entries"],
        )
        self.assertFalse(os.path.lexists(swarm))
        self.assertEqual(backup.read_bytes(), b"occupant\x00\xff")
        self.assert_displaced(aside, "directory")
        self.assertEqual(read_legacy(self.home)["backups"], rows)

    def test_an_uninstall_that_fails_to_remove_one_of_three_links_exits_3_and_removes_the_other_two(self):
        a = make_checkout(self.home, "a")
        self.ok(run(self.home, a, "--harness", "grok"), "linked 3 skills into grok")
        swarm = provider_link(self.home, "grok", "swarm")
        failed = run_failing(self.home, a, "os.rename", swarm, "--harness", "grok", "uninstall")
        self.assertEqual(failed.returncode, 3, failed.stdout + failed.stderr)
        self.assertEqual(
            failed.stdout.splitlines(),
            [
                f"skipped unlink {swarm}: [Errno 13] Permission denied: '{swarm}'",
                "removed 2 links, restored 0 entries",
                KEPT.format(n=1),
            ],
        )
        self.assertEqual(os.readlink(swarm), str(a / "skills" / "swarm"))
        self.assert_gone(("alpha", "pstack-runtime"))

    def test_an_install_that_fails_to_create_one_of_three_links_exits_3_and_creates_the_other_two(self):
        a = make_checkout(self.home, "a")
        swarm = provider_link(self.home, "grok", "swarm")
        failed = run_failing(self.home, a, "os.symlink", swarm, "--harness", "grok")
        self.assertEqual(failed.returncode, 3, failed.stdout + failed.stderr)
        self.assertEqual(
            failed.stdout.splitlines(),
            [
                f"skipped link {swarm}: [Errno 13] Permission denied: '{swarm}'",
                "linked 2 skills into grok",
                f"manifest: {legacy_file(self.home)}",
            ],
        )
        self.assertFalse(os.path.lexists(swarm))
        self.assert_grok_text(a, ("alpha", "pstack-runtime"))

    def test_an_unknown_harness_exits_2(self):
        a = make_checkout(self.home, "a")
        refused = run(self.home, a, "--harness", "grok,nope")
        self.assertEqual(refused.returncode, 2, refused.stdout + refused.stderr)
        self.assertIn("unknown harness nope", refused.stderr)
        self.assertFalse(state_dir(self.home).exists())

    def replaced_file(self, harnesses=("grok",)):
        """Checkout a after one `--replace` run moved a user's swarm file aside for each harness."""
        a = make_checkout(self.home, "a")
        for harness in harnesses:
            swarm = provider_link(self.home, harness, "swarm")
            swarm.parent.mkdir(parents=True)
            swarm.write_bytes(f"mine\x00{harness}\n".encode())
        self.ok(run(self.home, a, "--harness", ",".join(harnesses), "--replace"), f"linked {3 * len(harnesses)} skills into {', '.join(sorted(harnesses))}")
        return a

    def under_backups(self):
        backups = state_dir(self.home) / "backups"
        return sorted(str(path.relative_to(backups)) for path in backups.rglob("*"))

    def test_an_uninstall_after_a_dry_run_restores_a_replaced_file_and_leaves_backups_empty(self):
        a = self.replaced_file()
        swarm = provider_link(self.home, "grok", "swarm")
        before = snapshot(self.home)
        self.ok(run(self.home, a, "--harness", "grok", "uninstall", "--dry-run"), "would remove 3 links, would restore 1 entries")
        self.assertEqual(snapshot(self.home), before)
        self.ok(run(self.home, a, "--harness", "grok", "uninstall"), "removed 3 links, restored 1 entries")
        self.assertFalse(swarm.is_symlink())
        self.assertEqual(swarm.read_bytes(), b"mine\x00grok\n")
        self.assertTrue((state_dir(self.home) / "backups").is_dir())
        self.assertEqual(self.under_backups(), [])

    def test_an_uninstall_of_one_harness_removes_its_backup_directory_and_keeps_the_other_harness_backup(self):
        a = self.replaced_file(("codex", "grok"))
        stamps = self.under_backups()
        self.assertEqual(len(stamps), 5, stamps)
        stamp = stamps[0]
        self.assertEqual(stamps, [stamp, f"{stamp}/codex", f"{stamp}/codex/swarm", f"{stamp}/grok", f"{stamp}/grok/swarm"])
        self.ok(run(self.home, a, "--harness", "grok", "uninstall"), "removed 3 links, restored 1 entries")
        self.assertEqual(self.under_backups(), [stamp, f"{stamp}/codex", f"{stamp}/codex/swarm"])
        self.assertEqual((state_dir(self.home) / "backups" / stamp / "codex" / "swarm").read_bytes(), b"mine\x00codex\n")
        self.ok(run(self.home, a, "--harness", "codex", "uninstall"), "removed 3 links, restored 1 entries")
        self.assertEqual(provider_link(self.home, "codex", "swarm").read_bytes(), b"mine\x00codex\n")
        self.assertEqual(provider_link(self.home, "grok", "swarm").read_bytes(), b"mine\x00grok\n")
        self.assertTrue((state_dir(self.home) / "backups").is_dir())
        self.assertEqual(self.under_backups(), [])

    def test_withdrawing_links_another_checkout_moved_aside_removes_the_emptied_backup_directories(self):
        a, b = self.base()
        self.assertEqual(len(self.under_backups()), 5)
        self.ok(
            run(self.home, a, "--harness", "grok", "uninstall"),
            "removed 3 links, restored 0 entries",
            "3 of them had been moved aside by another checkout's --replace",
        )
        self.assert_grok_text(b)
        self.assertTrue((state_dir(self.home) / "backups").is_dir())
        self.assertEqual(self.under_backups(), [])

    def test_the_sweep_that_finishes_an_interrupted_restore_removes_the_emptied_backup_directories(self):
        a, swarm, backup, raced, aside = self.strand_backup(raising("same_entry"), kind="file")
        self.assertTrue(os.path.samefile(aside, swarm))
        self.ok(
            run(self.home, a, "--harness", "grok", "uninstall"),
            f"removed {aside}: it was a second name for {swarm}",
            "removed 0 links, restored 0 entries",
        )
        self.assert_displaced(swarm, "file")
        self.assertTrue((state_dir(self.home) / "backups").is_dir())
        self.assertEqual(self.under_backups(), [])

    def test_a_file_a_person_put_beside_a_backup_keeps_its_directory_after_the_restore(self):
        a = self.replaced_file()
        stamp = self.under_backups()[0]
        note = state_dir(self.home) / "backups" / stamp / "grok" / "notes.txt"
        note.write_bytes(b"keep\x00me\n")
        self.ok(run(self.home, a, "--harness", "grok", "uninstall"), "removed 3 links, restored 1 entries")
        self.assertEqual(provider_link(self.home, "grok", "swarm").read_bytes(), b"mine\x00grok\n")
        self.assertEqual(self.under_backups(), [stamp, f"{stamp}/grok", f"{stamp}/grok/notes.txt"])
        self.assertEqual(note.read_bytes(), b"keep\x00me\n")

    def test_a_restore_from_a_backup_outside_the_stamp_and_harness_layout_leaves_its_parent_directory(self):
        places = (
            ("outside the state directory", lambda: self.home / "elsewhere" / "keep"),
            ("directly under a stamp", lambda: state_dir(self.home) / "backups" / "20260101T000000-1-abcd"),
        )
        for where, parent in places:
            with self.subTest(where=where):
                self.use_fresh()
                a = make_checkout(self.home, "a")
                swarm = provider_link(self.home, "grok", "swarm")
                saved = parent() / "swarm"
                saved.parent.mkdir(parents=True)
                saved.write_bytes(b"saved\x00\xfe")
                write_legacy(self.home, [], [{"harnesses": ["grok"], "original": str(swarm), "backup": str(saved)}])
                self.ok(run(self.home, a, "--harness", "grok", "uninstall"), "removed 0 links, restored 1 entries")
                self.assertEqual(swarm.read_bytes(), b"saved\x00\xfe")
                self.assertFalse(os.path.lexists(saved))
                self.assertTrue(saved.parent.is_dir())
                self.assertEqual(os.listdir(saved.parent), [])

    def restore_through_symlink(self, level):
        """Restore swarm from a backup whose `level` directory is a symlink to a directory outside the state directory.

        Return the symlink, the directory it points at, and the real <harness> directory the backup was in.
        """
        a = make_checkout(self.home, "a")
        swarm = provider_link(self.home, "grok", "swarm")
        backups = state_dir(self.home) / "backups"
        stamp = backups / "20260101T000000-1-abcd"
        link = {"backups": backups, "stamp": stamp, "harness": stamp / "grok"}[level]
        real = self.home / "elsewhere" / level
        emptied = real / {"backups": Path(stamp.name) / "grok", "stamp": "grok", "harness": ""}[level]
        emptied.mkdir(parents=True)
        (emptied / "swarm").write_bytes(b"saved\x00\xfe")
        link.parent.mkdir(parents=True)
        os.symlink(real, link)
        write_legacy(self.home, [], [{"harnesses": ["grok"], "original": str(swarm), "backup": str(stamp / "grok" / "swarm")}])
        self.ok(run(self.home, a, "--harness", "grok", "uninstall"), "removed 0 links, restored 1 entries")
        self.assertEqual(swarm.read_bytes(), b"saved\x00\xfe")
        self.assertEqual(os.readlink(link), str(real))
        self.assertTrue(emptied.is_dir())
        self.assertEqual(os.listdir(emptied), [])
        return link, real, emptied

    def test_a_restore_through_a_symlink_at_backups_leaves_the_stamp_and_harness_directories_it_reaches(self):
        link, real, emptied = self.restore_through_symlink("backups")
        self.assertEqual(os.listdir(real), ["20260101T000000-1-abcd"])
        self.assertEqual(os.listdir(emptied.parent), ["grok"])

    def test_a_restore_through_a_symlink_at_a_stamp_leaves_the_harness_directory_it_reaches(self):
        link, real, emptied = self.restore_through_symlink("stamp")
        self.assertEqual(os.listdir(real), ["grok"])
        self.assertEqual(os.listdir(link.parent), [link.name])

    def test_a_restore_through_a_symlink_at_a_harness_leaves_the_link_its_stamp_and_the_directory_it_points_at(self):
        link, real, emptied = self.restore_through_symlink("harness")
        self.assertEqual(real, emptied)
        self.assertEqual(os.listdir(link.parent), ["grok"])
        self.assertEqual(os.listdir(link.parent.parent), [link.parent.name])

    def test_an_uninstall_with_the_state_directory_behind_a_symlink_removes_the_emptied_directories_in_the_real_one(self):
        places = (
            ("~/.config/pstack-t3 is the symlink", lambda: state_dir(self.home), lambda real: real),
            ("~/.config is the symlink", lambda: state_dir(self.home).parent, lambda real: real / "pstack-t3"),
        )
        for where, link, real_state in places:
            with self.subTest(where=where):
                self.use_fresh()
                real = self.home / "dotfiles" / "kept"
                real.mkdir(parents=True)
                link().parent.mkdir(parents=True, exist_ok=True)
                os.symlink(real, link())
                a = self.replaced_file()
                swarm = provider_link(self.home, "grok", "swarm")
                backups = real_state(real) / "backups"
                stamps = os.listdir(backups)
                self.assertEqual(len(stamps), 1, stamps)
                self.assertEqual((backups / stamps[0] / "grok" / "swarm").read_bytes(), b"mine\x00grok\n")
                self.ok(run(self.home, a, "--harness", "grok", "uninstall"), "removed 3 links, restored 1 entries")
                self.assertFalse(swarm.is_symlink())
                self.assertEqual(swarm.read_bytes(), b"mine\x00grok\n")
                self.assertEqual(os.readlink(link()), str(real))
                self.assertFalse(backups.is_symlink())
                self.assertEqual(os.listdir(backups), [])
                self.assertEqual(sorted(os.listdir(real_state(real))), ["backups", "install-manifest.json", "install-owners"])
                self.assertEqual(sorted(os.listdir(self.home / "dotfiles")), ["kept"])

    def follow(self, checkout, command):
        """Run `command`, a string doctor printed, the way a person who copied it does: in a shell, from the checkout.

        `python3` in that shell is this test run's interpreter.
        """
        with tempfile.TemporaryDirectory() as shims:
            shim = Path(shims) / "python3"
            shim.write_text(f'#!/bin/sh\nexec {shlex.quote(sys.executable)} "$@"\n')
            shim.chmod(0o755)
            env = _env(self.home)
            env["PATH"] = shims + os.pathsep + env.get("PATH", os.defpath)
            return subprocess.run(["sh", "-c", command], env=env, cwd=checkout, capture_output=True, text=True)

    def doctor(self, checkout, status, *args):
        result = run(self.home, checkout, "doctor", *args)
        self.assertEqual(result.returncode, status, result.stdout + result.stderr)
        self.assertEqual(result.stderr, "")
        return result.stdout.splitlines()

    def harness_line(self, harness, rest):
        return f"{harness:7} {provider_link(self.home, harness, 'swarm').parent}: {rest}"

    def installed_for_grok(self):
        a = make_checkout(self.home, "a")
        self.ok(run(self.home, a, "--harness", "grok"), "linked 3 skills into grok")
        return a, provider_link(self.home, "grok", "swarm")

    def inert_row(self):
        """Add a backup row with nothing at its backup path. Return the line doctor prints for it."""
        notes = provider_link(self.home, "grok", "notes")
        backup = state_dir(self.home) / "backups" / "20260101T000000-1-abcd" / "grok" / "notes"
        data = read_legacy(self.home)
        data["backups"].append({"harnesses": ["grok"], "original": str(notes), "backup": str(backup)})
        legacy_file(self.home).write_text(json.dumps(data, indent=2) + "\n")
        return (
            f"        backup row {backup}: nothing is there (recorded as the backup of {notes}); uninstall skips the row "
            f'while that path is empty; to drop it, delete the row from "backups" in {legacy_file(self.home)}'
        )

    def away_owner(self):
        """Install a second checkout for codex and delete it. Return the line doctor prints for its owner file."""
        gone = make_checkout(self.home, "gone")
        self.ok(run(self.home, gone, "--harness", "codex"), "linked 3 skills into codex")
        shutil.rmtree(gone)
        return (
            f"        {owner_file(self.home, gone)}: claims 3 links here for checkout {gone}, and no directory is at {gone}; "
            "delete this file unless that checkout will be back at that path; deleting it removes that checkout's claims "
            f"and removes no link they name and no row of {legacy_file(self.home)}"
        )

    def relink_line(self, swarm):
        return (
            f'        claim {swarm}: nothing is there; run "python3 scripts/install.py install --harness grok" to link it again, '
            'then "python3 scripts/install.py uninstall --harness grok" removes the link and this claim'
        )

    def test_doctor_names_a_claim_with_nothing_at_its_path_and_the_advised_commands_clear_it(self):
        a, swarm = self.installed_for_grok()
        swarm.unlink()
        self.assertEqual(
            self.doctor(a, 1, "--harness", "grok"),
            [self.harness_line("grok", "2/3 pstack-t3, 1 missing"), self.relink_line(swarm)],
        )
        self.ok(self.follow(a, "python3 scripts/install.py install --harness grok"), "linked 1 skills into grok")
        self.ok(self.follow(a, "python3 scripts/install.py uninstall --harness grok"), "removed 3 links, restored 0 entries")
        self.assertIsNone(read_owner(self.home, a))
        self.assert_gone()

    def test_doctor_names_a_claim_whose_path_is_taken_and_the_advised_commands_clear_it(self):
        foreign = "foreign-dir"
        kinds = (
            ("file", lambda swarm: swarm.write_bytes(b"taken\x00\xfe"), "a file is there"),
            ("directory", lambda swarm: swarm.mkdir(), "a directory is there"),
            ("repointed link", lambda swarm: os.symlink(self.home / foreign, swarm), "a link to {foreign} is there"),
        )
        for kind, take, there in kinds:
            with self.subTest(kind=kind):
                self.use_fresh()
                a, swarm = self.installed_for_grok()
                (self.home / foreign).mkdir()
                swarm.unlink()
                take(swarm)
                self.assertEqual(
                    self.doctor(a, 1, "--harness", "grok"),
                    [
                        self.harness_line("grok", "2/3 pstack-t3, 1 taken by other copies (swarm)"),
                        f"        claim {swarm}: {there.format(foreign=self.home / foreign)}; "
                        '"python3 scripts/install.py install --harness grok" stops on 1 taken paths; with --replace it moves '
                        "them aside and links this path (uninstall restores them and removes this claim)",
                    ],
                )
                taken = snapshot(swarm.parent)
                advised = "python3 scripts/install.py install --harness grok"
                stopped = self.follow(a, advised)
                self.assertEqual(stopped.returncode, 1, stopped.stdout + stopped.stderr)
                self.assertIn("these skills already exist", stopped.stderr)
                self.ok(self.follow(a, advised + " --replace"), "linked 1 skills into grok")
                self.assert_grok_text(a)
                self.ok(run(self.home, a, "uninstall", "--harness", "grok"), "removed 3 links, restored 1 entries")
                self.assertIsNone(read_owner(self.home, a))
                self.assertEqual(snapshot(swarm.parent), tuple(row for row in taken if row[0] == "swarm"))

    def test_doctor_names_a_claim_install_plans_no_link_for(self):
        a, swarm = self.installed_for_grok()
        swarm.unlink()
        shutil.rmtree(a / "skills" / "swarm")
        self.assertEqual(
            self.doctor(a, 0, "--harness", "grok"),
            [
                self.harness_line("grok", "2/2 pstack-t3"),
                f"        claim {swarm}: nothing is there; install plans no link at that path, so no command clears this claim; "
                f'to drop it, delete the "{swarm}" entry from {owner_file(self.home, a)}',
            ],
        )

    def test_doctor_names_a_claim_in_a_checkout_with_no_skills_directory(self):
        a, swarm = self.installed_for_grok()
        swarm.unlink()
        (a / "skills").rename(a / "skills.away")
        self.assertEqual(
            self.doctor(a, 0, "--harness", "grok"),
            [
                self.harness_line("grok", "0/0 pstack-t3"),
                f"        claim {swarm}: nothing is there; skills/ is missing, so install stops before it plans a link; "
                "run python3 scripts/build.py first and rerun doctor",
            ],
        )
        stopped = run(self.home, a, "install", "--harness", "grok")
        self.assertEqual(stopped.returncode, 1, stopped.stdout + stopped.stderr)
        self.assertEqual(stopped.stderr, "skills/ is missing; run python3 scripts/build.py first\n")

    def test_the_commands_doctor_prints_for_a_project_path_with_a_space_quotes_and_a_semicolon_clear_the_claim_in_a_shell(self):
        a = make_checkout(self.home, "a")
        project = self.home / """a "b" 'c'; touch ADVICE_RAN"""
        self.clear_the_claim_as_printed(a, project, ("--project", str(project)), str(project))

    def test_the_commands_doctor_prints_for_a_project_path_that_begins_with_a_dash_clear_the_claim_in_a_shell(self):
        a = make_checkout(self.home, "a")
        install, uninstall = self.clear_the_claim_as_printed(a, a / "-project", ("--project=-project",), "-project")
        self.assertEqual(install, "python3 scripts/install.py install --harness grok --project=-project")
        self.assertEqual(uninstall, "python3 scripts/install.py uninstall --harness grok --project=-project")

    def clear_the_claim_as_printed(self, a, project, given, value):
        """Strand one claim in `project`, then run the two commands doctor prints for it. Returns them as printed.

        `given` is how the caller names the project and `value` is the path inside it. Every run starts in the checkout,
        which is where the printed commands say to run them.
        """

        def call(*args):
            command = [sys.executable, "scripts/install.py", *args, *given, "--harness", "grok"]
            return subprocess.run(command, env=_env(self.home), cwd=a, capture_output=True, text=True)

        def doctor(status):
            result = call("doctor")
            self.assertEqual((result.returncode, result.stderr), (status, ""), result.stdout)
            return result.stdout.splitlines()

        def outside():
            return [record for record in snapshot(a) if project not in (a / record[0], *(a / record[0]).parents)]

        project.mkdir()
        self.ok(call("install"), "linked 3 skills into grok")
        swarm = project / ".grok" / "skills" / "swarm"
        swarm.unlink()
        owner = project / ".pstack" / "install-owners" / owner_file(self.home, a).name
        self.assertEqual(set(json.loads(owner.read_text())["links"]), {str(swarm.parent / name) for name in NAMES})
        lines = doctor(1)
        self.assertEqual(len(lines), 2, lines)
        printed = re.fullmatch(
            re.escape(f"        claim {swarm}: nothing is there; ")
            + r'run "(.+)" to link it again, then "(.+)" removes the link and this claim',
            lines[1],
        )
        self.assertIsNotNone(printed, lines[1])
        install, uninstall = printed.groups()
        self.assertEqual(
            lines,
            [
                f"grok    {swarm.parent}: 2/3 pstack-t3, 1 missing",
                f'        claim {swarm}: nothing is there; run "{install}" to link it again, '
                f'then "{uninstall}" removes the link and this claim',
            ],
        )
        self.assertEqual(shlex.split(install), ["python3", "scripts/install.py", "install", "--harness", "grok", f"--project={value}"])
        self.assertEqual(shlex.split(uninstall), ["python3", "scripts/install.py", "uninstall", "--harness", "grok", f"--project={value}"])
        checkout = outside()
        linked = self.follow(a, install)
        self.assertEqual((linked.returncode, linked.stderr), (0, ""), linked.stdout)
        self.assertEqual(linked.stdout.splitlines(), ["linked 1 skills into grok", f"manifest: {project / '.pstack' / 'install-manifest.json'}"])
        self.assertEqual(os.readlink(swarm), str(a / "skills" / "swarm"))
        self.assertEqual(doctor(0), [f"grok    {swarm.parent}: 3/3 pstack-t3"])
        removed = self.follow(a, uninstall)
        self.assertEqual((removed.returncode, removed.stderr), (0, ""), removed.stdout)
        self.assertEqual(removed.stdout.splitlines(), ["removed 3 links, restored 0 entries"])
        self.assertFalse(owner.exists())
        self.assertEqual(os.listdir(swarm.parent), [])
        self.assertEqual(outside(), checkout)
        self.assertEqual(sorted(os.listdir(self.home)), sorted({"checkouts", project.relative_to(self.home).parts[0]}))
        self.assertEqual(os.listdir(self.home / "checkouts"), ["a"])
        self.assertEqual(sorted(os.listdir(project)), [".grok", ".pstack"])
        return install, uninstall

    def test_doctor_names_a_claim_whose_link_sits_in_a_holder_beside_it(self):
        a, swarm, raced, aside = self.strand_link()
        self.assertEqual(
            self.doctor(a, 1, "--harness", "grok"),
            [
                self.harness_line("grok", "0/3 pstack-t3, 3 missing"),
                f"        claim {swarm}: nothing is there, and {aside} holds this checkout's link for it; "
                '"python3 scripts/install.py uninstall --dry-run" prints what the next run does with it',
            ],
        )

    def test_doctor_names_a_backup_row_with_nothing_at_its_backup_path(self):
        a, swarm = self.installed_for_grok()
        row = self.inert_row()
        self.assertEqual(self.doctor(a, 0, "--harness", "grok"), [self.harness_line("grok", "3/3 pstack-t3"), row])

    def test_doctor_names_a_backup_row_whose_entry_sits_in_a_holder_beside_it(self):
        a, swarm, backup, raced, aside = self.strand_backup(KILLED_ASIDE)
        self.assertEqual(
            self.doctor(a, 1, "--harness", "grok"),
            [
                self.harness_line("grok", "0/3 pstack-t3, 3 missing"),
                f"        backup row {backup}: nothing is there, and {aside} holds an entry under that name; "
                '"python3 scripts/install.py uninstall --dry-run" prints what the next run does with it',
            ],
        )

    def test_doctor_names_another_checkouts_owner_file_whose_checkout_directory_is_gone(self):
        a, swarm = self.installed_for_grok()
        away = self.away_owner()
        self.assertEqual(
            self.doctor(a, 1, "--harness", "codex,grok"),
            [self.harness_line("codex", "0/3 pstack-t3, 3 missing"), away, self.harness_line("grok", "3/3 pstack-t3")],
        )

    def test_doctor_does_not_name_a_claim_whose_link_another_checkout_moved_aside(self):
        a, b = self.base()
        self.assertEqual(
            self.doctor(a, 1, "--harness", "grok"),
            [self.harness_line("grok", "0/3 pstack-t3, 3 taken by other copies (alpha, pstack-runtime, swarm)")],
        )

    def test_doctor_does_not_name_the_owner_file_of_a_checkout_that_still_exists(self):
        a, b = self.two()
        self.ok(run(self.home, a, "--harness", "grok"), "linked 3 skills into grok")
        self.ok(run(self.home, b, "--harness", "codex"), "linked 3 skills into codex")
        self.assertEqual(
            self.doctor(a, 1, "--harness", "codex,grok"),
            [
                self.harness_line("codex", "0/3 pstack-t3, 3 taken by other copies (alpha, pstack-runtime, swarm)"),
                self.harness_line("grok", "3/3 pstack-t3"),
            ],
        )

    def test_doctor_for_claude_prints_none_of_the_lines_it_prints_for_grok(self):
        a, swarm = self.installed_for_grok()
        swarm.unlink()
        row = self.inert_row()
        self.assertEqual(
            self.doctor(a, 1, "--harness", "grok"),
            [self.harness_line("grok", "2/3 pstack-t3, 1 missing"), self.relink_line(swarm), row],
        )
        self.assertEqual(self.doctor(a, 1, "--harness", "claude"), [self.harness_line("claude", "0/3 pstack-t3, 3 missing")])

    def test_doctor_changes_nothing_in_a_home_with_a_stale_claim_an_inert_row_and_an_away_owner_file(self):
        a, swarm = self.installed_for_grok()
        swarm.unlink()
        row = self.inert_row()
        away = self.away_owner()
        before = snapshot(self.home)
        self.assertEqual(
            self.doctor(a, 1, "--harness", "codex,grok"),
            [
                self.harness_line("codex", "0/3 pstack-t3, 3 missing"),
                away,
                self.harness_line("grok", "2/3 pstack-t3, 1 missing"),
                self.relink_line(swarm),
                row,
            ],
        )
        self.assertEqual(snapshot(self.home), before)

    def test_doctor_on_a_fresh_home_creates_no_state_directory(self):
        a = make_checkout(self.home, "a")
        self.assertEqual(self.doctor(a, 1, "--harness", "grok"), [self.harness_line("grok", "0/3 pstack-t3, 3 missing")])
        self.assertFalse(state_dir(self.home).exists())
        self.assertFalse(provider_link(self.home, "grok", "swarm").parent.exists())

    def test_doctor_exits_0_on_a_fully_linked_home_with_an_inert_row_and_an_away_owner_file(self):
        a, swarm = self.installed_for_grok()
        away = self.away_owner()
        for name in NAMES:
            provider_link(self.home, "codex", name).unlink()
        self.ok(run(self.home, a, "--harness", "codex"), "linked 3 skills into codex")
        row = self.inert_row()
        self.assertEqual(
            self.doctor(a, 0, "--harness", "codex,grok"),
            [self.harness_line("codex", "3/3 pstack-t3"), away, self.harness_line("grok", "3/3 pstack-t3"), row],
        )

    def assert_stops(self, checkout, text):
        for command in ("install", "uninstall"):
            stopped = run(self.home, checkout, command, "--harness", "grok")
            self.assertEqual(stopped.returncode, 1, stopped.stdout + stopped.stderr)
            self.assertEqual(stopped.stderr, text + "\n")
            self.assertEqual(stopped.stdout, "")

    def test_doctor_names_a_manifest_that_is_not_json_and_still_checks_the_owner_files(self):
        a, swarm = self.installed_for_grok()
        away = self.away_owner()
        legacy_file(self.home).write_text("{not json\n")
        refusal = f"{legacy_file(self.home)} is not valid JSON; fix or move it and rerun"
        self.assertEqual(
            self.doctor(a, 1, "--harness", "codex,grok"),
            [
                self.harness_line("codex", "0/3 pstack-t3, 3 missing"),
                away,
                self.harness_line("grok", "3/3 pstack-t3"),
                f"{refusal} (doctor checked no claims and no backup rows)",
            ],
        )
        self.assert_stops(a, refusal)
        self.assertEqual(legacy_file(self.home).read_text(), "{not json\n")

    def test_doctor_names_this_checkouts_owner_file_that_is_not_json_and_still_checks_the_backup_rows(self):
        a, swarm = self.installed_for_grok()
        row = self.inert_row()
        owner = owner_file(self.home, a)
        owner.write_text("{not json\n")
        refusal = f"{owner} is not valid JSON; fix or move it and rerun"
        self.assertEqual(
            self.doctor(a, 1, "--harness", "grok"),
            [self.harness_line("grok", "3/3 pstack-t3"), row, f"{refusal} (doctor checked no claims of this checkout)"],
        )
        self.assert_stops(a, refusal)
        self.assertEqual(owner.read_text(), "{not json\n")

    def test_doctor_names_another_checkouts_owner_file_it_cannot_read_a_checkout_from_and_still_checks_the_claims(self):
        cases = (
            ("{not json\n", "{file} is not valid JSON; fix or move it and rerun (doctor read no checkout from it)"),
            ('{"links": {}}\n', "{file} names no checkout (doctor read no checkout from it)"),
        )
        for text, line in cases:
            with self.subTest(text=text):
                self.use_fresh()
                a, swarm = self.installed_for_grok()
                swarm.unlink()
                other = owner_file(self.home, a).with_name("00aa11bb22cc33dd.json")
                other.write_text(text)
                self.assertEqual(
                    self.doctor(a, 1, "--harness", "grok"),
                    [self.harness_line("grok", "2/3 pstack-t3, 1 missing"), self.relink_line(swarm), line.format(file=other)],
                )
                self.ok(run(self.home, a, "--harness", "grok"), "linked 1 skills into grok")
                self.ok(run(self.home, a, "--harness", "grok", "uninstall"), "removed 3 links, restored 0 entries")
                self.assertEqual(other.read_text(), text)

    INSTALL = "python3 scripts/install.py install --harness {harnesses}"
    UNINSTALL = "python3 scripts/install.py uninstall --harness {harnesses}"

    def relink_group(self, count, harnesses, paths):
        return [
            f'        {count} claims have nothing at their paths; run "{self.INSTALL.format(harnesses=harnesses)}" to link them again, '
            f'then "{self.UNINSTALL.format(harnesses=harnesses)}" removes the links and these claims:',
            *(f"          {path}" for path in paths),
        ]

    def test_doctor_prints_two_claims_with_nothing_at_their_paths_as_one_group_and_the_advised_commands_clear_them(self):
        a, swarm = self.installed_for_grok()
        alpha = provider_link(self.home, "grok", "alpha")
        alpha.unlink()
        swarm.unlink()
        self.assertEqual(
            self.doctor(a, 1, "--harness", "grok"),
            [self.harness_line("grok", "1/3 pstack-t3, 2 missing"), *self.relink_group(2, "grok", (alpha, swarm))],
        )
        self.ok(self.follow(a, self.INSTALL.format(harnesses="grok")), "linked 2 skills into grok")
        self.assert_grok_text(a)
        self.ok(self.follow(a, self.UNINSTALL.format(harnesses="grok")), "removed 3 links, restored 0 entries")
        self.assertIsNone(read_owner(self.home, a))
        self.assert_gone()

    def test_doctor_prints_one_group_under_each_of_two_harnesses_with_that_harness_in_its_commands(self):
        a = make_checkout(self.home, "a")
        self.ok(run(self.home, a, "--harness", "codex,grok"), "linked 6 skills into codex, grok")
        for harness in ("codex", "grok"):
            for name in NAMES:
                provider_link(self.home, harness, name).unlink()
        self.assertEqual(
            self.doctor(a, 1, "--harness", "codex,grok"),
            [
                self.harness_line("codex", "0/3 pstack-t3, 3 missing"),
                *self.relink_group(3, "codex", (provider_link(self.home, "codex", name) for name in NAMES)),
                self.harness_line("grok", "0/3 pstack-t3, 3 missing"),
                *self.relink_group(3, "grok", (provider_link(self.home, "grok", name) for name in NAMES)),
            ],
        )

    def test_doctor_prints_three_claims_at_a_file_a_directory_and_nothing_as_one_group_that_says_what_is_at_each(self):
        a, swarm = self.installed_for_grok()
        alpha, runtime = (provider_link(self.home, "grok", name) for name in ("alpha", "pstack-runtime"))
        for link in (alpha, runtime, swarm):
            link.unlink()
        alpha.write_bytes(b"taken\x00\xfe")
        runtime.mkdir()
        self.assertEqual(
            self.doctor(a, 1, "--harness", "grok"),
            [
                self.harness_line("grok", "0/3 pstack-t3, 2 taken by other copies (alpha, pstack-runtime), 1 missing"),
                '        3 claims; "python3 scripts/install.py install --harness grok" stops on 2 taken paths; with --replace it '
                "moves them aside and links the path of each claim (uninstall restores them and removes these claims):",
                f"          {alpha}: a file is there",
                f"          {runtime}: a directory is there",
                f"          {swarm}: nothing is there",
            ],
        )

    def test_doctor_prints_two_claims_install_plans_no_link_for_as_one_group_that_names_the_owner_file_once(self):
        a, swarm = self.installed_for_grok()
        alpha = provider_link(self.home, "grok", "alpha")
        for link in (alpha, swarm):
            link.unlink()
            shutil.rmtree(a / "skills" / link.name)
        self.assertEqual(
            self.doctor(a, 0, "--harness", "grok"),
            [
                self.harness_line("grok", "1/1 pstack-t3"),
                "        2 claims; install plans no link at the path of any of them, so no command clears them; "
                f"to drop one, delete the entry named by its path from {owner_file(self.home, a)}:",
                f"          {alpha}: nothing is there",
                f"          {swarm}: nothing is there",
            ],
        )

    def test_doctor_prints_two_claims_in_a_checkout_with_no_skills_directory_as_one_group(self):
        a, swarm = self.installed_for_grok()
        alpha = provider_link(self.home, "grok", "alpha")
        alpha.unlink()
        swarm.unlink()
        (a / "skills").rename(a / "skills.away")
        self.assertEqual(
            self.doctor(a, 0, "--harness", "grok"),
            [
                self.harness_line("grok", "0/0 pstack-t3"),
                "        2 claims; skills/ is missing, so install stops before it plans a link; "
                "run python3 scripts/build.py first and rerun doctor:",
                f"          {alpha}: nothing is there",
                f"          {swarm}: nothing is there",
            ],
        )

    def test_doctor_prints_two_backup_rows_with_nothing_at_their_backup_paths_as_one_group_that_names_the_manifest_once(self):
        a, swarm = self.installed_for_grok()
        stamp = state_dir(self.home) / "backups" / "20260101T000000-1-abcd" / "grok"
        rows = [(provider_link(self.home, "grok", name), stamp / name) for name in ("notes", "todo")]
        data = read_legacy(self.home)
        data["backups"].extend({"harnesses": ["grok"], "original": str(original), "backup": str(backup)} for original, backup in rows)
        legacy_file(self.home).write_text(json.dumps(data, indent=2) + "\n")
        self.assertEqual(
            self.doctor(a, 0, "--harness", "grok"),
            [
                self.harness_line("grok", "3/3 pstack-t3"),
                "        2 backup rows have nothing at their backup paths; uninstall skips each row while its backup path is empty; "
                f'to drop one, delete the row from "backups" in {legacy_file(self.home)}:',
                *(f"          {backup} (recorded as the backup of {original})" for original, backup in rows),
            ],
        )

    def test_doctor_prints_a_claim_and_a_backup_row_that_each_have_an_entry_in_a_holder_as_one_group(self):
        a, swarm, rows = self.displaced_by("directory")
        alpha = provider_link(self.home, "grok", "alpha")
        backup = Path(rows[0]["backup"])
        raced = uninstall_hooked(self.home, a, UNLINK_ASIDE.replace("'/swarm'", "'/alpha'") + KILLED_ASIDE)
        held_link, held_backup = set_aside(alpha), set_aside(backup)
        self.assertEqual((len(held_link), len(held_backup)), (1, 1), raced.stdout + raced.stderr)
        self.assertEqual(os.readlink(held_link[0]), str(a / "skills" / "alpha"))
        self.assert_displaced(held_backup[0], "directory")
        self.assertEqual(
            self.doctor(a, 1, "--harness", "grok"),
            [
                self.harness_line("grok", "0/3 pstack-t3, 3 missing"),
                '        2 records; "python3 scripts/install.py uninstall --dry-run" prints what the next run does with '
                "the entry held for each:",
                f"          claim {alpha}: nothing is there, and {held_link[0]} holds this checkout's link for it",
                f"          backup row {backup}: nothing is there, and {held_backup[0]} holds an entry under that name",
            ],
        )

    def test_doctor_prints_a_group_where_its_first_claim_is_and_a_claim_alone_in_its_advice_as_todays_sentence(self):
        a, swarm = self.installed_for_grok()
        alpha, runtime = (provider_link(self.home, "grok", name) for name in ("alpha", "pstack-runtime"))
        self.assertEqual(list(read_owner(self.home, a)["links"]), [str(alpha), str(runtime), str(swarm)])
        for link in (alpha, runtime, swarm):
            link.unlink()
        shutil.rmtree(a / "skills" / "pstack-runtime")
        self.assertEqual(
            self.doctor(a, 1, "--harness", "grok"),
            [
                self.harness_line("grok", "0/2 pstack-t3, 2 missing"),
                *self.relink_group(2, "grok", (alpha, swarm)),
                f"        claim {runtime}: nothing is there; install plans no link at that path, so no command clears this claim; "
                f'to drop it, delete the "{runtime}" entry from {owner_file(self.home, a)}',
            ],
        )

    def test_doctor_prints_two_claims_under_one_harness_whose_commands_name_different_harnesses_as_two_sentences(self):
        a = make_checkout(self.home, "a")
        shared = provider_link(self.home, "codex", "swarm").parent
        own = provider_link(self.home, "cursor", "swarm").parent
        shared.mkdir(parents=True)
        own.parent.mkdir()
        os.symlink(shared, own)
        self.ok(run(self.home, a, "--harness", "codex,cursor"), "linked 3 skills into codex, cursor")
        own.unlink()
        own.mkdir()
        alpha, swarm = (shared / name for name in ("alpha", "swarm"))
        swarm.unlink()
        self.ok(run(self.home, a, "--harness", "codex"), "linked 1 skills into codex")
        links = read_owner(self.home, a)["links"]
        self.assertEqual((links[str(alpha)], links[str(swarm)]), ({"harnesses": ["codex", "cursor"]}, {"harnesses": ["codex"]}))
        alpha.unlink()
        swarm.unlink()

        def relink(path, harnesses):
            return (
                f'        claim {path}: nothing is there; run "{self.INSTALL.format(harnesses=harnesses)}" to link it again, '
                f'then "{self.UNINSTALL.format(harnesses=harnesses)}" removes the link and this claim'
            )

        self.assertEqual(
            self.doctor(a, 1, "--harness", "codex,cursor"),
            [
                self.harness_line("codex", "1/3 pstack-t3, 2 missing"),
                relink(alpha, "codex,cursor"),
                relink(swarm, "codex"),
                self.harness_line("cursor", "0/3 pstack-t3, 3 missing"),
                relink(alpha, "codex,cursor"),
            ],
        )

    def test_the_two_commands_of_a_group_for_a_project_path_with_a_space_relink_every_listed_path_and_clear_every_claim(self):
        a = make_checkout(self.home, "a")
        project = self.home / "my project"
        project.mkdir()

        def call(*args):
            command = [sys.executable, "scripts/install.py", *args, "--project", str(project), "--harness", "grok"]
            return subprocess.run(command, env=_env(self.home), cwd=a, capture_output=True, text=True)

        self.ok(call("install"), "linked 3 skills into grok")
        skills = project / ".grok" / "skills"
        owner = project / ".pstack" / "install-owners" / owner_file(self.home, a).name
        (skills / "alpha").unlink()
        (skills / "swarm").unlink()
        reported = call("doctor")
        self.assertEqual((reported.returncode, reported.stderr), (1, ""), reported.stdout)
        lines = reported.stdout.splitlines()
        self.assertEqual(len(lines), 4, lines)
        printed = re.fullmatch(
            r'        2 claims have nothing at their paths; run "(.+)" to link them again, '
            r'then "(.+)" removes the links and these claims:',
            lines[1],
        )
        self.assertIsNotNone(printed, lines[1])
        install, uninstall = printed.groups()
        self.assertEqual(shlex.split(install), ["python3", "scripts/install.py", "install", "--harness", "grok", f"--project={project}"])
        self.assertEqual(shlex.split(uninstall), ["python3", "scripts/install.py", "uninstall", "--harness", "grok", f"--project={project}"])
        self.assertEqual(
            lines,
            [f"grok    {skills}: 1/3 pstack-t3, 2 missing", lines[1], f"          {skills / 'alpha'}", f"          {skills / 'swarm'}"],
        )
        self.ok(self.follow(a, install), "linked 2 skills into grok")
        for line in lines[2:]:
            listed = Path(line.strip())
            self.assertEqual(os.readlink(listed), str(a / "skills" / listed.name))
        self.assertEqual(set(json.loads(owner.read_text())["links"]), {str(skills / name) for name in NAMES})
        self.ok(self.follow(a, uninstall), "removed 3 links, restored 0 entries")
        self.assertFalse(owner.exists())
        self.assertEqual(os.listdir(skills), [])

    def test_after_the_owner_file_doctor_names_is_deleted_doctor_prints_no_line_for_it_and_this_checkouts_uninstall_leaves_that_checkouts_links_and_manifest_rows(self):
        a, swarm = self.installed_for_grok()
        away = self.away_owner()
        gone = self.home / "checkouts" / "gone"
        codex = self.harness_line("codex", "0/3 pstack-t3, 3 missing")
        grok = self.harness_line("grok", "3/3 pstack-t3")
        self.assertEqual(self.doctor(a, 1, "--harness", "codex,grok"), [codex, away, grok])
        rows = [row for row in read_legacy(self.home)["links"] if row["checkout"] == str(gone)]
        self.assertEqual([row["path"] for row in rows], [str(provider_link(self.home, "codex", name)) for name in NAMES])
        owner_file(self.home, gone).unlink()
        self.assertEqual(self.doctor(a, 1, "--harness", "codex,grok"), [codex, grok])
        self.ok(run(self.home, a, "uninstall", "--harness", "codex,grok"), "removed 3 links, restored 0 entries")
        for name in NAMES:
            self.assertEqual(os.readlink(provider_link(self.home, "codex", name)), str(gone / "skills" / name))
        self.assertEqual(sorted(os.listdir(provider_link(self.home, "codex", "swarm").parent)), sorted(NAMES))
        self.assertEqual(read_legacy(self.home)["links"], rows)

    def test_doctor_prints_two_claims_that_name_no_harness_as_one_unindented_group_after_the_last_harness_and_before_an_unreadable_owner_file(self):
        a, swarm = self.installed_for_grok()
        owner = owner_file(self.home, a)
        alpha = provider_link(self.home, "grok", "alpha")
        data = read_owner(self.home, a)
        for link in (alpha, swarm):
            data["links"][str(link)] = {"harnesses": []}
            link.unlink()
            shutil.rmtree(a / "skills" / link.name)
        owner.write_text(json.dumps(data, indent=2) + "\n")
        other = owner_file(self.home, self.home / "checkouts" / "b")
        other.write_text("{not json\n")
        self.assertEqual(
            self.doctor(a, 0, "--harness", "grok"),
            [
                self.harness_line("grok", "1/1 pstack-t3"),
                "2 claims; install plans no link at the path of any of them, so no command clears them; "
                f"to drop one, delete the entry named by its path from {owner}:",
                f"  {alpha}: nothing is there",
                f"  {swarm}: nothing is there",
                f"{other} is not valid JSON; fix or move it and rerun (doctor read no checkout from it)",
            ],
        )

    def test_doctor_exits_1_on_a_fully_linked_home_whose_manifest_is_not_json(self):
        a, swarm = self.installed_for_grok()
        legacy_file(self.home).write_text("{not json\n")
        refusal = f"{legacy_file(self.home)} is not valid JSON; fix or move it and rerun"
        self.assertEqual(
            self.doctor(a, 1, "--harness", "grok"),
            [self.harness_line("grok", "3/3 pstack-t3"), f"{refusal} (doctor checked no claims and no backup rows)"],
        )
        self.assert_stops(a, refusal)

    def test_doctor_exits_1_on_a_fully_linked_home_whose_owner_file_for_this_checkout_records_another_checkout(self):
        a, swarm = self.installed_for_grok()
        owner = owner_file(self.home, a)
        data = read_owner(self.home, a)
        data["checkout"] = "/elsewhere/checkout"
        owner.write_text(json.dumps(data, indent=2) + "\n")
        self.assertEqual(
            self.doctor(a, 1, "--harness", "grok"),
            [
                self.harness_line("grok", "3/3 pstack-t3"),
                f"{owner} records /elsewhere/checkout, not this checkout (doctor checked no claims of this checkout)",
            ],
        )

    def test_doctor_exits_1_and_names_the_manifest_then_this_checkouts_owner_file_when_neither_is_json(self):
        a, swarm = self.installed_for_grok()
        owner = owner_file(self.home, a)
        legacy_file(self.home).write_text("{not json\n")
        owner.write_text("{not json\n")
        self.assertEqual(
            self.doctor(a, 1, "--harness", "grok"),
            [
                self.harness_line("grok", "3/3 pstack-t3"),
                f"{legacy_file(self.home)} is not valid JSON; fix or move it and rerun (doctor checked no claims and no backup rows)",
                f"{owner} is not valid JSON; fix or move it and rerun (doctor checked no claims of this checkout)",
            ],
        )

    @unittest.skipIf(os.geteuid() == 0, "root reads a file of mode 000")
    def test_doctor_exits_1_on_a_fully_linked_home_whose_manifest_it_has_no_permission_to_read(self):
        a, swarm = self.installed_for_grok()
        legacy_file(self.home).chmod(0)
        self.addCleanup(legacy_file(self.home).chmod, 0o644)
        self.assertEqual(
            self.doctor(a, 1, "--harness", "grok"),
            [
                self.harness_line("grok", "3/3 pstack-t3"),
                f"[Errno 13] Permission denied: '{legacy_file(self.home)}' (doctor checked no claims and no backup rows)",
            ],
        )

    def test_doctor_exits_0_on_a_fully_linked_home_where_only_another_checkouts_owner_file_is_not_json(self):
        a, swarm = self.installed_for_grok()
        other = owner_file(self.home, a).with_name("00aa11bb22cc33dd.json")
        other.write_text("{not json\n")
        self.assertEqual(
            self.doctor(a, 0, "--harness", "grok"),
            [
                self.harness_line("grok", "3/3 pstack-t3"),
                f"{other} is not valid JSON; fix or move it and rerun (doctor read no checkout from it)",
            ],
        )

    def taken_swarm(self, harnesses=("grok",)):
        """Checkout b and a user's swarm file at each harness's path, before any install."""
        b = make_checkout(self.home, "b")
        for harness in harnesses:
            swarm = provider_link(self.home, harness, "swarm")
            swarm.parent.mkdir(parents=True)
            swarm.write_bytes(f"mine\x00{harness}\n".encode())
        return b, provider_link(self.home, "grok", "swarm")

    def refused(self, swarm):
        return f"skipped move {swarm}: [Errno 13] Permission denied: '{swarm}'"

    def test_a_replace_whose_only_move_raises_before_any_copy_leaves_nothing_under_backups(self):
        b, swarm = self.taken_swarm()
        failed = run_failing(self.home, b, "shutil.move", swarm, "--harness", "grok", "--replace")
        self.skipped(failed, "linked 2 skills into grok", self.refused(swarm))
        self.assertEqual(swarm.read_bytes(), b"mine\x00grok\n")
        self.assertTrue((state_dir(self.home) / "backups").is_dir())
        self.assertEqual(self.under_backups(), [])

    def test_a_replace_whose_only_move_is_skipped_because_its_path_vanished_leaves_nothing_under_backups(self):
        b, swarm = self.taken_swarm()
        vanish = (
            "checking = module.ready\n"
            "def ready(step, root):\n"
            "    if step.kind == 'move':\n"
            "        os.unlink(step.path)\n"
            "    return checking(step, root)\n"
            "module.ready = ready\n"
        )
        raced = install_hooked(self.home, b, vanish, "--harness", "grok", "--replace")
        self.skipped(raced, "linked 3 skills into grok", f"skipped move {swarm}: it changed before install")
        self.assertEqual(read_legacy(self.home)["backups"], [])
        self.assertTrue((state_dir(self.home) / "backups").is_dir())
        self.assertEqual(self.under_backups(), [])

    def test_a_replace_for_two_harnesses_where_one_move_raises_keeps_only_the_other_harness_backup_directory(self):
        b, swarm = self.taken_swarm(("codex", "grok"))
        failed = run_failing(self.home, b, "shutil.move", swarm, "--harness", "codex,grok", "--replace")
        self.skipped(failed, "linked 5 skills into codex, grok", self.refused(swarm))
        self.assertEqual(swarm.read_bytes(), b"mine\x00grok\n")
        stamp = self.under_backups()[0]
        self.assertEqual(self.under_backups(), [stamp, f"{stamp}/codex", f"{stamp}/codex/swarm"])
        self.assertEqual((state_dir(self.home) / "backups" / stamp / "codex" / "swarm").read_bytes(), b"mine\x00codex\n")

    def test_an_install_that_stops_on_an_unreadable_record_after_it_made_its_stamp_leaves_nothing_under_backups(self):
        b, swarm = self.taken_swarm()
        stop = (
            "def add_records(step, state, root):\n"
            "    if step.kind == 'move':\n"
            "        raise module.Unreadable('stop')\n"
            "    return lambda: None\n"
            "module.add_records = add_records\n"
        )
        stopped = install_hooked(self.home, b, stop, "--harness", "grok", "--replace")
        self.assertEqual((stopped.returncode, stopped.stderr), (1, "stop\n"), stopped.stdout)
        self.assertEqual(swarm.read_bytes(), b"mine\x00grok\n")
        self.assertTrue((state_dir(self.home) / "backups").is_dir())
        self.assertEqual(self.under_backups(), [])

    def failed_move_through_symlink(self, level):
        """A `--replace` whose move raises after the run's `level` directory became a symlink to a directory elsewhere.

        Return the symlink and the directory it points at, which holds the levels below it.
        """
        b, swarm = self.taken_swarm()
        real = self.home / "elsewhere" / level
        real.parent.mkdir()
        up = {"backups": "os.path.dirname(os.path.dirname(os.path.dirname(destination)))",
              "stamp": "os.path.dirname(os.path.dirname(destination))", "harness": "os.path.dirname(destination)"}[level]
        hook = refused_move(
            swarm,
            f"link = {up}",
            f"os.rename(link, {str(real)!r})",
            f"os.symlink({str(real)!r}, link)",
            f"open({str(self.home / 'link')!r}, 'w').write(link)",
        )
        self.skipped(install_hooked(self.home, b, hook, "--harness", "grok", "--replace"), self.refused(swarm))
        link = Path((self.home / "link").read_text())
        self.assertEqual(os.readlink(link), str(real))
        self.assertEqual(swarm.read_bytes(), b"mine\x00grok\n")
        return link, real

    def test_a_failed_move_with_backups_swapped_for_a_symlink_leaves_the_stamp_and_harness_directories_behind_it(self):
        link, real = self.failed_move_through_symlink("backups")
        self.assertEqual(link, state_dir(self.home) / "backups")
        stamps = os.listdir(real)
        self.assertEqual(len(stamps), 1, stamps)
        self.assertEqual(os.listdir(real / stamps[0]), ["grok"])
        self.assertEqual(os.listdir(real / stamps[0] / "grok"), [])

    def test_a_failed_move_with_its_stamp_swapped_for_a_symlink_leaves_the_link_and_the_harness_directory_behind_it(self):
        link, real = self.failed_move_through_symlink("stamp")
        self.assertEqual(os.listdir(link.parent), [link.name])
        self.assertEqual(os.listdir(real), ["grok"])
        self.assertEqual(os.listdir(real / "grok"), [])

    def test_a_failed_move_with_its_harness_directory_swapped_for_a_symlink_leaves_the_link_its_stamp_and_the_directory(self):
        link, real = self.failed_move_through_symlink("harness")
        self.assertEqual(os.listdir(link.parent), ["grok"])
        self.assertEqual(os.listdir(link.parent.parent), [link.parent.name])
        self.assertEqual(os.listdir(real), [])

    def test_a_file_written_beside_a_backup_that_never_arrived_keeps_its_harness_and_stamp_directories(self):
        b, swarm = self.taken_swarm()
        hook = refused_move(swarm, "open(os.path.join(os.path.dirname(destination), 'notes.txt'), 'wb').write(b'keep\\x00me\\n')")
        self.skipped(install_hooked(self.home, b, hook, "--harness", "grok", "--replace"), self.refused(swarm))
        stamp = self.under_backups()[0]
        self.assertEqual(self.under_backups(), [stamp, f"{stamp}/grok", f"{stamp}/grok/notes.txt"])
        self.assertEqual((state_dir(self.home) / "backups" / stamp / "grok" / "notes.txt").read_bytes(), b"keep\x00me\n")

    def test_a_harness_directory_this_run_did_not_make_in_its_stamp_stops_the_move_and_stays(self):
        b, swarm = self.taken_swarm()
        planted = (
            "import tempfile\n"
            "making = tempfile.mkdtemp\n"
            "def mkdtemp(*args, **kwargs):\n"
            "    made = making(*args, **kwargs)\n"
            "    os.mkdir(os.path.join(made, 'grok'))\n"
            "    return made\n"
            "tempfile.mkdtemp = mkdtemp\n"
        )
        raced = install_hooked(self.home, b, planted, "--harness", "grok", "--replace")
        stamp = self.under_backups()[0]
        self.skipped(
            raced,
            "linked 2 skills into grok",
            f"skipped move {swarm}: [Errno 17] File exists: '{state_dir(self.home) / 'backups' / stamp / 'grok'}'",
        )
        self.assertEqual(self.under_backups(), [stamp, f"{stamp}/grok"])
        self.assertEqual(swarm.read_bytes(), b"mine\x00grok\n")
        self.assertEqual(read_legacy(self.home)["backups"], [])

    def test_a_failed_move_leaves_an_empty_harness_directory_under_another_stamp(self):
        b, swarm = self.taken_swarm()
        other = state_dir(self.home) / "backups" / "20260101T000000-1-abcd" / "grok"
        other.mkdir(parents=True)
        failed = run_failing(self.home, b, "shutil.move", swarm, "--harness", "grok", "--replace")
        self.skipped(failed, "linked 2 skills into grok", self.refused(swarm))
        self.assertEqual(self.under_backups(), ["20260101T000000-1-abcd", "20260101T000000-1-abcd/grok"])
