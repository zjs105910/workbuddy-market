import { readFileSync } from "node:fs";
import path from "node:path";
import { runCommand } from "./git";

export type ParsedArguments = {
  readonly positionals: readonly string[];
  readonly values: ReadonlyMap<string, readonly string[]>;
  readonly switches: ReadonlySet<string>;
};

export function parseArguments(options: {
  readonly args: readonly string[];
  readonly valueFlags: readonly string[];
}): ParsedArguments {
  const positionals: string[] = [];
  const values = new Map<string, string[]>();
  const switches = new Set<string>();
  let index = 0;

  while (index < options.args.length) {
    const argument = options.args[index] ?? "";
    const [flag, inline] = argument.startsWith("--") ? argument.split(/=(.*)/s) : [argument, undefined];
    const name = flag ?? argument;

    if (name.startsWith("-") && name !== "-" && options.valueFlags.includes(name)) {
      const value = inline ?? options.args[index + 1] ?? "";

      values.set(name, [...(values.get(name) ?? []), value]);
      index += inline === undefined ? 2 : 1;
    } else if (name.startsWith("-") && name !== "-") {
      switches.add(name);
      index += 1;
    } else {
      positionals.push(argument);
      index += 1;
    }
  }

  return { positionals, values, switches };
}

export function firstValue(options: {
  readonly parsed: ParsedArguments;
  readonly names: readonly string[];
}): string | undefined {
  for (const name of options.names) {
    const found = options.parsed.values.get(name)?.[0];

    if (found !== undefined) {
      return found;
    }
  }

  return undefined;
}

export function hasSwitch(options: {
  readonly parsed: ParsedArguments;
  readonly names: readonly string[];
}): boolean {
  return options.names.some((name) => options.parsed.switches.has(name));
}

export function readBody(options: {
  readonly parsed: ParsedArguments;
  readonly cwd: string;
}): string | undefined {
  const inline = firstValue({ parsed: options.parsed, names: ["--body", "-b"] });

  if (inline !== undefined) {
    return inline;
  }

  const file = firstValue({ parsed: options.parsed, names: ["--body-file", "-F"] });

  if (file === undefined) {
    return undefined;
  }

  return readFileSync(file === "-" ? 0 : path.resolve(options.cwd, file), "utf8");
}

export function applyJq(options: {
  readonly value: unknown;
  readonly expression: string | undefined;
  readonly cwd: string;
}): { readonly text: string; readonly exitCode: number } {
  const json = JSON.stringify(options.value, null, 2);

  if (options.expression === undefined) {
    return { text: `${json}\n`, exitCode: 0 };
  }

  const result = runCommand({
    command: ["jq", "-r", options.expression],
    cwd: options.cwd,
    stdin: json,
  });

  return { text: result.exitCode === 0 ? result.stdout : result.stderr, exitCode: result.exitCode };
}

export function pickFields(options: {
  readonly record: Readonly<Record<string, unknown>>;
  readonly fields: string | undefined;
}): Readonly<Record<string, unknown>> {
  if (options.fields === undefined) {
    return options.record;
  }

  return Object.fromEntries(
    options.fields
      .split(",")
      .map((field) => field.trim())
      .filter((field) => field.length > 0)
      .map((field) => [field, options.record[field] ?? null]),
  );
}
