#!/usr/bin/env bun
import { handleSkillsMigration } from "./migrateSkills";

import product from "@shadowclone/core/product.json";
import { serveMcp } from "@shadowclone/mcp";
import { doctor } from "./doctor";
import { forgetAll } from "./forget";
import { runSessionEndHook, runSessionStartHook } from "./hooks";
import { handleSetupCommand } from "./setup";
import { importRepositoryGuidanceCommand } from "./import";
import { handleNativeCommand } from "./native";
import { handlePreferenceCommand } from "./preferences";
import { learn } from "./learn";
import { parseLearnOptions } from "./learnOptions";
import { parseRecallOptions, recallCommand } from "./recall";
import { handleProfileRepairCommand } from "./profileRepair";
import { handleMigrateCommand } from "./migrate";
import { harnessCheckCommand, parseHarnessCheck } from "./harnessCheck";
import { listSeedGuidance } from "./skills";
import { handleSkillMaintenance } from "./skillMaintenance";
import { showHome } from "./home";
import { redactSecrets } from "@shadowclone/redact";
import { botCommand } from "./bot";
import { reviewCommand } from "./review";

const usage =
  "Usage: shadowclone <init [--advanced]|init --status [--json]|init (--learn|--no-learn) (--skill-maintenance|--no-skill-maintenance) (--background-learning|--no-background-learning)|init --repo [--personal|--no-personal] [--skill <name>] [--no-enforce]|check [--changed] [--format human|json|claude-stop]|import|wizard|skills|learn [--deep] [--dry-run] [--apply] [--engine <id>] [--model <id>] [--reasoning-effort <level>] [--max-calls <n>]|doctor|profile repair [--decisions <file>] [--apply]|migrate skills [--apply] [--automatic] [--memory] [--activate-only] [--repo <path>]|migrate claude-memory [--decisions <file>] [--apply]|install [--agent claude-code|codex|cursor|antigravity|pi|all] [--global|--local] [--subagent] [--auto-delegate]|uninstall [--agent <agent>] [--global|--local]|context [--explain [--json]]|recall <query> [--limit 1..10]|sync|mcp|forget --all>";

function printUsage(): void {
  console.log(usage);
  console.log("Skill tree: wizard [--repo] [--no-open]; terminal setup: wizard --cli");
  console.log(
    "Preferences: remember [--repo|--global] <text>, history [revision-id], undo <revision-id>, learning enable|disable|status|list|pending|show <key>|apply <key>|reject <key>|repositories|bind <id>",
  );
  console.log(
    "Review: learning retire|narrow <key>, learning replace <key> <guidance>, learning remove-source <source> [--apply --expected <fingerprint>]",
  );
  console.log(
    "Behavior: learning probe <key> --agent claude-code|codex --task <synthetic task> --expect <exact response> [--model <model>] --yes; learning probe status; learning acknowledge <key>",
  );
  console.log(
    "Cloud bot: bot setup [--bot login] [--app] [--repo owner/repository]; bot status [--repo owner/repository]; bot export",
  );
  console.log(
    "Pull request review: review <pr-number> [--cloud] [--no-checks] [--repo owner/repository] [--output file.md] [--model <id>] [--effort <level>]; workflow stages: review prepare|checks|analyze|publish",
  );
  console.log(
    "Skill maintenance: skills configure [--repo|--global], skills list|update|pending, skills show|apply|reject <id>, skills manage <skill-id>, skills disable",
  );
}

function printVersion(): void {
  console.log(product.version);
}

async function main(arguments_: readonly string[]): Promise<void> {
  const [command, ...rest] = arguments_;

  if (command === undefined) {
    await showHome();

    return;
  }

  if (command === "--help" || command === "-h" || command === "help") {
    printUsage();

    return;
  }

  if (command === "--version" || command === "-v") {
    printVersion();

    return;
  }

  if (await handleSetupCommand({ command, arguments: rest })) {
    return;
  }

  if (command === "check") {
    const parsed = parseHarnessCheck(rest);

    if (parsed === null) {
      throw new Error("Use check [--changed] [--format human|json|claude-stop]");
    }

    process.exitCode = await harnessCheckCommand(parsed);

    return;
  }

  if (command === "import" && rest.length === 0) {
    await importRepositoryGuidanceCommand();

    return;
  }

  if (command === "skills" && rest.length === 0) {
    await listSeedGuidance();

    return;
  }

  if (command === "skills" && (await handleSkillMaintenance(rest))) {
    return;
  }

  if (await handlePreferenceCommand({ command, arguments: rest })) {
    return;
  }

  if (command === "learn") {
    const options = parseLearnOptions(rest);

    if (options) {
      await learn({ ...options, workingDirectory: process.cwd() });

      return;
    }
  }

  if (command === "doctor" && rest.length === 0) {
    await doctor();

    return;
  }

  if (await handleProfileRepairCommand({ command, arguments: rest })) {
    return;
  }

  if (
    (await handleSkillsMigration({ command, arguments: rest })) ||
    (await handleMigrateCommand({ command, arguments: rest }))
  ) {
    return;
  }

  if (command === "recall") {
    const options = parseRecallOptions(rest);

    if (options !== null) {
      await recallCommand(options);

      return;
    }
  }

  if (await handleNativeCommand({ command, arguments: rest })) {
    return;
  }

  if (command === "mcp") {
    await serveMcp();

    return;
  }

  if (command === "bot") {
    await botCommand(rest);

    return;
  }

  if (command === "review") {
    await reviewCommand(rest);

    return;
  }

  if (command === "hook" && rest[0] === "session-end") {
    await runSessionEndHook({ input: await Bun.stdin.text() });

    return;
  }

  if (command === "hook" && rest[0] === "session-start") {
    await runSessionStartHook({ input: await Bun.stdin.text() });

    return;
  }

  if (command === "forget" && rest[0] === "--all") {
    await forgetAll();

    return;
  }

  printUsage();

  if (command !== undefined) {
    process.exitCode = 1;
  }
}

await main(Bun.argv.slice(2)).catch((error: unknown) => {
  const message =
    error instanceof Error ? error.message : "Shadowclone could not complete this command";
  console.error(
    message.length <= 1_000
      ? redactSecrets({ text: message })
      : "Shadowclone could not complete this command. Run shadowclone doctor and inspect learning status.",
  );
  process.exitCode = 1;
});
