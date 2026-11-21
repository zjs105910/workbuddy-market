import { entropyThresholdBitsPerCharacter } from "./entropy";
import {
  type Redactor,
  sliced,
  assignedSecret,
  slicedAboveEntropy,
  slicedPrefix,
} from "./replace";

export type RedactionRule = {
  readonly label: string;
  readonly pattern: RegExp;
  readonly replace: Redactor;
};

export const redactionRules: readonly RedactionRule[] = [
  {
    label: "pem-block",
    pattern: /-----BEGIN [^-]+-----[\s\S]*?-----END [^-]+-----/g,
    replace: sliced("pem-block", 0),
  },
  {
    label: "authorization-header",
    pattern:
      /(Authorization\s*:\s*)(?:Bearer|Basic|Token)\s+[A-Za-z0-9._~+/=-]+/gi,
    replace: slicedPrefix("authorization", 0),
  },
  {
    label: "stripe-key",
    pattern: /\b[sr]k_(?:live|test)_[A-Za-z0-9]{20,}\b/g,
    replace: sliced("stripe-key", 8),
  },
  {
    label: "google-api-key",
    pattern: /\bAIza[0-9A-Za-z_-]{35}\b/g,
    replace: sliced("google-api-key", 4),
  },
  {
    label: "llm-api-key",
    pattern: /\bsk-[A-Za-z0-9_-]{12,}\b/g,
    replace: sliced("llm-api-key", 3),
  },
  {
    label: "github-token",
    pattern: /\b(?:gh[porsu]_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{20,})\b/g,
    replace: sliced("github-token", 4),
  },
  {
    label: "slack-token",
    pattern: /\bxox[abprs]-[A-Za-z0-9-]{10,}\b/g,
    replace: sliced("slack-token", 5),
  },
  {
    label: "aws-access-key-id",
    pattern: /\b(?:AKIA|ASIA)[0-9A-Z]{16}\b/g,
    replace: sliced("aws-access-key-id", 4),
  },
  {
    label: "jwt",
    pattern: /\beyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]+/g,
    replace: sliced("jwt", 0),
  },
  {
    label: "hex-secret",
    pattern: /\b[0-9a-f]{32,}\b/gi,
    replace: sliced("hex-secret", 0),
  },
  {
    label: "secret-assignment",
    pattern:
      /\b([A-Za-z0-9_]*(?:KEY|TOKEN|SECRET|PASSWORD|PASSWD|CREDENTIAL|CREDENTIALS|AUTH)(?:_[A-Za-z0-9]+)?)(\s*[:=]\s*)(?:\\"[^"\\\n]+\\"|\\'[^'\\\n]+\\'|"(?:\\.|[^"\\\n])+"|'(?:\\.|[^'\\\n])+'|[^\s"'`[\](){},;.\n]+)/gi,
    replace: assignedSecret({ label: "secret-assignment", keep: 0 }),
  },
  {
    label: "database-url",
    pattern:
      /\b((?:postgres(?:ql)?|mysql|mongodb(?:\+srv)?|redis):\/\/)[^\s"'`]+/gi,
    replace: slicedPrefix("database-url", 0),
  },
  {
    label: "git-remote",
    pattern:
      /\b(?:ssh:\/\/)?git@([A-Za-z0-9.-]+):[A-Za-z0-9._/-]+(?:\.git)?\b/g,
    replace: (_substring: string, hostGroup?: string): string =>
      `git@${hostGroup ?? ""}:[redacted:git-remote]`,
  },
  {
    label: "email-address",
    pattern: /\b(?!git@)[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b/gi,
    replace: sliced("email-address", 0),
  },
  {
    label: "ip-address",
    pattern:
      /\b(?:25[0-5]|2[0-4]\d|1\d\d|[1-9]?\d)(?:\.(?:25[0-5]|2[0-4]\d|1\d\d|[1-9]?\d)){3}(?::\d{1,5})?\b/g,
    replace: sliced("ip-address", 0),
  },
  {
    label: "internal-hostname",
    pattern: /\b(?:[a-z0-9-]+\.)+(?:internal|corp|local)\b/gi,
    replace: sliced("internal-hostname", 0),
  },
  {
    label: "cloud-resource",
    pattern: /\b(arn:aws:|(?:s3|gs):\/\/)[^\s"'`]+/gi,
    replace: slicedPrefix("cloud-resource", 0),
  },
  {
    label: "windows-path",
    pattern: /\b[A-Za-z]:(?:\/|\\{1,2})Users(?:\/|\\{1,2})[^\s"'`<>|]+/g,
    replace: sliced("windows-path", 0),
  },
  {
    label: "absolute-path",
    pattern:
      /(^|[\s("'=])\/(?:Users|home|private|var|opt|etc|srv|Volumes|mnt|root|data|workspace)\/[^\s"'`),]+/gm,
    replace: slicedPrefix("absolute-path", 0),
  },
  {
    label: "high-entropy-string",
    pattern:
      /\b(?=[A-Za-z0-9+/_=-]{40,}\b)(?=[A-Za-z0-9+/_=-]*(?:\d|[A-Z].*[a-z]|[a-z].*[A-Z]))[A-Za-z0-9+/_=-]+\b/g,
    replace: slicedAboveEntropy({
      label: "high-entropy-string",
      keep: 0,
      threshold: entropyThresholdBitsPerCharacter,
    }),
  },
  {
    label: "shannon-entropy",
    pattern: /[A-Za-z0-9+/_-]{24,}={0,2}/g,
    replace: slicedAboveEntropy({
      label: "shannon-entropy",
      keep: 0,
      threshold: entropyThresholdBitsPerCharacter,
    }),
  },
] as const;
