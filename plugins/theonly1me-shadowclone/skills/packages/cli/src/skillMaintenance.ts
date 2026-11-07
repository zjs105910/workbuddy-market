import {
  readConfig,
  readEffectiveConfig,
  setSourceEnabled,
  writeConfig,
  projectPaths,
} from "@shadowclone/core";
import {
  adoptSkill,
  applySkillProposal,
  inspectSkillLibrary,
  runLearningMaintenance,
} from "@shadowclone/learning";
import { handleEnvironmentSkills } from "./environmentSkills";
import {
  configureSkillMaintenance,
  disableSkillRoot,
  listSkillProposals,
  readMaintenanceState,
  rejectSkillProposal,
  showSkillProposal,
  showSkillRoots,
} from "@shadowclone/skills";

async function configure(arguments_: readonly string[]): Promise<void> {
  const scope = arguments_.includes("--global") ? "global" : "repository";

  if (arguments_.includes("--global") && arguments_.includes("--repo")) {
    throw new Error("Choose one skill scope");
  }

  let rootDirectory: string | undefined;
  const seen = new Set<string>();

  for (let position = 0; position < arguments_.length; position += 1) {
    const argument = arguments_[position];

    if (!argument || seen.has(argument)) {
      throw new Error("Repeated skill configuration option");
    }

    seen.add(argument);

    if (argument === "--root") {
      rootDirectory = arguments_[++position];

      if (!rootDirectory || rootDirectory.startsWith("--")) {
        throw new Error("--root requires a skill directory");
      }
    } else if (!["--repo", "--global", "--third-party"].includes(argument)) {
      throw new Error(
        "Use skills configure [--repo|--global] [--root <directory>] [--third-party]",
      );
    }
  }

  if (seen.has("--third-party") && !rootDirectory) {
    throw new Error("--third-party requires an explicit root");
  }

  const count = await configureSkillMaintenance({
    scope,
    rootDirectory,
    thirdParty: seen.has("--third-party"),
  });

  console.log(
    `Enabled skill maintenance for ${count} ${scope} root(s). User-owned and third-party changes require review.`,
  );
}

export async function handleSkillMaintenance(
  arguments_: readonly string[],
): Promise<boolean> {
  if (await handleEnvironmentSkills(arguments_)) {
    return true;
  }

  const [action, ...rest] = arguments_;
  const [id] = rest;

  if (!action) {
    return false;
  }

  if (action === "configure") {
    await configure(rest);
  } else if (action === "disable" && !id) {
    const config = await readConfig();

    await writeConfig({
      config: setSourceEnabled({
        config,
        source: "skill-library",
        enabled: false,
      }),
    });
    console.log("Skill library access disabled; existing skills preserved.");
  } else if (action === "update" && !id) {
    const { config } = await readEffectiveConfig();

    if (!config.sources["skill-library"]) {
      throw new Error(
        "Skill library access is disabled; run skills configure first",
      );
    }

    const status = await runLearningMaintenance({
      automatic: false,
      reportSkills: (summary) => console.log(JSON.stringify(summary, null, 2)),
    });

    if (status !== "completed") {
      throw new Error(
        `Skill maintenance ${status}; inspect learning status and consent before retrying`,
      );
    }
  } else if (action === "list" && !id) {
    const discovered = await inspectSkillLibrary({ paths: projectPaths });
    const state = await readMaintenanceState(projectPaths);

    console.log(
      JSON.stringify(
        {
          invalid: discovered.invalid,
          duplicates: discovered.duplicates,
          skills: discovered.skills.map((skill) => ({
            id: skill.id,
            name: skill.name,
            scope: skill.root.scope,
            owner: skill.root.owner,
            managed: state.tracked.some(
              (entry) => entry.id === skill.id && entry.automatic,
            ),
            findings: state.findings[skill.id] ?? [],
          })),
        },
        null,
        2,
      ),
    );
  } else if (action === "roots" && !id) {
    console.log(await showSkillRoots(projectPaths));
  } else if (action === "unconfigure" && id && rest.length === 1) {
    await disableSkillRoot({ paths: projectPaths, id });
    console.log(
      "Disabled this skill root; ownership records retained for recovery.",
    );
  } else if (action === "pending" && !id) {
    console.log(
      JSON.stringify(
        (await listSkillProposals(projectPaths)).filter(
          (proposal) => proposal.status === "pending",
        ),
        null,
        2,
      ),
    );
  } else if (
    ["show", "apply", "reject", "manage"].includes(action) &&
    id &&
    rest.length === 1
  ) {
    if (action === "show") {
      console.log(await showSkillProposal({ paths: projectPaths, id }));
    }

    if (action === "apply") {
      console.log(
        `Applied skill revision ${(await applySkillProposal({ paths: projectPaths, id })) ?? "unchanged"}.`,
      );
    }

    if (action === "reject") {
      await rejectSkillProposal({ paths: projectPaths, id });
      console.log("Skill proposal rejected.");
    }

    if (action === "manage") {
      await adoptSkill({ paths: projectPaths, id });
      console.log(
        "Enabled automatic preference additions for this skill; routing changes still require review.",
      );
    }
  } else {
    throw new Error(
      "Use skills configure|disable|list|update|pending|show <id>|apply <id>|reject <id>|manage <skill-id>",
    );
  }

  return true;
}
