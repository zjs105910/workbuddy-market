export type ReferenceSource =
  | "user"
  | "claude-memory"
  | "claude-project-memory";

type ReferenceLocation =
  | {
      readonly scope: "global";
      readonly originDirectory: null;
      readonly repositoryName: null;
    }
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

export type ReferenceRecord = ReferenceLocation & {
  readonly schema: 1;
  readonly key: string;
  readonly title: string;
  readonly summary: string;
  readonly tags: readonly string[];
  readonly source: ReferenceSource;
  readonly sourceLocator: string;
  readonly updatedAt: string;
  readonly body: string;
};

export type ReferenceSearchResult = {
  readonly record: ReferenceRecord;
  readonly relativePath: string;
};
