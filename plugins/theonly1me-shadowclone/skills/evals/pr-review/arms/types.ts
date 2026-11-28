import type { CopiedCase } from "../copy";
import type { PreparedCase } from "../prepare";

export const cloudArmNames = ["shadowclone", "openqodex", "greptile"] as const;

export const localArmNames = ["shadowclone-branch", "openqodex-branch", "shadowclone-upstream", "openqodex-upstream"] as const;

export const armNames = [...cloudArmNames, ...localArmNames] as const;

export type ArmName = (typeof armNames)[number];

export type LocalArmName = (typeof localArmNames)[number];

export type ArmRun = {
  readonly arm: ArmName;
  readonly caseId: string;
  readonly number: number;
  readonly startedAt: string;
  readonly finishedAt: string | null;
  readonly status: "done" | "timed-out" | "failed";
  readonly detail: string;
  readonly raw: unknown;
};

export type ArmRunner = (options: { readonly entry: CopiedCase; readonly evalRepository: string; readonly directory: string }) => Promise<ArmRun>;

export type LocalArmRunner = (options: { readonly entry: PreparedCase; readonly directory: string }) => Promise<ArmRun>;
