import { expect, test } from "bun:test";
import { guidanceFixture } from "../fixtures";
import { defaultBranchRuleset } from "./ruleset";
import { organizationMergeWarning, setUpAccountClone } from "./accountSetup";
import { ghApiFixture, setupRepository } from "./fixtures";
import type { GhCommand } from "./github";

const sha = (letter: string) => letter.repeat(40);

function githubState(options: { readonly botExists: boolean; readonly organization?: boolean }) {
  const events: string[] = [];
  let skillsCreated = false;
  let policyCreated = false;
  const api = ghApiFixture({
    "GET user": { status: 200, data: { login: "sample" } },
    "GET repos/sample/project": {
      status: 200,
      data: options.organization ? { ...setupRepository, owner: { login: "sample", type: "Organization" } } : setupRepository,
    },
    "GET users/sample-shadow": options.botExists
      ? { status: 200, data: { id: 31, login: "sample-shadow", type: "User" } }
      : { status: 404, data: null },
    "GET repos/sample/shadowclone-skills": () =>
      skillsCreated
        ? {
            status: 200,
            data: { full_name: "sample/shadowclone-skills", private: true, default_branch: "main" },
          }
        : { status: 404, data: null },
    "POST user/repos": () => {
      skillsCreated = true;
      events.push("create skills repository");
      return { status: 201, data: {} };
    },
    "GET repos/sample/shadowclone-skills/git/ref/heads/main": {
      status: 200,
      data: { object: { sha: sha("a") } },
    },
    [`GET repos/sample/shadowclone-skills/git/commits/${sha("a")}`]: {
      status: 200,
      data: { tree: { sha: sha("b") } },
    },
    "POST repos/sample/shadowclone-skills/git/blobs": { status: 201, data: { sha: sha("c") } },
    "POST repos/sample/shadowclone-skills/git/trees": { status: 201, data: { sha: sha("e") } },
    "POST repos/sample/shadowclone-skills/git/commits": { status: 201, data: { sha: sha("d") } },
    "PATCH repos/sample/shadowclone-skills/git/refs/heads/main": () => {
      events.push("push skills");
      return { status: 200, data: {} };
    },
    "GET repos/sample/shadowclone-skills/keys?per_page=100": { status: 200, data: [] },
    "POST repos/sample/shadowclone-skills/keys": () => {
      events.push("add deploy key");
      return { status: 201, data: {} };
    },
    "GET repos/sample/project/invitations?per_page=100": { status: 200, data: [] },
    "PUT repos/sample/project/collaborators/sample-shadow": () => {
      events.push("invite bot");
      return { status: 201, data: {} };
    },
    "GET repos/sample/project/git/ref/heads/main": {
      status: 200,
      data: { object: { sha: sha("f") } },
    },
    [`GET repos/sample/project/git/commits/${sha("f")}`]: {
      status: 200,
      data: { tree: { sha: sha("1") } },
    },
    [`GET repos/sample/project/git/trees/${sha("1")}?recursive=1`]: {
      status: 200,
      data: { truncated: false, tree: [] },
    },
    "POST repos/sample/project/git/trees": { status: 201, data: { sha: sha("2") } },
    "POST repos/sample/project/git/commits": { status: 201, data: { sha: sha("3") } },
    "POST repos/sample/project/git/refs": { status: 201, data: {} },
    "POST repos/sample/project/pulls": () => {
      events.push("open setup pull request");
      return { status: 201, data: { html_url: "https://github.com/sample/project/pull/5" } };
    },
  });
  const command: GhCommand = async (input) => {
    const route = input.arguments.find((argument) => argument.startsWith("repos/")) ?? "";

    if (input.arguments[0] === "secret") {
      events.push(`set ${input.arguments[2]}`);
      return "";
    }

    if (route.endsWith("rulesets?per_page=100&includes_parents=false")) {
      return "[]";
    }

    if (route.endsWith("/rulesets") && input.arguments.includes("POST")) {
      events.push("protect default branch");
      return JSON.stringify({ id: 8, ...JSON.parse(input.input ?? "{}") });
    }

    if (route.endsWith("rulesets/8")) {
      return JSON.stringify({ id: 8, ...defaultBranchRuleset("account") });
    }

    if (route.endsWith("environments?per_page=100")) {
      return JSON.stringify({ environments: [] });
    }

    if (route.endsWith("deployment-branch-policies") && input.arguments.includes("POST")) {
      policyCreated = true;
    }

    if (route.endsWith("deployment-branch-policies?per_page=100")) {
      return JSON.stringify({
        branch_policies: policyCreated ? [{ name: "main", type: "branch" }] : [],
      });
    }

    return "{}";
  };

  return { ...api, command, events };
}

test("setup opens the signup page when the bot account does not exist, and changes nothing", async () => {
  const fixture = await guidanceFixture();
  const github = githubState({ botExists: false });

  try {
    const outcome = await setUpAccountClone({
      ...fixture,
      repository: "sample/project",
      botLogin: "sample-shadow",
      approveSkills: true,
      engine: "claude",
      codexAuth: "api-key",
      ...github,
    });

    expect(outcome).toEqual({
      kind: "needs-account",
      login: "sample-shadow",
      signupUrl: "https://github.com/signup",
    });
    expect(github.events).toEqual([]);
  } finally {
    await fixture.cleanup();
  }
});

test("setup lists the skill files and waits for approval before it writes anything", async () => {
  const fixture = await guidanceFixture();
  const github = githubState({ botExists: true });

  try {
    const outcome = await setUpAccountClone({
      ...fixture,
      repository: "sample/project",
      botLogin: "sample-shadow",
      approveSkills: false,
      engine: "claude",
      codexAuth: "api-key",
      ...github,
    });

    expect(outcome.kind).toBe("needs-approval");
    expect(
      outcome.kind === "needs-approval" ? outcome.files.map((file) => file.path) : [],
    ).toContain("plugins/shadowclone-personal/skills/shadowclone-work/SKILL.md");
    expect(github.events).toEqual([]);
  } finally {
    await fixture.cleanup();
  }
});

test("an approved setup protects the branch first, keeps tokens off Shadowclone, and opens the setup pull request", async () => {
  const fixture = await guidanceFixture();
  const github = githubState({ botExists: true });

  try {
    const outcome = await setUpAccountClone({
      ...fixture,
      repository: "sample/project",
      botLogin: "sample-shadow",
      approveSkills: true,
      engine: "claude",
      codexAuth: "api-key",
      ...github,
    });

    expect(github.events).toEqual([
      "protect default branch",
      "create skills repository",
      "push skills",
      "add deploy key",
      "set SHADOWCLONE_SKILLS_KEY",
      "invite bot",
      "open setup pull request",
    ]);
    expect(
      outcome.kind === "configured"
        ? [outcome.clone.identity, outcome.clone.botLogin, outcome.pullUrl]
        : null,
    ).toEqual([{ kind: "account" }, "sample-shadow", "https://github.com/sample/project/pull/5"]);
  } finally {
    await fixture.cleanup();
  }
});

test("a machine account setup in an organization repository warns that write-role members can no longer merge alone", async () => {
  const fixture = await guidanceFixture();
  const github = githubState({ botExists: true, organization: true });

  try {
    const outcome = await setUpAccountClone({
      ...fixture,
      repository: "sample/project",
      botLogin: "sample-shadow",
      approveSkills: true,
      engine: "claude",
      codexAuth: "api-key",
      ...github,
    });

    expect(outcome.kind === "configured" ? outcome.warnings : null).toEqual([organizationMergeWarning]);
  } finally {
    await fixture.cleanup();
  }
});
