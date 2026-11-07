#!/usr/bin/env python3
"""Generate skills/ from vendor/pstack plus the T3 layer in t3/.

vendor/pstack      upstream pstack, byte-identical to upstream.json's commit
t3/overrides/      whole-file replacements, keyed by skill-relative path
t3/added/          files with no upstream counterpart
t3/removed.txt     upstream paths that pstack-t3 does not ship
t3/overrides.lock.json  sha256 of each upstream file an override replaces

An override whose upstream file changed since it was written fails the build
until it is re-ported and the lock refreshed with --update-lock.
"""

import argparse
import hashlib
import json
import re
import shutil
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
VENDOR = ROOT / "vendor/pstack"
T3 = ROOT / "t3"
LOCK = T3 / "overrides.lock.json"
DROP_KEYS = ("disable-model-invocation", "mode", "icon", "color", "reminder", "paths")
RUNTIME_POINTER = (
    "Read [the pstack-t3 runtime](../pstack-runtime/SKILL.md) before spawning workers, "
    "choosing models, scheduling, or isolating work. It maps those steps onto T3's orchestrator tools.\n\n"
)
NO_POINTER = re.compile(r"^(principle-|pstack-runtime$|bro$|unslop$|technical-writing$|typescript-best-practices$|tdd$)")


def sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def relative_files(base):
    return sorted(p.relative_to(base) for p in base.rglob("*") if p.is_file() and "__pycache__" not in p.parts)


def removed_paths():
    file = T3 / "removed.txt"
    if not file.exists():
        return set()
    return {Path(line.strip()) for line in file.read_text().splitlines() if line.strip() and not line.startswith("#")}


def normalize_skill(text, skill):
    match = re.match(r"---\n(.*?)\n---\n", text, re.S)
    if not match:
        raise ValueError(f"{skill}/SKILL.md: missing frontmatter")
    lines = []
    for line in match.group(1).splitlines():
        key = line.split(":", 1)[0].strip()
        if key in DROP_KEYS:
            continue
        if key == "name":
            line = f"name: {skill}"
        lines.append(line)
    body = text[match.end():].lstrip("\n")
    if not NO_POINTER.match(skill) and RUNTIME_POINTER.strip() not in body:
        heading, newline, rest = body.partition("\n")
        body = heading + newline + "\n" + RUNTIME_POINTER + rest.lstrip("\n") if heading.startswith("# ") else RUNTIME_POINTER + body
    return "---\n" + "\n".join(lines) + "\n---\n\n" + body


def check_lock(update):
    overrides = T3 / "overrides"
    current = {}
    for rel in relative_files(overrides):
        upstream = VENDOR / "skills" / rel
        current[str(rel)] = sha256(upstream) if upstream.exists() else None
    if update:
        LOCK.write_text(json.dumps(current, indent=2, sort_keys=True) + "\n")
        return []
    locked = json.loads(LOCK.read_text()) if LOCK.exists() else {}
    problems = []
    for rel, digest in current.items():
        if rel not in locked:
            problems.append(f"{rel}: override not in overrides.lock.json (run build.py --update-lock after reviewing)")
        elif locked[rel] != digest:
            problems.append(f"{rel}: upstream changed since this override was written; re-port it, then --update-lock")
    for rel in locked:
        if rel not in current:
            problems.append(f"{rel}: locked but no override exists (run --update-lock)")
    return problems


def copy_file(source, target):
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(source, target)
    shutil.copymode(source, target)


def render(destination):
    removed = removed_paths()
    skills = VENDOR / "skills"
    for rel in relative_files(skills):
        if rel in removed or any(parent in removed for parent in rel.parents):
            continue
        copy_file(skills / rel, destination / rel)
    for layer in ("overrides", "added"):
        base = T3 / layer
        for rel in relative_files(base):
            copy_file(base / rel, destination / rel)
    runtime = destination / "pstack-runtime"
    copy_file(T3 / "runtime.md", runtime / "SKILL.md")
    copy_file(T3 / "scripts/roles.py", runtime / "scripts/roles.py")
    for persona in sorted((T3 / "agents").glob("*.md")):
        copy_file(persona, runtime / "agents" / persona.name)
    copy_file(T3 / "setup.md", destination / "setup-pstack" / "SKILL.md")
    for skill_md in sorted(destination.glob("*/SKILL.md")):
        skill = skill_md.parent.name
        skill_md.write_text(normalize_skill(skill_md.read_text(), skill))


def build(destination, update_lock=False, skip_lock=False):
    problems = [] if skip_lock else check_lock(update_lock)
    if problems:
        raise SystemExit("override drift:\n  " + "\n  ".join(problems))
    with tempfile.TemporaryDirectory(prefix="pstack-t3-build-") as temporary:
        staged = Path(temporary) / "skills"
        render(staged)
        sys.path.insert(0, str(ROOT / "scripts"))
        from check import check_tree

        findings = check_tree(staged)
        if findings:
            raise SystemExit("check failed:\n  " + "\n  ".join(findings))
        replace_tree(staged, destination)
    if destination == ROOT / "skills":
        from catalog import write
        import cli_reference

        write(destination)
        cli_reference.write()
    return destination


def replace_tree(source, destination):
    """Swap destination for a full copy of source, keeping the old tree until the copy exists."""
    incoming = destination.with_name(destination.name + ".incoming")
    outgoing = destination.with_name(destination.name + ".outgoing")
    if outgoing.exists() and not destination.exists():
        # A previous swap died between renames; its old tree is the only good copy.
        outgoing.rename(destination)
    for leftover in (incoming, outgoing):
        if leftover.exists():
            shutil.rmtree(leftover)
    shutil.copytree(source, incoming)
    if destination.exists():
        destination.rename(outgoing)
    incoming.rename(destination)
    if outgoing.exists():
        shutil.rmtree(outgoing)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--update-lock", action="store_true", help="accept current upstream digests for every override")
    parser.add_argument("--skip-lock", action="store_true", help="check a work-in-progress port without the drift lock")
    parser.add_argument("--out", type=Path, default=ROOT / "skills")
    args = parser.parse_args()
    print(f"built {build(args.out, args.update_lock, args.skip_lock)}")
