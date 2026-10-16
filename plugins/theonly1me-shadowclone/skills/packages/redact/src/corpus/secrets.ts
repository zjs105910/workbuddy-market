export type SecretFixture = {
  readonly label: string;
  readonly value: string;
};

export const secretFixtures: readonly SecretFixture[] = [
  { label: "aws-key", value: ["AKIA", "IOSFODNN7EXAMPLE"].join("") },
  { label: "aws-session", value: "ASIAT7YUIOPASDFGHJKL" },
  { label: "openai-key", value: ["sk", "proj", "abc123DEF456ghi789JKL012mno345pqr"].join("-") },
  { label: "openai-legacy", value: ["sk", "abcdefghijklmnopqrstuvwxyz012345"].join("-") },
  { label: "anthropic-key", value: ["sk", "ant", "api03", "abc123DEF456ghi789JKL012mno"].join("-") },
  {
    label: "stripe-live",
    value: ["sk", "live", "51AbcDefGhIjKlMnOpQrStUvWxYz0123456789"].join("_"),
  },
  {
    label: "stripe-test",
    value: "sk_test_51AbcDefGhIjKlMnOpQrStUvWxYz0123456789",
  },
  {
    label: "stripe-restricted",
    value: ["rk", "live", "51AbcDefGhIjKlMnOpQrStUvWxYz0123456789"].join("_"),
  },
  { label: "google-ai", value: "AIzaSyD1234567890abcdefghijklmnopqrstuv" },
  {
    label: "github-personal",
    value: ["ghp", "1234567890abcdefghijklmnopqrstuvwxyzAB"].join("_"),
  },
  {
    label: "github-oauth",
    value: ["gho", "1234567890abcdefghijklmnopqrstuvwxyzAB"].join("_"),
  },
  { label: "github-user", value: ["ghu", "1234567890abcdefghijklmnopqrstuvwxyzAB"].join("_") },
  {
    label: "github-server",
    value: ["ghs", "1234567890abcdefghijklmnopqrstuvwxyzAB"].join("_"),
  },
  {
    label: "github-refresh",
    value: "ghr_1234567890abcdefghijklmnopqrstuvwxyzAB",
  },
  {
    label: "github-fine-grained",
    value: ["github", "pat", "11ABCDEFG0abcdefghij_KLMNOPQRSTUV0123456789"].join("_"),
  },
  {
    label: "slack-bot",
    value: [
      "xoxb",
      "123456789012",
      "1234567890123",
      "abcdefghijklmnopqrstuvwx",
    ].join("-"),
  },
  {
    label: "slack-user",
    value: [
      "xoxp",
      "123456789012",
      "1234567890123",
      "abcdefghijklmnopqrstuvwx",
    ].join("-"),
  },
  {
    label: "slack-app",
    value: [
      "xoxa",
      "123456789012",
      "1234567890123",
      "abcdefghijklmnopqrstuvwx",
    ].join("-"),
  },
  {
    label: "jwt-token",
    value:
      "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIxMjM0NTY3ODkwIiwibmFtZSI6IkpvaG4ifQ.SflKxwRJSMeKKF2QT4fwpMeJf36POk6yJV_adQssw5c",
  },
  {
    label: "pem-rsa",
    value: [
      "-----BEGIN",
      "RSA PRIVATE KEY-----\nMIIEowIBAAKCAQEA0Y123456789abcdef\n-----END RSA PRIVATE KEY-----",
    ].join(" "),
  },
  {
    label: "pem-openssh",
    value: [
      "-----BEGIN",
      "OPENSSH PRIVATE KEY-----\nb3BlbnNzaC1rZXktdjEAAAAABG5vbmUAAAA\n-----END OPENSSH PRIVATE KEY-----",
    ].join(" "),
  },
  {
    label: "bearer-auth",
    value: "Authorization: Bearer secret_bearer_token_123456",
  },
  {
    label: "basic-auth",
    value: "Authorization: Basic dXNlcjpwYXNzd29yZDEyMw==",
  },
  {
    label: "password-assign",
    value: "PASSWORD=my_super_secret_production_password",
  },
  { label: "token-assign", value: "TOKEN=ghp_secret_token_value_assignment" },
  { label: "secret-assign", value: "SECRET=super_sensitive_api_secret_key" },
  { label: "auth-assign", value: "AUTH=custom_auth_header_credentials_here" },
  { label: "yaml-password", value: "password: ultra_secret_cluster_pass" },
  {
    label: "flag-password",
    value: "--from-literal=password=cluster_admin_pass",
  },
  { label: "quoted-token", value: ('API_TOKEN="' + ['quoted', 'api', 'key', 'value', '987654'].join('_') + '"') },
  {
    label: "database-pg",
    value: "postgres://dbuser:supersecretpass@db.internal:5432/primary",
  },
  {
    label: "database-mysql",
    value: "mysql://admin:dbpassword123@prod-db.corp:3306/users",
  },
  {
    label: "database-mongo",
    value: "mongodb+srv://root:mongopass@cluster0.internal/analytics",
  },
  {
    label: "database-redis",
    value: "redis://default:redissecret@cache.local:6379/0",
  },
  {
    label: "git-remote-github",
    value: "git@github.com:employer-corp/private-service.git",
  },
  {
    label: "git-remote-gitlab",
    value: "git@gitlab.corp.internal:platform/infra.git",
  },
  {
    label: "git-remote-ssh",
    value: "ssh://git@code.corp:team/secret-repo.git",
  },
  { label: "email-user", value: "security-lead@acme-corp.com" },
  { label: "email-admin", value: "admin.alerts@internal-domain.org" },
  { label: "ip-rfc1918-10", value: "10.128.4.92:9090" },
  { label: "ip-rfc1918-192", value: "192.168.10.45:8080" },
  { label: "ip-rfc1918-172", value: "172.24.16.8:3000" },
  { label: "ip-public", value: "198.51.100.24:443" },
  { label: "internal-host", value: "auth-service.production.corp" },
  { label: "internal-local", value: "payment-gateway.internal" },
  {
    label: "aws-arn-role",
    value: "arn:aws:iam::123456789012:role/ProductionEksClusterRole",
  },
  {
    label: "s3-bucket",
    value: "s3://sensitive-customer-pii-backup/records.parquet",
  },
  {
    label: "gs-bucket",
    value: "gs://confidential-ml-datasets/user_weights.bin",
  },
  {
    label: "windows-path",
    value: "C:\\Users\\Administrator\\AppData\\Local\\secret.json",
  },
  { label: "linux-path", value: "/etc/kubernetes/pki/apiserver.key" },
  { label: "var-log-path", value: "/var/log/audit/tamper_evident.log" },
  { label: "mnt-path", value: "/mnt/credentials/vault_token.txt" },
  { label: "hex-secret-40", value: "a3f9c2d1b4e5a6b7c8d9e0f1a2b3c4d5e6f7a8b9" },
  {
    label: "hex-secret-64",
    value: "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
  },
  {
    label: "high-entropy",
    value: "MZXW6YTBOI======abcDEF1234567890abcdefghijk",
  },
  {
    label: "inhouse-prefixed-key",
    value: "int_9fKw2QzR7mVpL4xN8tYbH3sJ6dGcA1eZ5uT",
  },
  { label: "bare-random-token", value: "k7Xq2mZpR8vNwL4tJ6yHbF3sQ9dGcA1e" },
  {
    label: "session-cookie-value",
    value: "Xk9mQ2pLr7vNw4tJ6yHbF3sQ9dGcA1eZ5uT8i",
  },
  {
    label: "random-base64-blob",
    value: "aGVsbG8gd29ybGQgdGhpcyBpcyBhIHNlY3JldCE9PQ==",
  },
  {
    label: "custom-vendor-credential",
    value: "acme_live_Vp8xK2mQr7nT4wY6zB3jL9sH1dF5gC0e",
  },
] as const;
