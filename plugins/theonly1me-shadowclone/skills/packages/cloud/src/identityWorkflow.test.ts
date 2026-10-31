import { expect, test } from "bun:test";
import { fixtureAccountClone, fixtureClone } from "./fixtures";
import { actionPins, renderWorkflows } from "./workflow";

function worker(clone: typeof fixtureClone): string {
  return renderWorkflows(clone)[".github/workflows/shadowclone.yml"] ?? "";
}

test("a machine account bot writes with its own token and accepts the repository invitation", () => {
  const rendered = worker(fixtureAccountClone);

  expect(rendered).not.toContain(actionPins.appToken);
  expect(rendered).not.toContain("SHADOWCLONE_APP_PRIVATE_KEY");
  expect(rendered).toContain(`github_token: \${{ secrets.SHADOWCLONE_BOT_TOKEN }}`);
  expect(rendered).toContain("PATCH /user/repository_invitations/{invitation_id}");
  expect(rendered).toContain("invitation.repository.id === 10");
  expect(rendered).toContain("bot_name: 'sample-shadow'");
  expect(rendered).toContain("bot_id: '31'");
  expect(rendered).toContain("trigger_phrase: '@sample-shadow'");
  expect(rendered).toContain(`GH_TOKEN: \${{ secrets.SHADOWCLONE_BOT_TOKEN }}`);
});

test("an App bot mints a token for one repository and never reads a bot token", () => {
  const rendered = worker(fixtureClone);

  expect(rendered).toContain("app-id: '20'");
  expect(rendered).toContain("repositories: 'project'");
  expect(rendered).not.toContain("SHADOWCLONE_BOT_TOKEN");
  expect(rendered).toContain("trigger_phrase: '@shadowclone'");
});

test("both identities read the skills from the private repository with a read-only key, not from a secret bundle", () => {
  for (const clone of [fixtureClone, fixtureAccountClone]) {
    const rendered = worker(clone);

    expect(rendered).toContain("repository: 'sample/shadowclone-skills'");
    expect(rendered).toContain(`ssh-key: \${{ secrets.SHADOWCLONE_SKILLS_KEY }}`);
    expect(rendered).toContain(
      'mv "$GITHUB_WORKSPACE/.shadowclone-skills" "$RUNNER_TEMP/shadowclone-guidance"',
    );
    expect(rendered).not.toContain("SHADOWCLONE_GUIDANCE }}");
    expect(Object.keys(renderWorkflows(clone))).not.toContain(".github/shadowclone/restore.cjs");
  }
});
