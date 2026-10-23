import { expect, test } from "bun:test";
import { rm } from "node:fs/promises";
import { createLearningExecution } from "@shadowclone/agents";
import { learningRecord, skillEngineRun, skillFixture } from "@shadowclone/environment/testing";
import { discoverDeliverySkills, readMaintenanceState } from "@shadowclone/skills";
import { reconcileLearningBatch } from "./reconcile";
import { emptyEnvironment } from "@shadowclone/environment";

const records = [
  learningRecord({ key: "palette-order", body: "Sort palette colors by their label." }),
  learningRecord({ key: "palette-export", body: "Review palette exports before sharing." }),
];

test("direct pending routes keep their own reasons", async () => {
  const setup = await skillFixture();
  const reasons = ["Choose the ordering rule because labels conflict.", "Choose who reviews an export before sharing it."];

  try {
    const result = await reconcileLearningBatch({
      ...setup,
      state: emptyEnvironment,
      records,
      scope: { key: "global", directory: setup.home, repository: null },
      skills: [],
      execution: createLearningExecution({
        engine: "claude-code",
        runner: async () => skillEngineRun({ routes: records.map((record, index) => ({
          key: record.rule.key,
          destination: "pending",
          name: "",
          skillId: "",
          description: "",
          reason: reasons[index],
        })) }),
      }),
    });

    expect(result.state.dispositions.map(({ reason }) => reason)).toEqual(
      records.map((record, index) => `${record.rule.title}: ${reasons[index]}`),
    );
    expect(result.updates).toEqual([]);
  } finally {
    await rm(setup.home, { recursive: true, force: true });
  }
});

test("a blocked shared draft explains each record and preserves the skill", async () => {
  const setup = await skillFixture();

  try {
    const maintenance = await readMaintenanceState(setup.paths);
    const { skills } = await discoverDeliverySkills(maintenance.roots);
    const [skill] = skills;
    if (!skill) throw new Error("Expected the synthetic skill");

    const result = await reconcileLearningBatch({
      ...setup,
      state: emptyEnvironment,
      records,
      scope: { key: "global", directory: setup.home, repository: null },
      skills,
      execution: createLearningExecution({
        engine: "claude-code",
        runner: async (run) => skillEngineRun(run.prompt.includes("Organize durable")
          ? { routes: records.map(({ rule }) => ({
              key: rule.key, destination: "skill", skillId: skill.id,
              name: skill.name, description: skill.description, reason: "Related workflow",
            })) }
          : {
              description: "", body: "",
              outcomes: [
                { key: "palette-order", disposition: "apply", reason: "Supported order" },
                { key: "palette-export", disposition: "pending", reason: "No export reviewer is named. Choose that reviewer." },
              ],
              edits: [{ before: "", after: "Sort palette colors by their label.", keys: ["palette-order"] }],
            }),
      }),
    });

    expect(result.state.dispositions.find(({ key }) => key === "palette-order")?.reason)
      .toContain("blocked by learning palette-export");
    expect(result.state.dispositions.find(({ key }) => key === "palette-export")?.reason)
      .toContain("No export reviewer is named");
    expect(result.updates).toEqual([]);
    expect(await Bun.file(setup.filePath).text()).toBe(setup.original);
  } finally {
    await rm(setup.home, { recursive: true, force: true });
  }
});
