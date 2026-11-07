import type { FileUpdate } from "@shadowclone/changes";
import type { BuildInput, EnvironmentState } from "@shadowclone/environment";
import type { DiscoveredSkill } from "@shadowclone/skills";

export type BuildItem = {
  readonly id: string;
  readonly name: string;
  readonly title: string;
  readonly description: string;
  readonly text: string;
  readonly kind: "preference" | "skill";
  readonly category: string | null;
  readonly section: string | null;
  readonly axis: string | null;
  readonly alwaysOn: boolean;
  readonly owner: "packaged" | "managed" | "user" | "provider";
  readonly source?: DiscoveredSkill;
};

export type BuildPlan = {
  readonly input: BuildInput;
  readonly state: EnvironmentState;
  readonly updates: readonly FileUpdate[];
  readonly warnings: readonly string[];
  readonly observed: readonly {
    readonly filePath: string;
    readonly text: string | null;
  }[];
};
