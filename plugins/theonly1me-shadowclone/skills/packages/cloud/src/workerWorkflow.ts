import { claudeWorkStep, codexWorkSteps, jobMinutes, saveWorkStep } from "./agentSteps";
import { botToken, botTokenSteps, skillsSteps } from "./identitySteps";
import { reviewJobs, type ReviewPins, type ReviewVersions } from "./reviewJobs";
import type { Clone } from "./types";

export function workerWorkflow(options: {
  readonly clone: Clone;
  readonly configured: string;
  readonly pins: ReviewPins & { readonly claude: string };
  readonly versions: ReviewVersions;
  readonly prompt: string;
}): string {
  const { clone, configured, pins } = options;
  const allowed = "steps.validate.outputs.allowed == 'true'";
  const token = botToken(clone);
  const environment = [
    `          SHADOWCLONE_ENTITY: \${{ steps.validate.outputs.entity }}`,
    `          SHADOWCLONE_BRANCH: \${{ steps.validate.outputs.branch }}`,
    `          SHADOWCLONE_SOURCE: \${{ steps.validate.outputs.source }}`,
    `          SHADOWCLONE_IDENTIFIER: \${{ steps.validate.outputs.identifier }}`,
  ].join("\n");
  const agent =
    clone.engine === "codex"
      ? codexWorkSteps({ clone, token, when: allowed, version: options.versions.codex, prompt: options.prompt, environment })
      : claudeWorkStep({ clone, token, when: allowed, pin: pins.claude, prompt: options.prompt, environment });
  const concurrencyGroup =
    clone.engine === "codex" && clone.codexAuth === "plan"
      ? `shadowclone-${clone.repositoryId}-codex-login`
      : `shadowclone-${clone.repositoryId}-\${{ needs.guard.outputs.branch }}`;
  const guard = `${configured}
            const { resolveTrigger } = require('./.github/shadowclone/guard/events.cjs');
            const { allowWorker } = require('./.github/shadowclone/guard/policy.cjs');
            const request = github.request.bind(github);
            const trigger = await resolveTrigger({ clone: config, context, request });
            const allowed = trigger && trigger.kind !== 'pause' &&
              await allowWorker({ clone: config, context, request, trigger });

            core.setOutput('allowed', allowed ? 'true' : 'false');

            if (allowed) {
              for (const [name, value] of Object.entries(trigger)) {
                core.setOutput(name, String(value));
              }
            }`;

  return `name: Shadowclone
run-name: 'Shadowclone \${{ inputs.branch }} [\${{ inputs.key }}]'
on:
  workflow_dispatch:
    inputs:
      source: { required: true, type: string }
      identifier: { required: true, type: string }
      entity: { required: true, type: string }
      branch: { required: true, type: string }
      head: { required: false, type: string }
      key: { required: true, type: string }
      action: { required: false, type: string }
permissions:
  contents: read
  issues: read
  pull-requests: read
  actions: read
jobs:
  guard:
    if: >-
      github.repository_id == '${clone.repositoryId}' &&
      github.ref == 'refs/heads/${clone.defaultBranch.replaceAll("'", "''")}'
    runs-on: ubuntu-latest
    timeout-minutes: 3
    outputs:
      allowed: \${{ steps.validate.outputs.allowed }}
      branch: \${{ steps.validate.outputs.branch }}
      kind: \${{ steps.validate.outputs.kind }}
      source: \${{ steps.validate.outputs.source }}
      identifier: \${{ steps.validate.outputs.identifier }}
      entity: \${{ steps.validate.outputs.entity }}
      head: \${{ steps.validate.outputs.head }}
    steps:
      - uses: ${pins.checkout}
        with:
          persist-credentials: false
      - uses: ${pins.script}
        id: validate
        with:
          script: |
            ${guard}
  work:
    needs: guard
    if: needs.guard.outputs.allowed == 'true' && needs.guard.outputs.kind != 'review'
    runs-on: ubuntu-latest
    timeout-minutes: ${jobMinutes}
    environment: shadowclone
    concurrency:
      group: ${concurrencyGroup}
      cancel-in-progress: false
    steps:
      - uses: ${pins.checkout}
        with:
          persist-credentials: false
          fetch-depth: 0
      - uses: ${pins.script}
        id: validate
        with:
          script: |
            ${guard}
${botTokenSteps({
  clone,
  pins,
  permissions: ["contents: write", "issues: write", "pull-requests: write", "actions: write", "checks: read", "workflows: write"],
  when: allowed,
})}
      - uses: ${pins.script}
        if: ${allowed}
        with:
          github-token: ${token}
          script: |
            const { reactToRequest } = require('./.github/shadowclone/react.cjs');
            await reactToRequest({
              repository: '${clone.repository}',
              source: String('\${{ steps.validate.outputs.source }}'),
              identifier: Number('\${{ steps.validate.outputs.identifier }}'),
              entity: Number('\${{ steps.validate.outputs.entity }}'),
              request: github.request.bind(github),
              warn: core.warning,
            });
${skillsSteps({ clone, pins, when: allowed })}
      - uses: ${pins.script}
        if: ${allowed}
        with:
          github-token: ${token}
          script: |
            if (String('\${{ steps.validate.outputs.kind }}') === 'pull') {
              await github.rest.issues.addLabels({
                ...context.repo,
                issue_number: Number('\${{ steps.validate.outputs.entity }}'),
                labels: ['shadowclone:managed'],
              });
            }
${agent}
${saveWorkStep({ clone, token, when: allowed })}
${reviewJobs({ clone, pins, versions: options.versions })}`;
}
