import { expect, test } from "bun:test";
import { redactSecrets } from "./index";

const homeDirectory = "/Users/example";

function redact(text: string): string {
  return redactSecrets({ text, homeDirectory });
}

test("removes an openai style key and labels it", () => {
  const redacted = redact(
    ("export OPENAI_API_KEY=" + ["sk", "proj", "abc123DEF456ghi789JKL"].join("-")),
  );

  expect(redacted).not.toContain(["sk", "proj", "abc123DEF456ghi789JKL"].join("-"));
  expect(redacted).toContain("[redacted:llm-api-key]");
});

test("removes an anthropic style key", () => {
  const redacted = redact(
    ("curl -H 'x-api-key: " + ["sk", "ant", "api03", "abc123DEF456ghi789"].join("-") + "'"),
  );

  expect(redacted).not.toContain(["sk", "ant", "api03", "abc123DEF456ghi789"].join("-"));
  expect(redacted).toContain("[redacted:llm-api-key]");
});

test("removes github tokens in every prefix form", () => {
  const redacted = redact(
    [
      ["ghp", "A1b2C3d4E5f6G7h8I9j0K1l2M3n4O5p6Q7r8"].join("_"),
      ["github", "pat", "11ABCDEFG0abcdefghij_KLMNOP"].join("_"),
    ].join("\n"),
  );

  expect(redacted).not.toContain(["ghp", "A1b2C3d4E5f6G7h8I9j0K1l2M3n4O5p6Q7r8"].join("_"));
  expect(redacted).not.toContain(["github", "pat", "11ABCDEFG0abcdefghij_KLMNOP"].join("_"));
  expect(redacted.split("[redacted:github-token]")).toHaveLength(3);
});

test("removes a slack token", () => {
  const redacted = redact(("SLACK_BOT=" + ["xoxb", "1234567890-abcdefghij"].join("-")));

  expect(redacted).not.toContain(["xoxb", "1234567890-abcdefghij"].join("-"));
});

test("removes an aws access key id", () => {
  const redacted = redact(
    "aws configure set aws_access_key_id AKIAIOSFODNN7EXAMPLE",
  );

  expect(redacted).not.toContain("AKIAIOSFODNN7EXAMPLE");
  expect(redacted).toContain("[redacted:aws-access-key-id]");
});

test("removes a jwt", () => {
  const redacted = redact(
    "curl -d token=eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxMjM0NSJ9.dBjftJeZ4CVP",
  );

  expect(redacted).not.toContain("eyJhbGciOiJIUzI1NiJ9");
  expect(redacted).toContain("[redacted:jwt]");
});

test("removes an authorization header value but keeps the header name", () => {
  const redacted = redact(
    'curl -H "Authorization: Bearer abc123def456" https://api.example.com',
  );

  expect(redacted).not.toContain("abc123def456");
  expect(redacted).toContain("Authorization: [redacted:authorization]");
  expect(redacted).toContain("https://api.example.com");
});

test("removes a pem block across multiple lines", () => {
  const redacted = redact(
    [
      ["-----BEGIN", "RSA PRIVATE KEY-----"].join(" "),
      "MIIEowIBAAKCAQEAxyz",
      "-----END RSA PRIVATE KEY-----",
    ].join("\n"),
  );

  expect(redacted).not.toContain("MIIEowIBAAKCAQEAxyz");
  expect(redacted).toBe("[redacted:pem-block]");
});

test("removes a secret assignment that matches no specific provider", () => {
  const redacted = redact("export DATABASE_PASSWORD=hunter2correcthorse");

  expect(redacted).not.toContain("hunter2correcthorse");
  expect(redacted).toBe(
    "export DATABASE_PASSWORD=[redacted:secret-assignment]",
  );
});

test("removes compound secret assignments without underscores", () => {
  const text = "APIKEY=secretvalue123\nMYSECRET=anothersecret456";
  const redacted = redact(text);

  expect(redacted).not.toContain("secretvalue123");
  expect(redacted).not.toContain("anothersecret456");
  expect(redacted).toBe(
    "APIKEY=[redacted:secret-assignment]\nMYSECRET=[redacted:secret-assignment]",
  );
});

test("rewrites the home directory to a tilde", () => {
  const redacted = redact("cd /Users/example/Developer/shadowclone");

  expect(redacted).toBe("cd ~/Developer/shadowclone");
});

test("rewrites the home directory in file URLs to a tilde", () => {
  const redacted = redact(
    "see file:///Users/example/Developer/shadowclone/file.ts",
  );

  expect(redacted).toBe("see file:///~/Developer/shadowclone/file.ts");
});

test("leaves ordinary commands untouched", () => {
  const history = [
    "git status",
    "bun test",
    "git clone https://github.com/example/shadowclone.git",
    "rg --files-with-matches distillHistory src",
  ].join("\n");

  expect(redact(history)).toBe(history);
});

test("does not redact a placeholder a second time", () => {
  const once = redact(("export OPENAI_API_KEY=" + ["sk", "proj", "abc123DEF456ghi789JKL"].join("-")));

  expect(redact(once)).toBe(once);
});

test("removes transcript-grade sensitive values", () => {
  const text = [
    "postgres://user:password@db.internal:5432/app",
    "owner@example.org",
    "10.24.8.19",
    "service.prod.corp",
    "arn:aws:iam::123456789012:role/admin",
    "s3://private-customer-bucket/report.csv",
    "/var/log/company/service.log",
    "MZXW6YTBOI======abcDEF1234567890abcdefghijk",
  ].join("\n");

  const redacted = redact(text);

  expect(redacted).not.toContain("password");
  expect(redacted).not.toContain("owner@example.org");
  expect(redacted).not.toContain("10.24.8.19");
  expect(redacted).not.toContain("service.prod.corp");
  expect(redacted).not.toContain("123456789012");
  expect(redacted).not.toContain("private-customer-bucket");
  expect(redacted).not.toContain("/var/log/company");
  expect(redacted).not.toContain("MZXW6YTBOI");
});

test("keeps the home directory readable while redacting other absolute paths", () => {
  expect(redact("cd /Users/example/repo && cat /etc/company/config")).toBe(
    "cd ~/repo && cat [redacted:absolute-path]",
  );
});
