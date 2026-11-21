import { expect, test } from "bun:test";
import { fixtureAccountClone, fixtureClone } from "./fixtures";
import { cloneSchema } from "./types";
import { renderWorkflows } from "./workflow";

function worker(clone: typeof fixtureClone): string {
  return renderWorkflows(clone)[".github/workflows/shadowclone.yml"] ?? "";
}

const codexApiKey = { ...fixtureAccountClone, engine: "codex", codexAuth: "api-key" } as const;
const codexPlan = { ...fixtureAccountClone, engine: "codex", codexAuth: "plan" } as const;

test("a run lasts up to 3 hours, and its last step saves unfinished work unless the request is paused", () => {
  const rendered = worker(fixtureAccountClone);

  expect(rendered).toContain("timeout-minutes: 180");
  expect(rendered).toContain("timeout-minutes: 170");
  expect(rendered).not.toContain("--max-turns");
  expect(rendered).toContain(
    "name: Save unfinished work to the branch\n        if: always() && steps.validate.outputs.allowed == 'true'",
  );
  expect(rendered).toContain("grep -qx 'shadowclone:paused'");
  expect(rendered).toContain(`if [ "$BRANCH" = 'main' ]`);
  expect(rendered).toContain("31+sample-shadow@users.noreply.github.com");
  expect(rendered.indexOf("anthropics/claude-code-action")).toBeLessThan(
    rendered.indexOf("Save unfinished work"),
  );
});

test("a Codex bot signs in with the API key, gets the skills, and works with the bot token", () => {
  const rendered = worker(codexApiKey);

  expect(rendered).not.toContain("anthropics/claude-code-action");
  expect(rendered).toContain("printenv OPENAI_API_KEY | codex login --with-api-key");
  expect(rendered).toContain(
    'cp "$SHADOWCLONE_GUIDANCE_DIRECTORY/native.md" "$CODEX_HOME/AGENTS.md"',
  );
  expect(rendered).toContain("Use the shadowclone-work skill from your skills.");
  expect(rendered).toContain("codex exec - --skip-git-repo-check --sandbox danger-full-access");
  expect(rendered).not.toContain("CODEX_AUTH_JSON");
});

test("a Codex plan login runs one job at a time for each repository and stores the refreshed login", () => {
  const files = renderWorkflows(codexPlan);
  const rendered = files[".github/workflows/shadowclone.yml"] ?? "";

  expect(rendered).toContain("group: shadowclone-10-codex-login");
  expect(rendered).toContain(`printf '%s' "$CODEX_AUTH_JSON" > "$CODEX_HOME/auth.json"`);
  expect(rendered).toContain(
    "gh secret set CODEX_AUTH_JSON --env shadowclone --repo 'sample/project'",
  );
  expect(rendered.match(/Store the refreshed Codex login/g)?.length).toBe(2);
});

test("a Codex review runs the analyze stage with the Codex engine and never receives the Claude token", () => {
  const rendered = worker(codexApiKey);
  const analyze = rendered.slice(
    rendered.indexOf("  review-analyze:"),
    rendered.indexOf("  review-publish:"),
  );

  expect(analyze).toContain("--engine codex");
  expect(analyze).not.toContain("CLAUDE_CODE_OAUTH_TOKEN");
  expect(analyze).toContain("printenv OPENAI_API_KEY | codex login --with-api-key");
});

test("a ChatGPT plan login needs Codex and a machine account bot", () => {
  expect(
    cloneSchema.safeParse({ ...fixtureClone, engine: "codex", codexAuth: "plan" }).success,
  ).toBeFalse();
  expect(
    cloneSchema.safeParse({ ...fixtureAccountClone, engine: "claude", codexAuth: "plan" }).success,
  ).toBeFalse();
  expect(cloneSchema.safeParse(codexPlan).success).toBeTrue();
});
