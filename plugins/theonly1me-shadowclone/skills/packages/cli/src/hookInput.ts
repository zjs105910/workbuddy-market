import { z } from "zod";

const hookRecordSchema = z.record(z.string(), z.unknown());

export function parseHookInput(
  input: string,
): Readonly<Record<string, unknown>> {
  let parsed: unknown;

  try {
    parsed = JSON.parse(input);
  } catch {
    throw new Error("Hook input must be a JSON object");
  }

  const result = hookRecordSchema.safeParse(parsed);

  if (!result.success) {
    throw new Error("Hook input must be a JSON object");
  }

  return result.data;
}

export function readHookString(
  record: Readonly<Record<string, unknown>>,
  key: string,
): string | null {
  const value = record[key];

  return typeof value === "string" ? value : null;
}
