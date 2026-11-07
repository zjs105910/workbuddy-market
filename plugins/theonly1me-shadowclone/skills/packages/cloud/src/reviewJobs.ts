import { codexInstallStep, codexLoginReturnStep, codexLoginStep } from "./agentSteps";
import { botToken, botTokenSteps } from "./identitySteps";
import type { Clone } from "./types";

export type ReviewPins = {
  readonly checkout: string;
  readonly script: string;
  readonly appToken: string;
  readonly setupBun: string;
  readonly uploadArtifact: string;
  readonly downloadArtifact: string;
};

export type ReviewVersions = {
  readonly shadowclone: string;
  readonly claudeCode: string;
  readonly codex: string;
  readonly bun: string;
};

const reviewCondition =
  "needs.guard.outputs.allowed == 'true' && needs.guard.outputs.kind == 'review'";

function installSteps(options: { readonly pins: ReviewPins; readonly versions: ReviewVersions; readonly claude: boolean }): string {
  const claude = options.claude
    ? `\n          npm install --global --no-audit --no-fund --prefix "$RUNNER_TEMP/claude" "@anthropic-ai/claude-code@${options.versions.claudeCode}"\n          echo "$RUNNER_TEMP/claude/bin" >> "$GITHUB_PATH"`
    : "";

  return `      - uses: ${options.pins.setupBun}
        with:
          bun-version: ${options.versions.bun}
      - name: Install Shadowclone
        working-directory: \${{ runner.temp }}
        run: |
          npm install --global --ignore-scripts --no-audit --no-fund --prefix "$RUNNER_TEMP/shadowclone" "@shadowclone/cli@${options.versions.shadowclone}"${claude}`;
}

function pullCheckout(options: { readonly pins: ReviewPins; readonly fullHistory: boolean }): string {
  return `      - uses: ${options.pins.checkout}
        with:
          ref: \${{ needs.guard.outputs.head }}
          path: pull-request
          fetch-depth: ${options.fullHistory ? 0 : 1}
          persist-credentials: false`;
}

function artifact(options: { readonly pin: string; readonly name: string; readonly upload: boolean; readonly optional?: boolean }): string {
  const location = options.upload
    ? `path: \${{ runner.temp }}/${options.name}.json\n          retention-days: 1\n          overwrite: true`
    : `path: \${{ runner.temp }}`;

  return `      - uses: ${options.pin}${options.optional ? "\n        continue-on-error: true" : ""}
        with:
          name: review-${options.name}
          ${location}`;
}

export function reviewJobs(options: {
  readonly clone: Clone;
  readonly pins: ReviewPins;
  readonly versions: ReviewVersions;
}): string {
  const { clone, pins, versions } = options;
  const shadowclone = '"$RUNNER_TEMP/shadowclone/bin/shadowclone" review';
  const stageEnvironment = `          ENTITY: \${{ needs.guard.outputs.entity }}
          HEAD_SHA: \${{ needs.guard.outputs.head }}`;
  const tokenSteps = (permissions: readonly string[]) => botTokenSteps({ clone, pins, permissions, when: null });
  const codex = clone.engine === "codex";
  const planConcurrency =
    codex && clone.codexAuth === "plan"
      ? `\n    concurrency:\n      group: shadowclone-${clone.repositoryId}-codex-login\n      cancel-in-progress: false`
      : "";

  return `  review-acknowledge:
    needs: guard
    if: ${reviewCondition}
    runs-on: ubuntu-latest
    timeout-minutes: 3
    environment: shadowclone
    steps:
      - uses: ${pins.checkout}
        with:
          persist-credentials: false
${tokenSteps(["issues: write", "pull-requests: write"])}
      - uses: ${pins.script}
        with:
          github-token: ${botToken(clone)}
          script: |
            const { reactToRequest } = require('./.github/shadowclone/react.cjs');
            await reactToRequest({
              repository: '${clone.repository}',
              source: String('\${{ needs.guard.outputs.source }}'),
              identifier: Number('\${{ needs.guard.outputs.identifier }}'),
              entity: Number('\${{ needs.guard.outputs.entity }}'),
              request: github.request.bind(github),
              warn: core.warning,
            });
  review-prepare:
    needs: guard
    if: ${reviewCondition}
    runs-on: ubuntu-latest
    timeout-minutes: 10
    permissions:
      contents: read
      pull-requests: read
    steps:
${pullCheckout({ pins, fullHistory: true })}
${installSteps({ pins, versions, claude: false })}
      - name: Collect the context and run the built-in rules
        working-directory: \${{ runner.temp }}
        env:
          GH_TOKEN: \${{ github.token }}
${stageEnvironment}
        run: |
          ${shadowclone} prepare --repo '${clone.repository}' --pr "$ENTITY" --head "$HEAD_SHA" --network ${clone.reviewNetwork ? "on" : "off"} --checkout "$GITHUB_WORKSPACE/pull-request" --output "$RUNNER_TEMP/packet.json"
${artifact({ pin: pins.uploadArtifact, name: "packet", upload: true })}
  review-checks:
    needs: [guard, review-prepare]
    if: ${reviewCondition}
    runs-on: ubuntu-latest
    timeout-minutes: 30
    permissions:
      contents: read
    steps:
${pullCheckout({ pins, fullHistory: true })}
${installSteps({ pins, versions, claude: false })}
${artifact({ pin: pins.downloadArtifact, name: "packet", upload: false })}
      - name: Run the repository toolchain without secrets
        working-directory: \${{ runner.temp }}
        run: |
          corepack enable || true
          ${shadowclone} checks --packet "$RUNNER_TEMP/packet.json" --checkout "$GITHUB_WORKSPACE/pull-request" --output "$RUNNER_TEMP/checks.json"
${artifact({ pin: pins.uploadArtifact, name: "checks", upload: true })}
  review-analyze:
    needs: [guard, review-prepare, review-checks]
    if: \${{ !cancelled() && ${reviewCondition} && needs.review-prepare.result == 'success' }}
    runs-on: ubuntu-latest
    timeout-minutes: 30
    environment: shadowclone${planConcurrency}
    permissions:
      contents: read
    steps:
${pullCheckout({ pins, fullHistory: false })}
${installSteps({ pins, versions, claude: clone.engine === "claude" })}
${codex ? `${codexInstallStep({ version: versions.codex, when: "success()" })}\n${codexLoginStep({ clone, when: "success()" })}\n` : ""}${artifact({ pin: pins.downloadArtifact, name: "packet", upload: false })}
${artifact({ pin: pins.downloadArtifact, name: "checks", upload: false, optional: true })}
      - name: Review with the shadowclone-review skill
        working-directory: \${{ runner.temp }}
        env:
${codex ? `          CODEX_HOME: \${{ runner.temp }}/codex-home` : `          CLAUDE_CODE_OAUTH_TOKEN: \${{ secrets.CLAUDE_CODE_OAUTH_TOKEN }}`}
        run: |
          checks=()
          if [ -f "$RUNNER_TEMP/checks.json" ]; then checks=(--checks "$RUNNER_TEMP/checks.json"); fi
          ${shadowclone} analyze --packet "$RUNNER_TEMP/packet.json" "\${checks[@]}" --checkout "$GITHUB_WORKSPACE/pull-request" --engine ${clone.engine} --model '${clone.reviewModel}' --network ${clone.reviewNetwork ? "on" : "off"} --output "$RUNNER_TEMP/result.json"${codexLoginReturnStep({ clone, token: botToken(clone), when: "success()" })}
${artifact({ pin: pins.uploadArtifact, name: "result", upload: true })}
  review-publish:
    needs: [guard, review-analyze]
    if: ${reviewCondition}
    runs-on: ubuntu-latest
    timeout-minutes: 5
    environment: shadowclone
    permissions:
      contents: read
    steps:
${installSteps({ pins, versions, claude: false })}
${artifact({ pin: pins.downloadArtifact, name: "result", upload: false })}
${tokenSteps(["pull-requests: write"])}
      - name: Post the review as the clone
        working-directory: \${{ runner.temp }}
        env:
          GH_TOKEN: ${botToken(clone)}
        run: |
          ${shadowclone} publish --input "$RUNNER_TEMP/result.json"
`;
}
