import type { HarnessCommand, HarnessGate } from "../types";

export type ReadFirstSkill = {
  readonly name: string;
  readonly description: string;
};

function commandLine(options: {
  readonly command: HarnessCommand;
  readonly gate: HarnessGate | null;
}): string {
  if (options.command.label !== "Gate") {
    return `- ${options.command.label}: \`${options.command.command}\``;
  }

  const ci = options.gate?.ciRunsGate ? "; CI runs it too" : "";

  return `- Gate: \`${options.command.command}\`. Run it before presenting any change${ci}.`;
}

export function renderAgentsSection(options: {
  readonly skills: readonly ReadFirstSkill[];
  readonly commands: readonly HarnessCommand[];
  readonly gate: HarnessGate | null;
  readonly rules: string;
  readonly checked: boolean;
}): string {
  const finish =
    options.gate === null
      ? "the checks above pass"
      : `\`${options.gate.command}\` passes`;
  const check = options.checked
    ? " If `shadowclone` is installed, also run `shadowclone check --changed` and fix what it reports."
    : "";

  return [
    "## Working in this repository",
    "",
    "Maintained by `shadowclone init --repo` from this repository's manifests and its owner's confirmed preferences. Everything outside this section is yours to edit.",
    "",
    "### Read first",
    "",
    ...options.skills.map(
      (skill) => `- \`${skill.name}\`: ${skill.description}`,
    ),
    ...(options.commands.length === 0
      ? []
      : [
          "",
          "### Commands",
          "",
          ...options.commands.map((command) =>
            commandLine({ command, gate: options.gate }),
          ),
        ]),
    ...(options.rules.length === 0
      ? []
      : ["", "### Rules", "", options.rules.trimEnd()]),
    "",
    "### Finish line",
    "",
    `A change is done when ${finish} and you have reported what changed and how you verified it.${check} Do not commit, push, or open a pull request unless asked.`,
  ].join("\n");
}
