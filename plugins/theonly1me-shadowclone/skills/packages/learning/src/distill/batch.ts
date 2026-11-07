import type { CorrectionSignal, OriginScope } from "@shadowclone/sessions";

export type DistillBatch = {
  readonly origin: OriginScope;
  readonly repositoryName: string | null;
  readonly signals: readonly CorrectionSignal[];
};

export const distillSignalBatchSize = 20;
export const distillConcurrency = 8;

export function groupDistillBatches(options: {
  readonly signals: readonly CorrectionSignal[];
  readonly batchSize?: number;
}): readonly DistillBatch[] {
  const batchSize = options.batchSize ?? distillSignalBatchSize;

  if (!Number.isInteger(batchSize) || batchSize < 1) {
    throw new Error("Distillation batch size must be a positive integer");
  }

  const batches: DistillBatch[] = [];
  const grouped = Map.groupBy(
    options.signals,
    (signal) => `${signal.origin.id}\u0000${signal.repositoryName ?? ""}`,
  );

  for (const signals of grouped.values()) {
    const [first] = signals;

    if (!first) {
      continue;
    }

    for (let offset = 0; offset < signals.length; offset += batchSize) {
      batches.push({
        origin: first.origin,
        repositoryName: first.repositoryName,
        signals: signals.slice(offset, offset + batchSize),
      });
    }
  }

  return batches;
}
