import path from "node:path";
import ts from "typescript";

export type ImportEdge = {
  readonly file: string;
  readonly line: number;
  readonly specifier: string;
  readonly typeOnly: boolean;
};

function isTypeOnlyDeclaration(node: ts.ImportDeclaration | ts.ExportDeclaration): boolean {
  if (ts.isExportDeclaration(node)) {
    const clause = node.exportClause;

    return (
      node.isTypeOnly ||
      (clause !== undefined &&
        ts.isNamedExports(clause) &&
        clause.elements.length > 0 &&
        clause.elements.every((element) => element.isTypeOnly))
    );
  }

  const clause = node.importClause;
  const bindings = clause?.namedBindings;

  return (
    clause !== undefined &&
    (clause.isTypeOnly ||
      (clause.name === undefined &&
        bindings !== undefined &&
        ts.isNamedImports(bindings) &&
        bindings.elements.length > 0 &&
        bindings.elements.every((element) => element.isTypeOnly)))
  );
}

function importedLiteral(node: ts.Node): {
  readonly literal: ts.StringLiteralLike;
  readonly typeOnly: boolean;
} | null {
  if (
    (ts.isImportDeclaration(node) || ts.isExportDeclaration(node)) &&
    node.moduleSpecifier &&
    ts.isStringLiteralLike(node.moduleSpecifier)
  ) {
    return { literal: node.moduleSpecifier, typeOnly: isTypeOnlyDeclaration(node) };
  }

  const [argument] = ts.isCallExpression(node) ? node.arguments : [];
  const isLoader =
    ts.isCallExpression(node) &&
    (node.expression.kind === ts.SyntaxKind.ImportKeyword ||
      (ts.isIdentifier(node.expression) && node.expression.text === "require"));

  return isLoader && argument && ts.isStringLiteralLike(argument)
    ? { literal: argument, typeOnly: false }
    : null;
}

export function readImports(options: { file: string; text: string }): readonly ImportEdge[] {
  const source = ts.createSourceFile(options.file, options.text, ts.ScriptTarget.Latest, true);
  const edges: ImportEdge[] = [];

  function visit(node: ts.Node): void {
    const imported = importedLiteral(node);

    if (imported) {
      edges.push({
        file: options.file,
        line: source.getLineAndCharacterOfPosition(imported.literal.getStart()).line + 1,
        specifier: imported.literal.text,
        typeOnly: imported.typeOnly,
      });
    }

    ts.forEachChild(node, visit);
  }

  visit(source);

  return edges;
}

export function resolveRelativeImport(options: { file: string; specifier: string }): string | null {
  if (!options.specifier.startsWith(".")) {
    return null;
  }

  return path.posix.normalize(path.posix.join(path.posix.dirname(options.file), options.specifier));
}
