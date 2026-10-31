import { expect, test } from "bun:test";
import { mkdtemp } from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import { canonicalPath } from "@shadowclone/core";
import {
  materializeFixture,
  type FixtureRepository,
} from "../fixtures/materialize";
import { bunTaskList } from "../fixtures/bunTaskList";
import { pythonConfig } from "../fixtures/pythonConfig";
import { chooseGate, harnessCommands } from "../gate";
import { detectRepository } from "./index";

async function repository(
  files: Readonly<Record<string, string>>,
): Promise<string> {
  const fixture: FixtureRepository = {
    name: "repository",
    files,
    specification: "",
    acceptance: {},
    acceptanceCommand: "",
  };

  return materializeFixture({
    fixture,
    parent: canonicalPath(
      await mkdtemp(path.join(os.tmpdir(), "shadowclone-detect-")),
    ),
  });
}

test("the Bun fixture uses its check script as the gate", async () => {
  const facts = await detectRepository(
    await materializeFixture({ fixture: bunTaskList }),
  );

  expect(facts.node?.packageManager).toBe("bun");
  expect([...facts.tools]).toEqual(
    expect.arrayContaining(["bun", "typescript"]),
  );
  expect(chooseGate(facts)).toEqual({
    command: "bun run check",
    source: "the repository's check script",
    ciRunsGate: false,
  });
});

test("the Python fixture gets a unittest gate and no Node tooling", async () => {
  const facts = await detectRepository(
    await materializeFixture({ fixture: pythonConfig }),
  );

  expect(facts.python).toEqual({
    packageManager: "pip",
    testRunner: "unittest",
    hasRequirements: false,
  });
  expect(facts.node).toBeNull();
  expect([...facts.tools]).toEqual(["python"]);
  expect(chooseGate(facts)?.command).toBe("python3 -m unittest");
});

test("without a check script the gate composes typecheck, lint, and test", async () => {
  const root = await repository({
    "package.json": JSON.stringify({
      scripts: { typecheck: "tsc", lint: "eslint .", test: "vitest run" },
    }),
    "package-lock.json": "{}",
  });
  const facts = await detectRepository(root);
  const gate = chooseGate(facts);

  expect(gate?.command).toBe(
    "npm run typecheck && npm run lint && npm run test",
  );
  expect(
    harnessCommands({ facts, gate }).map((command) => command.label),
  ).toEqual(["Install", "Gate", "Tests", "Lint", "Typecheck"]);
});

test("a Makefile check target outranks composed scripts, and CI running it is detected", async () => {
  const root = await repository({
    "package.json": JSON.stringify({ scripts: { test: "jest" } }),
    Makefile: "check:\n\tnpm test\n",
    ".github/workflows/ci.yml":
      "jobs:\n  test:\n    steps:\n      - run: |\n          npm ci\n          make check\n",
  });

  expect(chooseGate(await detectRepository(root))).toEqual({
    command: "make check",
    source: "the Makefile",
    ciRunsGate: true,
  });
});

test("pytest and uv produce a uv-run pytest gate", async () => {
  const root = await repository({
    "pyproject.toml":
      '[project]\nname = "service"\n[dependency-groups]\ndev = ["pytest>=8"]\n',
    "uv.lock": "",
  });
  const facts = await detectRepository(root);

  expect([...facts.tools].sort()).toEqual(["pytest", "python", "uv"]);
  expect(chooseGate(facts)?.command).toBe("uv run python -m pytest");
});
