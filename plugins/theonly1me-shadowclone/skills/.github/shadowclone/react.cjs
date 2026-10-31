function reactionRoute(options) {
  const { repository, source, identifier, entity } = options;
  if (source === "issues") {
    return `POST /repos/${repository}/issues/${entity}/reactions`;
  }
  if (source === "issue_comment") {
    return `POST /repos/${repository}/issues/comments/${identifier}/reactions`;
  }
  if (source === "pull_request_review_comment") {
    return `POST /repos/${repository}/pulls/comments/${identifier}/reactions`;
  }
  return null;
}
async function reactToRequest(options) {
  const route = reactionRoute(options);
  if (!route) {
    return;
  }
  try {
    await options.request(route, { content: "eyes" });
  } catch (error) {
    options.warn(`The clone could not react to the request: ${error instanceof Error ? error.message : String(error)}`);
  }
}

module.exports = { reactToRequest };
