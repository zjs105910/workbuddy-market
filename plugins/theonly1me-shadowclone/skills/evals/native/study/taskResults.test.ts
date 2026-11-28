import { expect, test } from "bun:test";
import { studyFixture, studyTask } from "./fixtures";
import { pendingRun, type RunArmName } from "./record";
import type { StudyVerdict } from "./checkSchema";
import { taskResults } from "./taskResults";

function run(options: { arm: RunArmName; repeat: number; verdicts: readonly StudyVerdict[] }) {
  return {
    ...pendingRun({ arm: options.arm, taskId: "rename-config", repeat: options.repeat }), status: "complete" as const,
    checks: options.verdicts.map((verdict, index) => ({ id: `check-${index}`, keyItem: "commit-subject-shape", verdict, evidence: "" })),
  };
}

test("counts followed checks per setup and the multiple over the baseline", async () => {
  const fixture = await studyFixture({ tasks: [studyTask()] });
  try {
    const runs = [
      run({ arm: "bare", repeat: 0, verdicts: ["fail", "pass"] }), run({ arm: "bare", repeat: 1, verdicts: ["fail", "fail"] }),
      run({ arm: "deep", repeat: 0, verdicts: ["pass", "pass"] }), run({ arm: "deep", repeat: 1, verdicts: ["pass", "unknown"] }),
      run({ arm: "original", repeat: 0, verdicts: ["not-applicable", "pass"] }),
    ];
    const { overall, tasks } = taskResults({ suite: fixture.suite, runs });
    expect(overall.bare).toEqual({ followed: 1, checked: 4, timesBaseline: null });
    expect(overall.deep).toEqual({ followed: 3, checked: 3, timesBaseline: 4 });
    expect(overall.original.timesBaseline).toBe(4);
    expect(overall["first-time"]).toEqual({ followed: 0, checked: 0, timesBaseline: null });
    expect(tasks.map((task) => task.taskId)).toEqual(["rename-config"]);
  } finally {
    await fixture.cleanup();
  }
});

test("the multiple is empty when the baseline followed nothing", async () => {
  const fixture = await studyFixture({ tasks: [studyTask()] });
  try {
    const runs = [run({ arm: "bare", repeat: 0, verdicts: ["fail", "fail"] }), run({ arm: "deep", repeat: 0, verdicts: ["pass", "fail"] })];
    const { overall } = taskResults({ suite: fixture.suite, runs });
    expect(overall.deep).toEqual({ followed: 1, checked: 2, timesBaseline: null });
  } finally {
    await fixture.cleanup();
  }
});
