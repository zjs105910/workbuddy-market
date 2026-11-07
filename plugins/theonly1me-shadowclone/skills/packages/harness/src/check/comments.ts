type Scanner = {
  readonly scan: () => number;
  readonly getTokenStart: () => number;
  readonly getTokenText: () => string;
};

type ScannerModule = {
  readonly createScanner: (
    languageVersion: number,
    skipTrivia: boolean,
    languageVariant: number,
    text: string,
  ) => Scanner;
  readonly ScriptTarget: { readonly Latest: number };
  readonly LanguageVariant: { readonly Standard: number; readonly JSX: number };
  readonly SyntaxKind: {
    readonly SingleLineCommentTrivia: number;
    readonly MultiLineCommentTrivia: number;
    readonly EndOfFileToken: number;
  };
};

export type SourceComment = { readonly line: number; readonly text: string };
export type CommentReader = (options: {
  readonly text: string;
  readonly jsx: boolean;
}) => readonly SourceComment[];

function isScannerModule(value: unknown): value is ScannerModule {
  return (
    typeof value === "object" &&
    value !== null &&
    "createScanner" in value &&
    typeof value.createScanner === "function" &&
    "SyntaxKind" in value &&
    "ScriptTarget" in value &&
    "LanguageVariant" in value
  );
}

function scannerModule(loaded: unknown): ScannerModule | null {
  if (isScannerModule(loaded)) {
    return loaded;
  }

  const fallback =
    typeof loaded === "object" && loaded !== null && "default" in loaded
      ? loaded.default
      : null;

  return isScannerModule(fallback) ? fallback : null;
}

export async function loadRepositoryCommentReader(
  root: string,
): Promise<CommentReader | null> {
  let modulePath: string;

  try {
    modulePath = Bun.resolveSync("typescript", root);
  } catch {
    return null;
  }

  const typescript = scannerModule(await import(modulePath));

  if (typescript === null) {
    return null;
  }

  return (options) => {
    const scanner = typescript.createScanner(
      typescript.ScriptTarget.Latest,
      false,
      options.jsx
        ? typescript.LanguageVariant.JSX
        : typescript.LanguageVariant.Standard,
      options.text,
    );
    const comments: SourceComment[] = [];

    for (
      let token = scanner.scan();
      token !== typescript.SyntaxKind.EndOfFileToken;
      token = scanner.scan()
    ) {
      if (
        token === typescript.SyntaxKind.SingleLineCommentTrivia ||
        token === typescript.SyntaxKind.MultiLineCommentTrivia
      ) {
        comments.push({
          line: options.text.slice(0, scanner.getTokenStart()).split("\n")
            .length,
          text: scanner.getTokenText(),
        });
      }
    }

    return comments;
  };
}
