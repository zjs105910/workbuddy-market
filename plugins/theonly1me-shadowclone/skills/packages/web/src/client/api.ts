import { z } from "zod";

const supplied = window.location.hash.slice(1);
const token = supplied || sessionStorage.getItem("shadowclone-session") || "";

if (supplied) {
  sessionStorage.setItem("shadowclone-session", supplied);
  history.replaceState(null, "", `${location.pathname}${location.search}`);
}

export async function request<Output>(options: {
  readonly path: string;
  readonly schema: z.ZodType<Output>;
  readonly body?: unknown;
  readonly signal?: AbortSignal;
}): Promise<Output> {
  const response = await fetch(options.path, {
    method: options.body === undefined ? "GET" : "POST",
    headers: {
      Authorization: `Bearer ${token}`,
      "Content-Type": "application/json",
    },
    body: options.body === undefined ? undefined : JSON.stringify(options.body),
    signal: options.signal,
  });
  const payload: unknown = await response.json();

  if (!response.ok) {
    const error = z.object({ error: z.string() }).safeParse(payload);

    throw new Error(
      error.success
        ? error.data.error
        : "The local editor could not complete this action.",
    );
  }

  return options.schema.parse(payload);
}
