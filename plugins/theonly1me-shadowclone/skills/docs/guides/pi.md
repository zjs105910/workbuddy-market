# Pi setup

Configure a model in Pi, then keep coding in Pi. Shadowclone supplies skills, native guidance, and consented learning. Pi owns the coding loop, tools, endpoints, credentials, and provider extensions, so Shadowclone works with any model that you configure in Pi, including local models.

The integration uses `@earendil-works/pi-coding-agent` 1.0.0 and needs its `agent_settled` event and `modelRegistry.streamSimple` extension API. The [provider design record](../design/003-provider-expansion.md#qualification-results) lists the checks.

## Install

```bash
shadowclone init
shadowclone install --agent pi --global
```

`shadowclone init --advanced` has the separate Pi transcript choice. Installing alone turns on no capture source.

- A global install manages a section in `~/.pi/agent/AGENTS.md`, an extension under `~/.pi/agent/extensions/`, and the shared skill `~/.agents/skills/shadowclone-context`.
- `shadowclone install --agent pi --local` uses `.pi/extensions/` and `.agents/skills/` in one repository. It does not write the repository `AGENTS.md`, which your team may share. The extension loads guidance at session start. The next install removes a section that an older version wrote there, unless you edited it.
- Pi paths follow `PI_CODING_AGENT_DIR`. Codex and Pi share the global context skill, so removing one installation keeps the copy of the other.

Restart Pi after the install. Start a new session, or use `/reload`, after guidance changes.

## Learning models

Automatic learning uses the model of the Pi session that started it, including providers that extensions register there. A private socket connects the bounded learning worker to the Pi extension model registry. Requests have an empty tool set and exclude the messages, system prompt, and tool loop of the coding session.

Standalone maintenance runs the installed Pi CLI from an empty temporary directory. It keeps the global provider configuration and trusted global extensions of Pi, but loads no instructions, skills, prompt templates, or tools. It needs a model that you configured globally in Pi. If that model is unavailable, the request fails with no fallback.

Choose a saved model in the **Learning model** control of the wizard, or in the configuration:

```toml
[distillation]
deep = true
automatic = true
engine = "pi"
model = "ollama/your-configured-model"
```

Use the exact `provider/model` identifier that Pi offers. A saved model does not carry over to a different agent.

Learning shares the call and time limits of Shadowclone. Pi enforces no dollar cap, and cost stays unknown when Pi does not report it. Learning rejects tool calls and malformed structured responses. A local model does not alone meet a managed `local-only` policy, because Pi can configure remote providers.

## Capture and removal

The setting `sources.pi` is false by default. After consent, Shadowclone reads records from the version 3 JSONL sessions in the Pi agent directory and leaves them untouched. Learning excludes tool results, thinking, injected messages, compaction, and branch summaries.

`shadowclone uninstall --agent pi --global` or `--local` removes the files and sections that Shadowclone owns. An edited file blocks removal. Uninstall keeps your sessions, other integrations, and skills that you maintain yourself.

Pi evaluation is unavailable, because the Pi tools do not meet the isolation contract. Zed follows the agent that it hosts.
