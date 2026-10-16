import { runWizard } from "./wizard";

type BrowserOptions = { readonly repository: boolean; readonly open: boolean };

export async function runWizardCommand(options: {
  readonly arguments: readonly string[];
  readonly terminal?: () => Promise<void>;
  readonly browser?: (options: BrowserOptions) => Promise<void>;
}): Promise<void> {
  const supported = new Set(["--cli", "--web", "--repo", "--no-open"]);
  const terminal = options.arguments.includes("--cli");

  if (
    options.arguments.some((argument) => !supported.has(argument)) ||
    (terminal && options.arguments.some((argument) => argument !== "--cli"))
  ) {
    throw new Error("Use wizard [--repo] [--no-open] or wizard --cli");
  }

  if (terminal) {
    await (options.terminal ?? runWizard)();

    return;
  }

  const browser = options.browser ?? (await import("./webWizard")).runWebWizard;

  await browser({
    repository: options.arguments.includes("--repo"),
    open: !options.arguments.includes("--no-open"),
  });
}
