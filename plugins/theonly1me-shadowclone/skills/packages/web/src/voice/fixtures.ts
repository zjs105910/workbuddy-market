import type { HostRunner } from "./collect";
import type { VoiceDraft } from "./profile";

export const syntheticToken = `ghp_${"a1B2c3D4e5F6g7H8i9J0k1L2m3N4o5P6q7R8"}`;

export const keptPullRequest =
  "Keep cursors after a failed index\n\nThe index step threw away every cursor when one file failed to parse, so the next run started over. This keeps the cursors for files that worked.";
export const keptReview = "Can we name this after what it checks? The current name says how it works, and the next reader needs the why.";
export const keptCommit = "fix: keep the retry count when the queue restarts";

const writing = {
  data: {
    viewer: {
      login: "synthetic-writer",
      pullRequests: {
        nodes: [
          { title: "Keep cursors after a failed index", body: keptPullRequest.split("\n\n")[1], headRefName: "fix/cursors" },
          { title: "Add the sync command", body: "This adds sync and its tests for the queue.", headRefName: "codex/add-sync" },
          { title: "Tidy the parser", body: "Moves helpers.\n\nGenerated with [Claude Code](https://claude.com/claude-code)", headRefName: "tidy" },
          { title: "chore(main): release 1.4.0", body: "Release notes for the synthetic project.", headRefName: "release-please" },
          { title: "Fix the flaky clock test", body: "Uses a fixed clock.\n\n```ts\nconst secret = 1;\n```\nThe test no longer depends on the wall clock.", headRefName: "fix/clock" },
          null,
        ],
      },
      contributionsCollection: {
        pullRequestReviewContributions: {
          nodes: [
            { pullRequestReview: { body: keptReview, comments: { nodes: [{ body: `Please rotate ${syntheticToken} before the next deploy goes out.` }] } } },
            { pullRequestReview: { body: "", comments: { nodes: [null] } } },
            null,
          ],
        },
      },
    },
  },
};

const commits = [
  { commit: { message: keptCommit } },
  { commit: { message: "Merge pull request #12 from synthetic/branch" } },
  { commit: { message: "feat: add the queue\n\nCo-Authored-By: Claude <noreply@example.com>" } },
];

export function fakeGitHub(): { readonly run: HostRunner; readonly calls: string[][] } {
  const calls: string[][] = [];
  const run: HostRunner = async (options) => {
    calls.push([...options.arguments]);

    const stdout = options.arguments[1] === "api" ? JSON.stringify(writing) : JSON.stringify(commits);

    return { exitCode: 0, stdout, stderr: "" };
  };

  return { run, calls };
}

export const invented: VoiceDraft = {
  profile: {
    traits: ["Short sentences", "Names the user-visible symptom first", "No hedging"],
    do: ["Lead with what broke", "Give real numbers"],
    dont: ["Sell the change", "Narrate the investigation"],
  },
  samples: {
    pullRequest: "Show the forecast for the saved city\n\nThe weather card showed the default city after a refresh.",
    reviewComment: "Can this read the shelf code from the catalog record instead of the label?",
    commitMessage: "fix: keep the saved city after a refresh",
  },
};
