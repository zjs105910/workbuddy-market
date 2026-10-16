import { expect, test } from "bun:test";
import { claudeFinalText, commandOutputs, testRunResults, withTestRuns } from "./outputs";

const claudeStream = [
  { type: "assistant", message: { content: [{ type: "text", text: "Next I will run the tests." }, { type: "tool_use", id: "t1", name: "Bash", input: { command: "bun test 2>&1 | tail -5" } }] } },
  { type: "user", message: { content: [{ type: "tool_result", tool_use_id: "t1", content: [{ type: "text", text: " 3 pass\n 1 fail\n 4 expect() calls\nRan 4 tests" }] }] } },
  { type: "assistant", message: { content: [{ type: "text", text: "Fixed it." }] } },
  { type: "result", subtype: "success", result: "Fixed it." },
].map((entry) => JSON.stringify(entry)).join("\n");

test("Claude Bash output and the final message come from the stream", () => {
  expect(commandOutputs({ engine: "claude-code", stream: claudeStream })).toEqual([
    { command: "bun test 2>&1 | tail -5", output: " 3 pass\n 1 fail\n 4 expect() calls\nRan 4 tests" },
  ]);
  expect(claudeFinalText(claudeStream)).toBe("Fixed it.");
  expect(claudeFinalText("not json")).toBeNull();
});

test("Codex command output comes from completed command items", () => {
  const stream = JSON.stringify({ type: "item.completed", item: { type: "command_execution", command: "bun test", aggregated_output: " 2 pass\n 0 fail\n" } });
  expect(commandOutputs({ engine: "codex", stream })).toEqual([{ command: "bun test", output: " 2 pass\n 0 fail\n" }]);
});

test("test results are read per run and attached to the matching command", () => {
  expect(testRunResults(" 5 pass\n 0 fail\nRan 5\n 4 pass\n 1 fail\nRan 5")).toEqual(["pass", "fail"]);
  expect(testRunResults("error: cannot find module")).toEqual([]);
  expect(testRunResults("(fail) retries > never retries success [0.4ms]\nReceived: 1000")).toEqual(["fail"]);
  expect(testRunResults("(pass) retries > backs off")).toEqual(["pass"]);
  const [action] = withTestRuns({
    actions: [{ tool: "Bash", path: null, command: "bun test 2>&1 | tail -5", succeeded: true }],
    outputs: commandOutputs({ engine: "claude-code", stream: claudeStream }),
  });
  expect(action?.testRuns).toEqual(["fail"]);
});
