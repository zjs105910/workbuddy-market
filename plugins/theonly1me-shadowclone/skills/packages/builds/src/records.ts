import {
  type BuildDefinition,
  type EnvironmentState,
  learningRecordSchema,
  profileRuleFromSeedGuidance,
} from "@shadowclone/environment";
import { loadSeedLibrary } from "@shadowclone/skills";

export async function recordBuildPreferences(options: {
  readonly state: EnvironmentState;
  readonly build: BuildDefinition;
}): Promise<EnvironmentState> {
  if (options.build.scope !== "global") {
    return options.state;
  }

  const library = await loadSeedLibrary();

  const records = library.preferences
    .filter((entry) => options.build.choices[entry.id])
    .map((entry) =>
      learningRecordSchema.parse({
        kind: "guidance",
        sourceHash: null,
        sourceLocator: null,
        rule: {
          ...profileRuleFromSeedGuidance(entry),
          body: options.build.edits[entry.id] ?? entry.body,
        },
      }),
    );

  const declaredKeys = new Set(
    library.preferences.map((entry) => `seed:${entry.id}`),
  );
  const userKeys = new Set(
    options.state.records
      .filter((record) => record.rule.source === "user")
      .map((record) => record.rule.key),
  );

  const preserved = options.state.records.filter(
    (record) =>
      !declaredKeys.has(record.rule.key) || userKeys.has(record.rule.key),
  );
  const selected = records.filter((record) => !userKeys.has(record.rule.key));

  return { ...options.state, records: [...preserved, ...selected] };
}
