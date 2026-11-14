import type { FileUpdate } from "@shadowclone/changes";

export type OriginRepair = {
  readonly sourceDirectory: string;
  readonly targetDirectory: string;
  readonly files: number;
};

export type BlockedOriginRepair = {
  readonly sourceDirectory: string;
  readonly targetDirectory: string;
  readonly reason: "conflicting-rule" | "edited-block" | "invalid-content";
};

export type ProfileRepairPlan = {
  readonly repairs: readonly OriginRepair[];
  readonly blocked: readonly BlockedOriginRepair[];
  readonly isolatedDirectories: number;
  readonly legacyDirectories: number;
  readonly updates: readonly FileUpdate[];
};
