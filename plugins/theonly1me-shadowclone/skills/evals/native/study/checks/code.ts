import ts from "typescript";
import { introducesViolation } from "../../checks";
import type { ChangedFile } from "../../receipt";
import type { StudyVerdict } from "../checkSchema";

export type Outcome = { readonly verdict: StudyVerdict; readonly evidence: string };

function codeFiles(files: readonly ChangedFile[]): ChangedFile[] {
  return files.filter((file) => file.after !== null && /\.[cm]?tsx?$/.test(file.path));
}

function parse(options: { path: string; content: string }): ts.SourceFile {
  return ts.createSourceFile(options.path, options.content, ts.ScriptTarget.Latest, true);
}

export function introducedSyntax(options: { files: readonly ChangedFile[]; check: "zero-comments" | "type-safety" }): Outcome {
  const files = codeFiles(options.files);
  if (files.length === 0) return { verdict: "not-applicable", evidence: "No changed code." };
  const violations = files.filter((file) => introducesViolation({ file, criterion: { check: options.check } }));
  return violations.length > 0
    ? { verdict: "fail", evidence: `Introduced in ${violations.map((file) => file.path).join(", ")}` }
    : { verdict: "pass", evidence: `Checked ${files.length} changed code files.` };
}

export function fileLength(options: { files: readonly ChangedFile[]; limit: number }): Outcome {
  const files = codeFiles(options.files);
  if (files.length === 0) return { verdict: "not-applicable", evidence: "No changed code." };
  const lines = (content: string | null) => content === null ? 0 : content.trimEnd().split("\n").length;
  const long = files.filter((file) => lines(file.after) >= options.limit && lines(file.after) > lines(file.before));
  return long.length > 0
    ? { verdict: "fail", evidence: long.map((file) => `${file.path}: ${lines(file.after)} lines`).join(", ") }
    : { verdict: "pass", evidence: `All ${files.length} changed code files stay under ${options.limit} lines.` };
}

type Signature = { readonly key: string; readonly parameters: number };

function functionName(node: ts.Node): string {
  if ((ts.isFunctionDeclaration(node) || ts.isMethodDeclaration(node)) && node.name) return node.name.getText();
  const parent = node.parent;
  if (ts.isVariableDeclaration(parent) || ts.isPropertyAssignment(parent) || ts.isPropertyDeclaration(parent)) return parent.name.getText();
  return "anonymous";
}

export function signatures(source: ts.SourceFile): Signature[] {
  const found: Signature[] = [];
  const visit = (node: ts.Node) => {
    const functionLike = ts.isFunctionDeclaration(node) || ts.isMethodDeclaration(node) || ts.isArrowFunction(node) || ts.isFunctionExpression(node);
    if (functionLike && node.body && !ts.isCallExpression(node.parent) && !ts.isNewExpression(node.parent)) {
      const parameters = node.parameters.filter((parameter) => parameter.name.getText() !== "this");
      found.push({ key: `${functionName(node)}(${parameters.map((parameter) => parameter.getText()).join(",")})`, parameters: parameters.length });
    }
    ts.forEachChild(node, visit);
  };
  visit(source);
  return found;
}

export function optionsObject(options: { files: readonly ChangedFile[] }): Outcome {
  const introduced = codeFiles(options.files).flatMap((file) => {
    const before = new Set(file.before === null ? [] : signatures(parse({ path: file.path, content: file.before })).map((entry) => entry.key));
    return signatures(parse({ path: file.path, content: file.after ?? "" })).filter((entry) => !before.has(entry.key))
      .map((entry) => ({ ...entry, path: file.path }));
  });
  if (introduced.length === 0) return { verdict: "not-applicable", evidence: "No new or changed function signatures." };
  const positional = introduced.filter((entry) => entry.parameters >= 2);
  return positional.length > 0
    ? { verdict: "fail", evidence: positional.map((entry) => `${entry.path}: ${entry.key}`).join("; ").slice(0, 1500) }
    : { verdict: "pass", evidence: `${introduced.length} new or changed signatures take at most one parameter.` };
}

export function declaredNames(source: ts.SourceFile): string[] {
  const names: string[] = [];
  const collect = (name: ts.BindingName) => {
    if (ts.isIdentifier(name)) names.push(name.text);
    else for (const element of name.elements) if (!ts.isOmittedExpression(element)) collect(element.name);
  };
  const visit = (node: ts.Node) => {
    if (ts.isVariableDeclaration(node) || ts.isParameter(node)) collect(node.name);
    if ((ts.isFunctionDeclaration(node) || ts.isClassDeclaration(node)) && node.name) names.push(node.name.text);
    ts.forEachChild(node, visit);
  };
  visit(source);
  return names;
}

export function identifiers(options: { files: readonly ChangedFile[]; denylist: readonly string[] }): Outcome {
  const denied = new Set(options.denylist);
  const introduced = codeFiles(options.files).flatMap((file) => {
    const before = file.before === null ? [] : declaredNames(parse({ path: file.path, content: file.before }));
    const remaining = [...before];
    return declaredNames(parse({ path: file.path, content: file.after ?? "" })).filter((name) => {
      const position = remaining.indexOf(name);
      if (position >= 0) remaining.splice(position, 1);
      return position < 0;
    });
  });
  if (introduced.length === 0) return { verdict: "not-applicable", evidence: "No new declarations." };
  const abbreviated = introduced.filter((name) => denied.has(name) || (name.length === 1 && name !== "_"));
  return abbreviated.length > 0
    ? { verdict: "fail", evidence: `Abbreviated names: ${[...new Set(abbreviated)].join(", ")}` }
    : { verdict: "pass", evidence: `${introduced.length} new declarations use full words.` };
}

export function filePatterns(options: { files: readonly ChangedFile[]; filePattern: RegExp; forbidden: readonly RegExp[] }): Outcome {
  const matching = options.files.filter((file) => file.after !== null && options.filePattern.test(file.path));
  if (matching.length === 0) return { verdict: "not-applicable", evidence: "No matching changed files." };
  const count = (text: string | null, pattern: RegExp) => text === null ? 0 : text.split("\n").filter((line) => pattern.test(line)).length;
  const introduced = matching.filter((file) => options.forbidden.some((pattern) => count(file.after, pattern) > count(file.before, pattern)));
  return introduced.length > 0
    ? { verdict: "fail", evidence: `Introduced forbidden text in ${introduced.map((file) => file.path).join(", ")}` }
    : { verdict: "pass", evidence: `Checked ${matching.length} changed files.` };
}
