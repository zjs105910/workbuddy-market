import type { ManagedPolicy, ProjectPaths } from "@shadowclone/core";
import type { InitializeAdvancedOptions, ConsentPrompt } from "./initAdvanced";
import type { OnboardingPresence } from "./onboardingPresence";
import { runWizard } from "./wizard";

export async function offerInitialGuidance(
  options: InitializeAdvancedOptions & {
    readonly policy: ManagedPolicy;
    readonly paths: ProjectPaths;
    readonly presence: OnboardingPresence;
    readonly ask: ConsentPrompt;
    readonly writeLine: (line: string) => void;
  },
): Promise<boolean> {
  const { policy, paths, presence, ask, writeLine } = options;

  const importAllowed =
    policy.enabled && policy.allowedSources.includes("declared-rules");
  let importEnabled = false;

  if (presence.hasRepositoryGuidance) {
    if (importAllowed) {
      importEnabled = await ask("Import existing repository guidance?");
    } else {
      writeLine("Managed policy blocks repository guidance import.");
    }

    if (!importEnabled) {
      writeLine("Existing agent instructions detected and left unread.");

      if (await ask("Set up a seed profile instead?")) {
        await runWizard({
          paths,
          library: options.library,
          answer: options.answer,
          confirm: ask,
          writeLine,
        });
      }
    }
  } else {
    await runWizard({
      paths,
      library: options.library,
      answer: options.answer,
      confirm: ask,
      writeLine,
    });
  }

  return importEnabled;
}
