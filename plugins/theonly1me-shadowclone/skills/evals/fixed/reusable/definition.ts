import { fingerprint } from "../../shared/structured";
import { styleCases } from "./cases/style";
import { workflowCases } from "./cases/workflow";
import { scopeCases } from "./cases/scope";
import { correctionSessions, correctionRepositoryHistory, excludedCorpusDecoy } from "./corpus";
import { preferenceSpecification } from "./oracle";
import { existingManualSkill, intendedAtlasSkill, intendedGlobalSkill } from "./guidance";
import { routingCases, routingLibrary } from "./routing";

export const developmentCases = [...styleCases, ...workflowCases, ...scopeCases];
export const repositoryInstructions =
  "# Repository requirements\n\nUse Bun and TypeScript. Preserve the requested API. Tests must run locally. Current explicit user requests override personal defaults. Git and gh remote endpoints are offline fixtures. Repository requirements outrank personal preferences.\n";
export const reusableDefinition = {
  protocol: "preference-respect-v3",
  developmentCases,
  correctionSessions,
  correctionRepositoryHistory,
  excludedCorpusDecoy,
  existingManualSkill,
  intendedAtlasSkill,
  intendedGlobalSkill,
  preferenceSpecification,
  routingCases,
  routingLibrary,
  repositoryInstructions,
  repetitions: 3,
  retry:
    "One confirmed infrastructure failure per cell; fresh workspace; both attempts retained and charged; no timeout guessing.",
  bootstrap: "Resample entire matched repetition/preparation groups, never the fixed case mix.",
};
export const benchmarkFingerprint = fingerprint(reusableDefinition);
