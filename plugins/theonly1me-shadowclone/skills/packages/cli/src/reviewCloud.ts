import { createReviewUpdatePull, githubApi, readInstalledClone, runGh } from "@shadowclone/cloud";
import { projectPaths } from "@shadowclone/core";
import { handleSetupCommand } from "./setup";
import { runWebWizard } from "./webWizard";

export async function requestCloudReview(options: {
  readonly repository: string;
  readonly number: number;
}): Promise<void> {
  const { repository, number } = options;
  const token = (await runGh({ arguments: ["auth", "token"] })).trim();
  const installed = await readInstalledClone({ repository, token });

  if (installed === null) {
    if (!(await Bun.file(projectPaths.configFile).exists())) {
      await handleSetupCommand({ command: "init", arguments: [] });
    }

    console.log(`${repository} has no GitHub clone yet. Set it up on the page that opens, merge its setup PR, and then run shadowclone review ${number} --cloud again.`);
    await runWebWizard({ bot: true, targetRepository: repository, open: true });
    return;
  }

  if (!installed.hasReview) {
    const url = await createReviewUpdatePull({ clone: installed.clone, token, api: githubApi });

    console.log(`The clone's workflows cannot review yet. Merge ${url}, and then run shadowclone review ${number} --cloud again.`);
    return;
  }

  await runGh({ arguments: ["pr", "comment", String(number), "--repo", repository, "--body", "@shadowclone review"] });
  console.log(`Asked ${installed.clone.botLogin} to review ${repository}#${number}. The review appears on the pull request when the workflow finishes.`);
}
