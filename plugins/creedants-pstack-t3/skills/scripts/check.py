#!/usr/bin/env python3
"""Lint a generated skills tree for Cursor-only leftovers and broken structure."""

import importlib.util
import re
import sys

try:
    import yaml
except ImportError:  # the build still runs; frontmatter gets the shallow check only
    yaml = None
from pathlib import Path

# Each pattern names a Cursor-only mechanism and its T3 replacement.
FORBIDDEN = [
    (r"subagent_type", "Cursor Task schema; use delegate_task with role and target"),
    (r"environment: ?\"(?:cloud|local)\"", "Cursor cloud agents; T3 children run locally"),
    (r"cloud_base_branch", "Cursor cloud agents; name the branch in the brief"),
    (r"run_in_background", "Cursor Task flag; use delegate_task mode async"),
    (r"`Task`|Task tool|Task call|Task subagent|Task `model`", "Cursor Task tool; use delegate_task"),
    (r"pstack-models\.mdc|\.cursor/rules", "Cursor rule file; use roles.py and roles.json"),
    (r"(?<![\w/])/loop\b", "Cursor /loop; use schedule_task"),
    (r"AskQuestion", "Cursor question tool; use the host's question tool"),
    (r"cursor-team-kit|Cursor's built-in", "Cursor plugin dependency"),
    (r"agent-transcripts", "Cursor transcript store; use t3_thread_search and t3_thread_read"),
    (r"inherit-parent", "Cursor alias; use inherit"),
    (r"\b(?:claude-opus-5-5-max|claude-opus-5-5-xhigh|claude-fable-5-1-thinking-\w+|gpt-5\.6-sol-max|grok-4\.7-xhigh-fast|claude-opus-5-thinking-\w+)\b", "hard-coded Cursor model slug; resolve a role"),
    (r"cursor\.com/agents|cloud agent", "Cursor cloud agents; T3 child tasks or threads"),
]
FRONTMATTER_REQUIRED = ("name", "description")
# Generated files that teach a PR wait must name T3's watch tools. Absent files are not checked.
REQUIRED_TOOLS = {
    "pstack-runtime/SKILL.md": ("watch_pull_request", "unwatch_pull_request"),
    "landing/SKILL.md": ("watch_pull_request", "unwatch_pull_request"),
    "brigade/SKILL.md": ("watch_pull_request", "unwatch_pull_request"),
    "poteto-mode/playbooks/babysit.md": ("watch_pull_request",),
    "poteto-mode/playbooks/shipping.md": ("watch_pull_request",),
    "poteto-mode/playbooks/autonomous-run.md": ("watch_pull_request",),
    "poteto-mode/playbooks/orchestrate.md": ("watch_pull_request",),
    "poteto-mode/playbooks/autopilot-full.md": ("watch_pull_request",),
    "poteto-mode/playbooks/autopilot-stack.md": ("watch_pull_request",),
    "setup-pstack/SKILL.md": ("watch_pull_request", "0.0.46-nightly.20261005.2702"),
}
LINK = re.compile(r"\]\(((?!https?:|mailto:|#)[^)\s]+)\)")
# A T3 thread link is `t3-thread://v1/<threadId>`. It names no file.
THREAD_LINK = re.compile(r"t3-thread://v1/[^)\s]")
# Bash ends a <<'JSON' body only on a line that is JSON and nothing else.
CATALOG_HEREDOC_OPEN = "<<'JSON'"
CATALOG_HEREDOC_CLOSER = "JSON"

ROLES_PY = Path(__file__).resolve().parents[1] / "t3/scripts/roles.py"
LIGHT_HEADER_CELLS = frozenset({"light", "light mode", "light behavior", "in light mode"})
LIGHT_MODE_NAME = re.compile(r"(?i:\blight mode\b)|Mode: light")
TABLE_SEPARATOR = re.compile(r"\|?\s*:?-{3,}:?\s*(\|\s*:?-{3,}:?\s*)*\|?")


def light_waiver_cells():
    spec = importlib.util.spec_from_file_location("pstack_roles", ROLES_PY)
    roles = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(roles)
    return tuple(sorted({", ".join(steps) for steps in roles.LIGHT_WAIVERS.values() if len(steps) >= 2}))


def _header_cells(line):
    return [cell.replace("`", "").replace("*", "").strip().casefold() for cell in line.strip().strip("|").split("|")]


def light_table_findings(rel_s, text, cells):
    findings = []
    lines = text.splitlines()
    for number, line in enumerate(lines, 1):
        restated = any(cell in line for cell in cells)
        if line.lstrip().startswith("|") and number < len(lines) and TABLE_SEPARATOR.fullmatch(lines[number].strip()):
            header = _header_cells(line)
            restated = restated or bool(LIGHT_HEADER_CELLS.intersection(header)) or (
                "playbook" in header and any(cell == "first" or cell.startswith("fix") for cell in header)
            )
        if restated:
            findings.append(f"{rel_s}:{number}: light table restated. Link pstack-runtime/SKILL.md#modes instead of pasting it: {line.strip()[:120]}")
        elif LIGHT_MODE_NAME.search(line) and "pstack-runtime/SKILL.md#" not in line:
            findings.append(f"{rel_s}:{number}: names light mode without a link to the runtime's Modes section. Link pstack-runtime/SKILL.md#modes: {line.strip()[:120]}")
    return findings


def catalog_heredoc_findings(rel, text):
    findings = []
    in_body = False
    for number, line in enumerate(text.splitlines(), 1):
        if not in_body:
            if CATALOG_HEREDOC_OPEN in line:
                in_body = True
            continue
        if line == CATALOG_HEREDOC_CLOSER:
            in_body = False
            continue
        if line.strip() != CATALOG_HEREDOC_CLOSER:
            continue
        if line.lstrip() != line:
            findings.append(f"{rel}:{number}: catalog heredoc closer JSON is indented. Put JSON at column 0")
        else:
            findings.append(f"{rel}:{number}: catalog heredoc closer JSON has trailing whitespace. The closer is JSON with nothing after it")
    return findings


def check_tree(root):
    root = Path(root)
    findings = []
    cells = light_waiver_cells()
    for skill_md in sorted(root.glob("*/SKILL.md")):
        skill = skill_md.parent.name
        text = skill_md.read_text()
        match = re.match(r"---\n(.*?)\n---\n", text, re.S)
        if not match:
            findings.append(f"{skill}/SKILL.md: missing frontmatter")
            continue
        try:
            keys = yaml.safe_load(match.group(1)) if yaml else dict(
                (k.strip(), v.strip().strip('"')) for k, v in (line.split(":", 1) for line in match.group(1).splitlines() if ":" in line and not line.startswith(" ")))
        except Exception as error:
            findings.append(f"{skill}/SKILL.md: frontmatter is not valid YAML: {str(error).splitlines()[0]}")
            continue
        if not isinstance(keys, dict):
            findings.append(f"{skill}/SKILL.md: frontmatter is not a mapping")
            continue
        for key in FRONTMATTER_REQUIRED:
            if not isinstance(keys.get(key), str) or not keys[key].strip():
                findings.append(f"{skill}/SKILL.md: frontmatter lacks a string {key}")
        if keys.get("name") != skill:
            findings.append(f"{skill}/SKILL.md: name must equal the directory name")
        if len(str(keys.get("description", ""))) > 1024:
            findings.append(f"{skill}/SKILL.md: description over 1024 characters")
    for file in sorted(root.rglob("*")):
        if not file.is_file() or file.suffix not in (".md", ".ts", ".mjs", ".sh", ".py", ".json", ".yaml", ".tsv"):
            continue
        rel = file.relative_to(root)
        text = file.read_text()
        rel_s = str(rel)
        for tool in REQUIRED_TOOLS.get(rel_s, ()):
            if tool not in text:
                findings.append(f"{rel_s}: missing {tool}")
        # The runtime's vocabulary table names each Cursor term it replaces.
        patterns = [] if rel_s == "pstack-runtime/SKILL.md" else FORBIDDEN
        for number, line in enumerate(text.splitlines(), 1):
            for pattern, why in patterns:
                if re.search(pattern, line):
                    findings.append(f"{rel}:{number}: {why}: {line.strip()[:120]}")
        findings.extend(catalog_heredoc_findings(rel, text))
        if file.suffix == ".md":
            if rel_s != "pstack-runtime/SKILL.md":
                findings.extend(light_table_findings(rel_s, text, cells))
            for target in LINK.findall(text):
                if THREAD_LINK.match(target):
                    continue
                path = target.split("#", 1)[0]
                # Template placeholders such as (url) are not paths.
                if "/" not in path and "." not in path:
                    continue
                if path and not (file.parent / path).resolve().exists():
                    findings.append(f"{rel}: broken link {target}")
    return findings


if __name__ == "__main__":
    tree = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(__file__).resolve().parents[1] / "skills"
    problems = check_tree(tree)
    print("\n".join(problems) or "ok")
    sys.exit(1 if problems else 0)
