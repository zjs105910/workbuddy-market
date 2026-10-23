import { initialize, runWizard } from "@shadowclone/cli";
import type { EngineRunner } from "@shadowclone/agents";
import { installIntegration } from "@shadowclone/environment";
import type { ProjectPaths } from "@shadowclone/core";
import type { GitRemoteReader } from "@shadowclone/sessions";
import { loadSeedLibrary } from "@shadowclone/skills";

type WizardChoices = {
  readonly axes: readonly { readonly id: string; readonly guidance: readonly { readonly id: string }[] }[];
  readonly independentSkills: readonly { readonly id: string }[];
};

export function scriptedWizardAnswer(options: {
  readonly library: WizardChoices;
  readonly build: readonly string[];
}): (question: string) => string {
  const selected = new Set(options.build);

  return (question) => {
    const axis = options.library.axes.find((entry) => question.startsWith(`Choose one for ${entry.id}:`));

    if (axis) {
      const position = axis.guidance.findIndex((entry) => selected.has(entry.id));

      if (position < 0) {
        throw new Error(`Scripted build has no choice for ${axis.id}`);
      }

      return String(position + 1);
    }

    if (question.startsWith("Choose optional skills:")) {
      const choices = options.library.independentSkills.flatMap((entry, position) =>
        selected.has(entry.id) ? [String(position + 1)] : []);
      return choices.length > 0 ? choices.join(",") : "none";
    }

    throw new Error("Unexpected wizard question");
  };
}

export async function prepareFirstTime(options: {
  readonly paths: ProjectPaths;
  readonly learningPaths: ProjectPaths;
  readonly workspace: string;
  readonly runner: EngineRunner;
  readonly readRemote: GitRemoteReader;
  readonly build: readonly string[];
  readonly writeLine: (line: string) => void;
}): Promise<readonly string[]> {
  await initialize({
    paths: options.learningPaths,
    workingDirectory: options.workspace,
    managedConfigPath: null,
    presence: { hasRepositoryGuidance: true, presentCaptureSources: new Set(["claude-code"]) },
    agents: ["codex"],
    ask: () => true,
    engine: "codex",
    runner: options.runner,
    readRemote: options.readRemote,
    install: async ({ agents }) => {
      for (const agent of agents) {
        await installIntegration({ paths: options.paths, agent, scope: "global", cwd: options.workspace });
      }

      return { skipped: [] };
    },
    writeLine: options.writeLine,
  });

  const library = await loadSeedLibrary();
  const wizard = await runWizard({
    paths: options.paths,
    library,
    answer: scriptedWizardAnswer({ library, build: options.build }),
    confirm: async () => true,
    writeLine: options.writeLine,
  });

  if (!wizard.written || new Set(wizard.selectedGuidanceIds).size !== new Set(options.build).size) {
    throw new Error("Scripted wizard build was not fully applied");
  }

  return wizard.selectedGuidanceIds;
}
