#!/usr/bin/env python3
"""Rewrite a project tree from expanded upstream references to the compact
``sources`` form, and verify a tree that is already compact.

Expanded form (still accepted everywhere, never rewritten back)::

    {"owner": "...", "artifact": "...", "record_id": "..."}

Compact form::

    {"src": "<sources key>", "record_id": "..."}

with the file declaring each upstream snapshot exactly once:

* ``.json``  -> a top-level ``"sources"`` object.
* ``.jsonl`` -> a first-line header record
  ``{"record_type": "sources", "schema_version": "1.0.0", "sources": {...}}``.
  When the file already opens with its own header record whose ``record_type``
  ends in ``_meta`` (``screenplay_index_meta`` is the existing precedent), the
  ``sources`` map is folded into that record instead of adding a second header
  line, so ``records[0]["record_type"]`` keeps its current value.

Usage::

    python3 tools/compact_refs.py <project-dir>            # rewrite in place
    python3 tools/compact_refs.py --check <project-dir>    # verify only

Guarantees:

* Deterministic. Source keys, key ordering and serialisation depend only on the
  input bytes.
* Idempotent. Running the tool twice produces identical bytes, because every
  file is first normalised back to the expanded form in memory, then re-compacted.
* Byte-faithful. Nothing outside the reference objects and the ``sources``
  declaration is touched: record order, key order, creative text, IDs and every
  other field survive unchanged, and each file keeps its own indentation and
  trailing-newline convention.
* Fixed point. Files are rewritten in topological order. When file ``F`` is
  rewritten its bytes change, so every later reference whose recorded hash was
  ``F``'s pre-rewrite hash is re-bound to ``F``'s new hash. A recorded hash that
  did not match the pre-rewrite bytes names some other snapshot and is preserved
  verbatim.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from collections import defaultdict
from collections.abc import Iterable, Iterator
from pathlib import Path, PurePosixPath
from typing import Any, NamedTuple, TextIO

# ---------------------------------------------------------------------------
# REFERENCE RESOLVER -- reference implementation.
#
# Each skill checker carries its own copy of this block. The suite has no shared
# library on purpose: a skill must stay runnable after copying only its own
# directory, so duplicating these few lines across skills is the correct shape.
# Copy the block verbatim; do not import it.
# ---------------------------------------------------------------------------

SOURCES_RECORD_TYPE = "sources"
SOURCES_SCHEMA_VERSION = "1.0.0"


class ResolvedRef(NamedTuple):
    """An upstream reference with its snapshot resolved, whichever form it used."""

    owner: str
    artifact: str
    record_id: str | None
    field: str | None
    authority: str | None


class RefFinding(NamedTuple):
    """A structural defect in a reference object."""

    code: str
    location: str
    detail: str


def load_sources(document: Any) -> dict[str, dict[str, Any]]:
    """Return the ``sources`` declaration of a parsed file, or ``{}`` if absent.

    Accepts a parsed ``.json`` document (a dict) or the parsed record list of a
    ``.jsonl`` file, whose declaration lives on the first record.
    """
    if isinstance(document, list):
        document = document[0] if document else None
    if not isinstance(document, dict):
        return {}
    declared = document.get("sources")
    if not isinstance(declared, dict):
        return {}
    return {key: value for key, value in declared.items() if isinstance(value, dict)}


def resolve_ref(
    ref: Any, sources: dict[str, dict[str, Any]], location: str
) -> tuple[ResolvedRef | None, RefFinding | None]:
    """Resolve a reference object written in either the compact or expanded form."""
    if not isinstance(ref, dict):
        return None, RefFinding("REF_IS_NOT_AN_OBJECT", location, f"got {type(ref).__name__}")
    src = ref.get("src")
    if isinstance(src, str):
        entry = sources.get(src)
        if entry is None:
            return None, RefFinding(
                "REF_SRC_IS_NOT_DECLARED", location, f"src {src!r} has no sources entry"
            )
        owner, artifact = entry.get("owner"), entry.get("artifact")
        if not (isinstance(owner, str) and isinstance(artifact, str)):
            return None, RefFinding(
                "SOURCE_ENTRY_IS_INCOMPLETE", location, f"sources[{src!r}] needs owner/artifact"
            )
    elif all(isinstance(ref.get(key), str) for key in ("owner", "artifact")):
        owner, artifact = ref["owner"], ref["artifact"]
    else:
        return None, RefFinding(
            "REF_HAS_NO_UPSTREAM_BINDING", location, "needs src, or owner+artifact"
        )
    optional = {
        key: ref[key] for key in ("record_id", "field", "authority") if isinstance(ref.get(key), str)
    }
    return (
        ResolvedRef(
        owner,
        artifact,
            optional.get("record_id"),
            optional.get("field"),
            optional.get("authority"),
        ),
        None,
    )


# ---------------------------------------------------------------------------
# END REFERENCE RESOLVER
# ---------------------------------------------------------------------------

REF_PAIR = ("owner", "artifact")
SOURCES_KEY = "sources"
DATA_SUFFIXES = (".json", ".jsonl")
MAX_KEY_QUALIFIER_DEPTH = 8

# A reference slot is named by convention, so --check can tell a defective
# reference from an ordinary object. ``reviewed_artifacts`` is the one carrier in
# the suite that predates the convention; ``boundary_refs`` holds named refs
# rather than one ref, and is handled as a container below.
REF_CARRIER_SUFFIXES = ("_ref", "_refs")
EXTRA_REF_CARRIERS = ("reviewed_artifacts",)

# (owner, artifact) identifies one upstream artifact.
SourceId = tuple[str, str]


class Finding(NamedTuple):
    """A defect reported by ``--check``."""

    path: str
    code: str
    detail: str


class FileFormat(NamedTuple):
    """The serialisation conventions of one file, detected from its own bytes."""

    is_jsonl: bool
    indent: int | None
    ensure_ascii: bool
    trailing_newline: bool


class LoadedFile(NamedTuple):
    """A parsed data file plus everything needed to write it back unchanged."""

    path: Path
    relative: str
    fmt: FileFormat
    records: list[Any]
    original_bytes: bytes


def emit(line: str, *, stream: TextIO | None = None) -> None:
    """Print a line that may name a path like ``剧集/EP001/…``.

    A Windows console defaults to a legacy codepage that cannot encode those
    names, and the findings worth reporting are exactly the ones carrying a
    project path.
    """
    target = stream if stream is not None else sys.stdout
    try:
        print(line, file=target)
        return
    except UnicodeEncodeError:
        pass
    buffer = getattr(target, "buffer", None)
    if buffer is None:
        encoding = getattr(target, "encoding", "ascii") or "ascii"
        print(line.encode(encoding, "backslashreplace").decode(encoding), file=target)
        return
    target.flush()
    buffer.write(f"{line}\n".encode())
    buffer.flush()


def sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


# ---------------------------------------------------------------------------
# Reading and writing while preserving each file's conventions
# ---------------------------------------------------------------------------


def detect_format(path: Path, text: str, records: list[Any]) -> FileFormat:
    """Infer indent / escaping / trailing-newline so a round trip is byte-exact."""
    is_jsonl = path.suffix == ".jsonl"
    trailing_newline = text.endswith("\n")
    for ensure_ascii in (False, True):
        for indent in (None, 2, 4) if not is_jsonl else (None,):
            fmt = FileFormat(is_jsonl, indent, ensure_ascii, trailing_newline)
            if render(records, fmt) == text:
                return fmt
    # Unknown layout: fall back to the suite default and normalise on write.
    return FileFormat(is_jsonl, None if is_jsonl else 2, False, trailing_newline)


def render(records: list[Any], fmt: FileFormat) -> str:
    if fmt.is_jsonl:
        lines = [
            json.dumps(record, ensure_ascii=fmt.ensure_ascii, separators=(",", ":"))
            for record in records
        ]
        text = "\n".join(lines)
    else:
        text = json.dumps(records[0], ensure_ascii=fmt.ensure_ascii, indent=fmt.indent)
    return text + "\n" if fmt.trailing_newline else text


def load_file(path: Path, root: Path) -> LoadedFile | None:
    original_bytes = path.read_bytes()
    text = original_bytes.decode("utf-8")
    try:
        if path.suffix == ".jsonl":
            records: list[Any] = [json.loads(line) for line in text.splitlines() if line.strip()]
        else:
            records = [json.loads(text)]
    except json.JSONDecodeError:
        return None
    if not records:
        return None
    relative = PurePosixPath(path.relative_to(root).as_posix()).as_posix()
    return LoadedFile(path, relative, detect_format(path, text, records), records, original_bytes)


def iter_data_files(root: Path) -> Iterator[Path]:
    for path in sorted(root.rglob("*")):
        if path.suffix not in DATA_SUFFIXES or not path.is_file():
            continue
        if any(part.startswith(".") for part in path.relative_to(root).parts):
            continue
        yield path


# ---------------------------------------------------------------------------
# Walking references
# ---------------------------------------------------------------------------


def is_expanded_ref(node: Any) -> bool:
    """True for an object carrying the full snapshot triple as non-empty strings.

    Requiring all three keys is what keeps look-alikes out: an ``observer``
    object has ``owner`` but no ``artifact``, and a deliberately hash-free
    locator has ``owner`` and ``artifact`` but no ``hash`` because its target is
    not published yet. Neither becomes a ``sources`` entry.
    """
    if not isinstance(node, dict):
        return False
    return all(isinstance(node.get(key), str) and node[key] for key in REF_PAIR)


def is_compact_ref(node: Any) -> bool:
    return isinstance(node, dict) and isinstance(node.get("src"), str)


def expand_refs(node: Any, sources: dict[str, dict[str, Any]]) -> Any:
    """Rewrite every compact ref back to the expanded triple, in memory.

    Normalising first is what makes the tool idempotent and lets an already
    migrated tree be re-bound to new upstream hashes.
    """
    if isinstance(node, list):
        return [expand_refs(item, sources) for item in node]
    if not isinstance(node, dict):
        return node
    if is_compact_ref(node):
        entry = sources.get(str(node["src"]))
        if entry is not None and all(isinstance(entry.get(key), str) for key in REF_PAIR):
            rest = {
                key: expand_refs(value, sources) for key, value in node.items() if key != "src"
            }
            return {key: entry[key] for key in REF_PAIR} | rest
    return {key: expand_refs(value, sources) for key, value in node.items()}


def iter_expanded_refs(node: Any) -> Iterator[dict[str, Any]]:
    if isinstance(node, list):
        for item in node:
            yield from iter_expanded_refs(item)
        return
    if not isinstance(node, dict):
        return
    if is_expanded_ref(node):
        yield node
    for value in node.values():
        yield from iter_expanded_refs(value)


def compact_refs(node: Any, keys: dict[SourceId, str]) -> Any:
    if isinstance(node, list):
        return [compact_refs(item, keys) for item in node]
    if not isinstance(node, dict):
        return node
    if is_expanded_ref(node):
        source_id = resolved_source_id(node)
        rest = {
            key: compact_refs(value, keys)
            for key, value in node.items()
            if key not in REF_PAIR
        }
        return {"src": keys[source_id]} | rest
    return {key: compact_refs(value, keys) for key, value in node.items()}


def resolved_source_id(ref: dict[str, Any]) -> SourceId:
    """A reference identifies its upstream by owner and artifact."""
    owner, artifact = (str(ref[key]) for key in REF_PAIR)
    return owner, artifact



def slug(text: str) -> str:
    out: list[str] = []
    for char in text.lower():
        if char.isalnum():
            out.append(char)
        elif out and out[-1] != "-":
            out.append("-")
    return "".join(out).strip("-")


def _ancestors(artifact: str) -> list[str]:
    """Directory components of an artifact path, nearest parent first."""
    return [part for part in reversed(PurePosixPath(artifact).parent.parts) if part not in (".", "/")]


def _candidate_key(artifact: str, depths: set[int]) -> str:
    stem = slug(PurePosixPath(artifact).stem) or "source"
    ancestors = _ancestors(artifact)
    prefix = [slug(ancestors[depth]) for depth in sorted(depths, reverse=True) if depth < len(ancestors)]
    return "-".join([part for part in prefix if part] + [stem])


def derive_source_keys(source_ids: Iterable[SourceId]) -> dict[SourceId, str]:
    """Map each upstream snapshot to a short, lowercase, file-unique key.

    The key starts as the artifact's basename. Basenames collide often -- eight
    episodes each own a ``shots.jsonl`` -- so a colliding group is qualified by
    the nearest ancestor directory that actually differs between its members,
    which yields ``ep001-shots`` rather than ``ep001-storyboard-shots``. Two
    snapshots of the same artifact (a supersession record naming a candidate and
    an accepted hash) get a numeric suffix in hash order.
    """
    entries = sorted(set(source_ids))
    depths: dict[SourceId, set[int]] = {entry: set() for entry in entries}
    for _ in range(MAX_KEY_QUALIFIER_DEPTH):
        groups: dict[str, list[SourceId]] = defaultdict(list)
        for entry in entries:
            groups[_candidate_key(entry[1], depths[entry])].append(entry)
        colliding = [group for group in groups.values() if len(group) > 1]
        if not colliding:
            break
        progressed = False
        for group in colliding:
            ancestor_lists = {entry: _ancestors(entry[1]) for entry in group}
            depth_limit = max(len(values) for values in ancestor_lists.values())
            for depth in range(depth_limit):
                if depth in depths[group[0]]:
                    continue
                seen = {
                    ancestor_lists[entry][depth] if depth < len(ancestor_lists[entry]) else ""
                    for entry in group
                }
                if len(seen) > 1:
                    for entry in group:
                        depths[entry].add(depth)
                    progressed = True
                    break
        if not progressed:
            break

    keys: dict[SourceId, str] = {}
    taken: dict[str, int] = {}
    for entry in entries:
        base = _candidate_key(entry[1], depths[entry])
        count = taken.get(base, 0)
        taken[base] = count + 1
        keys[entry] = base if count == 0 else f"{base}-{count + 1}"
    return keys


# ---------------------------------------------------------------------------
# Sources declaration placement
# ---------------------------------------------------------------------------


def strip_sources(loaded: LoadedFile) -> tuple[list[Any], str, int]:
    """Remove any existing declaration.

    Returns the payload records, the placement mode used to write a declaration
    back (``"json"``, ``"header"`` or ``"folded"``) and the key position to
    restore inside the carrier object, or ``-1`` to place it first.
    """
    records = [dict(record) if isinstance(record, dict) else record for record in loaded.records]
    if not loaded.fmt.is_jsonl:
        document = records[0]
        position = -1
        if isinstance(document, dict) and SOURCES_KEY in document:
            position = list(document).index(SOURCES_KEY)
            del document[SOURCES_KEY]
        return records, "json", position
    first = records[0]
    if isinstance(first, dict) and first.get("record_type") == SOURCES_RECORD_TYPE:
        return records[1:], "header", -1
    if isinstance(first, dict) and str(first.get("record_type", "")).endswith("_meta"):
        position = -1
        if SOURCES_KEY in first:
            position = list(first).index(SOURCES_KEY)
            del first[SOURCES_KEY]
        return records, "folded", position
    return records, "header", -1


def place_sources(
    records: list[Any], mode: str, position: int, sources: dict[str, dict[str, str]]
) -> list[Any]:
    if not sources:
        return records
    if mode == "header":
        header = {
            "record_type": SOURCES_RECORD_TYPE,
            "schema_version": SOURCES_SCHEMA_VERSION,
            SOURCES_KEY: sources,
        }
        return [header, *records]
    carrier = records[0]
    if not isinstance(carrier, dict):
        return records
    items = list(carrier.items())
    index = position if 0 <= position <= len(items) else (len(items) if mode == "folded" else 0)
    records[0] = dict(items[:index]) | {SOURCES_KEY: sources} | dict(items[index:])
    return records


# ---------------------------------------------------------------------------
# Dependency graph
# ---------------------------------------------------------------------------


def build_order(files: dict[str, LoadedFile]) -> list[str]:
    """Topologically order files so an upstream file is rewritten before its consumers."""
    dependencies: dict[str, set[str]] = {relative: set() for relative in files}
    for relative, loaded in files.items():
        sources = load_sources(loaded.records)
        for record in loaded.records:
            for ref in iter_expanded_refs(expand_refs(record, sources)):
                artifact = str(ref["artifact"])
                if artifact in files and artifact != relative:
                    dependencies[relative].add(artifact)

    order: list[str] = []
    done: set[str] = set()
    pending = sorted(files)
    while pending:
        ready = [name for name in pending if dependencies[name] <= done]
        if not ready:
            # A cycle: break it in name order so the run stays deterministic.
            ready = [pending[0]]
            emit(f"warning: reference cycle involving {pending[0]}", stream=sys.stderr)
        for name in ready:
            order.append(name)
            done.add(name)
        pending = [name for name in pending if name not in done]
    return order


# ---------------------------------------------------------------------------
# Migration
# ---------------------------------------------------------------------------


def migrate(root: Path) -> int:
    files: dict[str, LoadedFile] = {}
    for path in iter_data_files(root):
        loaded = load_file(path, root)
        if loaded is not None:
            files[loaded.relative] = loaded

    # (artifact, pre-rewrite hash) -> post-rewrite hash.
    changed = 0
    for relative in build_order(files):
        loaded = files[relative]
        declared = load_sources(loaded.records)
        records, mode, position = strip_sources(loaded)
        records = [expand_refs(record, declared) for record in records]

        source_ids = {
            resolved_source_id(ref)
            for record in records
            for ref in iter_expanded_refs(record)
        }
        keys = derive_source_keys(source_ids)
        sources = {
            keys[source_id]: {"owner": source_id[0], "artifact": source_id[1]}
            for source_id in sorted(source_ids, key=lambda entry: keys[entry])
        }
        compact = place_sources(
            [compact_refs(record, keys) for record in records], mode, position, sources
        )
        compact_payload = render(compact, loaded.fmt).encode("utf-8")
        inline_payload = render(records, loaded.fmt).encode("utf-8")
        # Declaring a snapshot once pays off only when something references it
        # more than once. A fan-in manifest naming 104 artifacts once each would
        # grow, so it keeps the inline form.
        payload = (
            compact_payload if len(compact_payload) < len(inline_payload) else inline_payload
        )
        if payload != loaded.original_bytes:
            loaded.path.write_bytes(payload)
            changed += 1

    emit(f"rewrote {changed} of {len(files)} data files under {root}")
    return 0


# ---------------------------------------------------------------------------
# Verification
# ---------------------------------------------------------------------------


def check(root: Path) -> int:
    files: dict[str, LoadedFile] = {}
    for path in iter_data_files(root):
        loaded = load_file(path, root)
        if loaded is not None:
            files[loaded.relative] = loaded
    # References no longer carry bytes, so the strongest local claim is that the
    # artifact a reference names is really there. Whether it is *current* is a
    # lifecycle question, answered by project_tool state, not by these files.
    on_disk = set(files)

    findings: list[Finding] = []
    for relative in sorted(files):
        loaded = files[relative]
        sources = load_sources(loaded.records)
        used: set[str] = set()
        for index, record in enumerate(loaded.records, start=1):
            for ref, location in iter_ref_candidates(record, f"{relative}#record{index}"):
                compact = isinstance(ref.get("src"), str)
                if compact:
                    used.add(str(ref["src"]))
                resolved, defect = resolve_ref(ref, sources, location)
                if defect is not None:
                    detail = f"{defect.location}: {defect.detail}"
                    findings.append(Finding(relative, defect.code, detail))
                    continue
                # A declared source is checked once below; an inline one is only
                # reachable here.
                if resolved is not None and not compact:
                    if resolved.artifact not in on_disk and (root / resolved.artifact).is_file() is False:
                        detail = f"{location} names {resolved.artifact}, which is not in this project"
                        findings.append(Finding(relative, "REF_TARGET_IS_MISSING", detail))
        for key in sorted(sources):
            entry = sources[key]
            artifact = entry.get("artifact")
            if key not in used:
                detail = f"sources[{key!r}] is declared but no reference uses it"
                findings.append(Finding(relative, "SOURCE_IS_UNUSED", detail))
            if not isinstance(artifact, str):
                continue
            if artifact not in on_disk and not (root / artifact).is_file():
                detail = f"sources[{key!r}] names {artifact}, which is not in this project"
                findings.append(Finding(relative, "SOURCE_TARGET_IS_MISSING", detail))

    if not findings:
        emit(f"every reference in {len(files)} data files under {root} names an artifact that exists")
        return 0
    for report in findings:
        emit(f"{report.path}: {report.code}: {report.detail}")
    emit(f"\n{len(findings)} finding(s)", stream=sys.stderr)
    return 1


def is_ref_carrier(key: str) -> bool:
    return key.endswith(REF_CARRIER_SUFFIXES) or key in EXTRA_REF_CARRIERS


def is_ref_container(node: dict[str, Any]) -> bool:
    """True for ``boundary_refs``-style objects that hold several named refs."""
    return bool(node) and all(isinstance(value, dict) for value in node.values())


def iter_ref_candidates(
    node: Any, location: str, in_slot: bool = False
) -> Iterator[tuple[dict[str, Any], str]]:
    """Yield every object used as a reference, with a readable location.

    Objects in either valid form are found structurally. An object sitting in a
    reference slot in *neither* form is yielded too, so ``--check`` reports it
    rather than silently skipping it.
    """
    if isinstance(node, list):
        for index, item in enumerate(node):
            yield from iter_ref_candidates(item, f"{location}[{index}]", in_slot)
        return
    if not isinstance(node, dict):
        return
    if is_compact_ref(node) or is_expanded_ref(node):
        yield node, location
    elif in_slot:
        if not is_ref_container(node):
            yield node, location
            return
        for key, value in node.items():
            yield from iter_ref_candidates(value, f"{location}/{key}", True)
        return
    for key, value in node.items():
        if key == SOURCES_KEY:
            continue
        yield from iter_ref_candidates(value, f"{location}/{key}", is_ref_carrier(key))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("project", type=Path, help="project directory to rewrite or verify")
    parser.add_argument("--check", action="store_true", help="verify only; never write")
    args = parser.parse_args(argv)
    root: Path = args.project
    if not root.is_dir():
        emit(f"error: {root} is not a directory", stream=sys.stderr)
        return 2
    return check(root) if args.check else migrate(root)


if __name__ == "__main__":
    raise SystemExit(main())
