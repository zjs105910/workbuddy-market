import {
  readEffectiveConfig,
  fingerprint,
  projectPaths,
  type ProjectPaths,
} from "@shadowclone/core";
import { refreshIntegrations, writeProfile } from "@shadowclone/environment";
import type { ProfileRule } from "@shadowclone/profile";
import { redactSecrets } from "@shadowclone/redact";
import {
  isOriginBlocked,
  resolveRepository,
  type GitRemoteReader,
} from "@shadowclone/sessions";

function preferenceTitle(body: string): string {
  const paragraph =
    body
      .split(/\n\s*\n/, 1)[0]
      ?.replaceAll(/\s+/g, " ")
      .trim() ?? "";
  const sentence = paragraph.match(/^.*?[.!?](?=\s|$)/)?.[0] ?? paragraph;
  const withoutPunctuation = sentence.replace(/[.!?]+$/, "");

  if (withoutPunctuation.length === 0) {
    return "Explicit engineering preference";
  }

  if (withoutPunctuation.length <= 96) {
    return withoutPunctuation;
  }

  const clause = withoutPunctuation.slice(0, 97);
  const clauseBoundary = Math.max(
    clause.lastIndexOf(", "),
    clause.lastIndexOf("; "),
    clause.lastIndexOf(": "),
  );

  if (clauseBoundary > 48) {
    return clause.slice(0, clauseBoundary);
  }

  const prefix = withoutPunctuation.slice(0, 93);
  const boundary = prefix.lastIndexOf(" ");

  return `${prefix.slice(0, boundary > 48 ? boundary : 93).trimEnd()}...`;
}

export async function rememberPreference(options: {
  readonly text: string;
  readonly scope: "global" | "repository";
  readonly cwd?: string;
  readonly paths?: ProjectPaths;
  readonly managedConfigPath?: string | null;
  readonly readRemote?: GitRemoteReader;
}): Promise<string> {
  if (!options.text.trim() || Buffer.byteLength(options.text) > 8_192) {
    throw new Error("Preference must contain between 1 and 8192 bytes");
  }

  const paths = options.paths ?? projectPaths;

  const { config, policy } = await readEffectiveConfig({
    configPath: paths.configFile,
    managedConfigPath:
      options.managedConfigPath === undefined
        ? paths.managedConfigFile
        : options.managedConfigPath,
  });

  if (!policy.enabled) {
    throw new Error("Shadowclone is disabled by managed policy");
  }

  const repository = await resolveRepository({
    cwd: options.cwd ?? process.cwd(),
    enabled: config.sources["git-metadata"],
    readRemote: options.readRemote,
  });

  if (isOriginBlocked({ repository, patterns: policy.blockedOrigins })) {
    throw new Error("Managed policy blocks preferences for this repository");
  }

  const body = redactSecrets({ text: options.text })
    .trim()
    .replace(/^#{1,6}\s+/gm, "")
    .replace(/<!--/g, "&lt;!--")
    .replace(/--(!?)>/g, "--$1&gt;");

  const location =
    options.scope === "global"
      ? {
          scope: "global" as const,
          originDirectory: null,
          repositoryName: null,
        }
      : repository.profileFileName
        ? {
            scope: "project" as const,
            originDirectory: repository.origin.directoryName,
            repositoryName: repository.profileFileName,
          }
        : {
            scope: "org" as const,
            originDirectory: repository.origin.directoryName,
            repositoryName: null,
          };

  const key = `declared-${fingerprint(JSON.stringify({ body, location })).slice(0, 24)}`;

  const rule: ProfileRule = {
    ...location,
    key,
    title: preferenceTitle(body),
    body,
    section: "engineering",
    source: "declared",
    status: "active",
    proposal: null,
    appliesWhen: [],
    evidence: { for: [], against: [] },
    observations: 0,
    sessions: 0,
    lastSeen: new Date().toISOString(),
    origins: [],
    importReference: null,
  };

  await writeProfile({ paths, rules: [rule] });
  await refreshIntegrations({
    paths,
    configPath: paths.configFile,
    managedConfigPath: options.managedConfigPath,
    readRemote: options.readRemote,
  });

  return key;
}
