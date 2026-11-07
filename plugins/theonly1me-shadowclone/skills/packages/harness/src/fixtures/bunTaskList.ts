import type { FixtureRepository } from "./materialize";

const packageJson = {
  name: "task-list",
  private: true,
  type: "module",
  scripts: {
    check: "bun run typecheck && bun test tests",
    typecheck: "tsc --noEmit",
    test: "bun test tests",
  },
  devDependencies: { "@types/bun": "latest", typescript: "^5" },
};

const tasks = `export type TaskStatus = "open" | "done";

export type Task = {
  readonly id: number;
  readonly title: string;
  readonly status: TaskStatus;
};

export function addTask(options: { readonly tasks: readonly Task[]; readonly title: string }): readonly Task[] {
  const id = options.tasks.reduce((highest, task) => Math.max(highest, task.id), 0) + 1;
  return [...options.tasks, { id, title: options.title, status: "open" }];
}

export function completeTask(options: { readonly tasks: readonly Task[]; readonly id: number }): readonly Task[] {
  if (!options.tasks.some((task) => task.id === options.id)) throw new Error("Unknown task");
  return options.tasks.map((task) => (task.id === options.id ? { ...task, status: "done" } : task));
}

export function renderTasks(tasks: readonly Task[]): string {
  return tasks.map((task) => \`\${task.id} [\${task.status === "done" ? "x" : " "}] \${task.title}\`).join("\\n");
}
`;

const cli = `import { addTask, completeTask, renderTasks, type Task } from "./tasks";

export function runCommand(options: { readonly tasks: readonly Task[]; readonly arguments: readonly string[] }): { readonly tasks: readonly Task[]; readonly output: string } {
  const [command, ...rest] = options.arguments;
  if (command === "add") return { tasks: addTask({ tasks: options.tasks, title: rest.join(" ") }), output: "added" };
  if (command === "done") return { tasks: completeTask({ tasks: options.tasks, id: Number(rest[0]) }), output: "done" };
  if (command === "list") return { tasks: options.tasks, output: renderTasks(options.tasks) };
  throw new Error("Use add <title>, done <id>, or list");
}
`;

const existingTests = `import { expect, test } from "bun:test";
import { runCommand } from "../src/cli";

test("adds and completes a task", () => {
  const added = runCommand({ tasks: [], arguments: ["add", "write", "docs"] });
  const completed = runCommand({ tasks: added.tasks, arguments: ["done", "1"] });
  expect(runCommand({ tasks: completed.tasks, arguments: ["list"] }).output).toBe("1 [x] write docs");
});
`;

const acceptance = `import { expect, test } from "bun:test";
import { runCommand } from "../../src/cli";

const tasks = runCommand({ tasks: runCommand({ tasks: runCommand({ tasks: [], arguments: ["add", "a"] }).tasks, arguments: ["add", "b"] }).tasks, arguments: ["done", "2"] }).tasks;

test("list --status open shows only open tasks", () => {
  expect(runCommand({ tasks, arguments: ["list", "--status", "open"] }).output).toBe("1 [ ] a");
});

test("list --status done shows only done tasks", () => {
  expect(runCommand({ tasks, arguments: ["list", "--status", "done"] }).output).toBe("2 [x] b");
});

test("an unknown status is rejected", () => {
  expect(() => runCommand({ tasks, arguments: ["list", "--status", "later"] })).toThrow();
});
`;

export const bunTaskList: FixtureRepository = {
  name: "bun-task-list",
  files: {
    "package.json": `${JSON.stringify(packageJson, null, 2)}\n`,
    "bun.lock": '{\n  "lockfileVersion": 1,\n  "workspaces": {}\n}\n',
    "tsconfig.json": `${JSON.stringify({ compilerOptions: { strict: true, noEmit: true, module: "ESNext", target: "ESNext", moduleResolution: "bundler", types: ["bun"] }, include: ["src", "tests"] }, null, 2)}\n`,
    "README.md": "# Task list\n\nA small command-line task list.\n",
    "src/tasks.ts": tasks,
    "src/cli.ts": cli,
    "tests/tasks.test.ts": existingTests,
  },
  specification:
    "Add a status filter: `list --status open` shows only open tasks, `list --status done` shows only done tasks, and any other status value is rejected with an error. `list` without the flag keeps its current output.",
  acceptance: { "tests/acceptance/status-filter.test.ts": acceptance },
  acceptanceCommand: "bun test tests/acceptance",
};
