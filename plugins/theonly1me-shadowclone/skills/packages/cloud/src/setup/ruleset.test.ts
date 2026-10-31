import { expect, test } from "bun:test";
import { setupRepository } from "./fixtures";
import type { GhCommand } from "./github";
import { defaultBranchRuleset, protectDefaultBranch } from "./ruleset";

function rulesetFixture(
  options: {
    readonly existing?: Record<string, unknown>;
    readonly stored?: (created: Record<string, unknown>) => Record<string, unknown>;
  } = {},
) {
  const calls: Parameters<GhCommand>[0][] = [];
  let ruleset: Record<string, unknown> | null = options.existing
    ? { id: 7, ...options.existing }
    : null;
  const command: GhCommand = async (input) => {
    calls.push(input);
    const route = input.arguments.at(-1) ?? "";

    if (input.arguments.includes("PUT") && ruleset) {
      ruleset = { id: ruleset.id, ...JSON.parse(input.input ?? "{}") };

      return JSON.stringify(ruleset);
    }

    if (input.arguments.includes("POST")) {
      const created = { id: 8, ...JSON.parse(input.input ?? "{}") };

      ruleset = options.stored ? options.stored(created) : created;

      return JSON.stringify(ruleset);
    }

    if (route.endsWith("rulesets?per_page=100&includes_parents=false")) {
      return JSON.stringify(ruleset ? [{ id: ruleset.id, name: ruleset.name }] : []);
    }

    if (ruleset && route.endsWith(`rulesets/${ruleset.id}`)) {
      return JSON.stringify(ruleset);
    }

    throw new Error(`Unexpected route ${route}`);
  };

  return { calls, command };
}

test("fresh setup lets only people with write access update or delete the default branch", async () => {
  const fixture = rulesetFixture();

  await protectDefaultBranch({ repository: setupRepository, identity: "app", command: fixture.command });

  const created = fixture.calls.find((call) => call.arguments.includes("POST"));
  const payload = JSON.parse(created?.input ?? "{}");

  expect(created?.arguments).toContain("repos/sample/project/rulesets");
  expect(payload.conditions.ref_name.include).toEqual(["~DEFAULT_BRANCH"]);
  expect(payload.rules.map((rule: { type: string }) => rule.type)).toEqual(["update", "deletion"]);
  expect(payload.bypass_actors).toEqual([
    { actor_id: 5, actor_type: "RepositoryRole", bypass_mode: "exempt" },
    { actor_id: 2, actor_type: "RepositoryRole", bypass_mode: "exempt" },
    { actor_id: 4, actor_type: "RepositoryRole", bypass_mode: "exempt" },
  ]);
  expect(fixture.calls.at(-1)?.arguments).toEqual(["api", "repos/sample/project/rulesets/8"]);
});

test("a matching ruleset from an earlier setup is reused", async () => {
  const fixture = rulesetFixture({ existing: defaultBranchRuleset("app") });

  await protectDefaultBranch({ repository: setupRepository, identity: "app", command: fixture.command });

  expect(fixture.calls.some((call) => call.arguments.includes("POST"))).toBeFalse();
});

test("a changed ruleset with the same name stops setup", async () => {
  const fixture = rulesetFixture({
    existing: {
      ...defaultBranchRuleset("app"),
      bypass_actors: [
        ...defaultBranchRuleset("app").bypass_actors,
        { actor_id: 15368, actor_type: "Integration", bypass_mode: "always" },
      ],
    },
  });

  await expect(
    protectDefaultBranch({ repository: setupRepository, identity: "app", command: fixture.command }),
  ).rejects.toThrow("Review the existing shadowclone default branch ruleset");
  expect(fixture.calls.some((call) => call.arguments.includes("POST"))).toBeFalse();
});

test("setup stops when GitHub does not enforce the created ruleset", async () => {
  const fixture = rulesetFixture({
    stored: (created) => ({ ...created, enforcement: "evaluate" }),
  });

  await expect(
    protectDefaultBranch({ repository: setupRepository, identity: "app", command: fixture.command }),
  ).rejects.toThrow("could not be verified");
});

test("setup accepts the created ruleset when GitHub leaves out the default update parameter", async () => {
  const fixture = rulesetFixture({
    stored: (created) => ({ ...created, rules: [{ type: "update" }, { type: "deletion" }] }),
  });

  await protectDefaultBranch({ repository: setupRepository, identity: "app", command: fixture.command });

  expect(fixture.calls.at(-1)?.arguments).toEqual(["api", "repos/sample/project/rulesets/8"]);
});

test("a machine account setup exempts only admins and maintainers, so the bot cannot update the default branch", async () => {
  const fixture = rulesetFixture();

  await protectDefaultBranch({ repository: setupRepository, identity: "account", command: fixture.command });

  const created = fixture.calls.find((call) => call.arguments.includes("POST"));

  expect(JSON.parse(created?.input ?? "{}").bypass_actors).toEqual([
    { actor_id: 5, actor_type: "RepositoryRole", bypass_mode: "exempt" },
    { actor_id: 2, actor_type: "RepositoryRole", bypass_mode: "exempt" },
  ]);
});

test("switching an App setup to a machine account removes the write exemption from its own ruleset", async () => {
  const fixture = rulesetFixture({ existing: defaultBranchRuleset("app") });

  await protectDefaultBranch({ repository: setupRepository, identity: "account", command: fixture.command });

  const updated = fixture.calls.find((call) => call.arguments.includes("PUT"));

  expect(JSON.parse(updated?.input ?? "{}").bypass_actors).toEqual(defaultBranchRuleset("account").bypass_actors);
});
