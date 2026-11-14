export {
  discoverRepositoryGuidance,
  maximumGuidanceBytes,
  maximumGuidanceFiles,
  type RepositoryGuidanceSource,
} from "./discovery";

export { importRepositoryGuidance } from "./importRepositoryGuidance";

export {
  mergeImportReference,
  repositoryAliases,
  sourceLocator,
} from "./identity";

export {
  nestMarkdownHeadings,
  transformRepositoryGuidance,
  type ImportedGuidanceContent,
} from "./markdown";

export type { RepositoryGuidanceImportResult } from "./types";
