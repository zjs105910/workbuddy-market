import type { Clone, EventContext, GithubRequest } from "../types";
import type { Trigger } from "./events";
import { readGithub, record, records } from "./records";

export async function allowWorker(options: {
  readonly clone: Clone;
  readonly context: EventContext;
  readonly request: GithubRequest;
  readonly trigger: Trigger;
}): Promise<boolean> {
  const { clone, context, request, trigger } = options;
  const runs = records(
    record(
      (
        await request(`GET /repos/${clone.repository}/actions/workflows/shadowclone.yml/runs`, {
          per_page: 100,
          created: `>=${new Date().toISOString().slice(0, 10)}`,
        })
      ).data,
    ).workflow_runs,
  );

  if (runs.length >= 100) {
    return false;
  }

  const title = `Shadowclone ${trigger.branch} [${trigger.key}]`;
  const previous = runs.filter(
    (run) =>
      run.id !== context.runId &&
      String(run.display_title).startsWith(`Shadowclone ${trigger.branch} [`),
  );

  if (previous.length >= clone.maximumRuns || previous.some((run) => run.display_title === title)) {
    return false;
  }

  const current = await readGithub({
    request,
    route: `GET /repos/${clone.repository}/actions/runs/${context.runId}`,
  });

  return (
    current.display_title === title &&
    current.event === "workflow_dispatch" &&
    current.head_branch === clone.defaultBranch
  );
}

export async function cancelBranchWork(options: {
  readonly clone: Clone;
  readonly request: GithubRequest;
  readonly branch: string;
}): Promise<void> {
  const runs = records(
    record(
      (
        await options.request(
          `GET /repos/${options.clone.repository}/actions/workflows/shadowclone.yml/runs`,
          { per_page: 100 },
        )
      ).data,
    ).workflow_runs,
  );

  for (const run of runs) {
    if (
      ["queued", "in_progress", "waiting", "pending"].includes(String(run.status)) &&
      String(run.display_title).startsWith(`Shadowclone ${options.branch} [`)
    ) {
      await options.request(
        `POST /repos/${options.clone.repository}/actions/runs/${run.id}/cancel`,
      );
    }
  }
}
