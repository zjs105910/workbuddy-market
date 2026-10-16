import ts from "typescript";
import type { ChangedFile } from "./receipt";

export function findings(options: { path: string; content: string; check: string }): string[] {
  const source = ts.createSourceFile(options.path, options.content, ts.ScriptTarget.Latest, true);
  const matches: string[] = [];
  const commentPositions = new Set<number>();

  function visit(node: ts.Node): void {
    if (options.check === "type-safety" && (
      node.kind === ts.SyntaxKind.AnyKeyword || ts.isNonNullExpression(node) ||
      ts.isTypeAssertionExpression(node) || (ts.isAsExpression(node) && !(
        ts.isTypeReferenceNode(node.type) && ts.isIdentifier(node.type.typeName) && node.type.typeName.text === "const"
      ))
    )) {
      matches.push(node.getText(source));
    }

    if (options.check === "zero-comments") {
      for (const range of [
        ...(ts.getLeadingCommentRanges(options.content, node.pos) ?? []),
        ...(ts.getTrailingCommentRanges(options.content, node.end) ?? []),
      ]) {
        if (!commentPositions.has(range.pos)) {
          commentPositions.add(range.pos);
          matches.push(options.content.slice(range.pos, range.end));
        }
      }
    }

    ts.forEachChild(node, visit);
  }

  visit(source);
  return matches;
}

export function introducesViolation(options: { file: ChangedFile; criterion: { readonly check: string } }): boolean {
  const before = options.file.before ?? "";
  const after = options.file.after ?? "";

  if (options.criterion.check === "file-length") {
    const count = after.trimEnd().split("\n").length;
    return count >= 200 && count > before.trimEnd().split("\n").length;
  }

  const previous = findings({ path: options.file.path, content: before, check: options.criterion.check });
  const current = findings({ path: options.file.path, content: after, check: options.criterion.check });

  for (const match of current) {
    const index = previous.indexOf(match);

    if (index < 0) {
      return true;
    }

    previous.splice(index, 1);
  }

  return false;
}
