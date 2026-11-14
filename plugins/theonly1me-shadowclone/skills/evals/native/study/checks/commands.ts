import type { StudyAction } from "../record";

export type Step = "test-edit" | "production-edit" | "test-pass" | "test-fail" | "other";

const testCommand = /\bbun\s+(?:run\s+)?test\b/;
const inPlaceEdit = /\b(?:sed\s+-i|perl\s+-p?i|git\s+(?:stash|checkout\s+--|restore)|apply_patch|tee\s|cat\s*>)|>>?\s*["']?[^\s"'&|]+\.[cm]?[jt]sx?\b/;
const heredoc = /<<-?\s*(['"]?)(\w+)\1[^\n]*\n[\s\S]*?\n[ \t]*\2[ \t]*(?=\n|$)/g;

function withoutHeredocBodies(command: string): string {
  return command.replace(heredoc, (block) => block.split("\n")[0] ?? "");
}

function copiesIntoWorkspace(segment: string): boolean {
  const match = /\b(?:cp|mv)\s+(?:-\S+\s+)*\S+\s+(\S+)/.exec(segment);
  return match?.[1] !== undefined && !/^["']?(?:\$|\/tmp|\/private\/tmp|\/var\/)/.test(match[1]);
}

function writesTestFile(options: { segment: string; testPattern: RegExp }): boolean {
  return options.segment.split(/\s+/).some((token) => options.testPattern.test(token.replace(/^["']|["']$/g, "")));
}

function commandSteps(options: { action: StudyAction; testPattern: RegExp }): Step[] {
  const command = withoutHeredocBodies(options.action.command ?? "");
  const results = options.action.testRuns ?? (options.action.succeeded === null ? [] : [options.action.succeeded ? "pass" : "fail"]);
  let next = 0;
  const steps: Step[] = [];

  for (const segment of command.split(/\n|;|&&|\|\|/)) {
    if (testCommand.test(segment)) {
      steps.push(results[next] === "fail" ? "test-fail" : results[next] === "pass" ? "test-pass" : "other");
      next += 1;
    } else if (inPlaceEdit.test(segment) || copiesIntoWorkspace(segment)) {
      steps.push(writesTestFile({ segment, testPattern: options.testPattern }) ? "test-edit" : "production-edit");
    }
  }

  return steps.length > 0 ? steps : ["other"];
}

export function classifySteps(options: { actions: readonly StudyAction[]; testPattern: RegExp }): Step[] {
  return options.actions.flatMap((action): Step[] => {
    if (["Edit", "Write", "MultiEdit"].includes(action.tool) && action.path && /\.[cm]?tsx?$/.test(action.path)) {
      return [options.testPattern.test(action.path) ? "test-edit" : "production-edit"];
    }
    return action.tool === "Bash" && action.command ? commandSteps({ action, testPattern: options.testPattern }) : ["other"];
  });
}
