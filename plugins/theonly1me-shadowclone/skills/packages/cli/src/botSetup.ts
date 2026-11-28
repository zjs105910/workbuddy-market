import { projectPaths } from "@shadowclone/core";
import {
  checklistText,
  ghApiCall,
  openPage,
  pendingPages,
  readCloudChecklist,
  remainingSteps,
  runGh,
  setUpAccountClone,
} from "@shadowclone/cloud";
import { promptConfirmation } from "./confirm";

const pollMilliseconds = 15_000;
const pollLimitMilliseconds = 30 * 60_000;

async function currentRepository(cwd: string): Promise<string> {
  const child = Bun.spawn(
    ["gh", "repo", "view", "--json", "nameWithOwner", "--jq", ".nameWithOwner"],
    { cwd, stdout: "pipe", stderr: "ignore" },
  );
  const output = (await new Response(child.stdout).text()).trim();

  if ((await child.exited) !== 0 || !/^[\w.-]+\/[\w.-]+$/.test(output)) {
    throw new Error(
      "Run setup in a GitHub repository checkout, or name it with --repo owner/repository.",
    );
  }

  return output;
}

export async function setUpBotInTerminal(options: {
  readonly repository: string | null;
  readonly botLogin: string;
  readonly engine: "claude" | "codex";
  readonly codexAuth: "api-key" | "plan";
  readonly yes: boolean;
  readonly open: boolean;
}): Promise<void> {
  const cwd = process.cwd();
  const repository = options.repository ?? (await currentRepository(cwd));
  const setup = (approveSkills: boolean) =>
    setUpAccountClone({
      paths: projectPaths,
      cwd,
      repository,
      botLogin: options.botLogin,
      approveSkills,
      engine: options.engine,
      codexAuth: options.codexAuth,
      call: ghApiCall,
      command: runGh,
    });
  const first = await setup(false);

  if (first.kind === "needs-account") {
    console.log(
      `Create the GitHub account ${first.login} for the bot, then run this command again: ${first.signupUrl}`,
    );

    if (options.open) {
      await openPage(first.signupUrl);
    }

    return;
  }

  if (first.kind === "needs-approval") {
    console.log(
      `Setup pushes these ${first.files.length} files to the private repository ${first.skillsRepository}:`,
    );
    console.log(first.files.map((file) => `  ${file.path} (${file.bytes} bytes)`).join("\n"));

    if (!options.yes && !promptConfirmation("Push them?")) {
      console.log("Nothing changed.");
      return;
    }
  }

  const outcome = first.kind === "configured" ? first : await setup(true);

  if (outcome.kind !== "configured") {
    throw new Error("Setup stopped before it configured the repository. Run it again.");
  }

  console.log([...outcome.warnings, checklistText(outcome.checklist)].join("\n\n"));

  for (const url of options.open ? pendingPages(outcome.checklist) : []) {
    await openPage(url);
  }

  const finishedBy = Date.now() + pollLimitMilliseconds;
  let remaining = remainingSteps(outcome.checklist).filter((item) => item.key !== "invitation");

  while (remaining.length > 0 && Date.now() < finishedBy) {
    console.log(
      `Waiting for: ${remaining.map((item) => item.title).join(", ")}. Press Ctrl+C to stop; run shadowclone bot status later.`,
    );
    await Bun.sleep(pollMilliseconds);

    const checklist = await readCloudChecklist({
      call: ghApiCall,
      clone: outcome.clone,
      pullUrl: outcome.pullUrl,
    });
    const next = remainingSteps(checklist).filter((item) => item.key !== "invitation");

    for (const item of remaining.filter(
      (pending) => !next.some((still) => still.key === pending.key),
    )) {
      console.log(`Done: ${item.title}`);
    }

    remaining = next;
  }

  if (remaining.length === 0) {
    console.log(`Setup is complete. Mention @${outcome.clone.botLogin} on an issue to start work.`);
  }
}
