import path from "node:path";
import { linkedHomeFile } from "@shadowclone/core";
import type { Integration, IntegrationFile } from "./types";

export function integrationTargets(
  integration: Pick<
    Integration,
    "agent" | "scope" | "directory" | "userDirectory" | "codexInstructions"
  >,
): readonly {
  readonly relativePath: string;
  readonly kind: IntegrationFile["kind"];
}[] {
  const global = integration.scope === "global";

  if (integration.agent === "pi") {
    return [
      ...(global ? [{ relativePath: "AGENTS.md", kind: "instructions" as const }] : []),
      { relativePath: global ? "extensions/shadowclone.js" : ".pi/extensions/shadowclone.js", kind: "extension" },
      {
        relativePath: global
          ? path.relative(integration.directory, path.join(integration.userDirectory, ".agents/skills/shadowclone-context/SKILL.md"))
          : ".agents/skills/shadowclone-context/SKILL.md",
        kind: "skill",
      },
    ];
  }

  if (integration.agent === "claude-code") {
    return [
      {
        relativePath: global ? "CLAUDE.md" : "CLAUDE.local.md",
        kind: "instructions",
      },
      {
        relativePath: global ? "settings.json" : ".claude/settings.local.json",
        kind: "hooks",
      },
      {
        relativePath: global
          ? "skills/shadowclone-context/SKILL.md"
          : ".claude/skills/shadowclone-context/SKILL.md",
        kind: "skill",
      },
    ];
  }

  if (integration.agent === "codex") {
    return [
      { relativePath: integration.codexInstructions, kind: "instructions" },
      {
        relativePath: global ? "hooks.json" : ".codex/hooks.json",
        kind: "hooks",
      },
      {
        relativePath: global
          ? path.relative(
              integration.directory,
              path.join(
                integration.userDirectory,
                ".agents/skills/shadowclone-context/SKILL.md",
              ),
            )
          : ".agents/skills/shadowclone-context/SKILL.md",
        kind: "skill",
      },
    ];
  }

  if (integration.agent === "antigravity") {
    return [
      {
        relativePath: global ? "hooks.json" : ".agents/hooks.json",
        kind: "hooks",
      },
      {
        relativePath: global
          ? "skills/shadowclone-context/SKILL.md"
          : ".agents/skills/shadowclone-context/SKILL.md",
        kind: "skill",
      },
    ];
  }

  return [
    ...(global
      ? []
      : [
          {
            relativePath: ".cursor/rules/shadowclone.mdc",
            kind: "instructions" as const,
          },
        ]),
    {
      relativePath: global ? "hooks.json" : ".cursor/hooks.json",
      kind: "hooks",
    },
    {
      relativePath: global
        ? "skills/shadowclone-context/SKILL.md"
        : ".cursor/skills/shadowclone-context/SKILL.md",
      kind: "skill",
    },
  ];
}

export function retiredIntegrationTargets(
  integration: Pick<Integration, "agent" | "scope">,
): readonly { readonly relativePath: string; readonly kind: IntegrationFile["kind"] }[] {
  return integration.agent === "pi" && integration.scope === "repository"
    ? [{ relativePath: "AGENTS.md", kind: "instructions" }]
    : [];
}

export function integrationFilePath(options: {
  readonly integration: Integration;
  readonly file: Pick<IntegrationFile, "relativePath" | "kind">;
}): string {
  if (
    ![
      ...integrationTargets(options.integration),
      ...retiredIntegrationTargets(options.integration),
    ].some(
      (target) =>
        target.relativePath === options.file.relativePath &&
        target.kind === options.file.kind,
    )
  ) {
    throw new Error("Unknown integration destination");
  }

  const filePath = path.resolve(options.integration.directory, options.file.relativePath);

  return options.integration.scope === "global" && options.file.kind === "instructions"
    ? (linkedHomeFile({ filePath, homeDirectory: options.integration.userDirectory }) ?? filePath)
    : filePath;
}
