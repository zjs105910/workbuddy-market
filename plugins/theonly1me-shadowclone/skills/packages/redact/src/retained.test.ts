import { expect, test } from "bun:test";
import { redactSecrets } from "./index";

const homeDirectory = "/Users/example";

function redact(text: string): string {
  return redactSecrets({ text, homeDirectory });
}

test("retains nothing from a secret that has no public prefix", () => {
  const cases: readonly {
    readonly value: string;
    readonly label: string;
  }[] = [
    {
      value: "a3f9c2d1b4e5a6b7c8d9e0f1a2b3c4d5e6f7a8b9",
      label: "hex-secret",
    },
    {
      value: "k7Xq2mZpR8vNwL4tJ6yHbF3sQ9dGcA1e",
      label: "shannon-entropy",
    },
    {
      value: "Bkx2VBx7BisAV5M+7v+b=vo5DdbCz6F+UqtwxqOP3S3U",
      label: "high-entropy-string",
    },
  ];

  for (const item of cases) {
    expect(redact(item.value)).toBe(`[redacted:${item.label}]`);
  }
});

test("retains only the vendor prefix of a recognized token", () => {
  const cases: readonly {
    readonly value: string;
    readonly retained: string;
    readonly label: string;
  }[] = [
    {
      value: ["sk", "proj", "abc123DEF456ghi789JKL"].join("-"),
      retained: "sk-",
      label: "llm-api-key",
    },
    {
      value: ["ghp", "A1b2C3d4E5f6G7h8I9j0K1l2M3n4O5p6Q7r8"].join("_"),
      retained: "ghp_",
      label: "github-token",
    },
    {
      value: [
        "xoxb",
        "123456789012",
        "1234567890123",
        "abcdefghijklmnopqrstuvwx",
      ].join("-"),
      retained: "xoxb-",
      label: "slack-token",
    },
    {
      value: ["sk", "live", "51AbcDefGhIjKlMnOpQrStUvWxYz0123456789"].join("_"),
      retained: "sk_live_",
      label: "stripe-key",
    },
    {
      value: ["AIza", "SyD1234567890abcdefghijklmnopqrstuv"].join(""),
      retained: "AIza",
      label: "google-api-key",
    },
    {
      value: ["AKIA", "IOSFODNN7EXAMPLE"].join(""),
      retained: "AKIA",
      label: "aws-access-key-id",
    },
  ];

  for (const item of cases) {
    expect(redact(item.value)).toBe(
      `${item.retained}...[redacted:${item.label}]`,
    );
    expect(item.value.startsWith(item.retained)).toBeTrue();
  }
});

test("retains repository relative paths that only look high entropy", () => {
  const paths = [
    "packages/collections/src/operations/groupBySize.ts",
    "packages/collections/src/operations/groupBySize.test.ts",
    "apps/service/src/controllers/taskCoordinator.ts",
    "packages/utilities/src/scheduling/retryDelays.ts",
    "src/eval/study/candidateValidation.test.ts",
  ];

  for (const value of paths) {
    expect(redact(value)).toBe(value);
  }
});

test("still removes a high entropy secret of the same length as a path", () => {
  expect(redact("Bkx2VBx7BisAV5M+7v+b=vo5DdbCz6F+UqtwxqOP3S3U9zQr")).toBe(
    "[redacted:high-entropy-string]",
  );
});

test("retains ordinary code that names keys, tokens, and secrets", () => {
  const code = [
    "delete: (key: Key) => boolean;",
    "const key = { id: 1 };",
    "token: string",
    "secret: SecretType",
    "function readAuth(authState: AuthState) { return authState; }",
    "const evictedKey = this.evictOldestIfNeeded();",
    "const firstKey = namespaceEntries.keys().next().value;",
    'cache.set({ namespace: "one", key: "a", value: 1 });',
  ];

  for (const line of code) {
    expect(redact(line)).toBe(line);
  }
});

test("still removes a secret shaped assignment beside that code", () => {
  for (const assignment of [
    ('const apiKey = "' + ['sk', 'live-abc123def456ghi789jkl'].join('-') + '";'),
    "PASSWORD=correcthorsebatterystaple",
    "API_KEY=abc123def456",
    ('AUTH_TOKEN: "' + ['ghp', 'abc123def456'].join('_') + '"'),
  ]) {
    expect(redact(assignment)).toContain("[redacted:secret-assignment]");
  }
});
