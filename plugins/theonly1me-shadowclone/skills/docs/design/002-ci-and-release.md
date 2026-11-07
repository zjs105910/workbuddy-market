# CI and release checks

The original release design used compiled archives. The project now publishes through Release Please and npm. See [releasing](../../CONTRIBUTING.md#releasing).

## Problem

Local type checks and tests did not prevent unchecked changes from merging. Several repository conventions also depended entirely on review.

## Decision

Use `bun run check` as the shared local and CI gate: typecheck, lint, then tests. Run tests on Linux and macOS because filesystem paths, policy locations, and process behavior differ.

Run knip after lint to fail on unused files, dependencies, and binaries. `knip.json` lists the entry points that a static import graph cannot find: the MCP server, the browser client, scripts, plugin helpers, and tests. Unused exports stay ungated until the project prunes the barrel re-exports.

Use Biome for TypeScript linting, a GritQL rule for type assertions, and a tested repository checker for file length, comments, and prohibited prose characters. Pin the runtime version in `package.json` and GitHub Actions to commit digests. Grant workflows only the permissions their jobs need.

Release checks verify the package version, test the built CLI, and attach provenance to published output. Provenance identifies the source and build process. It does not prove that the program is safe or that the build is byte-for-byte reproducible.

## Tradeoffs

The initial choice of compiled archives avoided a runtime installation. Packaging later moved to npm, so archive download, signing, and first-release instructions are no longer installation guidance.

Biome covered the required rules with a small toolchain. Formatting stayed separate, because enabling it would produce an unrelated repository-wide rewrite. Custom checks need tests for both violations and valid input, including strings that look like comments.

## Verification

Test each custom rule with a failing fixture and a clean fixture. Make sure that the walker finds the expected files and ignores generated directories. Check workflow syntax, version mismatch failures, package contents, and the built CLI. The workflow files are the source of truth for publishing steps.

## Release test timing repair

The `v0.0.11` release gate exposed two timing-dependent tests. The project published that version later. The deadline test allowed 200 ms for setup and receipt writes. Then it assumed that every judge arm had saved its first vote. On a slower Linux runner, the test recorded the timeout correctly, but that assumption failed. A maintenance test ran repeated Git and receipt checks. It exceeded its 30-second test limit on macOS.

Seed the deadline test with valid saved votes. Wait for a judge call that ignores cancellation. Verify that the hard deadline keeps the receipt and resumes the remaining work. Give the deadline and maintenance tests enough time for runner variation. Run focused tests and the full check gate, so these tests do not block future releases.

## Maintainer source scan

The catalog scans Shadowclone independently. A source change can pass the repository typecheck, lint, and tests and still fail that gate. Run the pinned HOL scanner action on pushes and pull requests, with a score floor of 80 and no high-severity findings. Give it read-only repository access. Keep checkout credentials out of the workspace. Leave PR comments, online probing, and SARIF upload disabled.

Before you publish the workflow, do these steps:

1. Verify the workflow syntax.
2. Run the scanner locally against the repository.
3. Run `bun run check`.
