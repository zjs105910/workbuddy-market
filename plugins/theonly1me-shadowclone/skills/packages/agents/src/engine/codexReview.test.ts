import { expect, test } from "bun:test";
import { buildCodexArguments } from "./index";

function reviewArguments(network: boolean) {
  return buildCodexArguments({
    run: {
      prompt: "review",
      cwd: "/repo",
      execution: { purpose: "review", network },
      permissionMode: "dontAsk",
    },
  });
}

test("a Codex review reads in the read-only sandbox and searches the web only when the network is on", () => {
  expect(reviewArguments(true)).toContain('web_search="live"');
  expect(reviewArguments(false)).toContain('web_search="disabled"');
  expect(reviewArguments(true)).not.toContain("--dangerously-bypass-approvals-and-sandbox");
});

test("a Codex review can read only the checkout and gets no secret environment variables", () => {
  const arguments_ = reviewArguments(true);

  expect(arguments_).toContain('default_permissions="shadowclone-review"');
  expect(
    arguments_.find((argument) => argument.startsWith("permissions.shadowclone-review=")),
  ).toStartWith(
    'permissions.shadowclone-review={extends=":read-only",filesystem={":root"="deny",":minimal"="read","/repo"="read",',
  );
  expect(arguments_.join(" ")).toContain('/.codex"="deny"');
  expect(arguments_).toContain(
    'shell_environment_policy={inherit="core",ignore_default_excludes=false}',
  );
});

test("a Codex review refuses a tool allowlist or a permission mode that it cannot enforce", () => {
  const run = {
    prompt: "review",
    cwd: "/repo",
    execution: { purpose: "review" as const, network: true },
  };

  expect(() =>
    buildCodexArguments({ run: { ...run, permissionMode: "dontAsk", allowedTools: ["Read"] } }),
  ).toThrow("allowlist");
  expect(() => buildCodexArguments({ run: { ...run, permissionMode: "acceptEdits" } })).toThrow(
    "dontAsk",
  );
});

test("work outside a review keeps web search off", () => {
  const arguments_ = buildCodexArguments({
    run: {
      prompt: "task",
      cwd: "/repo",
      execution: { purpose: "learning" },
      permissionMode: "dontAsk",
    },
  });

  expect(arguments_).toContain('web_search="disabled"');
});
