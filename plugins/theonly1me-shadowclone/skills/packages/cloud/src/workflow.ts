import product from "@shadowclone/core/product.json";
import { runtimeSources } from "./guardSource" with { type: "macro" };
import { cloneSchema, type Clone } from "./types";
import { cloudPrompt } from "./prompt";
import { workerWorkflow } from "./workerWorkflow";

export const actionPins = {
  checkout: "actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1",
  script: "actions/github-script@ed597411d8f924073f98dfc5c65a23a2325f34cd",
  appToken: "actions/create-github-app-token@fee1f7d63c2ff003460e3d139729b119787bc349",
  claude: "anthropics/claude-code-action@ed670b4cf9de2a5a570d130d2f6197b9e543cd64",
  setupBun: "oven-sh/setup-bun@0c5077e51419868618aeaa5fe8019c62421857d6",
  uploadArtifact: "actions/upload-artifact@043fb46d1a93c77aae656e7c1c64a875d1fc6a0a",
  downloadArtifact: "actions/download-artifact@3e5f45b2cfb9172054b4087a40e8e0b5a5461e7c",
} as const;

export const reviewVersions = {
  shadowclone: product.version,
  claudeCode: "2.1.286",
  codex: "0.159.0",
  bun: "1.4.2",
} as const;

export function renderWorkflows(input: Clone): Record<string, string> {
  const clone = cloneSchema.parse(input);
  const configured = `const config = ${JSON.stringify(clone, null, 2).replaceAll("\n", "\n            ")};`;
  const worker = workerWorkflow({
    clone,
    configured,
    pins: actionPins,
    versions: reviewVersions,
    prompt: cloudPrompt(clone.engine),
  });
  const relay = `name: Shadowclone relay
on:
  issues:
    types: [opened, labeled, unlabeled]
  issue_comment:
    types: [created, edited]
  pull_request_review_comment:
    types: [created, edited]
  pull_request_review:
    types: [submitted]
  pull_request_target:
    types: [labeled, unlabeled, opened, ready_for_review]
  workflow_run:
    workflows: ["*"]
    types: [completed]
permissions:
  contents: read
  issues: read
  pull-requests: read
  actions: write
jobs:
  relay:
    if: github.repository_id == '${clone.repositoryId}'
    runs-on: ubuntu-latest
    timeout-minutes: 3
    steps:
      - uses: ${actionPins.checkout}
        with:
          ref: ${JSON.stringify(clone.defaultBranch)}
          persist-credentials: false
      - uses: ${actionPins.script}
        with:
          script: |
            ${configured}
            const { resolveTrigger } = require('./.github/shadowclone/guard/events.cjs');
            const { cancelBranchWork } = require('./.github/shadowclone/guard/policy.cjs');
            const request = github.request.bind(github);
            const trigger = await resolveTrigger({ clone: config, context, request });

            if (!trigger) {
              return;
            }

            if (trigger.kind === 'pause') {
              await cancelBranchWork({
                clone: config,
                request,
                branch: trigger.branch,
              });

              return;
            }

            await github.rest.actions.createWorkflowDispatch({
              ...context.repo,
              workflow_id: 'shadowclone.yml',
              ref: config.defaultBranch,
              inputs: {
                source: trigger.source,
                identifier: String(trigger.identifier),
                entity: String(trigger.entity),
                branch: trigger.branch,
                head: trigger.head,
                key: trigger.key,
                action: String(context.payload.action || ''),
              },
            });
`;

  return {
    ...runtimeSources(),
    ".github/workflows/shadowclone-relay.yml": relay,
    ".github/workflows/shadowclone.yml": worker,
  };
}
