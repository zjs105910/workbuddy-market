# Consent checks and capability claims

## Problem

Onboarding needed to show the available sources without reading them before consent. The documentation also mixed up implemented behavior, tested behavior, and future work.

## Decision

Before consent, allow only a bounded source-presence check. It returns one ephemeral boolean that says whether the configured root exists and is not empty. It must not keep or log entry names, counts, timestamps, paths, or provider identifiers. It must not open source contents.

Keep transcript consent separate from Git metadata consent. Repository guidance follows the exact repository and remote-owner scope. Action authorization applies to the repository that changes. A broader profile scope cannot imply it.

Document edit, rejection, and deletion behavior as part of the guidance lifecycle. Cleanup commands must state which recorded integrations they can remove. They must keep user-owned files when ownership is uncertain.

Public capability claims must separate implementation, fixture coverage, and live qualification. Update the architecture diagram when the data flow or a trust boundary changes. [Documentation design](025-documentation.md) defines where current instructions and historical decisions belong.

## Verification

Prove that pre-consent discovery emits only the presence result and never reads a source entry. Test repository isolation, user-edit preservation, and cleanup conflicts. A passing unit test is evidence for the tested contract. It is not a claim about every installed provider version.
