import type {
  HarnessCommand,
  HarnessGate,
  NodeFacts,
  PythonFacts,
  RepositoryFacts,
} from "./types";

const checkScriptNames = ["check", "verify", "validate", "ci"] as const;
const typecheckScriptNames = [
  "typecheck",
  "type-check",
  "types",
  "tsc",
] as const;

function runScript(options: {
  readonly node: NodeFacts;
  readonly name: string;
}): string {
  return options.node.packageManager === "yarn"
    ? `yarn ${options.name}`
    : `${options.node.packageManager} run ${options.name}`;
}

function scriptCommand(options: {
  readonly node: NodeFacts | null;
  readonly names: readonly string[];
}): string | null {
  const { node } = options;
  const name =
    node === null
      ? undefined
      : options.names.find((candidate) => candidate in node.scripts);

  return node === null || name === undefined ? null : runScript({ node, name });
}

function pythonTool(options: {
  readonly python: PythonFacts;
  readonly command: string;
}): string {
  if (options.python.packageManager === "uv") {
    return `uv run ${options.command}`;
  }

  if (options.python.packageManager === "poetry") {
    return `poetry run ${options.command}`;
  }

  return options.command.startsWith("python ")
    ? `python3 ${options.command.slice("python ".length)}`
    : options.command;
}

function pythonTests(python: PythonFacts): string {
  return pythonTool({
    python,
    command:
      python.testRunner === "pytest"
        ? "python -m pytest"
        : "python -m unittest",
  });
}

function pythonLint(facts: RepositoryFacts): string | null {
  return facts.python !== null && facts.tools.has("ruff")
    ? pythonTool({ python: facts.python, command: "ruff check ." })
    : null;
}

function pythonTypecheck(facts: RepositoryFacts): string | null {
  return facts.python !== null && facts.tools.has("mypy")
    ? pythonTool({ python: facts.python, command: "mypy ." })
    : null;
}

function testCommand(facts: RepositoryFacts): string | null {
  return (
    scriptCommand({ node: facts.node, names: ["test"] }) ??
    (facts.python === null ? null : pythonTests(facts.python)) ??
    (facts.rust ? "cargo test" : null) ??
    (facts.go ? "go test ./..." : null)
  );
}

function gateCandidate(
  facts: RepositoryFacts,
): { readonly command: string; readonly source: string } | null {
  const checkScript = scriptCommand({
    node: facts.node,
    names: checkScriptNames,
  });

  if (checkScript !== null) {
    return { command: checkScript, source: "the repository's check script" };
  }

  const makeCheck = ["check", "verify"].find((target) =>
    facts.makeTargets.includes(target),
  );

  if (makeCheck !== undefined) {
    return { command: `make ${makeCheck}`, source: "the Makefile" };
  }

  const composed = [
    scriptCommand({ node: facts.node, names: typecheckScriptNames }) ??
      pythonTypecheck(facts),
    scriptCommand({ node: facts.node, names: ["lint"] }) ?? pythonLint(facts),
    testCommand(facts),
  ].filter((command): command is string => command !== null);

  if (composed.length > 0) {
    return {
      command: composed.join(" && "),
      source: "the repository's typecheck, lint, and test commands",
    };
  }

  if (facts.makeTargets.includes("test")) {
    return { command: "make test", source: "the Makefile" };
  }

  if (facts.node?.packageManager === "bun") {
    return { command: "bun test", source: "Bun's test runner" };
  }

  return null;
}

export function chooseGate(facts: RepositoryFacts): HarnessGate | null {
  const candidate = gateCandidate(facts);

  return candidate === null
    ? null
    : {
        ...candidate,
        ciRunsGate: facts.ciWorkflows.some((workflow) =>
          workflow.includes(candidate.command),
        ),
      };
}

function installCommand(facts: RepositoryFacts): string | null {
  if (facts.node !== null) {
    return `${facts.node.packageManager} install`;
  }

  if (facts.python?.packageManager === "uv") {
    return "uv sync";
  }

  if (facts.python?.packageManager === "poetry") {
    return "poetry install";
  }

  return facts.python?.hasRequirements
    ? "python3 -m pip install -r requirements.txt"
    : null;
}

export function harnessCommands(options: {
  readonly facts: RepositoryFacts;
  readonly gate: HarnessGate | null;
}): readonly HarnessCommand[] {
  const { facts, gate } = options;
  const entries: readonly {
    readonly label: HarnessCommand["label"];
    readonly command: string | null;
  }[] = [
    { label: "Install", command: installCommand(facts) },
    { label: "Gate", command: gate?.command ?? null },
    { label: "Tests", command: testCommand(facts) },
    {
      label: "Lint",
      command:
        scriptCommand({ node: facts.node, names: ["lint"] }) ??
        pythonLint(facts),
    },
    {
      label: "Typecheck",
      command:
        scriptCommand({ node: facts.node, names: typecheckScriptNames }) ??
        pythonTypecheck(facts),
    },
  ];

  return entries.flatMap((entry) =>
    entry.command === null ||
    (entry.label !== "Gate" && entry.command === gate?.command)
      ? []
      : [{ label: entry.label, command: entry.command }],
  );
}
