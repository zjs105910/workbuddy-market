import type { GithubRequest } from "../types";

export function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

export function record(value: unknown): Record<string, unknown> {
  return isRecord(value) ? value : {};
}

export function records(value: unknown): Record<string, unknown>[] {
  return Array.isArray(value) ? value.map(record) : [];
}

export async function readGithub(options: {
  readonly request: GithubRequest;
  readonly route: string;
  readonly parameters?: Record<string, unknown>;
}) {
  return record((await options.request(options.route, options.parameters)).data);
}

export async function readIssueEvents(options: {
  readonly request: GithubRequest;
  readonly route: string;
}): Promise<Record<string, unknown>[] | null> {
  const events: Record<string, unknown>[] = [];

  for (let page = 1; page <= 10; page++) {
    const entries = records((await options.request(options.route, { per_page: 100, page })).data);

    events.push(...entries);

    if (entries.length < 100) {
      return events;
    }
  }

  return null;
}

export function positiveNumber(value: unknown): number | null {
  const number =
    typeof value === "number"
      ? value
      : typeof value === "string" && /^\d+$/.test(value)
        ? Number(value)
        : 0;

  return Number.isSafeInteger(number) && number > 0 ? number : null;
}
