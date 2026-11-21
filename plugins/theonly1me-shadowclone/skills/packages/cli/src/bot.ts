import path from "node:path";
import { canonicalPath, projectPaths } from "@shadowclone/core";
import {
  checklistText,
  cloneStatus,
  exportGuidance,
  ghApiCall,
  readCloudChecklist,
  readInstallation,
  writeDeliveryFiles,
} from "@shadowclone/cloud";
import { setUpBotInTerminal } from "./botSetup";
import { runWebWizard } from "./webWizard";

const setupUsage =
  "Use shadowclone bot setup [--bot login] [--engine claude|codex] [--codex-auth api-key|plan] [--app] [--repo owner/repository] [--yes] [--no-open].";

function flagValue(options: { readonly arguments: readonly string[]; readonly flag: string }): string | null {
  const index = options.arguments.indexOf(options.flag);

  return index < 0 ? null : (options.arguments[index + 1] ?? "");
}

async function setup(arguments_: readonly string[]): Promise<void> {
  const repository = flagValue({ arguments: arguments_, flag: "--repo" });
  const botLogin = flagValue({ arguments: arguments_, flag: "--bot" });
  const engine = flagValue({ arguments: arguments_, flag: "--engine" }) ?? "claude";
  const codexAuth = flagValue({ arguments: arguments_, flag: "--codex-auth" }) ?? "api-key";
  const known = new Set(["--app", "--yes", "--no-open", "--repo", "--bot", "--engine", "--codex-auth"]);
  const values = new Set([repository, botLogin, engine, codexAuth]);

  if (
    (repository !== null && !/^[\w.-]+\/[\w.-]+$/.test(repository)) ||
    (botLogin !== null && !/^[A-Za-z0-9-]{1,39}$/.test(botLogin)) ||
    (botLogin !== null && arguments_.includes("--app")) ||
    (engine !== "claude" && engine !== "codex") ||
    (codexAuth !== "api-key" && codexAuth !== "plan") ||
    arguments_.some((argument) => !known.has(argument) && !values.has(argument))
  ) {
    throw new Error(setupUsage);
  }

  if (botLogin !== null) {
    await setUpBotInTerminal({
      repository,
      botLogin,
      engine,
      codexAuth,
      yes: arguments_.includes("--yes"),
      open: !arguments_.includes("--no-open"),
    });
    return;
  }

  await runWebWizard({ bot: true, targetRepository: repository ?? undefined, open: !arguments_.includes("--no-open") });
}

async function status(arguments_: readonly string[]): Promise<void> {
  const repository = flagValue({ arguments: arguments_, flag: "--repo" });

  if (repository === null) {
    console.log(JSON.stringify(await cloneStatus(projectPaths), null, 2));
    return;
  }

  const installation = await readInstallation({ paths: projectPaths, repository });

  if (installation === null) {
    throw new Error(`No cloud bot setup is saved for ${repository}. Run shadowclone bot setup first.`);
  }

  console.log(checklistText(await readCloudChecklist({ call: ghApiCall, clone: installation.clone, pullUrl: installation.pullUrl })));
}

async function exportSkills(arguments_: readonly string[]): Promise<void> {
  const skills: string[] = [];
  let destination: string | null = null;

  for (let position = 0; position < arguments_.length; position += 2) {
    const flag = arguments_[position];
    const value = arguments_[position + 1];

    if (!value || !["--skill", "--output"].includes(flag ?? "")) {
      throw new Error("Use shadowclone bot export --skill shadowclone-work [--skill name] --output folder.");
    }

    if (flag === "--skill") {
      skills.push(value);
    }

    if (flag === "--output") {
      destination = value;
    }
  }

  if (!destination) {
    throw new Error("Choose a private output folder outside the repository checkout.");
  }

  const cwd = canonicalPath(process.cwd());
  const output = canonicalPath(destination);
  const relative = path.relative(cwd, output);

  if (!relative || (!relative.startsWith(`..${path.sep}`) && !path.isAbsolute(relative))) {
    throw new Error("The guidance output must stay outside the repository checkout.");
  }

  const delivery = await exportGuidance({ paths: projectPaths, cwd, skills });

  await writeDeliveryFiles({ files: delivery.files, destination: output });
  console.log(JSON.stringify({ output, skills: delivery.skills, files: delivery.files.length, fingerprint: delivery.fingerprint }, null, 2));
}

export async function botCommand(arguments_: readonly string[]): Promise<void> {
  const [operation, ...rest] = arguments_;

  if (operation === "setup") {
    await setup(rest);
    return;
  }

  if (operation === "status") {
    await status(rest);
    return;
  }

  if (operation === "export") {
    await exportSkills(rest);
    return;
  }

  console.log("shadowclone bot setup [--bot login] [--engine claude|codex] [--codex-auth api-key|plan] [--app] [--repo owner/repository] [--yes] [--no-open]");
  console.log("shadowclone bot export --skill shadowclone-work [--skill name] --output folder");
  console.log("shadowclone bot status [--repo owner/repository]");
}
