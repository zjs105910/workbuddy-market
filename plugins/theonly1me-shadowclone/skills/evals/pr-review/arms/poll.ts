import { ghJson } from "../github";

export async function postComment(options: { readonly repository: string; readonly number: number; readonly body: string }): Promise<void> {
  await ghJson(["api", "--method", "POST", `repos/${options.repository}/issues/${options.number}/comments`, "-f", `body=${options.body}`]);
}

export async function waitFor<Result>(options: {
  readonly check: () => Promise<Result | null>;
  readonly timeoutMilliseconds: number;
  readonly intervalMilliseconds: number;
}): Promise<Result | null> {
  const deadline = Date.now() + options.timeoutMilliseconds;

  while (Date.now() < deadline) {
    const result = await options.check().catch(() => null);

    if (result !== null) {
      return result;
    }

    await Bun.sleep(options.intervalMilliseconds);
  }

  return null;
}

export async function reviewActivity(options: { readonly repository: string; readonly number: number }) {
  const [reviews, reviewComments, issueComments] = await Promise.all([
    ghJson(["api", "--paginate", `repos/${options.repository}/pulls/${options.number}/reviews`]),
    ghJson(["api", "--paginate", `repos/${options.repository}/pulls/${options.number}/comments`]),
    ghJson(["api", "--paginate", `repos/${options.repository}/issues/${options.number}/comments`]),
  ]);

  return { reviews, reviewComments, issueComments };
}
