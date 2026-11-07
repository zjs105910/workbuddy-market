# Synthetic secret fixtures

Shadowclone tests need credential-shaped inputs to verify redaction, capture boundaries, and local evaluation probes. The source scanner of the catalog treats literal strings with those shapes as possible credentials, even when they appear in tests. Moving fixtures outside the repository would make tests depend on an external store. It would also leave other scanned literals in place.

Keep the fixtures in the repository. Build each deterministic value from meaningful parts, such as a provider prefix and a synthetic payload. Then no complete credential-shaped literal appears in source. Keep the value that each test observes, its assertions, and the redaction coverage. Local probes keep the same nonempty synthetic key for the CLI contract.

Do these steps:

1. Update the affected fixtures.
2. Run the focused tests.
3. Run the repository check.
4. Scan the source with the pinned scanner version of the catalog.

The scan must report no hardcoded-secret findings. It must do this without repository-owned ignore rules or a baseline.
