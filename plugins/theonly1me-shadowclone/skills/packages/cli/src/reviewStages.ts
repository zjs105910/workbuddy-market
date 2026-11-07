import { mkdtemp, rm } from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import {
  runClaudeCode,
  runCodex,
  reasoningEfforts,
  type ReasoningEffort,
} from "@shadowclone/agents";
import { publishReview, reviewResultSchema } from "@shadowclone/review";
import { defaultCodexReviewModel } from "@shadowclone/review";
import { analyzeStage, checksFileSchema, checksStage, packetFileSchema, prepareStage } from "@shadowclone/review";
import { defaultReviewModel } from "./reviewArguments";

const stageUsage = [
  "shadowclone review prepare --repo owner/repository --pr <number> --checkout <directory> --output <file> [--head <sha>] [--network on|off]",
  "shadowclone review checks --packet <file> --checkout <directory> --output <file>",
  "shadowclone review analyze --packet <file> [--checks <file>] --checkout <directory> --output <file> [--engine claude|codex] [--model <id>] [--effort <level>] [--network on|off]",
  "shadowclone review publish --input <file>",
].join("\n");

function readFlags(options: { readonly arguments: readonly string[]; readonly allowed: readonly string[] }): ReadonlyMap<string, string> {
  const flags = new Map<string, string>();

  for (let position = 0; position < options.arguments.length; position += 2) {
    const flag = options.arguments[position];
    const value = options.arguments[position + 1];

    if (!flag || value === undefined || !options.allowed.includes(flag) || flags.has(flag)) {
      throw new Error(`Use:\n${stageUsage}`);
    }

    flags.set(flag, value);
  }

  return flags;
}

function required(options: { readonly flags: ReadonlyMap<string, string>; readonly name: string }): string {
  const value = options.flags.get(options.name);

  if (value === undefined) {
    throw new Error(`Use:\n${stageUsage}`);
  }

  return value;
}

function isReasoningEffort(value: string): value is ReasoningEffort {
  return reasoningEfforts.some((effort) => effort === value);
}

async function writeJson(options: { readonly file: string; readonly value: unknown }): Promise<void> {
  await Bun.write(path.resolve(options.file), JSON.stringify(options.value));
}

export const reviewStages: Readonly<Record<string, (arguments_: readonly string[]) => Promise<void>>> = {
  prepare: async (arguments_) => {
    const flags = readFlags({ arguments: arguments_, allowed: ["--repo", "--pr", "--checkout", "--output", "--head", "--network"] });
    const number = Number(required({ flags, name: "--pr" }));
    const head = flags.get("--head");
    const network = flags.get("--network") ?? "on";

    if (!Number.isInteger(number) || number <= 0 || (head !== undefined && !/^[a-f0-9]{40}$/.test(head)) || (network !== "on" && network !== "off")) {
      throw new Error(`Use:\n${stageUsage}`);
    }

    const packet = await prepareStage({
      repository: required({ flags, name: "--repo" }),
      number,
      checkout: path.resolve(required({ flags, name: "--checkout" })),
      cwd: process.cwd(),
      network: network === "on",
      ...(head === undefined ? {} : { head }),
    });

    await writeJson({ file: required({ flags, name: "--output" }), value: packet });
    console.log(`Prepared ${packet.context.files.length} changed files and ${packet.ruleHits.length} rule hits.`);
  },
  checks: async (arguments_) => {
    const flags = readFlags({ arguments: arguments_, allowed: ["--packet", "--checkout", "--output"] });
    const packet = packetFileSchema.parse(await Bun.file(path.resolve(required({ flags, name: "--packet" }))).json());
    const workDirectory = await mkdtemp(path.join(os.tmpdir(), "shadowclone-checks-"));

    try {
      const checks = await checksStage({
        packet,
        repository: path.resolve(required({ flags, name: "--checkout" })),
        workDirectory,
        onProgress: (message) => console.error(message),
      });

      await writeJson({ file: required({ flags, name: "--output" }), value: checks });
      console.log(checks.reports.map((report) => `${report.stack} ${report.tool}: ${report.status}, ${report.diagnostics.length} new`).join("\n") || "No toolchain applies.");
    } finally {
      await rm(workDirectory, { recursive: true, force: true });
    }
  },
  analyze: async (arguments_) => {
    const flags = readFlags({ arguments: arguments_, allowed: ["--packet", "--checks", "--checkout", "--output", "--engine", "--model", "--effort", "--network"] });
    const engine = flags.get("--engine") ?? "claude";
    const effort = flags.get("--effort") ?? null;
    const checksFile = flags.get("--checks");

    const network = flags.get("--network") ?? "on";

    if (effort !== null && !isReasoningEffort(effort)) {
      throw new Error(`Choose an effort from ${reasoningEfforts.join(", ")}.`);
    }

    if (engine !== "claude" && engine !== "codex") {
      throw new Error("Choose --engine claude or --engine codex.");
    }

    if (network !== "on" && network !== "off") {
      throw new Error(`Use:\n${stageUsage}`);
    }

    const result = await analyzeStage({
      packet: packetFileSchema.parse(await Bun.file(path.resolve(required({ flags, name: "--packet" }))).json()),
      checks: checksFile === undefined ? null : checksFileSchema.parse(await Bun.file(path.resolve(checksFile)).json()),
      checkout: path.resolve(required({ flags, name: "--checkout" })),
      reviewModel: {
        runner: engine === "codex" ? runCodex : runClaudeCode,
        engine,
        model: flags.get("--model") ?? (engine === "codex" ? defaultCodexReviewModel : defaultReviewModel),
        effort,
        network: network === "on",
      },
    });

    await writeJson({ file: required({ flags, name: "--output" }), value: result });
    console.log(JSON.stringify({ findings: result.findings.length, ...result.statistics }));
  },
  publish: async (arguments_) => {
    const flags = readFlags({ arguments: arguments_, allowed: ["--input"] });
    const result = reviewResultSchema.parse(await Bun.file(path.resolve(required({ flags, name: "--input" }))).json());

    console.log(await publishReview({ result, cwd: process.cwd() }));
  },
};
