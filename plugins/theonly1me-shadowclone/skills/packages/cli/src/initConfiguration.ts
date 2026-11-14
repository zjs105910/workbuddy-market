import {
  defaultConfig,
  setDeepEnabled,
  setSourceEnabled,
  type ShadowcloneConfig,
} from "@shadowclone/core";
import type { OnboardingPresence } from "./onboardingPresence";

export function initialConfiguration(options: {
  readonly learn: boolean;
  readonly skills: boolean;
  readonly background: boolean;
  readonly presence: OnboardingPresence;
}): ShadowcloneConfig {
  const { learn, skills, background, presence } = options;

  let config = defaultConfig;

  if (learn) {
    for (const source of presence.presentCaptureSources) {
      config = setSourceEnabled({ config, source, enabled: true });
    }

    config = setSourceEnabled({
      config,
      source: "git-metadata",
      enabled: true,
    });
    config = setSourceEnabled({
      config,
      source: "agent-context",
      enabled: true,
    });
    config = setSourceEnabled({
      config,
      source: "declared-rules",
      enabled: presence.hasRepositoryGuidance,
    });
  }

  config = setSourceEnabled({
    config,
    source: "skill-library",
    enabled: skills,
  });
  config = setDeepEnabled({ config, enabled: learn });
  config = {
    ...config,
    distillation: { ...config.distillation, automatic: background },
  };

  return config;
}
