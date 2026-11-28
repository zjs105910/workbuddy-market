import type { LearningExecution } from "@shadowclone/agents";
import type { FileUpdate } from "@shadowclone/changes";
import type { ProjectPaths } from "@shadowclone/core";
import type { DiscoveredSkill } from "@shadowclone/skills";
import { reconcileDirectLearning } from "./reconcileDirect";
import { reconcileSkillLearning } from "./reconcileSkill";
import { routeLearning } from "./planner";
import type { EnvironmentState, LearningRecord, LearningScope } from "@shadowclone/environment";

export async function reconcileLearningBatch(options: {
  readonly paths: ProjectPaths;
  readonly state: EnvironmentState;
  readonly records: readonly LearningRecord[];
  readonly scope: LearningScope;
  readonly skills: readonly DiscoveredSkill[];
  readonly execution: LearningExecution;
}): Promise<{
  readonly state: EnvironmentState;
  readonly updates: readonly FileUpdate[];
  readonly applied: number;
}> {
  const routes = await routeLearning({
    ...options,
    cwd: options.paths.shadowcloneDirectory,
  });
  let state = options.state;
  const updates: FileUpdate[] = [];
  let applied = 0;

  const groups = Map.groupBy(routes, (route) => {
    if (["pending", "excluded", "fact"].includes(route.destination)) {
      return `${route.destination}:${route.key}`;
    }

    const skill = options.skills.find(({ id }) => id === route.skillId);

    return skill?.root.owner === "third-party"
      ? `shadowclone-local-${skill.id.slice(0, 20)}`
      : (skill?.id ?? route.name);
  });

  for (const group of groups.values()) {
    const [route] = group;

    if (!route) continue;

    const keys = new Set(group.map(({ key }) => key));
    const records = options.records.filter(({ rule }) => keys.has(rule.key));

    if (route.destination === "fact" && records.some((record) => record.rule.body.length > 512)) {
      route.destination = "pending";
      route.reason = "The fact exceeds the native context limit. Select a scoped workflow skill before publishing it.";
    }

    if (["pending", "excluded", "fact"].includes(route.destination)) {
      state = reconcileDirectLearning({ ...options, state, route, records, keys });
      continue;
    }

    if (options.execution.callsRemaining() === 0) break;

    const result = await reconcileSkillLearning({ ...options, state, route, records, keys });
    state = result.state;
    updates.push(...result.updates);
    applied += result.applied;
  }

  return { state, updates, applied };
}
