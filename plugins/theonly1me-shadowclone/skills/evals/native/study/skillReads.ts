import path from "node:path";

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function shellBody(command: string): string | null {
  const marker = " -lc ";
  const position = command.indexOf(marker);
  if (position < 0) return null;
  const raw = command.slice(position + marker.length).trim();
  if (raw.length < 2) return null;
  const quote = raw[0];
  if ((quote !== "'" && quote !== '"') || raw.at(-1) !== quote) return null;
  return raw.slice(1, -1).replaceAll('\\"', '"');
}

function directRead(options: { command: string; filePath: string; directory?: string }): boolean {
  const body = shellBody(options.command);
  if (!body) return false;
  const match =
    /^(?:cat|head -n \d+|sed -n ['"][^'";|&]+['"])\s+(?:'([^']+)'|"([^"$`]+)"|([^\s'"$`;|&<>\\]+))$/.exec(
      body,
    );
  const operand = match?.[1] ?? match?.[2] ?? match?.[3];
  if (!operand || operand.startsWith("~") || operand.startsWith("-")) return false;
  if (path.isAbsolute(operand)) return path.normalize(operand) === options.filePath;
  return (
    options.directory !== undefined && path.resolve(options.directory, operand) === options.filePath
  );
}

function readCommands(command: string): string[] {
  const body = shellBody(command);
  if (!body || /[\n\r]/.test(body)) return [];
  const commands: string[] = [];
  let quote: string | null = null;
  let start = 0;
  for (let index = 0; index < body.length; index += 1) {
    const character = body[index];
    if (character === "\\" && quote !== "'") {
      index += 1;
      continue;
    }
    if (character === quote) {
      quote = null;
      continue;
    }
    if (!quote && (character === "'" || character === '"')) {
      quote = character;
      continue;
    }
    if (quote) continue;
    if (character === "&" && body[index + 1] === "&") {
      commands.push(body.slice(start, index).trim());
      index += 1;
      start = index + 1;
    } else if (
      (character && ";|&<>`".includes(character)) ||
      (character === "$" && body[index + 1] === "(")
    )
      return [];
  }
  if (quote) return [];
  commands.push(body.slice(start).trim());
  if (
    commands.some(
      (segment) => /^(?:cd|pushd|popd|if|while|for|eval|exec)\b/.test(segment) || !segment,
    )
  )
    return [];
  return commands.map((segment) => `/bin/sh -lc ${JSON.stringify(segment)}`);
}

export function observedSkillReads(options: {
  readonly stream: string;
  readonly skillPaths: Readonly<Record<string, string>>;
  readonly directory?: string;
  readonly skillContents?: Readonly<Record<string, string>>;
}): string[] {
  const names = new Set<string>();
  for (const line of options.stream.split("\n")) {
    let event: unknown;
    try {
      event = JSON.parse(line);
    } catch {
      continue;
    }
    if (!isRecord(event) || event.type !== "item.completed" || !isRecord(event.item)) continue;
    const item = event.item;
    if (
      (item.item_type ?? item.type) !== "command_execution" ||
      item.status !== "completed" ||
      typeof item.command !== "string"
    )
      continue;
    for (const [name, filePath] of Object.entries(options.skillPaths)) {
      const content = options.skillContents?.[name];
      const confirmedOutput =
        content !== undefined &&
        content.trim().length > 0 &&
        typeof item.aggregated_output === "string" &&
        item.aggregated_output.includes(content);
      if (
        (item.exit_code === 0 || confirmedOutput) &&
        readCommands(item.command).some((command) =>
          directRead({ command, filePath, directory: options.directory }),
        )
      )
        names.add(name);
    }
  }
  return [...names].sort();
}

export function claudeSkillReads(options: {
  readonly actions: readonly {
    readonly tool: string;
    readonly path: string | null;
    readonly command?: string | null;
  }[];
  readonly locations: Readonly<Record<string, readonly string[]>>;
}): string[] {
  const names = new Set<string>();

  for (const action of options.actions) {
    for (const [key, paths] of Object.entries(options.locations)) {
      const skill = key.slice(key.indexOf(":") + 1);
      const invoked =
        action.tool === "Skill" &&
        (action.command === skill || action.command?.endsWith(`:${skill}`) === true);
      const read = action.tool === "Read" && action.path !== null && paths.includes(action.path);

      if (invoked || read) {
        names.add(key);
      }
    }
  }

  return [...names].sort();
}
