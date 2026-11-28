import { z } from "zod";
import { projectPaths } from "@shadowclone/core";
import { readLatestProbe, runLearningProbe } from "@shadowclone/learning";

export async function handleLearningProbe(arguments_: readonly string[]): Promise<boolean> {
  if (arguments_[0] !== "probe") return false;
  const key = arguments_[1];
  if (key === "status" && arguments_.length === 2) {
    console.log(JSON.stringify(await readLatestProbe(projectPaths), null, 2));
    return true;
  }
  const values = new Map<string, string>();
  let approved = false;
  for (let position = 2; position < arguments_.length; position += 1) {
    const argument = arguments_[position];
    if (argument === "--yes" && !approved) { approved = true; continue; }
    if (!argument || !["--agent", "--task", "--expect", "--model"].includes(argument) || values.has(argument)) {
      throw new Error("Use learning probe <key> --agent claude-code|codex --task <synthetic task> --expect <exact response> [--model <model>] --yes");
    }
    const value = arguments_[++position];
    if (!value || value.startsWith("--")) throw new Error(`${argument} requires a value`);
    values.set(argument, value);
  }
  if (!key) throw new Error("Choose a published rule key");
  const receipt = await runLearningProbe({
    paths: projectPaths, cwd: process.cwd(), key,
    engine: z.enum(["claude-code", "codex"]).parse(values.get("--agent")),
    task: values.get("--task") ?? "", expected: values.get("--expect") ?? "",
    model: values.get("--model"), approved,
  });
  console.log(JSON.stringify(receipt, null, 2));
  if (receipt.outcome !== "pass") process.exitCode = 1;
  return true;
}
