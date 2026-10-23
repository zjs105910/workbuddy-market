import { readBoundedFile, maximumProfileBytes } from "@shadowclone/core";
import { resolveRedacted } from "@shadowclone/sessions";
import { parseProfileRejectionText, type ProfileRejection } from "./state";

export type MaterializedProfileRejection = {
  readonly rejection: ProfileRejection;
  readonly promptTitle: string | null;
  readonly promptBody: string | null;
};

type LineRange = {
  readonly text: string;
  readonly start: number;
};

function nonemptyLineRanges(text: string): readonly LineRange[] {
  const lines: LineRange[] = [];
  let start = 0;

  for (;;) {
    const newline = text.indexOf("\n", start);
    const end = newline < 0 ? text.length : newline;
    const line = text.slice(start, end);

    if (line.trim().length > 0) {
      lines.push({ text: line, start });
    }

    if (newline < 0) {
      return lines;
    }

    start = newline + 1;
  }
}

function stringLiteralRange(options: {
  readonly line: LineRange;
  readonly field: "title" | "body";
  readonly value: string;
}): { readonly start: number; readonly end: number; readonly literal: string } {
  const prefix = `"${options.field}":`;
  const fieldStart = options.line.text.indexOf(prefix);
  const literal = JSON.stringify(options.value);

  if (fieldStart < 0 || literal === undefined) {
    throw new Error("Profile rejection state contains an invalid prompt field");
  }

  const start = fieldStart + prefix.length;

  if (!options.line.text.startsWith(literal, start)) {
    throw new Error("Profile rejection state contains an invalid prompt field");
  }

  return {
    start: options.line.start + start,
    end: options.line.start + start + literal.length,
    literal,
  };
}

async function redactedString(options: {
  readonly filePath: string;
  readonly profileDirectory: string;
  readonly raw: string;
  readonly line: LineRange;
  readonly field: "title" | "body";
  readonly value: string | null;
}): Promise<string | null> {
  if (options.value === null) {
    return null;
  }

  const range = stringLiteralRange({
    line: options.line,
    field: options.field,
    value: options.value,
  });
  const byteOffset = Buffer.byteLength(
    options.raw.slice(0, range.start),
    "utf8",
  );
  const byteLength = Buffer.byteLength(range.literal, "utf8");

  const text = await resolveRedacted({
    ref: {
      type: "file",
      sourcePath: options.filePath,
      byteOffset,
      byteLength,
      contentHash: new Bun.CryptoHasher("sha256")
        .update(range.literal)
        .digest("hex"),
    },
    roots: [options.profileDirectory],
  });

  try {
    const value: unknown = JSON.parse(text);

    if (typeof value === "string") {
      return value;
    }
  } catch {
    throw new Error("Profile rejection prompt field could not be redacted");
  }

  throw new Error("Profile rejection prompt field could not be redacted");
}

export async function readMaterializedProfileRejections(options: {
  readonly filePath: string;
  readonly profileDirectory: string;
}): Promise<readonly MaterializedProfileRejection[]> {
  const raw = await readBoundedFile({
    filePath: options.filePath,
    roots: [options.profileDirectory],
    maximumBytes: maximumProfileBytes,
  });

  if (raw === null) {
    return [];
  }

  const rejections = parseProfileRejectionText(raw);
  const lines = nonemptyLineRanges(raw);

  if (lines.length !== rejections.length) {
    throw new Error("Profile rejection state does not match its prompt fields");
  }

  return Promise.all(
    rejections.map(async (rejection, index) => {
      const line = lines[index];

      if (line === undefined) {
        throw new Error(
          "Profile rejection state does not match its prompt fields",
        );
      }

      const common = {
        filePath: options.filePath,
        profileDirectory: options.profileDirectory,
        raw,
        line,
      };

      const [promptTitle, promptBody] = await Promise.all([
        redactedString({ ...common, field: "title", value: rejection.title }),
        redactedString({ ...common, field: "body", value: rejection.body }),
      ]);

      return { rejection, promptTitle, promptBody };
    }),
  );
}
