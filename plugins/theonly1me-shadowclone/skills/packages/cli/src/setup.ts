import { projectPaths } from "@shadowclone/core";
import { harnessInitCommand, parseRepositoryInit } from "./harness";
import { initialize } from "./init";
import { parsePersonalInit } from "./initOptions";
import { runWizardCommand } from "./wizardCommand";

export async function handleSetupCommand(options: {
  readonly command: string | undefined;
  readonly arguments: readonly string[];
}): Promise<boolean> {
  if (options.command !== "init" && options.command !== "wizard") {
    return false;
  }

  if (options.command === "wizard") {
    await runWizardCommand(options);

    return true;
  }

  const repository = options.arguments.includes("--repo");
  const web = options.arguments.includes("--web");

  if (web) {
    const supported = new Set(["--web", "--repo", "--no-open"]);

    if (options.arguments.some((argument) => !supported.has(argument))) {
      throw new Error("Use init --web or wizard --web [--repo] [--no-open]");
    }

    const { runWebWizard } = await import("./webWizard");

    await runWebWizard({
      repository,
      open: !options.arguments.includes("--no-open"),
    });

    return true;
  }

  if (!repository) {
    const parsed = parsePersonalInit(options.arguments);

    if (parsed === null) {
      throw new Error(
        "Use init [--advanced] or pass all three consent decisions",
      );
    }

    if (parsed.kind === "status") {
      const initialized = await Bun.file(projectPaths.configFile).exists();
      console.log(
        parsed.json
          ? JSON.stringify({ initialized })
          : initialized
            ? "Shadowclone is initialized."
            : "Shadowclone is not initialized.",
      );

      return true;
    }

    if (await Bun.file(projectPaths.configFile).exists()) {
      console.log(
        "Shadowclone is already initialized; existing consent settings were preserved.",
      );

      return true;
    }

    if (parsed.kind === "consent") {
      await initialize({ consent: parsed.consent });

      return true;
    }

    if (!process.stdin.isTTY) {
      throw new Error(
        "Non-interactive setup requires all three explicit consent decisions",
      );
    }
  }

  const repositoryOptions = parseRepositoryInit(
    options.arguments.filter(
      (argument) => argument !== "--advanced" && argument !== "--repo",
    ),
  );

  if (
    repositoryOptions === null ||
    (!repository &&
      options.arguments.some((argument) => argument !== "--advanced"))
  ) {
    throw new Error("Use init [--advanced] [--repo] or init --web [--repo]");
  }

  if (process.stdin.isTTY && !options.arguments.includes("--advanced")) {
    const answer = prompt(
      "Setup: [1] Terminal (default)  [2] Browser skill tree",
    );

    if (answer?.trim() === "2") {
      const { runWebWizard } = await import("./webWizard");

      await runWebWizard({ repository });

      return true;
    }
  }

  if (!(await Bun.file(projectPaths.configFile).exists())) {
    await initialize({ advanced: options.arguments.includes("--advanced") });
  }

  if (repository) {
    await harnessInitCommand({ ...repositoryOptions, apply: "confirm" });
  }

  return true;
}
