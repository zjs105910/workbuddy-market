import { z } from "zod";
import type { Repository } from "../types";
import type { GhCommand } from "./github";

const branchSchema = z.object({
  branch_policies: z.array(z.object({ name: z.string(), type: z.string() })),
});
const environmentSchema = z.object({
  environments: z.array(
    z.object({
      name: z.string(),
      deployment_branch_policy: z
        .object({
          protected_branches: z.boolean(),
          custom_branch_policies: z.boolean(),
        })
        .nullable(),
    }),
  ),
});

export async function configureEnvironment(options: {
  readonly repository: Repository;
  readonly command: GhCommand;
  readonly secrets: Readonly<Record<string, string>>;
}): Promise<void> {
  const base = `repos/${options.repository.full_name}/environments/shadowclone`;
  const environments = environmentSchema.parse(
    JSON.parse(
      await options.command({
        arguments: ["api", `repos/${options.repository.full_name}/environments?per_page=100`],
      }),
    ),
  );

  if (environments.environments.length >= 100) {
    throw new Error("Review the environment list before setup.");
  }

  const existing = environments.environments.find(
    (environment) => environment.name.toLowerCase() === "shadowclone",
  );

  if (
    existing &&
    (!existing.deployment_branch_policy?.custom_branch_policies ||
      existing.deployment_branch_policy.protected_branches)
  ) {
    throw new Error(
      "Restrict the existing shadowclone environment to the default branch before " + "setup.",
    );
  }

  if (!existing) {
    await options.command({
      arguments: ["api", "--method", "PUT", base, "--input", "-"],
      input: JSON.stringify({
        deployment_branch_policy: {
          protected_branches: false,
          custom_branch_policies: true,
        },
      }),
    });
  }

  const branches = branchSchema.parse(
    JSON.parse(
      await options.command({
        arguments: ["api", `${base}/deployment-branch-policies?per_page=100`],
      }),
    ),
  );

  if (
    branches.branch_policies.some(
      (branch) => branch.name !== options.repository.default_branch || branch.type !== "branch",
    ) ||
    (existing && branches.branch_policies.length === 0)
  ) {
    throw new Error(
      "The shadowclone environment permits another branch or tag. Review its " +
        "policy before setup.",
    );
  }

  if (branches.branch_policies.length === 0) {
    await options.command({
      arguments: ["api", "--method", "POST", `${base}/deployment-branch-policies`, "--input", "-"],
      input: JSON.stringify({
        name: options.repository.default_branch,
        type: "branch",
      }),
    });
  }

  const verified = branchSchema.parse(
    JSON.parse(
      await options.command({
        arguments: ["api", `${base}/deployment-branch-policies?per_page=100`],
      }),
    ),
  );

  if (
    verified.branch_policies.length !== 1 ||
    verified.branch_policies[0]?.name !== options.repository.default_branch ||
    verified.branch_policies[0]?.type !== "branch"
  ) {
    throw new Error("The environment branch restriction could not be verified.");
  }

  for (const [name, value] of Object.entries(options.secrets)) {
    await options.command({
      arguments: [
        "secret",
        "set",
        name,
        "--repo",
        options.repository.full_name,
        "--env",
        "shadowclone",
      ],
      input: value,
    });
  }
}
