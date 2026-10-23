# Privacy

Shadowclone runs on your machine. It has no collection service and no telemetry.

Each session, memory, repository, and skill source is off until you consent to it. Setup asks three separate questions: session learning, skill maintenance, and background learning. Learning excludes tool results, tool-returned file contents, thinking blocks, and data-access results. Shadowclone redacts eligible text before any model work. Redaction does not guarantee anonymity, so send only material that you may send.

## What leaves your machine

The wizard and the local MCP server send nothing to Shadowclone. These features send data to the provider that you choose:

- **Learning, skill maintenance, and build naming:** selected redacted text, or skill titles and redacted summaries.
- **Voice capture:** your redacted GitHub writing, after you turn on `github-writing`.
- **Pull request review:** the pull request, its diff, and related files. `--offline` stops web search and the OSV lookup of lockfile package names.
- **Cloud bot:** your reviewed skills, the repository, and the task. You enter tokens on GitHub, and Shadowclone never reads them.

The provider and GitHub govern retention of what they receive. [Data handling](docs/data-handling.md) lists every source, request, and file.

## Removal

- `shadowclone learning disable` stops background learning.
- `shadowclone skills automatic off` stops automatic skill edits.
- `shadowclone forget --all` removes the recorded state.

Local state stays in the state folder. Uninstalling the plugin removes only its setup workflow.

Ask privacy questions that hold no sensitive data in [GitHub issues](https://github.com/theonly1me/shadowclone/issues). Report private material under the [security policy](SECURITY.md).
