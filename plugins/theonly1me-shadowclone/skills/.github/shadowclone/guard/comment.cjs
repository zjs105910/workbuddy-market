const { positiveNumber, readGithub, record } = require("./records.cjs");
async function readRequestComment(options) {
  const { clone, request, source, identifier, entity } = options;
  const routes = {
    issue_comment: `issues/comments/${identifier}`,
    pull_request_review_comment: `pulls/comments/${identifier}`,
    pull_request_review: `pulls/${entity}/reviews/${identifier}`
  };
  const route = routes[source];
  if (!route) {
    return null;
  }
  const comment = await readGithub({
    request,
    route: `GET /repos/${clone.repository}/${route}`
  });
  const actor = String(record(comment.user).login);
  const actorType = record(comment.user).type;
  const maintenance = source !== "issue_comment" || actorType === "Bot" && clone.reviewerBots.includes(actor);
  const category = source === "issue_comment" ? "issues" : "pulls";
  const prefix = `https://api.github.com/repos/${clone.repository}/${category}/`;
  const entityUrl = source === "pull_request_review" ? `${prefix}${entity}` : source !== "issue_comment" ? comment.pull_request_url : comment.issue_url;
  if (typeof entityUrl !== "string" || !entityUrl.startsWith(prefix)) {
    return null;
  }
  const entityNumber = positiveNumber(entityUrl.slice(prefix.length));
  const alias = clone.botLogin.replace(/\[bot\]$/, "");
  const tagged = new RegExp(`(^|\\s)@(shadowclone|${alias})(?=$|[\\s,:])`, "i").test(String(comment.body));
  if (!entityNumber || !maintenance && (!tagged || !clone.requesters.includes(actor) || actorType === "Bot")) {
    return null;
  }
  return {
    actor,
    actorType,
    entityNumber,
    maintenance,
    version: String(comment.updated_at ?? comment.submitted_at)
  };
}

module.exports = { readRequestComment };
