# Acknowledge requests

## Problem

A tagged comment or a new issue gives no visible sign that the clone accepted it. The owner opens the Actions tab to check.

## Decision

After the worker validates a request and mints its token, it adds an `eyes` reaction as the clone. The reaction goes on the source comment, or on the issue when the request is a new issue. A review body and a run that CI started have no reaction target, so the worker skips them.

The reaction lives in `src/cloud/react.ts`, which the renderer ships beside the guards. The worker runs it before it restores guidance, so the owner sees the reaction as early as possible. A reaction that fails logs a warning, and the work continues. The reaction only reports state, and the work does not depend on it. The token already has `issues: write`, which covers reactions on issues and on issue and review comments.

The installed `.github/workflows/shadowclone.yml` is the rendered workflow for this repository.

## Verification

Tests cover the reaction route for each request type, the skipped types, a failed reaction, and the step order in the rendered workflow.
