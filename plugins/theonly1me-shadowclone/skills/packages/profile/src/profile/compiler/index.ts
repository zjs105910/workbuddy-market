import { ownedWrite } from "@shadowclone/core";
import { seedGuidanceProfileKey, loadSeedLibrary } from "@shadowclone/skills";
import { readScopedReferences } from "../../references";
import {
  compilerBlocksFromReferences,
  compilerBlocksFromRules,
  readCompilerBlocks,
} from "./read";
import {
  addOmittedBreakdown,
  defaultProfileByteBudget,
  renderCompilation,
} from "./render";
import { defaultIndexByteBudget, renderIndexCompilation } from "./renderIndex";
import { selectCompilerBlocks } from "./select";
import type { RepositoryApplicability } from "./applicability";
import type {
  CompilerBlock,
  ProfileCompilation,
  ProfileCompilationAudience,
  ProfileCompilationFormat,
  ProfileCompilationRepositoryContext,
  ProfileCompileInput,
} from "./types";

export { profileScopePaths } from "./read";

export { defaultProfileByteBudget } from "./render";

export { defaultIndexByteBudget } from "./renderIndex";

export {
  toolPatterns,
  type KnownTool,
  type RepositoryApplicability,
} from "./applicability";

export type {
  ProfileCompilation,
  ProfileCompilationAudience,
  ProfileCompilationBreakdown,
  ProfileCompilationFormat,
  ProfileCompilationOmission,
  ProfileCompilationOmissionReason,
  ProfileCompilationRepositoryContext,
  ProfileCompileInput,
} from "./types";

const seedKeyPrefix = "seed:";

async function seedAxes(
  blocks: readonly CompilerBlock[],
): Promise<ReadonlyMap<string, string>> {
  const carriesSeedGuidance = blocks.some((block) =>
    block.ruleKey?.startsWith(seedKeyPrefix),
  );

  if (!carriesSeedGuidance) {
    return new Map();
  }

  const axes = new Map<string, string>();

  try {
    const library = await loadSeedLibrary();

    for (const axis of library.axes) {
      for (const guidance of axis.guidance) {
        axes.set(seedGuidanceProfileKey(guidance.id), axis.id);
      }
    }
  } catch {
    return new Map();
  }

  return axes;
}

async function compilerBlocks(options: {
  readonly input: ProfileCompileInput;
  readonly audience: ProfileCompilationAudience;
}): Promise<readonly CompilerBlock[]> {
  const input = options.input;

  if (input.kind === "rules") {
    return compilerBlocksFromRules(input.rules);
  }

  const rules = await readCompilerBlocks({
    profileDirectory: input.profileDirectory,
    origin: input.origin,
    targetRepo: input.targetRepo,
    scope: input.scope,
  });

  if (options.audience === "subagent") {
    return rules;
  }

  const references = await readScopedReferences({
    profileDirectory: input.profileDirectory,
    origin: input.origin,
    targetRepo: input.targetRepo,
    scope: input.scope,
  });

  return [...rules, ...compilerBlocksFromReferences(references)];
}

function withoutInternalFields(
  compilation: ProfileCompilation & {
    readonly omittedBlocks: readonly CompilerBlock[];
  },
): ProfileCompilation {
  const { omittedBlocks: _omittedBlocks, ...result } = compilation;

  return result;
}

export async function compileProfile(options: {
  readonly input: ProfileCompileInput;
  readonly outputPath?: string;
  readonly byteBudget?: number;
  readonly audience?: ProfileCompilationAudience;
  readonly repositoryContext?: ProfileCompilationRepositoryContext;
  readonly format?: ProfileCompilationFormat;
  readonly knownNativeText?: readonly string[];
  readonly applicability?: RepositoryApplicability;
  readonly committedRuleKeys?: ReadonlySet<string>;
}): Promise<ProfileCompilation> {
  const blocks = await compilerBlocks({
    input: options.input,
    audience: options.audience ?? "main",
  });

  const selection = selectCompilerBlocks({
    blocks,
    axes: await seedAxes(blocks),
    repositoryContext: options.repositoryContext ?? "native",
    knownNativeText: options.knownNativeText,
    applicability: options.applicability,
    committedRuleKeys: options.committedRuleKeys,
  });

  const rendered =
    options.format === "index" || options.format === "harness"
      ? renderIndexCompilation({
          blocks: selection.selected,
          byteBudget: options.byteBudget ?? defaultIndexByteBudget,
          standalone: options.format === "index",
        })
      : renderCompilation({
          blocks: selection.selected,
          byteBudget: options.byteBudget ?? defaultProfileByteBudget,
        });

  if (options.outputPath !== undefined) {
    await ownedWrite({
      path: options.outputPath,
      content: rendered.markdown,
    });
  }

  return withoutInternalFields({
    ...rendered,
    breakdown: addOmittedBreakdown({
      breakdown: rendered.breakdown,
      blocks: selection.omittedBlocks,
    }),
    omissions: [...selection.omissions, ...rendered.omissions],
  });
}
