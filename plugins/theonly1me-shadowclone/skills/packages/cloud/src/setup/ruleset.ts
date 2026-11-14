import { z } from "zod";
import type { Identity, Repository } from "../types";
import type { GhCommand } from "./github";

const repositoryRoleIds = { admin: 5, maintain: 2, write: 4 } as const;

const exemptRoles: Readonly<Record<Identity["kind"], readonly (keyof typeof repositoryRoleIds)[]>> = {
  app: ["admin", "maintain", "write"],
  account: ["admin", "maintain"],
};

export function defaultBranchRuleset(identity: Identity["kind"]) {
  return {
    ...defaultBranchRules,
    bypass_actors: exemptRoles[identity].map((role) => ({
      actor_id: repositoryRoleIds[role],
      actor_type: "RepositoryRole",
      bypass_mode: "exempt",
    })),
  };
}

const defaultBranchRules = {
  name: "shadowclone default branch",
  target: "branch",
  enforcement: "active",
  conditions: { ref_name: { include: ["~DEFAULT_BRANCH"], exclude: [] } },
  rules: [
    { type: "update", parameters: { update_allows_fetch_and_merge: false } },
    { type: "deletion" },
  ],
} as const;

const summarySchema = z.array(z.object({ id: z.number().int().positive(), name: z.string() }));

const rulesetSchema = z.object({
  id: z.number().int().positive(),
  target: z.string(),
  enforcement: z.string(),
  conditions: z
    .object({
      ref_name: z.object({ include: z.array(z.string()), exclude: z.array(z.string()) }),
    })
    .nullable(),
  rules: z.array(
    z.object({
      type: z.string(),
      parameters: z.record(z.string(), z.unknown()).optional(),
    }),
  ),
  bypass_actors: z
    .array(
      z.object({
        actor_id: z.number().nullable(),
        actor_type: z.string(),
        bypass_mode: z.string(),
      }),
    )
    .default([]),
});

type Ruleset = z.infer<typeof rulesetSchema>;

function sortedKeys(values: readonly string[]): string {
  return [...values].sort().join(",");
}

function bypassKey(actors: Ruleset["bypass_actors"]): string {
  return sortedKeys(actors.map((actor) => `${actor.actor_type}:${actor.actor_id}:${actor.bypass_mode}`));
}

function hasDefaultBranchRules(ruleset: Ruleset): boolean {
  const update = ruleset.rules.find((rule) => rule.type === "update");

  return (
    ruleset.target === "branch" &&
    ruleset.enforcement === "active" &&
    sortedKeys(ruleset.conditions?.ref_name.include ?? []) === "~DEFAULT_BRANCH" &&
    (ruleset.conditions?.ref_name.exclude.length ?? 0) === 0 &&
    sortedKeys(ruleset.rules.map((rule) => rule.type)) === "deletion,update" &&
    (update?.parameters?.update_allows_fetch_and_merge ?? false) === false
  );
}

export async function protectDefaultBranch(options: {
  readonly repository: Repository;
  readonly identity: Identity["kind"];
  readonly command: GhCommand;
}): Promise<void> {
  const expected = defaultBranchRuleset(options.identity);
  const base = `repos/${options.repository.full_name}/rulesets`;
  const summaries = summarySchema.parse(
    JSON.parse(
      await options.command({
        arguments: ["api", `${base}?per_page=100&includes_parents=false`],
      }),
    ),
  );

  if (summaries.length >= 100) {
    throw new Error("Review the repository rulesets before setup.");
  }

  const existing = summaries.find((ruleset) => ruleset.name === expected.name);
  const id =
    existing?.id ??
    rulesetSchema.parse(
      JSON.parse(
        await options.command({
          arguments: ["api", "--method", "POST", base, "--input", "-"],
          input: JSON.stringify(expected),
        }),
      ),
    ).id;
  const read = async () => rulesetSchema.parse(JSON.parse(await options.command({ arguments: ["api", `${base}/${id}`] })));
  const stored = await read();

  const otherIdentity = options.identity === "app" ? "account" : "app";
  const switchesIdentity = bypassKey(stored.bypass_actors) === bypassKey(defaultBranchRuleset(otherIdentity).bypass_actors);

  if (existing && hasDefaultBranchRules(stored) && switchesIdentity) {
    await options.command({
      arguments: ["api", "--method", "PUT", `${base}/${id}`, "--input", "-"],
      input: JSON.stringify(expected),
    });
  }

  const verified = existing ? await read() : stored;

  if (!hasDefaultBranchRules(verified) || bypassKey(verified.bypass_actors) !== bypassKey(expected.bypass_actors)) {
    throw new Error(
      existing
        ? "Review the existing shadowclone default branch ruleset before setup."
        : "The default branch ruleset could not be verified.",
    );
  }
}
