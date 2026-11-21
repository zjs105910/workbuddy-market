import { expect, test } from "bun:test";
import { benignFixtures } from "./corpus/benign";
import { secretFixtures } from "./corpus/secrets";
import { redactSecrets } from "./index";

const homeDirectory = "/Users/developer";

function isObjectRecord(
  value: unknown,
): value is Readonly<Record<string, unknown>> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

test("mustRedact removes all secrets in adversarial corpus", () => {
  for (const fixture of secretFixtures) {
    const redacted = redactSecrets({
      text: fixture.value,
      homeDirectory,
    });

    expect(redacted).not.toBe(fixture.value);
    expect(redacted).toContain("[redacted:");
  }
});

test("each rule produces its dedicated redaction label", () => {
  const cases: readonly {
    readonly value: string;
    readonly expectedLabel: string;
  }[] = [
    {
      value: ["sk", "live", "51AbcDefGhIjKlMnOpQrStUvWxYz0123456789"].join("_"),
      expectedLabel: "stripe-key",
    },
    {
      value: "AIzaSyD1234567890abcdefghijklmnopqrstuv",
      expectedLabel: "google-api-key",
    },
    {
      value: ["ghp", "1234567890abcdefghijklmnopqrstuvwxyzAB"].join("_"),
      expectedLabel: "github-token",
    },
    {
      value: "a3f9c2d1b4e5a6b7c8d9e0f1a2b3c4d5e6f7a8b9",
      expectedLabel: "hex-secret",
    },
    {
      value: [
        "xoxb",
        "123456789012",
        "1234567890123",
        "abcdefghijklmnopqrstuvwx",
      ].join("-"),
      expectedLabel: "slack-token",
    },
    {
      value: "C:\\Users\\Administrator\\AppData\\secret.json",
      expectedLabel: "windows-path",
    },
    {
      value: "git@github.com:employer-corp/private-service.git",
      expectedLabel: "git-remote",
    },
  ];

  for (const item of cases) {
    const redacted = redactSecrets({ text: item.value, homeDirectory });

    expect(redacted).toContain(`[redacted:${item.expectedLabel}]`);
  }
});

test("mustRedact scrubs secrets inside jsonl message envelopes", () => {
  for (const fixture of secretFixtures) {
    const payload = JSON.stringify({
      type: "user_message",
      content: `Credential entry: ${fixture.value}`,
    });

    const redacted = redactSecrets({
      text: payload,
      homeDirectory,
    });

    expect(redacted).toContain("[redacted:");

    const decoded: unknown = JSON.parse(redacted);

    expect(isObjectRecord(decoded)).toBe(true);

    if (isObjectRecord(decoded)) {
      expect(decoded.type).toBe("user_message");
      expect(typeof decoded.content).toBe("string");
      expect(decoded.content).not.toContain(fixture.value);
    }
  }
});

test("mustSurvive preserves all benign developer strings untouched", () => {
  for (const fixture of benignFixtures) {
    const result = redactSecrets({
      text: fixture.value,
      homeDirectory,
    });

    expect(result).toBe(fixture.value);
  }
});

test("mustSurvive preserves benign strings in jsonl message envelopes", () => {
  for (const fixture of benignFixtures) {
    const payload = JSON.stringify({
      type: "user_message",
      content: fixture.value,
    });

    const result = redactSecrets({
      text: payload,
      homeDirectory,
    });

    expect(result).toBe(payload);
  }
});

test("redaction is idempotent across all corpus fixtures", () => {
  const combined = [
    ...secretFixtures.map((fixture) => fixture.value),
    ...benignFixtures.map((fixture) => fixture.value),
  ];

  for (const value of combined) {
    const once = redactSecrets({ text: value, homeDirectory });
    const twice = redactSecrets({ text: once, homeDirectory });

    expect(twice).toBe(once);
  }
});
