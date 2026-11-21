import { expect, test } from "bun:test";
import { configureEnvironment } from "./environment";
import { setupRepository } from "./fixtures";
import type { GhCommand } from "./github";

function environmentFixture(
  options: {
    readonly existing?: boolean;
    readonly allowedBranch?: string;
    readonly protectedBranches?: boolean;
  } = {},
) {
  const calls: Parameters<GhCommand>[0][] = [];
  let createdPolicy = false;
  const command: GhCommand = async (input) => {
    calls.push(input);
    const route = input.arguments.at(-1) ?? "";

    if (route.endsWith("environments?per_page=100")) {
      return JSON.stringify({
        environments: options.existing
          ? [
              {
                name: "shadowclone",
                deployment_branch_policy: {
                  protected_branches: options.protectedBranches ?? false,
                  custom_branch_policies: true,
                },
              },
            ]
          : [],
      });
    }

    if (input.arguments.includes("POST")) {
      createdPolicy = true;
    }

    if (route.endsWith("deployment-branch-policies?per_page=100")) {
      return JSON.stringify({
        branch_policies:
          options.existing || createdPolicy
            ? [{ name: options.allowedBranch ?? "main", type: "branch" }]
            : [],
      });
    }

    return "{}";
  };

  return { calls, command };
}

test("fresh setup restricts the environment before sending credentials through stdin", async () => {
  const fixture = environmentFixture();
  const token = "synthetic-subscription-token";

  await configureEnvironment({
    repository: setupRepository,
    command: fixture.command,
    secrets: { CLAUDE_CODE_OAUTH_TOKEN: token },
  });

  const uploaded = fixture.calls.find((call) => call.arguments[0] === "secret");
  const restriction = fixture.calls.findIndex((call) => call.arguments.includes("POST"));

  expect(uploaded?.input).toBe(token);
  expect(uploaded?.arguments).not.toContain(token);
  expect(uploaded?.arguments).toContain("--env");
  expect(restriction).toBeLessThan(fixture.calls.findIndex((call) => call === uploaded));
});

test("an existing default-branch environment keeps its approval settings", async () => {
  const fixture = environmentFixture({ existing: true });

  await configureEnvironment({
    repository: setupRepository,
    command: fixture.command,
    secrets: { SHADOWCLONE_GUIDANCE: "synthetic-bundle" },
  });

  expect(fixture.calls.some((call) => call.arguments.includes("PUT"))).toBeFalse();
});

test("another branch or a protected-branches policy prevents any secret upload", async () => {
  for (const options of [
    { existing: true, allowedBranch: "feature/*" },
    { existing: true, protectedBranches: true },
  ]) {
    const fixture = environmentFixture(options);

    await expect(
      configureEnvironment({
        repository: setupRepository,
        command: fixture.command,
        secrets: { CLAUDE_CODE_OAUTH_TOKEN: "synthetic-token" },
      }),
    ).rejects.toThrow();
    expect(fixture.calls.some((call) => call.arguments[0] === "secret")).toBeFalse();
    expect(fixture.calls.some((call) => call.arguments.includes("PUT"))).toBeFalse();
  }
});
