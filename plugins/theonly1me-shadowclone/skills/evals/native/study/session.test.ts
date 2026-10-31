import { expect, test } from "bun:test";
import path from "node:path";
import { evaluationBudget } from "../../shared/accounting";
import { engineRun, recordingRunner, runGit, studyFixture, type RecordedCall } from "./fixtures";
import { runMatrix } from "./matrix";
import { pendingRun } from "./record";
import { runStudySession } from "./session";

test("a two-turn session resumes, observes commits and stub calls, and scores the commit", async () => {
  const fixture = await studyFixture();
  try {
    const calls: RecordedCall[] = [];
    const runner = recordingRunner({ calls, turn: async (request, index) => {
      if (index === 0) {
        await Bun.write(path.join(request.directory, "src/loader.ts"), "export const configuration = 1;\n");
        return engineRun({ text: "Renamed it.", actions: [{ tool: "Edit", path: "src/loader.ts", succeeded: true }] });
      }
      await runGit({ directory: request.directory, arguments: ["-c", "user.name=Agent", "-c", "user.email=agent@example.test", "commit", "-qam", "Rename cfg (TAL-502)"] });
      const stub = Bun.spawn({ cmd: [path.join(request.homeDirectory, "bin/gh"), "pr", "create", "--title", "chore: names"], env: { ...process.env, HOME: request.homeDirectory } });
      await stub.exited;
      return engineRun({ text: "Committed." });
    } });
    const budget = await evaluationBudget({ directory: fixture.outputDirectory, resume: false, maximumCalls: 10 });
    const [task] = fixture.suite.tasks;
    if (!task) throw new Error("Missing synthetic task");
    const record = await runStudySession({ suite: fixture.suite, task, arm: "deep", repeat: 0, runner, budget,
      outputDirectory: fixture.outputDirectory, deadlineAt: Date.now() + 60_000 });

    expect(calls.map((call) => call.resumeSessionId)).toEqual([undefined, "session-1"]);
    expect(calls[0]?.writablePaths.some((entry) => entry.endsWith(".git"))).toBe(true);
    expect(record.status).toBe("complete");
    expect(record.files.map((file) => file.path)).toEqual(["src/loader.ts"]);
    expect(record.turns[0]?.commits).toEqual([]);
    expect(record.commits.map((commit) => commit.subject)).toEqual(["Rename cfg (TAL-502)"]);
    expect(record.toolCalls).toEqual([{ tool: "gh", args: ["pr", "create", "--title", "chore: names"], body: null }]);
  } finally {
    await fixture.cleanup();
  }
});

test("told controls receive the task's statements and matrix resume keeps interrupted runs", async () => {
  const fixture = await studyFixture();
  try {
    const calls: RecordedCall[] = [];
    const runner = recordingRunner({ calls, turn: async () => engineRun({ text: "Done." }) });
    const budget = await evaluationBudget({ directory: fixture.outputDirectory, resume: false, maximumCalls: 20 });
    const receiptFile = path.join(fixture.outputDirectory, "receipt.json");
    const receipt = await runMatrix({
      suite: fixture.suite, runner, budget, receiptFile, outputDirectory: fixture.outputDirectory, concurrency: 2,
      entries: [{ arm: "told", taskId: "rename-config", repeat: 0 }, { arm: "bare", taskId: "rename-config", repeat: 0 }],
      receipt: {
        protocol: "preference-study-v1", phase: "validation", suiteFingerprint: "0".repeat(64), deadlineAt: Date.now() + 60_000,
        status: "running", failure: null,
        runs: [pendingRun({ arm: "bare", taskId: "rename-config", repeat: 0 })],
      },
    });

    expect(calls[0]?.prompt).toContain("Synthetic preference commit-subject-shape.");
    expect(calls).toHaveLength(2);
    expect(receipt.runs.find((run) => run.arm === "bare")?.status).toBe("error");
    expect(receipt.runs.find((run) => run.arm === "told")?.checks.map((check) => check.verdict)).toEqual(["fail", "not-applicable"]);
  } finally {
    await fixture.cleanup();
  }
});
