import {
  compileContext,
  compileContextDetails,
  explainLearningEnvironment,
  installIntegration,
  nativeSessionEnd,
  nativeSessionStart,
  readIntegrations,
  refreshIntegrations,
  sessionStartProjection,
  type SkippedRouting,
  syncLearningEnvironment,
  uninstallIntegration,
} from "@shadowclone/environment";
import { renderBundledSkillReport, updateBundledSkills } from "@shadowclone/builds";
import { parseNativeOptions, type NativeInstallOptions } from "./nativeOptions";

export { parseNativeOptions, type NativeInstallOptions } from "./nativeOptions";
import { describeSkippedAgent, skippedAgentFrom, type SkippedAgent } from "./skippedAgents";
import { canonicalPath, projectPaths } from "@shadowclone/core";
import { installLiveClone } from "./install";
import { uninstallLiveClone } from "./uninstall";
import { removeUneditedLegacySubagent } from "./legacyUpgrade";
import { scheduleLearning, runAutomaticLearning } from "@shadowclone/learning";
import { explainContext, renderContextExplanation } from "./contextExplain";
import { harnessSyncCommand } from "./harnessSync";
import { nativeModelSchema } from "./automaticLearning";

export async function installNativeCommand(
  options: NativeInstallOptions & {
    readonly skipUnsafeDestinations?: boolean;
    readonly install?: (options: {
      readonly agent: NativeInstallOptions["agents"][number];
      readonly scope: NativeInstallOptions["scope"];
    }) => Promise<unknown>;
  },
): Promise<{ readonly skipped: readonly SkippedAgent[] }> {
  const skipped: SkippedAgent[] = [];

  for (const agent of options.agents) {
    try {
      await (options.install ?? installIntegration)({ agent, scope: options.scope });
      console.log(`Installed ${agent} main-agent guidance (${options.scope}).`);
    } catch (error) {
      const skip = skippedAgentFrom({
        agent,
        error,
        skipUnsafeDestinations: options.skipUnsafeDestinations ?? false,
      });

      if (skip === null) {
        throw error;
      }

      skipped.push(skip);
    }
  }

  if (!options.subagent && (await removeUneditedLegacySubagent())) {
    console.log(
      "Removed the unchanged legacy Shadowclone subagent; edited copies are preserved.",
    );
  }

  if (options.subagent) {
    await installLiveClone({ autoDelegate: options.autoDelegate });
  }

  return { skipped };
}

export async function uninstallNativeCommand(
  options: NativeInstallOptions & { readonly allAgents?: boolean },
): Promise<void> {
  const integrations = await readIntegrations(projectPaths);

  for (const integration of integrations) {
    if (
      integration.scope !== options.scope ||
      (!options.allAgents && !options.agents.includes(integration.agent))
    ) {
      continue;
    }

    if (
      integration.scope === "repository" &&
      integration.directory !== canonicalPath(process.cwd())
    ) {
      continue;
    }

    await uninstallIntegration({ integration });
    console.log(
      `Removed ${integration.agent} managed guidance (${integration.scope}); surrounding content preserved.`,
    );
  }

  if (options.scope === "repository") {
    await uninstallLiveClone();
  }
}

export async function handleNativeCommand(options: {
  readonly command: string | undefined;
  readonly arguments: readonly string[];
}): Promise<boolean> {
  if (options.command === "install" || options.command === "uninstall") {
    const parsed = parseNativeOptions(options.arguments);

    if (!parsed) {
      throw new Error(
        "Use --agent claude-code|codex|cursor|antigravity|pi|all and --global or --local; subagents require local Claude installation",
      );
    }

    if (options.command === "install") {
      const { skipped } = await installNativeCommand(parsed);

      for (const entry of skipped) {
        console.log(describeSkippedAgent(entry));
      }

      if (skipped.length > 0) {
        process.exitCode = 1;
      }
    } else {
      await uninstallNativeCommand({
        ...parsed,
        allAgents: !options.arguments.includes("--agent"),
      });
    }

    return true;
  }

  if (options.command === "context" && options.arguments.length === 0) {
    console.log(
      (await compileContext({ cwd: process.cwd() })) ??
        "Shadowclone guidance is disabled by policy.",
    );

    return true;
  }

  if (
    options.command === "context" &&
    (options.arguments.length === 1 || options.arguments.length === 2) &&
    options.arguments[0] === "--explain" &&
    (options.arguments.length === 1 || options.arguments[1] === "--json")
  ) {
    const environment = await explainLearningEnvironment({
      paths: projectPaths,
      cwd: process.cwd(),
    });

    if (environment !== null) {
      await Bun.stdout.write(`${environment}\n`);

      return true;
    }

    const details = await compileContextDetails({
      cwd: process.cwd(),
      ...sessionStartProjection,
    });

    if (details === null) {
      await Bun.stdout.write("Shadowclone guidance is disabled by policy.\n");

      return true;
    }

    const explanation = explainContext(details);

    await Bun.stdout.write(
      options.arguments[1] === "--json"
        ? `${JSON.stringify(explanation, null, 2)}\n`
        : renderContextExplanation(explanation),
    );

    return true;
  }

  if (options.command === "sync" && options.arguments.length === 0) {
    const bundled = await updateBundledSkills(projectPaths);

    for (const line of bundled ? renderBundledSkillReport(bundled) : []) {
      console.log(line);
    }

    if (
      bundled?.retired.some((change) => change.kind === "failed") ||
      bundled?.alwaysOn.some((change) => change.kind === "failed")
    ) {
      process.exitCode = 1;
    }

    const skipped: SkippedRouting[] = [];

    if (await syncLearningEnvironment(projectPaths, { onSkipped: (entries) => skipped.push(...entries) })) {
      for (const entry of skipped) {
        console.log(
          `Did not update ${entry.agent}: ${entry.path} is ${entry.target === null ? "not a regular file" : `a symbolic link to ${entry.target}`}. Shadowclone does not write through links, so ${entry.agent} keeps its old routing. Replace the link with a regular file, then run shadowclone sync.`,
        );
      }

      console.log(
        skipped.length === 0
          ? "Synchronized learned skills and native routing."
          : `Synchronized learned skills and native routing for every agent except ${skipped.map((entry) => entry.agent).join(", ")}.`,
      );

      if (skipped.length > 0) process.exitCode = 1;

      return true;
    }

    const result = await refreshIntegrations();

    console.log(
      `Refreshed ${result.refreshed} integration(s); preserved ${result.preserved} edited or unavailable integration(s).`,
    );
    await harnessSyncCommand({ apply: "confirm" });

    return true;
  }

  if (options.command === "hook" && options.arguments.length === 2) {
    const [event, id] = options.arguments;

    if (!id) {
      return false;
    }

    if (event === "native-start") {
      const result = await nativeSessionStart({
        id,
        input: await Bun.stdin.text(),
      });

      await Bun.stdout.write(`${JSON.stringify(result)}\n`);

      return true;
    }

    if (event === "native-end") {
      const input = await Bun.stdin.text();
      const sessionKey = await nativeSessionEnd({
        id,
        input,
      });

      if (sessionKey) {
        const selection = nativeModelSchema.parse(JSON.parse(input || "{}"));
        if (selection.engine === "pi" && process.env.SHADOWCLONE_PI_SOCKET) {
          await runAutomaticLearning({ sessionKeys: [sessionKey], ...selection });
        } else {
          await scheduleLearning({ sessionKeys: [sessionKey], ...selection });
        }
      }

      return true;
    }
  }

  return false;
}
