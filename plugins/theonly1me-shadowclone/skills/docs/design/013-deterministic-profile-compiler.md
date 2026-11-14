# Deterministic profiles and reversible installs

This is the legacy profile compiler design. [Repository harnesses](022-repository-harness.md) reduced startup context. [Skills delivery](023-skills-as-delivery.md) replaced profile injection for active skill environments.

## Problem

Different callers rendered profiles differently. Some dropped conditions and provenance, counted nested headings as separate rules, or delivered conflicting choices. Installed artifacts also lacked a reliable removal record.

## Decision

Use one `compileProfile` operation for profile delivery. It returns Markdown, applied-rule counts and keys, and explicit omission reasons. Read only global files, the matching remote-owner files, and the exact repository file.

Order user-written, declared, and imported guidance ahead of mined guidance. Resolve known preference-axis conflicts deterministically. Lifecycle states decide eligibility. The compiler does not reinterpret evidence. It does not match natural-language conditions against task keywords. Render those conditions for the agent to follow.

Admit whole blocks under a 16,384-byte UTF-8 limit, including labels and separators. Keep considering smaller blocks after the compiler omits an oversized block. Never slice a rule, code fence, or multibyte character. Report lifecycle, axis-conflict, and budget omissions.

Pair local metadata with redacted visible text from the same bounded snapshot. Fingerprints and lifecycle come from the original text. Every model-facing title, body, and condition comes from the redacted text. Redaction must not make a generated rule appear manually edited.

## Installation ownership

Record installed paths and installer-added Git exclude entries in a local manifest. Reinstallation keeps ownership records. Uninstall removes only supported artifacts and owned entries and keeps unrelated files. `forget --all` processes recorded installations before it deletes local state.

Automatic delegation is opt-in through `--auto-delegate`. Its workflow carries a structured task brief with context, constraints, verification, and expected output. Default installation must not silently enable delegation.

## Verification

Check deterministic output, authority ordering, scope, whole-block budgets, redaction, and accurate applied-rule counts. Test install, reinstall, uninstall, edited artifacts, missing repositories, and unrelated exclude entries. Installations that predate the manifest need bounded compatibility handling. Shadowclone cannot discover them by scanning arbitrary repositories.
