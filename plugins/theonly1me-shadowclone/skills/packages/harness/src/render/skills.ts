import { harnessMarkers } from "@shadowclone/environment";
import type { HarnessGate } from "../types";

export type AuthoredSkill = {
  readonly name: string;
  readonly description: string;
  readonly text: string;
};

function skillFile(options: {
  readonly name: string;
  readonly description: string;
  readonly body: readonly string[];
}): AuthoredSkill {
  const frontmatter = [
    "---",
    `name: ${options.name}`,
    `description: ${options.description}`,
    "metadata:",
    "  authored-by: shadowclone",
    "---",
  ].join("\n");
  const text = `${frontmatter}${harnessMarkers.start}\n${options.body.join("\n")}\n${harnessMarkers.end}`;

  return { name: options.name, description: options.description, text };
}

export function renderFeatureWorkflowSkill(options: {
  readonly gate: HarnessGate | null;
}): AuthoredSkill {
  const gate =
    options.gate === null
      ? "the checks listed in `AGENTS.md`"
      : `\`${options.gate.command}\``;

  return skillFile({
    name: "feature-workflow",
    description:
      "Use before any feature, fix, or refactor in this repository. It scopes the change, stops for approval when asked, implements only approved work, runs the gate, and reports.",
    body: [
      "# Feature workflow",
      "",
      "Authored by Shadowclone for this repository. Your own additions outside the marked section are kept when Shadowclone refreshes it.",
      "",
      "## Steps",
      "",
      "1. Read `AGENTS.md` and load every skill it lists under Read first.",
      "2. Restate the request as a scope and the checks that will prove it: the behavior to add, the tests to add or change, and what must stay the same.",
      "3. If the user asked for a plan, or the change touches a public interface, stored data, or more than a few files, stop after the plan and wait for approval.",
      "4. Implement only the approved scope. Report anything else you notice as a follow-up instead of changing it.",
      "5. Add or update tests that fail without the change.",
      `6. Run ${gate} and fix every failure. Never skip, disable, or weaken a check to get green.`,
      "7. Report what changed, the exact commands you ran with their results, and what is left.",
      "8. Stop. Do not commit, push, open a pull request, or start another task unless asked.",
      "",
      "## Approval boundaries",
      "",
      "- Ask before adding a dependency, changing a public interface, deleting files, or running anything that sends, publishes, or spends.",
      "- Never commit, push, or open a pull request unless the user asks for that specific action.",
      "",
      "## Verification",
      "",
      `The change is verified when ${gate} passes and each new behavior has a test. Name the checks you ran; never claim one you did not run.`,
    ],
  });
}

export function renderHarnessBuilderSkill(): AuthoredSkill {
  return skillFile({
    name: "harness-builder",
    description:
      "Use when asked to describe this repository for coding agents, such as writing or refreshing the purpose, map, or invariants in AGENTS.md.",
    body: [
      "# Harness builder",
      "",
      "Write the parts of `AGENTS.md` that Shadowclone cannot derive from manifests, above its marked section.",
      "",
      "1. Read `AGENTS.md`, `README.md`, and the top-level layout.",
      "2. Write or refresh three short sections: Purpose (what the repository does and for whom), Map (the main directories or modules and what each does), and Rules that outrank convenience (invariants a reviewer would reject a change for breaking, each with its reason).",
      "3. Keep `AGENTS.md` under 150 lines. Link to longer documents instead of copying them.",
      "4. Leave the marked section alone. Preferences change through `shadowclone remember` and the next `shadowclone sync`.",
      "5. Show the diff and stop. Do not commit unless asked.",
    ],
  });
}
