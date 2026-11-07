# Named GitHub clones

## Decision

Each personal installation uses a named GitHub App that the user owns. Organization repositories register a private App under their organization, because GitHub restricts private Apps to their owning account. The App operates only on explicitly selected repositories. Claude Code runs through the pinned upstream GitHub Action. Shadowclone supplies a reviewed skills bundle and repository workflows. It adds no coding runtime.

The owner can start work with an issue or an `@shadowclone` request. The App slug is an alias. The issue grants plan approval within its stated scope. The clone opens a draft PR. It maintains checks and reviewer findings. Then it marks the PR ready for owner review. A CI result resumes the PR once, after the last workflow run on its head finishes. Runs that the clone's own push started count, because a CI result is not a request from the clone. The worker prompt grants the ready step by name, because the native rules say that skill guidance does not authorize additional actions. The clone never merges or force pushes.

## Boundaries

- Reject installations with access to all repositories. Verify repository IDs and mint installation tokens for one repository.
- Keep the App key, Claude subscription token, and guidance in a default-branch-only environment. An event relay uses the repository token to dispatch the worker on that branch. The worker validates the live entity, sender, head, pause state, and run budget again. GitHub leaves an empty input out of the dispatch event, so the worker reads a missing head as the empty head of an issue request.
- Add a `shadowclone default branch` ruleset before any secret upload. It lets only the admin, maintain, and write roles update or delete the default branch. So the App cannot push or merge there. Those roles are exempt, so people merge without a bypass prompt. GitHub Actions gets no bypass, because a workflow added on a branch could otherwise push with `GITHUB_TOKEN`. GitHub leaves a rule parameter out of the stored ruleset when it has its default value, so verification reads a missing `update_allows_fetch_and_merge` as `false`.
- Treat issue text and reviewer comments as untrusted task data. They cannot widen repository access or the authorized scope.
- Export only selected maintained skills and their supporting resources through the existing redacted delivery boundary. Include applicable native rules. Exclude capture, evidence records, receipts, source history, credentials, and identifying local paths.
- Store setup state and credential material outside the checkout. The MCP can start setup and inspect status. Human browser actions authorize App creation, repository installation, guidance upload, and subscription use.
- The default branch and authorized repository code remain trusted. Environment restrictions do not isolate credentials from code that runs with them.

## Sequence

1. Export reviewed guidance into a Claude Code plugin. Encode its compressed bundle within the GitHub secret limit.
2. Render pinned relay and worker workflows with live event validation, one-repository tokens, serialized branch work, and bounded runs.
3. Extend the existing loopback browser wizard for App registration, installation validation, subscription connection, and a setup PR.
4. Add CLI and MCP entry points and document the data flow.
5. Verify with synthetic fixtures and the repository gate. Before you claim a click count, qualify installation separately.

The workflow invokes the selected `shadowclone-work` skill. When someone updates that export, the workflow adopts the owner's evaluated variant. The execution architecture does not change.

The skill holds every pull request rule. The worker prompt adds only cloud facts. These are the entity, the authorized scope, the branch, the pause check, and a ban on pushes to the default branch. The pinned action allows only read tools by default. So the worker grants `Bash` and `Skill` and accepts file edits. The skill needs `git`, `gh`, and the repository's checks.

## Delivery

A main-only environment secret holds the compressed plugin marketplace. The runner restores it outside the checkout and supplies it through `plugin_marketplaces` and `plugins`. Reject an oversized encoded bundle before upload. This option adds no private guidance repository or second repository token.

The browser wizard previews the exact selected skill bodies, resources, and native rules before upload. The skill list starts with `shadowclone-work`, the skills equipped in the personal build, and learned skills. Other library and plugin skills stay out until the owner names them, because a list of every discovered skill exceeds the bundle limit. A failed preview shows its reason, such as the encoded size or the file that contains a local path. Later steps handle the Claude token, so their errors stay generic. The Claude token comes from `claude setup-token`, never from an existing interactive credential. A native sign-in may need one secure paste into the local wizard. Credentials never enter MCP arguments or responses.

## Maintenance

A validated CI completion or a named reviewer bot can resume a managed PR. The relay ignores the clone's own comments and worker runs. A pause label blocks new work. Local handoff cancels active worker runs before the owner edits. It then resumes explicitly. Branch work keeps the owner's commits.

Label authorization reads all issue-event pages within a 1,000-event bound. An incomplete history rejects the trigger. This prevents a first-page actor from authorizing a later label change.

A fixed finding receives only its commit hash. The clone resolves only bot threads. Declined findings receive no reply and stay open. The owner performs the final merge.

## Verification

Synthetic tests cover selected scope, resource delivery, local path rejection, installation selection, callback replay, forged requests, stale heads, forks, bot loops, pause, and workflow pins. The repository typecheck, lint, tests, and CLI help remain the release gate. A bounded synthetic live pilot qualifies behavior beyond the isolated plugin-delivery spike.
