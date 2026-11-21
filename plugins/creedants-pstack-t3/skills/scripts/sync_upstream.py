#!/usr/bin/env python3
"""Replace vendor/pstack with a newer upstream revision and report override drift.

After syncing, `python3 scripts/build.py` lists every override whose upstream
file changed. Re-port each one, then run `build.py --update-lock`.

With --check, sync nothing. Print each path upstream changed since the pinned
commit and what pstack-t3 does with that path, and write nothing in the checkout.
"""

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
from dataclasses import asdict, dataclass
from pathlib import Path, PurePosixPath
from typing import Literal, Mapping

ROOT = Path(__file__).resolve().parents[1]
UPSTREAM = ROOT / "upstream.json"

Change = Literal["changed", "added", "removed"]
Handling = Literal["overridden", "dropped", "unchanged", "not-shipped"]

STATUS = {"M": "changed", "T": "changed", "A": "added", "D": "removed"}
HANDLING_TEXT = {
    "overridden": "overridden by {t3_path}",
    "dropped": "dropped by t3/removed.txt",
    "unchanged": "ships unchanged",
    "not-shipped": "not shipped",
}
FIXED_COPIES = {
    "pstack-runtime/SKILL.md": "runtime.md",
    "pstack-runtime/scripts/roles.py": "scripts/roles.py",
    "setup-pstack/SKILL.md": "setup.md",
}


@dataclass(frozen=True)
class Layers:
    hand_ported: Mapping[str, str]
    added: frozenset[str]
    overrides: frozenset[str]
    removed: frozenset[str]


@dataclass(frozen=True)
class Entry:
    path: str
    change: Change
    handling: Handling
    t3_path: str | None


@dataclass(frozen=True)
class Report:
    repository: str
    ref: str
    pinned: str
    commit: str
    version: str | None
    changes: tuple[Entry, ...]

    @property
    def up_to_date(self):
        return self.commit == self.pinned


def run(*command, cwd=None):
    return subprocess.run(command, cwd=cwd, check=True, capture_output=True, text=True).stdout.strip()


def load_layers():
    # Importing build would otherwise leave scripts/__pycache__ in the checkout.
    sys.dont_write_bytecode = True
    sys.path.insert(0, str(ROOT / "scripts"))
    import build

    t3 = build.T3
    hand_ported = {f"skills/{key}": f"t3/{file}" for key, file in FIXED_COPIES.items() if (t3 / file).is_file()}
    for persona in sorted((t3 / "agents").glob("*.md")):
        hand_ported[f"agents/{persona.name}"] = f"t3/agents/{persona.name}"
        hand_ported[f"skills/pstack-runtime/agents/{persona.name}"] = f"t3/agents/{persona.name}"
    return Layers(
        hand_ported=hand_ported,
        added=frozenset(rel.as_posix() for rel in build.relative_files(t3 / "added")),
        overrides=frozenset(rel.as_posix() for rel in build.relative_files(t3 / "overrides")),
        removed=frozenset(rel.as_posix() for rel in build.removed_paths()),
    )


def classify(path, prefix, layers):
    rest = PurePosixPath(path).relative_to(prefix)
    if "__pycache__" in rest.parts:
        return "not-shipped", None
    if str(rest) in layers.hand_ported:
        return "overridden", layers.hand_ported[str(rest)]
    if len(rest.parts) < 2 or rest.parts[0] != "skills":
        return "not-shipped", None
    key = PurePosixPath(*rest.parts[1:])
    if str(key) in layers.added:
        return "overridden", f"t3/added/{key}"
    if str(key) in layers.overrides:
        return "overridden", f"t3/overrides/{key}"
    if str(key) in layers.removed or any(str(parent) in layers.removed for parent in key.parents):
        return "dropped", None
    return "unchanged", None


def upstream_changes(repository, ref, pinned, prefix):
    with tempfile.TemporaryDirectory(prefix="pstack-upstream-") as temporary:
        clone = Path(temporary) / "upstream.git"

        def git(*arguments, cwd=clone):
            return subprocess.run(
                ("git", *arguments),
                cwd=cwd,
                check=True,
                capture_output=True,
                encoding="utf-8",
                errors="surrogateescape",
                env={**os.environ, "GIT_TERMINAL_PROMPT": "0"},
            ).stdout

        git("clone", "--bare", "--filter=blob:none", repository, str(clone), cwd=temporary)
        commit = git("rev-parse", "--verify", "--end-of-options", f"{ref}^{{commit}}").strip()
        changes = []
        if commit != pinned:
            listing = git(
                "diff", "--name-status", "--no-renames", "--no-ext-diff", "-z", pinned, commit, "--", f":(literal){prefix}"
            )
            fields = listing.split("\0")[:-1]
            changes = [(STATUS[status], path) for status, path in zip(fields[::2], fields[1::2])]
        try:
            version = json.loads(git("show", f"{commit}:{prefix}/.cursor-plugin/plugin.json")).get("version")
        except (subprocess.CalledProcessError, ValueError, AttributeError):
            version = None
    return commit, version if isinstance(version, str) else None, changes


def quoted(text):
    return text if text.isprintable() and " " not in text else json.dumps(text)


def render_text(report, prefix):
    if report.up_to_date:
        return f"up to date ({report.pinned[:12]})\n"
    version = f" ({quoted(report.version)})" if report.version else ""
    lines = [f"upstream {report.ref}: {report.pinned[:12]} -> {report.commit[:12]}{version}"]
    for entry in report.changes:
        handling = HANDLING_TEXT[entry.handling].format(t3_path=quoted(entry.t3_path or ""))
        lines.append(f"{entry.change:<7}  {quoted(entry.path)}  {handling}")
    if not report.changes:
        lines.append(f"no changes under {prefix}/")
    return "\n".join(lines) + "\n"


def render_json(report):
    fields = asdict(report)
    changes = fields.pop("changes")
    return json.dumps({**fields, "up_to_date": report.up_to_date, "changes": changes}, indent=2) + "\n"


def check(args, meta):
    repository = args.repository or meta["repository"]
    try:
        commit, version, changes = upstream_changes(repository, args.ref, meta["commit"], meta["path"])
    except subprocess.CalledProcessError as error:
        print(error.stderr.strip() or error, file=sys.stderr)
        return 1
    except OSError as error:
        print(error, file=sys.stderr)
        return 1
    layers = load_layers()
    entries = (Entry(path, change, *classify(path, meta["path"], layers)) for change, path in changes)
    report = Report(
        repository, args.ref, meta["commit"], commit, version, tuple(sorted(entries, key=lambda entry: entry.path))
    )
    sys.stdout.write(render_json(report) if args.json else render_text(report, meta["path"]))
    return 0


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ref", default="main", help="upstream branch, tag, or commit")
    parser.add_argument("--check", action="store_true", help="report what upstream changed since the pinned commit and sync nothing")
    parser.add_argument("--json", action="store_true", help="with --check, print the report as one JSON object")
    parser.add_argument("--repository", help="with --check, the upstream to read (default: the repository in upstream.json)")
    args = parser.parse_args()
    if not args.check and (args.json or args.repository):
        parser.error("--json and --repository need --check")
    meta = json.loads(UPSTREAM.read_text())
    if args.check:
        return check(args, meta)
    with tempfile.TemporaryDirectory(prefix="pstack-upstream-") as temporary:
        checkout = Path(temporary) / "plugins"
        run("git", "clone", "--filter=blob:none", "--no-checkout", meta["repository"], str(checkout))
        run("git", "sparse-checkout", "set", meta["path"], cwd=checkout)
        run("git", "checkout", args.ref, cwd=checkout)
        commit = run("git", "rev-parse", "HEAD", cwd=checkout)
        source = checkout / meta["path"]
        plugin = json.loads((source / ".cursor-plugin/plugin.json").read_text())
        sys.path.insert(0, str(ROOT / "scripts"))
        from build import replace_tree

        shutil.rmtree(source / ".git", ignore_errors=True)
        replace_tree(source, ROOT / "vendor/pstack")
    previous = meta["commit"]
    meta.update(commit=commit, version=plugin.get("version", meta.get("version")))
    UPSTREAM.write_text(json.dumps(meta, indent=2) + "\n")
    print(f"vendor/pstack: {previous[:12]} -> {commit[:12]} ({meta['version']})")
    result = subprocess.run([sys.executable, str(ROOT / "scripts/build.py")], capture_output=True, text=True)
    print(result.stdout + result.stderr)
    return result.returncode


if __name__ == "__main__":
    sys.exit(main())
