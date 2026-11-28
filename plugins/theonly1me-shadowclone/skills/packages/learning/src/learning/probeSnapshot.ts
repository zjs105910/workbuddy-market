import path from "node:path";
import {
  readEffectiveConfig,
  fingerprint,
  canonicalPath,
  type ProjectPaths,
} from "@shadowclone/core";
import {
  compileContext,
  integrationFilePath,
  managedSection,
  prepareIntegrationFiles,
  readEnvironment,
  readIntegrations,
  recordFingerprint,
} from "@shadowclone/environment";
import { materializeSnapshot } from "@shadowclone/redact";
import type { NativeEngine } from "@shadowclone/agents";

export type ProbeFile = {
  readonly location: "home" | "workspace";
  readonly relativePath: string;
  readonly text: string;
};

export async function freezeProbeGuidance(options: {
  readonly paths: ProjectPaths;
  readonly key: string;
  readonly engine: NativeEngine;
  readonly cwd: string;
}): Promise<{ readonly files: readonly ProbeFile[]; readonly inputFingerprint: string }> {
  const { config, policy } = await readEffectiveConfig({
    configPath: options.paths.configFile, managedConfigPath: options.paths.managedConfigFile,
  });
  if (!config.sources["skill-library"] || !config.distillation.deep ||
    !policy.enabled || policy.distillation !== "allowed" || !policy.allowedEngines.includes(options.engine)) {
    throw new Error("A probe needs skill-library and learning consent and an allowed agent");
  }
  const state = await readEnvironment(options.paths);
  const record = state?.records.find(({ rule }) => rule.key === options.key);
  if (state?.phase !== "active" || !record || record.retirementRequested ||
    record.rule.status !== "active" || record.rule.proposal !== null) {
    throw new Error("A probe needs an active published rule without an unresolved proposal");
  }
  const inputFingerprint = recordFingerprint(record);
  const cwd = canonicalPath(options.cwd);
  const integrations = (await readIntegrations(options.paths)).filter((entry) =>
    entry.agent === options.engine && (entry.scope === "global" || entry.directory === cwd),
  );
  const selected = integrations.find((entry) => record.rule.scope === "global"
    ? entry.scope === "global" : entry.scope === "repository") ??
    (record.rule.scope === "global" ? integrations[0] : undefined);
  if (!selected) throw new Error("Install this agent locally in the rule's repository before probing scoped guidance");
  const scopes = new Set(["global", ...state.repositories.filter((repository) =>
    canonicalPath(repository.directory) === cwd,
  ).map((repository) => `${repository.originDirectory}/${repository.repositoryName}`)]);
  if (!state.dispositions.some((entry) => entry.key === options.key &&
    entry.inputFingerprint === inputFingerprint && scopes.has(entry.scope ?? "") &&
    (entry.status === "published" || entry.status === "covered"))) {
    throw new Error("Resolve publication and scope before probing this rule");
  }
  const files: ProbeFile[] = [];
  let bytes = 0;
  for (const integration of integrations) {
    const profile = await compileContext({
      paths: options.paths, cwd: integration.scope === "global" ? integration.directory : cwd,
      scope: integration.scope === "global" ? "global" : "combined",
    });
    if (profile === null) throw new Error("Policy blocks this integration");
    const changes = await prepareIntegrationFiles({ integration, profile, environment: true });
    for (const file of integration.files.filter((entry) => entry.kind === "instructions")) {
      const filePath = integrationFilePath({ integration, file });
      const snapshot = await materializeSnapshot({
        filePath, roots: [integration.directory], maximumBytes: 256_000,
        parse: (text) => ({ digest: fingerprint(managedSection(text) ?? ""), text }),
      });
      const desired = changes.find((change) => change.filePath === filePath);
      if (!snapshot || snapshot.parsed.digest !== file.fingerprint || desired?.next !== snapshot.parsed.text) {
        throw new Error("Native guidance is missing, edited, or stale. Refresh the integration before probing.");
      }
      const text = managedSection(snapshot.redacted);
      if (!text) throw new Error("Native guidance is empty");
      bytes += Buffer.byteLength(text);
      files.push({
        location: integration.scope === "global" ? "home" : "workspace",
        relativePath: integration.scope === "global"
          ? path.join(options.engine === "claude-code" ? ".claude" : ".codex", file.relativePath)
          : file.relativePath,
        text,
      });
    }
  }
  const routing = files.map((file) => file.text).join("\n");
  const instruction = record.rule.body.replace(/\s+/gu, " ").trim();
  const artifacts = state.artifacts.filter((artifact) => scopes.has(artifact.scope) &&
    routing.includes(`Use the ${artifact.name} skill`));
  if (!routing.includes(instruction) && !artifacts.some((artifact) => artifact.learningKeys.includes(options.key))) {
    throw new Error("The installed native routing does not deliver this rule");
  }
  for (const artifact of artifacts) {
    const skillRoot = artifact.filePath.split("/skills/")[0];
    if (!skillRoot || artifact.encoding === "base64") {
      throw new Error("This probe supports text skill resources only");
    }
    const relativePath = artifact.filePath.slice(skillRoot.length + "/skills/".length);
    if (relativePath.split(path.sep).some((segment) => segment === "..") || path.isAbsolute(relativePath)) {
      throw new Error("Invalid skill destination");
    }
    if (options.engine === "claude-code" ? !skillRoot.endsWith("/.claude") : !skillRoot.endsWith("/.agents")) continue;
    const snapshot = await materializeSnapshot({
      filePath: artifact.filePath, roots: [path.join(skillRoot, "skills")], maximumBytes: 256_000,
      parse: fingerprint,
    });
    if (!snapshot || snapshot.parsed !== artifact.fingerprint) throw new Error("A published skill changed. Review and refresh it before probing.");
    bytes += Buffer.byteLength(snapshot.redacted);
    files.push({
      location: artifact.scope === "global" ? "home" : "workspace",
      relativePath: path.join(options.engine === "claude-code" ? ".claude/skills" : ".agents/skills", relativePath),
      text: snapshot.redacted,
    });
  }
  if (bytes > 1_000_000) throw new Error("Probe guidance exceeds its 1 MB limit");
  return { files, inputFingerprint };
}
