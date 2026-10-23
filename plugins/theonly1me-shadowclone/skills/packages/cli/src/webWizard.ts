import { canonicalPath, projectPaths } from "@shadowclone/core";
import { serveBuildWizard } from "@shadowclone/web";

export async function runWebWizard(
  options: {
    readonly repository?: boolean;
    readonly open?: boolean;
    readonly bot?: boolean;
    readonly targetRepository?: string;
  } = {},
): Promise<void> {
  const wizard = serveBuildWizard({
    paths: projectPaths,
    cwd: canonicalPath(process.cwd()),
    scope: options.repository ? "private" : "global",
    bot: options.bot,
    repository: options.targetRepository,
  });

  console.log(`Open your local skill tree: ${wizard.url}`);
  console.log("Keep this terminal open. Press Ctrl+C to close the editor.");

  const stop = () => {
    wizard.stop();
    process.exit(0);
  };

  process.once("SIGINT", stop);
  process.once("SIGTERM", stop);

  if (options.open === false) {
    return;
  }

  const command = process.platform === "darwin" ? "open" : "xdg-open";
  const executable = Bun.which(command);

  if (executable) {
    const arguments_ =
      process.platform === "darwin" && options.bot
        ? [executable, "-a", "Safari", wizard.url]
        : [executable, wizard.url];
    const child = Bun.spawn(arguments_, {
      stdout: "ignore",
      stderr: "ignore",
    });

    await child.exited;
  }
}
