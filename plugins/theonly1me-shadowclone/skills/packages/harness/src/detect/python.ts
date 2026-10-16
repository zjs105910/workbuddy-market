import toml from "smol-toml";
import { z } from "zod";
import type { KnownTool } from "@shadowclone/profile";
import type { PythonFacts } from "../types";

const pyprojectSchema = z.object({
  project: z
    .object({
      dependencies: z.array(z.string()).optional(),
      "optional-dependencies": z
        .record(z.string(), z.array(z.string()))
        .optional(),
    })
    .optional(),
  "dependency-groups": z.record(z.string(), z.array(z.unknown())).optional(),
  tool: z.record(z.string(), z.unknown()).optional(),
});

const pythonMarkers = [
  "pyproject.toml",
  "requirements.txt",
  "setup.py",
  "setup.cfg",
] as const;

export function hasPythonProject(entries: readonly string[]): boolean {
  return pythonMarkers.some((marker) => entries.includes(marker));
}

function dependencyNames(
  pyproject: z.infer<typeof pyprojectSchema>,
): ReadonlySet<string> {
  const declared = [
    ...(pyproject.project?.dependencies ?? []),
    ...Object.values(pyproject.project?.["optional-dependencies"] ?? {}).flat(),
    ...Object.values(pyproject["dependency-groups"] ?? {})
      .flat()
      .filter((entry): entry is string => typeof entry === "string"),
  ];

  return new Set(
    declared.map((entry) => entry.split(/[\s<>=!~;[]/)[0]?.toLowerCase() ?? ""),
  );
}

export function detectPython(options: {
  readonly entries: readonly string[];
  readonly pyprojectText: string | null;
  readonly requirementsText: string | null;
}): { readonly facts: PythonFacts; readonly tools: readonly KnownTool[] } {
  let parsed: z.infer<typeof pyprojectSchema> = {};

  if (options.pyprojectText !== null) {
    let document: unknown;

    try {
      document = toml.parse(options.pyprojectText);
    } catch {
      throw new Error("pyproject.toml could not be parsed");
    }

    const result = pyprojectSchema.safeParse(document);

    parsed = result.success ? result.data : {};
  }

  const names = new Set([
    ...dependencyNames(parsed),
    ...(options.requirementsText ?? "")
      .split("\n")
      .map((line) => line.split(/[\s<>=!~;[]/)[0]?.toLowerCase() ?? ""),
  ]);
  const tool = parsed.tool ?? {};
  const usesPytest =
    names.has("pytest") ||
    "pytest" in tool ||
    options.entries.includes("pytest.ini") ||
    options.entries.includes("conftest.py");

  const packageManager = options.entries.includes("uv.lock")
    ? "uv"
    : options.entries.includes("poetry.lock") || "poetry" in tool
      ? "poetry"
      : "pip";
  const tools = new Set<KnownTool>(["python"]);

  if (usesPytest) {
    tools.add("pytest");
  }

  if (packageManager === "uv") {
    tools.add("uv");
  }

  if (packageManager === "poetry") {
    tools.add("poetry");
  }

  if (
    "ruff" in tool ||
    names.has("ruff") ||
    options.entries.includes("ruff.toml")
  ) {
    tools.add("ruff");
  }

  if (
    "mypy" in tool ||
    names.has("mypy") ||
    options.entries.includes("mypy.ini")
  ) {
    tools.add("mypy");
  }

  return {
    facts: {
      packageManager,
      testRunner: usesPytest ? "pytest" : "unittest",
      hasRequirements: options.requirementsText !== null,
    },
    tools: [...tools],
  };
}
