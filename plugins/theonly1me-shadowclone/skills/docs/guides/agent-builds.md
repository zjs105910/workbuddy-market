# Agent builds

An Agent build is the set of workflow skills that your agents load. You pick the skills on a browser skill map, and Shadowclone installs them.

```bash
shadowclone wizard
```

![Agent builds: skills grouped by source and category](../assets/agent-builds.jpg)

`--repo` opens a build for the current repository, `--no-open` prints the local URL, and `--cli` configures a build in the terminal. Opening the wizard makes no model request.

## Pick skills on the Skill constellation

The map shows every local skill. Skills group by source (bundled, working preferences, your custom skills, your skills, and each plugin) and then by category.

- Click a skill to equip or unequip it and to read its details. Click a category to equip all its skills, or to unequip them if all are equipped.
- Groups collapse, and the wizard remembers that in this browser. Search highlights matches. **Map / list** shows a compact list, the default on narrow screens.

A plugin manages some skills, and you cannot equip them. Their details offer a local companion skill. **Create a skill** adds your own skill, and **Use AI** can draft its instructions. **Review your build** shows the files that will change. After you apply the build, open a new coding-agent session.

`write-plain-english` is always on. The wizard locks it on, and `shadowclone sync` adds it to existing builds.

## Choose a build scope

The **Build scope** menu sets where a build applies.

- **Personal · everywhere** applies to every repository and agent. Skills go to `~/.agents/skills`, `~/.claude/skills`, and `~/.gemini/config/skills`, with native routing for each agent.
- **Personal · this repository** writes skills to a private folder under `~/.shadowclone/builds/`, outside the repository.
- **Shared · this repository** applies to everyone who uses the repository. It writes `.agents/skills`, `.claude/skills`, and a guidance block in the repository `AGENTS.md`, which `CLAUDE.md` imports.

To make a shared build:

1. Run `shadowclone wizard --repo` and choose **Shared · this repository**.
2. Equip skills, read **Review your build**, and apply.
3. Review the new files and commit them.

A private build cannot weaken a shared requirement. A shared skill cannot contain personal paths. Anyone with repository access can read committed files. For checks as well, see [repository setup](repositories.md).

## Your build name

The character sheet names your build. Five seconds after your last equip change, the wizard asks your fast model for a name. Claude uses the `haiku` alias, Codex a fixed small preset, and Pi your saved model, at low reasoning effort where the engine supports it. Other engines use their own default model. The sheet names the engine and model.

A saved build that you open shows **Name my build** and makes no request. If naming fails, choose **Retry**. **Turn naming off** stops naming requests in this browser. [Data handling](../data-handling.md#execution) lists what naming sends.

## Your writing voice

Skills that write for you read `~/.agents/voice.md`. To draft it, choose **My voice**, allow Shadowclone to read your GitHub writing through `gh`, and choose **Read my writing and describe my voice**. Your learning model describes your style and writes 3 invented examples. Edit the description, choose **Rewrite the samples**, then choose **Save my voice** or **Discard**.

Shadowclone does not change a `~/.agents/voice.md` that exists or is a link. [Data handling](../data-handling.md#execution) lists what capture reads, skips, and sends.

## Shared files and links

- If `~/.claude/skills/<name>` links to the skill's own folder, the wizard writes nothing there. If an instruction file links to a file in your home folder, the review shows that real file as the file to change. The wizard skips any other link and names it.
- Applying a build copies supporting files, such as a checker script, next to each installed `SKILL.md`. A later version replaces unedited copies. If you edited a copy, applying stops and names the conflict. Unequipping a skill removes its unedited files and keeps edited ones, with a warning.
