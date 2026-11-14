import type { Clone, GithubRequest } from "../types";
import { readGithub, record } from "./records";

const reviewOpenActions = ["opened", "ready_for_review"] as const;

export function isReviewOpenAction(action: unknown): boolean {
  return reviewOpenActions.some((candidate) => candidate === action);
}

export async function readReviewablePull(options: {
  readonly clone: Clone;
  readonly request: GithubRequest;
  readonly number: number;
}): Promise<{ readonly actor: string; readonly version: string } | null> {
  const { clone } = options;
  const pull = await readGithub({
    request: options.request,
    route: `GET /repos/${clone.repository}/pulls/${options.number}`,
  });
  const author = String(record(pull.user).login);
  const head = record(pull.head);

  if (
    pull.draft === true ||
    !clone.requesters.includes(author) ||
    author.endsWith("[bot]") ||
    record(head.repo).id !== clone.repositoryId
  ) {
    return null;
  }

  return { actor: author, version: String(head.sha) };
}
