import type { Clone, GithubRequest } from "../types";
import { positiveNumber, readGithub, record } from "./records";

export function mentionNames(clone: Clone): readonly string[] {
  const login = clone.botLogin.replace(/\[bot\]$/, "");

  return clone.identity.kind === "app" ? ["shadowclone", login] : [login];
}

export async function readRequestComment(options: {
  readonly clone: Clone;
  readonly request: GithubRequest;
  readonly source: string;
  readonly identifier: number;
  readonly entity: number | null;
}) {
  const { clone, request, source, identifier, entity } = options;
  const routes: Record<string, string> = {
    issue_comment: `issues/comments/${identifier}`,
    pull_request_review_comment: `pulls/comments/${identifier}`,
    pull_request_review: `pulls/${entity}/reviews/${identifier}`,
  };
  const route = routes[source];

  if (!route) {
    return null;
  }

  const comment = await readGithub({
    request,
    route: `GET /repos/${clone.repository}/${route}`,
  });
  const actor = String(record(comment.user).login);
  const actorType = record(comment.user).type;
  const maintenance =
    source !== "issue_comment" || (actorType === "Bot" && clone.reviewerBots.includes(actor));
  const category = source === "issue_comment" ? "issues" : "pulls";
  const prefix = `https://api.github.com/repos/${clone.repository}/${category}/`;
  const entityUrl =
    source === "pull_request_review"
      ? `${prefix}${entity}`
      : source !== "issue_comment"
        ? comment.pull_request_url
        : comment.issue_url;

  if (typeof entityUrl !== "string" || !entityUrl.startsWith(prefix)) {
    return null;
  }

  const entityNumber = positiveNumber(entityUrl.slice(prefix.length));
  const names = mentionNames(clone).join("|");
  const tagged = new RegExp(`(^|\\s)@(${names})(?=$|[\\s,:])`, "i").test(String(comment.body));
  const [firstLine = ""] = String(comment.body).split("\n");
  const review = new RegExp(`^\\s*@(${names})\\s+review\\s*$`, "i").test(firstLine);

  if (
    !entityNumber ||
    (!maintenance && (!tagged || !clone.requesters.includes(actor) || actorType === "Bot"))
  ) {
    return null;
  }

  return {
    actor,
    actorType,
    entityNumber,
    maintenance,
    review: review && !maintenance,
    version: String(comment.updated_at ?? comment.submitted_at),
  };
}
