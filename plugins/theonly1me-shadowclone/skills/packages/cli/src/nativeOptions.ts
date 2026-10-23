import {
  integrationAgentSchema,
  type IntegrationAgent,
  type IntegrationScope,
} from "@shadowclone/environment";

export type NativeInstallOptions = {
  readonly agents: readonly IntegrationAgent[];
  readonly scope: IntegrationScope;
  readonly subagent: boolean;
  readonly autoDelegate: boolean;
};

export function parseNativeOptions(
  arguments_: readonly string[],
): NativeInstallOptions | null {
  let agents: readonly IntegrationAgent[] = ["claude-code"];
  let scope: IntegrationScope = "global";
  let subagent = false;
  let autoDelegate = false;

  const seen = new Set<string>();

  for (let position = 0; position < arguments_.length; position += 1) {
    const argument = arguments_[position];

    if (!argument || seen.has(argument)) {
      return null;
    }

    seen.add(argument);

    if (argument === "--global") {
      scope = "global";
    } else if (argument === "--local") {
      scope = "repository";
    } else if (argument === "--subagent") {
      subagent = true;
    } else if (argument === "--auto-delegate") {
      subagent = true;
      autoDelegate = true;
    } else if (argument === "--agent") {
      const value = arguments_[++position];

      if (value === "all") {
        agents = integrationAgentSchema.options;
      } else {
        const parsed = integrationAgentSchema.safeParse(value);

        if (!parsed.success) {
          return null;
        }

        agents = [parsed.data];
      }
    } else {
      return null;
    }
  }

  if (seen.has("--global") && seen.has("--local")) {
    return null;
  }

  if (subagent && (scope === "global" || !agents.includes("claude-code"))) {
    return null;
  }

  return { agents, scope, subagent, autoDelegate };
}
