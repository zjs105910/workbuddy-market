import { expect, test } from "bun:test";
import { runnerEnvironment } from "./environment";

const hostEnvironment = {
  PATH: "/usr/bin",
  HOME: "/home/person",
  TERM: "xterm",
  ANTHROPIC_API_KEY: "sk-ant-example",
  OPENAI_API_KEY: "sk-openai-example",
  AWS_SECRET_ACCESS_KEY: "aws-secret",
  GH_TOKEN: "gho-example",
  DATABASE_URL: "postgres://user:password@host/db",
  NPM_TOKEN: ["npm", "secret"].join("-"),
  SLACK_WEBHOOK: "https://hooks.slack.example",
} as const;

test("a claude run receives the base keys and only its own provider prefix", () => {
  const environment = runnerEnvironment({
    engine: "claude-code",
    source: hostEnvironment,
  });

  expect(Object.keys(environment).sort()).toEqual([
    "ANTHROPIC_API_KEY",
    "HOME",
    "PATH",
    "TERM",
  ]);
});

test("a codex run never receives the anthropic key", () => {
  const environment = runnerEnvironment({
    engine: "codex",
    source: hostEnvironment,
  });

  expect(environment.OPENAI_API_KEY).toBe("sk-openai-example");
  expect(environment.ANTHROPIC_API_KEY).toBeUndefined();
});

test("unrelated host credentials never reach a spawned engine", () => {
  for (const engine of ["claude-code", "codex", "cursor-agent"] as const) {
    const environment = runnerEnvironment({ engine, source: hostEnvironment });

    expect(environment.AWS_SECRET_ACCESS_KEY).toBeUndefined();
    expect(environment.DATABASE_URL).toBeUndefined();
    expect(environment.NPM_TOKEN).toBeUndefined();
    expect(environment.SLACK_WEBHOOK).toBeUndefined();
  }
});

test("a github token never reaches the engine", () => {
  expect(runnerEnvironment({ engine: "claude-code", source: hostEnvironment }).GH_TOKEN).toBeUndefined();
});
