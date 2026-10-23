# MCP server

The MCP server gives a connected agent seven tools. It runs on your machine and needs no Shadowclone credentials.

## Start the server

The Shadowclone plugin registers the server and starts `shadowclone mcp` after you install the CLI. For another agent that supports stdio servers, add a server that runs `shadowclone mcp`, then restart the agent session.

The server reads one JSON-RPC 2.0 message from standard input on each line. It uses MCP protocol version `2024-11-05` and the methods `initialize`, `tools/list`, and `tools/call`. The tools follow your consent settings and managed policy. If policy turns Shadowclone off, they return "Shadowclone context is disabled.", an error, or no results. Opening the server makes no model request.

## Tools

- `shadowclone_context` returns the learned skills and native routing for the repository where the server runs, the same text as `shadowclone context`. `shadowclone_profile` is a deprecated alias.
- `shadowclone_recall` takes `query` (1 to 1,000 characters) and `limit` (1 to 10, default 3). It returns the full text of matching reference records in the scope of the current repository, and respects blocked origins. If nothing matches, it says so.
- `shadowclone_remember` takes `text` (1 to 8,192 characters) and `scope` (`repository` or `global`). It records the preference locally and returns "Recorded preference" with its key. The tool description tells the agent never to infer consent from a task or an interruption.
- `shadowclone_history` returns a JSON list of revision identifiers with their times and counts.
- `shadowclone_skills_status` returns JSON with `roots` (the enabled skill roots), `managed` (the skills that Shadowclone maintains), and `pending` (the items that wait for review). It makes no model call.
- `shadowclone_bot` configures the cloud bot or reads its status.

Tools other than `shadowclone_context` and its alias reject unlisted input fields.

## Configure the cloud bot

`shadowclone_bot` takes these inputs:

- `operation`: `setup` or `status`. Required.
- `repository`: the repository as `owner/repository`.
- `bot`: the GitHub login of the machine account.
- `approveSkills`: `true` only after the owner approved the listed skill files.
- `engine` (`claude` by default, or `codex`) and `codexAuth` (`api-key` by default, or the experimental `plan`).

The behavior depends on the inputs:

- `status` with a saved `repository` returns the open setup steps. Otherwise it returns the saved bot status as JSON.
- `setup` with `bot` and `repository` sets up a machine account bot, and opens the GitHub signup page if the account does not exist. The first call returns the skill files that setup will push. Show the list to the owner, and call again with `approveSkills` set to `true` only after the owner agrees. The last answer lists the open steps.
- `setup` with `bot` and no `repository` returns an error that asks for it.
- `setup` with no `bot` starts the local wizard and returns its URL. The owner chooses a machine account or a GitHub App there. Keep the MCP connection open until setup ends.

The owner enters every token on GitHub, never in the tool. See the [cloud bot guide](cloud-bot.md).
