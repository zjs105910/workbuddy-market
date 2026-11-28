import { collectReview, readPullFacts } from "../collect";
import { checkDependencies } from "../dependencies";
import { checkBuiltInRules } from "../rules";
import { runToolchain } from "../toolchain";
import type { PullFacts } from "../types";
import type { ChecksFile, PacketFile } from "./schemas";

export { analyzeStage } from "./analyze";
export { checksFileSchema, packetFileSchema, type ChecksFile, type PacketFile } from "./schemas";

export async function prepareStage(options: {
  readonly repository: string;
  readonly number: number;
  readonly checkout: string;
  readonly cwd: string;
  readonly network: boolean;
  readonly head?: string;
}): Promise<PacketFile> {
  const current = await readPullFacts({ repository: options.repository, number: options.number, cwd: options.cwd });
  const facts = options.head === undefined ? current : { ...current, headSha: options.head };

  return preparePacket({ facts, checkout: options.checkout, network: options.network });
}

export async function preparePacket(options: {
  readonly facts: PullFacts;
  readonly checkout: string;
  readonly network: boolean;
}): Promise<PacketFile> {
  const { facts } = options;
  const context = await collectReview({ checkout: options.checkout, facts });

  const dependencies = await checkDependencies({
    checkout: options.checkout,
    baseSha: context.mergeBaseSha,
    headSha: facts.headSha,
    files: context.files,
    network: options.network,
  });

  return {
    version: 1,
    context,
    ruleHits: [...dependencies.hits, ...checkBuiltInRules(context.files)],
    reports: dependencies.reports,
  };
}

export async function checksStage(options: {
  readonly packet: PacketFile;
  readonly repository: string;
  readonly workDirectory: string;
  readonly onProgress: (message: string) => void;
}): Promise<ChecksFile> {
  const { facts, files, mergeBaseSha } = options.packet.context;
  const reports = await runToolchain({
    repository: options.repository,
    baseSha: mergeBaseSha,
    headSha: facts.headSha,
    files,
    workDirectory: options.workDirectory,
    onProgress: options.onProgress,
  });

  return { version: 1, headSha: facts.headSha, reports };
}
