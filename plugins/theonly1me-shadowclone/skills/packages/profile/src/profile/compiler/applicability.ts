import type { CompilerBlock } from "./types";

export type RepositoryApplicability = {
  readonly tools: ReadonlySet<string>;
  readonly entries: ReadonlySet<string>;
};

export const toolPatterns = {
  bun: /\bbun\b/i,
  npm: /\bnpm\b|\bnpx\b/i,
  pnpm: /\bpnpm\b/i,
  yarn: /\byarn\b/i,
  deno: /\bdeno\b/i,
  typescript: /\btypescript\b|\btsc\b|\.tsx?\b/i,
  python: /\bpython\d?\b|\bpip\b|\.py\b/i,
  pytest: /\bpytest\b/i,
  poetry: /\bpoetry\b/i,
  uv: /\buv (?:run|sync|pip|add)\b/i,
  ruff: /\bruff\b/i,
  mypy: /\bmypy\b/i,
  jest: /\bjest\b/i,
  vitest: /\bvitest\b/i,
  mocha: /\bmocha\b/i,
  eslint: /\beslint\b/i,
  prettier: /\bprettier\b/i,
  biome: /\bbiome\b/i,
  rust: /\bcargo\b|\brust\b|\.rs\b/i,
  go: /\bgo (?:test|build|vet|mod|run|fmt)\b|\bgolang\b|\bgofmt\b/i,
  react: /\breact\b/i,
  nx: /\bnx\b/i,
  docker: /\bdocker(?:file)?\b/i,
  make: /\bmake (?:check|test|lint|build)\b|\bmakefile\b/i,
} as const;

export type KnownTool = keyof typeof toolPatterns;

const backtickedToken = /`([A-Za-z0-9_.-]+\/[A-Za-z0-9_./-]*)`/g;

function referencedTopLevelEntries(text: string): readonly string[] {
  return [...text.matchAll(backtickedToken)].flatMap((match) => {
    const token = match[1] ?? "";
    const looksLikePath =
      token.endsWith("/") ||
      /\.[A-Za-z0-9]{1,5}$/.test(token) ||
      token.split("/").length > 2;
    const [first = ""] = token.split("/");

    return looksLikePath && first !== "." && first !== ".." ? [first] : [];
  });
}

export function isNotApplicable(options: {
  readonly block: CompilerBlock;
  readonly applicability: RepositoryApplicability;
}): boolean {
  const text = options.block.visible;
  const mentioned = Object.entries(toolPatterns)
    .filter(([, pattern]) => pattern.test(text))
    .map(([tool]) => tool);
  const namesOnlyAbsentTools =
    mentioned.length > 0 &&
    !mentioned.some((tool) => options.applicability.tools.has(tool));
  const namesAbsentPath = referencedTopLevelEntries(text).some(
    (entry) => !options.applicability.entries.has(entry),
  );

  return namesOnlyAbsentTools || namesAbsentPath;
}
