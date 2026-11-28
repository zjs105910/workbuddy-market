import { listRevisions, showRevision } from "@shadowclone/changes";
import { readConfig, readEffectiveConfig, writeConfig, projectPaths } from "@shadowclone/core";
import { refreshIntegrations, reviewLearning, undoRevision } from "@shadowclone/environment";
import {
  acknowledgeCorrections,
  correctionReviewSignals,
  decidePendingLearning,
  learningCatalog,
  publishReviewedLearning,
  readLatestLearningReceipt,
  readLatestProbe,
  readLearningState,
  readPendingLearning,
  rememberPreference,
  showLearning,
} from "@shadowclone/learning";
import { readHarnessRoots } from "@shadowclone/harness";
import { skillRevisionRoots, listSkillProposals } from "@shadowclone/skills";
import { handleHistoricalRepositories } from "./learningRepositories";
import { handleLearningReview } from "./learningReview";
import { handleLearningProbe } from "./learningProbe";
import { handleSkillMaintenance } from "./skillMaintenance";
import { automaticLearning } from "./automaticLearning";

export async function handlePreferenceCommand(options: {
  readonly command: string | undefined;
  readonly arguments: readonly string[];
}): Promise<boolean> {
  const [action, ...rest] = options.arguments;

  if (options.command === "remember") {
    const scope = action === "--global" ? "global" : "repository";
    const words =
      action === "--global" || action === "--repo" ? rest : options.arguments;

    if (words.length === 0 || words.some((word) => word.startsWith("--"))) {
      throw new Error("Use remember [--global|--repo] <explicit preference>");
    }

    const key = await rememberPreference({ scope, text: words.join(" ") });

    console.log(`Recorded ${scope} preference ${key}.`);

    return true;
  }

  if (options.command === "history") {
    if (!action) {
      console.log(JSON.stringify(await listRevisions(projectPaths), null, 2));
    } else if (rest.length === 0) {
      console.log(await showRevision({ paths: projectPaths, id: action }));
    } else {
      throw new Error("Use history [revision-id]");
    }

    return true;
  }

  if (options.command === "undo" && action && rest.length === 0) {
    const revision = await undoRevision({
      paths: projectPaths,
      id: action,
      skillRoots: await skillRevisionRoots(projectPaths),
      harnessRoots: await readHarnessRoots(projectPaths),
    });

    await refreshIntegrations();
    console.log(
      revision
        ? `Restored files in revision ${revision}.`
        : "Files already match the prior revision.",
    );

    return true;
  }

  if (options.command === "learn" && action === "--automatic") {
    await automaticLearning(rest);

    return true;
  }

  if (options.command !== "learning") {
    return false;
  }

  if (await handleLearningReview(options.arguments)) return true;
  if (await handleLearningProbe(options.arguments)) return true;
  if (action === "acknowledge" && rest.length === 1) {
    await acknowledgeCorrections({ paths: projectPaths, key: rest[0] ?? "" });
    console.log("Marked the recorded corrections reviewed; guidance is unchanged.");
    return true;
  }
  if (["show", "apply", "reject"].includes(action ?? "") && rest.length === 1 &&
    (await listSkillProposals(projectPaths)).some((proposal) => proposal.id === rest[0])) {
    return handleSkillMaintenance(options.arguments);
  }

  if ((action === "pending" || action === "list") && rest.length === 0) {
    console.log(JSON.stringify(await learningCatalog({
      paths: projectPaths,
      pendingOnly: action === "pending",
    }), null, 2));

    return true;
  }

  if (action === "repositories" && rest.length === 0) {
    await handleHistoricalRepositories({ action });

    return true;
  }

  if (action === "bind" && rest.length === 1) {
    await handleHistoricalRepositories({ action, id: rest[0] });

    return true;
  }

  if (action === "show" && rest.length === 1) {
    console.log(JSON.stringify(await showLearning({
      paths: projectPaths, key: rest[0] ?? "",
    }), null, 2));

    return true;
  }

  if ((action === "apply" || action === "reject") && rest.length === 1) {
    const key = rest[0] ?? "";
    const pending = await readPendingLearning(projectPaths);
    if (pending.rules.some((rule) => rule.key === key)) {
      await decidePendingLearning({ paths: projectPaths, key, action });
    } else {
      await reviewLearning({
        paths: projectPaths, key,
        action: action === "apply" ? "retry" : "exclude",
        reason: action === "reject" ? "Explicitly rejected in learning review" : undefined,
      });
      if (action === "apply") {
        await publishReviewedLearning({ paths: projectPaths, keys: [key] });
      } else {
        await refreshIntegrations();
      }
    }
    console.log(action === "apply"
      ? "Learned rule approved. Check learning status for delivery."
      : "Learned rule rejected; the same proposal will not return.");

    return true;
  }

  if (
    rest.length !== 0 ||
    !["enable", "disable", "status"].includes(action ?? "status")
  ) {
    throw new Error("Use learning enable|disable|status|list|pending|show <key>|apply <key>|reject <key>|repositories|bind <id>|retire|replace|narrow|remove-source");
  }

  const { config: effective, policy } = await readEffectiveConfig();

  if (action === "enable" || action === "disable") {
    if (
      action === "enable" &&
      (!effective.distillation.deep || policy.distillation !== "allowed")
    ) {
      throw new Error(
        "Enable deep learning consent in shadowclone init before automatic learning",
      );
    }

    const config = await readConfig();

    await writeConfig({
      config: {
        ...config,
        distillation: {
          ...config.distillation,
          automatic: action === "enable",
        },
      },
    });
    console.log(
      `Automatic learning ${action === "enable" ? "enabled" : "disabled"}.`,
    );
  } else {
    const state = await readLearningState(projectPaths);

    console.log(
      JSON.stringify(
        {
          enabled: effective.distillation.automatic === true,
          status: state.status,
          lastAttemptAt: state.lastAttemptAt,
          lastCompletedAt: state.lastCompletedAt,
          pendingReview: (await readPendingLearning(projectPaths)).rules.length,
          latestAttempt: await readLatestLearningReceipt(projectPaths),
          latestProbe: await readLatestProbe(projectPaths),
          laterCorrections: await correctionReviewSignals(projectPaths),
        },
        null,
        2,
      ),
    );
  }

  return true;
}
