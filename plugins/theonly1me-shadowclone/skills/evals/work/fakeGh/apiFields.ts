import { readFileSync } from "node:fs";
import path from "node:path";
import { z } from "zod";

export type ApiRequest = {
  readonly method: string;
  readonly endpoint: string;
  readonly fields: Readonly<Record<string, unknown>>;
  readonly jq: string | undefined;
};

const valueFlags = new Set(["-X", "--method", "-f", "--raw-field", "-F", "--field", "--input", "-q", "--jq", "-H", "--header", "-t", "--template", "--hostname", "--cache", "-p", "--preview"]);

function typedValue(options: { readonly raw: string; readonly cwd: string }): unknown {
  if (options.raw === "true" || options.raw === "false") {
    return options.raw === "true";
  }

  if (/^-?\d+$/.test(options.raw)) {
    return Number(options.raw);
  }

  if (options.raw.startsWith("@")) {
    const file = options.raw.slice(1);

    return readFileSync(file === "-" ? 0 : path.resolve(options.cwd, file), "utf8");
  }

  return options.raw;
}

function splitField(field: string): readonly [string, string] {
  const separator = field.indexOf("=");

  return separator < 0 ? [field, ""] : [field.slice(0, separator), field.slice(separator + 1)];
}

export function parseApiRequest(options: {
  readonly args: readonly string[];
  readonly cwd: string;
}): ApiRequest {
  const fields: Record<string, unknown> = {};
  const positionals: string[] = [];
  let method: string | undefined;
  let jq: string | undefined;
  let index = 0;

  while (index < options.args.length) {
    const argument = options.args[index] ?? "";
    const value = options.args[index + 1] ?? "";

    if (!valueFlags.has(argument)) {
      if (!argument.startsWith("-")) {
        positionals.push(argument);
      }

      index += 1;
      continue;
    }

    if (argument === "-X" || argument === "--method") {
      method = value.toUpperCase();
    } else if (argument === "-q" || argument === "--jq") {
      jq = value;
    } else if (argument === "-f" || argument === "--raw-field") {
      const [key, raw] = splitField(value);

      fields[key] = raw;
    } else if (argument === "-F" || argument === "--field") {
      const [key, raw] = splitField(value);

      fields[key] = typedValue({ raw, cwd: options.cwd });
    } else if (argument === "--input") {
      const parsed = z
        .record(z.string(), z.unknown())
        .safeParse(JSON.parse(readFileSync(value === "-" ? 0 : path.resolve(options.cwd, value), "utf8")));

      Object.assign(fields, parsed.success ? parsed.data : {});
    }

    index += 2;
  }

  const endpoint = (positionals[0] ?? "").replace(/^\//, "");
  const hasFields = Object.keys(fields).length > 0;

  return {
    method: method ?? (hasFields && endpoint !== "graphql" ? "POST" : endpoint === "graphql" ? "POST" : "GET"),
    endpoint,
    fields,
    jq,
  };
}

export function stringField(options: {
  readonly fields: Readonly<Record<string, unknown>>;
  readonly names: readonly string[];
}): string | undefined {
  for (const name of options.names) {
    const value = options.fields[name];

    if (typeof value === "string" || typeof value === "number") {
      return String(value);
    }
  }

  return undefined;
}
