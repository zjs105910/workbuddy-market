import type { FileTextRef } from "@shadowclone/sessions";
import type { ProfileImportReference } from "@shadowclone/profile";

export type ImportIdentity = {
  readonly key: string;
  readonly relativePath: string;
  readonly importReference: ProfileImportReference | null;
};

export type RepositoryGuidanceImportResult = {
  readonly imported: number;
  readonly preserved: number;
  readonly rejected: number;
  readonly retired: number;
};

export type RedactedResolver = (options: {
  readonly ref: FileTextRef;
}) => Promise<string>;

export type RepositoryRuleLocation =
  | {
      readonly scope: "org";
      readonly originDirectory: string;
      readonly repositoryName: null;
    }
  | {
      readonly scope: "project";
      readonly originDirectory: string;
      readonly repositoryName: string;
    };
