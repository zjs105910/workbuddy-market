import { mentionNames } from "./guard/comment";
import type { Clone } from "./types";

export const agentMinutes = 170;
export const jobMinutes = 180;

const codexHome = `\${{ runner.temp }}/codex-home`;

function indented(options: { readonly text: string; readonly spaces: number }): string {
  return options.text
    .split("\n")
    .map((line) => `${" ".repeat(options.spaces)}${line}`)
    .join("\n");
}

function botEmail(clone: Clone): string {
  return `${clone.botId}+${clone.botLogin}@users.noreply.github.com`;
}

export function codexInstallStep(options: {
  readonly version: string;
  readonly when: string;
}): string {
  return `      - name: Install Codex
        if: ${options.when}
        run: |
          npm install --global --ignore-scripts --no-audit --no-fund --prefix "$RUNNER_TEMP/codex" "@openai/codex@${options.version}"
          echo "$RUNNER_TEMP/codex/bin" >> "$GITHUB_PATH"`;
}

export function codexLoginStep(options: { readonly clone: Clone; readonly when: string }): string {
  if (options.clone.codexAuth === "plan") {
    return `      - name: Restore the Codex login
        if: ${options.when}
        env:
          CODEX_HOME: ${codexHome}
          CODEX_AUTH_JSON: \${{ secrets.CODEX_AUTH_JSON }}
        run: |
          mkdir -p "$CODEX_HOME"
          printf '%s' "$CODEX_AUTH_JSON" > "$CODEX_HOME/auth.json"
          chmod 600 "$CODEX_HOME/auth.json"`;
  }

  return `      - name: Sign in to Codex with the API key
        if: ${options.when}
        env:
          CODEX_HOME: ${codexHome}
          OPENAI_API_KEY: \${{ secrets.OPENAI_API_KEY }}
        run: |
          mkdir -p "$CODEX_HOME"
          printenv OPENAI_API_KEY | codex login --with-api-key`;
}

export function codexLoginReturnStep(options: {
  readonly clone: Clone;
  readonly token: string;
  readonly when: string;
}): string {
  if (options.clone.codexAuth !== "plan") {
    return "";
  }

  return `
      - name: Store the refreshed Codex login
        if: always() && ${options.when}
        env:
          CODEX_HOME: ${codexHome}
          GH_TOKEN: ${options.token}
        run: |
          if [ -f "$CODEX_HOME/auth.json" ]; then
            gh secret set CODEX_AUTH_JSON --env shadowclone --repo '${options.clone.repository}' < "$CODEX_HOME/auth.json" || echo "::warning::GitHub refused the refreshed Codex login. Add a fresh auth.json as CODEX_AUTH_JSON."
          fi`;
}

export function codexWorkSteps(options: {
  readonly clone: Clone;
  readonly token: string;
  readonly when: string;
  readonly version: string;
  readonly prompt: string;
  readonly environment: string;
}): string {
  const { clone, when } = options;

  return `${codexInstallStep({ version: options.version, when })}
${codexLoginStep({ clone, when })}
      - name: Give Codex the reviewed skills
        if: ${when}
        env:
          CODEX_HOME: ${codexHome}
        run: |
          mkdir -p "$CODEX_HOME/skills"
          cp -R "$SHADOWCLONE_GUIDANCE_DIRECTORY/plugins/shadowclone-personal/skills/." "$CODEX_HOME/skills/"
          cp "$SHADOWCLONE_GUIDANCE_DIRECTORY/native.md" "$CODEX_HOME/AGENTS.md"
      - name: Work with Codex
        if: ${when}
        timeout-minutes: ${agentMinutes}
        env:
          CODEX_HOME: ${codexHome}
          GH_TOKEN: ${options.token}
${options.environment}
          SHADOWCLONE_PROMPT: |
${indented({ text: options.prompt, spaces: 12 })}
        run: |
          gh auth setup-git
          git config user.name '${clone.botLogin}'
          git config user.email '${botEmail(clone)}'
          printf '%s' "$SHADOWCLONE_PROMPT" | codex exec - --skip-git-repo-check --sandbox danger-full-access -c 'approval_policy="never"' -c 'shell_environment_policy.inherit="all"'${codexLoginReturnStep({ clone, token: options.token, when })}`;
}

export function claudeWorkStep(options: {
  readonly clone: Clone;
  readonly token: string;
  readonly when: string;
  readonly pin: string;
  readonly prompt: string;
  readonly environment: string;
}): string {
  const { clone } = options;
  const appBots = clone.identity.kind === "app" ? [clone.botLogin] : [];

  return `      - uses: ${options.pin}
        if: ${options.when}
        timeout-minutes: ${agentMinutes}
        env:
${options.environment}
        with:
          github_token: ${options.token}
          claude_code_oauth_token: \${{ secrets.CLAUDE_CODE_OAUTH_TOKEN }}
          bot_id: '${clone.botId}'
          bot_name: '${clone.botLogin}'
          allowed_bots: '${[...new Set([...clone.reviewerBots, ...appBots, "github-actions[bot]"])].join(",")}'
          trigger_phrase: '@${mentionNames(clone)[0]}'
          plugin_marketplaces: \${{ env.SHADOWCLONE_GUIDANCE_DIRECTORY }}
          plugins: shadowclone-personal@shadowclone-personal
          claude_args: '--permission-mode acceptEdits --allowedTools Bash,Skill --append-system-prompt-file \${{ env.SHADOWCLONE_GUIDANCE_DIRECTORY }}/native.md'
          prompt: |
${indented({ text: options.prompt, spaces: 12 })}
          display_report: false
          show_full_output: false`;
}

export function saveWorkStep(options: {
  readonly clone: Clone;
  readonly token: string;
  readonly when: string;
}): string {
  const { clone } = options;

  return `      - name: Save unfinished work to the branch
        if: always() && ${options.when}
        env:
          GH_TOKEN: ${options.token}
          BRANCH: \${{ steps.validate.outputs.branch }}
          ENTITY: \${{ steps.validate.outputs.entity }}
        run: |
          if [ "$BRANCH" = '${clone.defaultBranch.replaceAll("'", "")}' ] || [ "$(git branch --show-current)" != "$BRANCH" ]; then exit 0; fi
          if gh api "repos/${clone.repository}/issues/$ENTITY" --jq '.labels[].name' | grep -qx 'shadowclone:paused'; then exit 0; fi
          git add -A
          git diff --cached --quiet || git -c user.name='${clone.botLogin}' -c user.email='${botEmail(clone)}' commit --quiet -m "chore: save unfinished shadowclone work"
          git push --quiet "https://x-access-token:\${GH_TOKEN}@github.com/${clone.repository}.git" "HEAD:refs/heads/$BRANCH" || echo "::warning::The unfinished work could not be pushed to $BRANCH."`;
}
