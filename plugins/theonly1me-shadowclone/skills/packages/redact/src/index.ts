import { readBoundedFile } from "@shadowclone/core";
import os from "node:os";
import { redactionRules } from "./rules";

export { redactionRules } from "./rules";

function escapeRegExp(value: string): string {
  return value.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
}

function replaceHomeDirectory(options: {
  readonly text: string;
  readonly homeDirectory: string;
}): string {
  if (options.homeDirectory.length === 0) {
    return options.text;
  }

  const escaped = escapeRegExp(options.homeDirectory);
  const filePrefix = ["file:", "", ""].join("/");
  const unslashed = escaped.startsWith("/") ? escaped.slice(1) : escaped;
  const fileUrlPattern = new RegExp(
    `(${filePrefix}/?)${unslashed}(?=[/\\\\\\s"'\\),]|$)`,
    "gm",
  );
  const pattern = new RegExp(
    `(^|[\\s"'\\(=:,])${escaped}(?=[/\\\\\\s"'\\),]|$)`,
    "gm",
  );

  return options.text.replace(fileUrlPattern, "$1~").replace(pattern, "$1~");
}

export function redactSecrets(options: {
  readonly text: string;
  readonly homeDirectory?: string;
}): string {
  const homeDirectory = options.homeDirectory ?? os.homedir();

  let redacted = homeDirectory
    ? replaceHomeDirectory({ text: options.text, homeDirectory })
    : options.text;

  for (const rule of redactionRules) {
    redacted = redacted.replace(rule.pattern, rule.replace);
  }

  return redacted;
}

export const redactionLabels: readonly string[] = redactionRules.map(
  (rule) => rule.label,
);

export async function materializeSnapshot<Value>(options: {
  readonly filePath: string;
  readonly roots: readonly string[];
  readonly maximumBytes: number;
  readonly parse: (text: string) => Value;
}): Promise<{ readonly parsed: Value; readonly redacted: string } | null> {
  const text = await readBoundedFile(options);

  return text === null
    ? null
    : { parsed: options.parse(text), redacted: redactSecrets({ text }) };
}
