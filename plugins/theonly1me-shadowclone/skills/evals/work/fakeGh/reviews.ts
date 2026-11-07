import type { FakeState, ReviewThread } from "./state";
import { takeId } from "./state";

export function releasedThreads(options: {
  readonly state: FakeState;
  readonly pullRequest: number;
}): readonly ReviewThread[] {
  return options.state.threads.filter(
    (thread) => thread.pullRequest === options.pullRequest && thread.released,
  );
}

export function threadByCommentId(options: {
  readonly state: FakeState;
  readonly commentId: number;
}): ReviewThread | undefined {
  return options.state.threads.find(
    (thread) => thread.released && thread.comments.some((comment) => comment.id === options.commentId),
  );
}

export function threadById(options: {
  readonly state: FakeState;
  readonly threadId: string;
}): ReviewThread | undefined {
  return options.state.threads.find((thread) => thread.released && thread.id === options.threadId);
}

export function addReply(options: {
  readonly state: FakeState;
  readonly thread: ReviewThread;
  readonly body: string;
}): number {
  const id = takeId(options.state);

  options.thread.comments.push({
    id,
    author: options.state.viewer,
    bot: false,
    body: options.body,
    createdAt: new Date().toISOString(),
  });

  return id;
}

export function setResolved(options: {
  readonly state: FakeState;
  readonly thread: ReviewThread;
  readonly resolved: boolean;
}): void {
  options.thread.resolved = options.resolved;
  options.thread.resolvedBy = options.resolved ? options.state.viewer : null;
}

function userRecord(options: { readonly login: string; readonly bot: boolean }) {
  return { login: options.login, type: options.bot ? "Bot" : "User" };
}

export function restComments(options: {
  readonly state: FakeState;
  readonly pullRequest: number;
}): readonly Readonly<Record<string, unknown>>[] {
  const base = `https://github.com/${options.state.repository.owner}/${options.state.repository.name}/pull/${options.pullRequest}`;

  return releasedThreads(options).flatMap((thread) => {
    const [first] = thread.comments;

    return thread.comments.map((comment) => ({
      id: comment.id,
      node_id: `PRRC_${comment.id}`,
      pull_request_review_id: first?.id ?? comment.id,
      path: thread.path,
      line: thread.line,
      original_line: thread.line,
      body: comment.body,
      user: userRecord({ login: comment.author, bot: comment.bot }),
      in_reply_to_id: first && first.id !== comment.id ? first.id : undefined,
      created_at: comment.createdAt,
      html_url: `${base}#discussion_r${comment.id}`,
    }));
  });
}

export function graphqlThreads(options: {
  readonly state: FakeState;
  readonly pullRequest: number;
}): Readonly<Record<string, unknown>> {
  const nodes = releasedThreads(options).map((thread) => ({
    id: thread.id,
    isResolved: thread.resolved,
    isOutdated: false,
    path: thread.path,
    line: thread.line,
    comments: {
      totalCount: thread.comments.length,
      nodes: thread.comments.map((comment) => ({
        id: `PRRC_${comment.id}`,
        databaseId: comment.id,
        author: { login: comment.author, __typename: comment.bot ? "Bot" : "User" },
        body: comment.body,
        createdAt: comment.createdAt,
        path: thread.path,
        line: thread.line,
      })),
    },
  }));

  return {
    data: {
      repository: {
        pullRequest: {
          number: options.pullRequest,
          reviewThreads: { totalCount: nodes.length, pageInfo: { hasNextPage: false, endCursor: null }, nodes },
        },
      },
    },
  };
}
