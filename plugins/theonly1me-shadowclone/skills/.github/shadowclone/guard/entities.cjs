const { readGithub, readIssueEvents, record, records } = require("./records.cjs");
async function managedPull(options) {
  if (record(options.pull.user).id === options.clone.botId) {
    return true;
  }
  if (!records(options.pull.labels).some((label) => label.name === "shadowclone:managed")) {
    return false;
  }
  const events = await readIssueEvents({
    request: options.request,
    route: `GET /repos/${options.clone.repository}/issues/${options.pull.number}/events`
  });
  if (!events) {
    return false;
  }
  const latest = [...events].reverse().find((event) => record(event.label).name === "shadowclone:managed");
  return latest?.event === "labeled" && record(latest.actor).id === options.clone.botId;
}
async function findPull(options) {
  const pulls = records((await options.request(`GET /repos/${options.clone.repository}/pulls`, {
    state: "open",
    head: `${options.clone.repository.split("/")[0]}:${options.branch}`,
    per_page: 100
  })).data);
  return pulls.find((pull) => record(pull.head).ref === options.branch) ?? null;
}
async function pausedEntity(options) {
  if (records(options.entity.labels).some((label) => label.name === "shadowclone:paused")) {
    return true;
  }
  const issue = /^shadowclone\/issue-(\d+)$/.exec(options.branch)?.[1];
  if (!issue || Number(issue) === options.entity.number) {
    return false;
  }
  const origin = await readGithub({
    request: options.request,
    route: `GET /repos/${options.clone.repository}/issues/${issue}`
  });
  return records(origin.labels).some((label) => label.name === "shadowclone:paused");
}
async function headStillRunning(options) {
  const runs = records(record((await options.request(`GET /repos/${options.clone.repository}/actions/runs`, {
    head_sha: options.head,
    per_page: 100
  })).data).workflow_runs);
  return runs.some((run) => !String(run.path).includes("shadowclone") && ["queued", "in_progress", "requested", "pending"].includes(String(run.status)));
}
async function approvedReviewer(options) {
  if (options.actor === options.clone.botLogin) {
    return false;
  }
  if (options.actorType === "Bot" || options.actor.endsWith("[bot]")) {
    return options.clone.reviewerBots.includes(options.actor);
  }
  if (options.clone.requesters.includes(options.actor)) {
    return true;
  }
  const permission = await readGithub({
    request: options.request,
    route: `GET /repos/${options.clone.repository}/collaborators/${options.actor}/permission`
  });
  return ["admin", "maintain", "write"].includes(String(permission.permission));
}

module.exports = { managedPull, findPull, pausedEntity, headStillRunning, approvedReviewer };
