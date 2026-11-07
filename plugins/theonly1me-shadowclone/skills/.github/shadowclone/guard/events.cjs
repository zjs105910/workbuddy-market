const { readRequestComment } = require("./comment.cjs");
const { readGithub, readIssueEvents, record, positiveNumber } = require("./records.cjs");
const {
  findPull,
  headStillRunning,
  managedPull,
  pausedEntity,
  approvedReviewer
} = require("./entities.cjs");
async function resolveTrigger(options) {
  const { clone, context, request } = options;
  if (`${context.repo.owner}/${context.repo.repo}` !== clone.repository) {
    return null;
  }
  if (record(context.payload.repository).id !== clone.repositoryId) {
    return null;
  }
  const dispatched = context.eventName === "workflow_dispatch";
  const input = record(context.payload.inputs);
  if (dispatched && ![...clone.requesters, "github-actions[bot]"].includes(context.actor)) {
    return null;
  }
  const source = dispatched ? String(input.source) : context.eventName;
  const payload = context.payload;
  const identifier = positiveNumber(dispatched ? input.identifier : source === "workflow_run" ? record(payload.workflow_run).id : source === "pull_request_review" ? record(payload.review).id : source.includes("comment") ? record(payload.comment).id : record(payload.issue).number ?? record(payload.pull_request).number);
  if (!identifier) {
    return null;
  }
  let entityNumber = positiveNumber(dispatched ? input.entity : record(payload.issue).number ?? record(payload.pull_request).number);
  let actor = context.actor;
  let actorType = record(payload.sender).type;
  let task = {};
  let head = "";
  let branch = "";
  let maintenance = false;
  let pause = false;
  let version = "";
  if (source === "workflow_run") {
    const run = await readGithub({
      request,
      route: `GET /repos/${clone.repository}/actions/runs/${identifier}`
    });
    if (run.status !== "completed" || record(run.head_repository).id !== clone.repositoryId || String(run.path).includes("shadowclone") || ["cancelled", "skipped"].includes(String(run.conclusion))) {
      return null;
    }
    branch = String(run.head_branch);
    head = String(run.head_sha);
    if (await headStillRunning({ clone, request, head })) {
      return null;
    }
    const pull = await findPull({ clone, request, branch });
    if (!pull) {
      return null;
    }
    entityNumber = positiveNumber(pull.number);
    actor = String(record(run.actor).login);
    task = pull;
    maintenance = true;
    version = String(run.run_attempt);
  } else if (["issue_comment", "pull_request_review_comment", "pull_request_review"].includes(source)) {
    const comment = await readRequestComment({
      clone,
      request,
      source,
      identifier,
      entity: entityNumber
    });
    if (!comment) {
      return null;
    }
    actor = comment.actor;
    actorType = comment.actorType;
    entityNumber = comment.entityNumber;
    maintenance = comment.maintenance;
    version = comment.version;
  } else if (source === "issues" || source === "pull_request_target") {
    entityNumber = identifier;
    const action = dispatched ? input.action : payload.action;
    if (!["opened", "labeled", "unlabeled"].includes(String(action)) || source === "pull_request_target" && action === "opened") {
      return null;
    }
    if (action !== "opened") {
      if (!dispatched && record(payload.label).name !== "shadowclone:paused") {
        return null;
      }
      const events = await readIssueEvents({
        request,
        route: `GET /repos/${clone.repository}/issues/${identifier}/events`
      });
      if (!events) {
        return null;
      }
      const event = [...events].reverse().find((entry) => entry.event === action && record(entry.label).name === "shadowclone:paused");
      if (!event) {
        return null;
      }
      actor = String(record(event.actor).login);
      version = String(event.id);
      pause = action === "labeled";
    }
    if (action === "opened") {
      task = await readGithub({
        request,
        route: `GET /repos/${clone.repository}/issues/${identifier}`
      });
      actor = String(record(task.user).login);
    }
    if (!clone.requesters.includes(actor) || actor.endsWith("[bot]")) {
      return null;
    }
  } else {
    return null;
  }
  if (!entityNumber || source !== "workflow_run" && actor === clone.botLogin) {
    return null;
  }
  if (!dispatched && source !== "workflow_run" && actor !== context.actor) {
    return null;
  }
  if (source !== "workflow_run") {
    task = await readGithub({
      request,
      route: `GET /repos/${clone.repository}/issues/${entityNumber}`
    });
  }
  if (task.state !== "open") {
    return null;
  }
  const isPull = maintenance || Object.keys(record(task.pull_request)).length > 0;
  if (isPull) {
    task = await readGithub({
      request,
      route: `GET /repos/${clone.repository}/pulls/${entityNumber}`
    });
    if (task.state !== "open" || record(record(task.head).repo).id !== clone.repositoryId) {
      return null;
    }
    if (head && head !== record(task.head).sha) {
      return null;
    }
    head = String(record(task.head).sha);
    branch = String(record(task.head).ref);
    if (maintenance && !await managedPull({ clone, request, pull: task })) {
      return null;
    }
    if (maintenance && source !== "workflow_run" && !await approvedReviewer({ clone, request, actor, actorType })) {
      return null;
    }
  } else {
    if (source === "issues" && !version && record(task.user).login !== clone.owner) {
      return null;
    }
    branch = `shadowclone/issue-${entityNumber}`;
  }
  if (!/^[A-Za-z0-9._/-]+$/.test(branch)) {
    return null;
  }
  if (!pause && await pausedEntity({ clone, request, entity: task, branch })) {
    return null;
  }
  const key = `${source}:${identifier}:${version}`;
  if (dispatched && (input.branch !== branch || String(input.head ?? "") !== head || input.key !== key || positiveNumber(input.entity) !== entityNumber)) {
    return null;
  }
  return {
    source,
    identifier,
    entity: entityNumber,
    actor,
    branch,
    head,
    key,
    kind: pause ? "pause" : isPull ? "pull" : "issue"
  };
}

module.exports = { resolveTrigger };
