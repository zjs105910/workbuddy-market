import { expect, test } from "bun:test";
import { observedSkillReads } from "./skillReads";

test("credits only successful direct reads of an expected skill", () => {
  const skillPath = "/private/tmp/run/home/.agents/skills/names/SKILL.md";
  const item = (command: string, exitCode: number) =>
    JSON.stringify({
      type: "item.completed",
      item: { item_type: "command_execution", status: "completed", command, exit_code: exitCode },
    });
  const stream = [
    item(`/bin/zsh -lc "cat '${skillPath}'"`, 0),
    item(`/bin/zsh -lc "echo cat '${skillPath}'"`, 0),
    item(`/bin/zsh -lc "cat '${skillPath}'"`, 1),
  ].join("\n");
  expect(observedSkillReads({ stream, skillPaths: { names: skillPath } })).toEqual(["names"]);
});

test("leaves ambiguous shell pipelines uncredited", () => {
  const skillPath = "/private/tmp/run/home/.agents/skills/names/SKILL.md";
  const stream = JSON.stringify({
    type: "item.completed",
    item: {
      item_type: "command_execution",
      status: "completed",
      exit_code: 0,
      command: `/bin/zsh -lc "cat '${skillPath}' | head"`,
    },
  });
  expect(observedSkillReads({ stream, skillPaths: { names: skillPath } })).toEqual([]);
});

test("resolves successful direct relative reads against the session workspace", () => {
  const directory = "/private/tmp/run/workspace";
  const skillPath = `${directory}/.agents/skills/atlas-engineering/SKILL.md`;
  const stream = JSON.stringify({
    type: "item.completed",
    item: {
      item_type: "command_execution",
      status: "completed",
      exit_code: 0,
      command: '/bin/zsh -lc "cat .agents/skills/atlas-engineering/SKILL.md"',
    },
  });
  expect(observedSkillReads({ stream, directory, skillPaths: { atlas: skillPath } })).toEqual([
    "atlas",
  ]);
  expect(observedSkillReads({ stream, skillPaths: { atlas: skillPath } })).toEqual([]);
  expect(
    observedSkillReads({
      stream,
      directory: "/private/tmp/other",
      skillPaths: { atlas: skillPath },
    }),
  ).toEqual([]);
});

test("does not credit indirect, unsuccessful, or ambiguous relative reads", () => {
  const directory = "/private/tmp/run/workspace";
  const operand = ".agents/skills/atlas-engineering/SKILL.md";
  const commands = [
    `echo cat ${operand}`,
    `cat ${operand} | head`,
    `cat ${operand}; true`,
    `cat ${operand} || true`,
    `cat "$SKILL"`,
    `cat ${operand} other.md`,
  ];
  for (const command of commands) {
    const stream = JSON.stringify({
      type: "item.completed",
      item: {
        item_type: "command_execution",
        status: "completed",
        exit_code: 0,
        command: `/bin/zsh -lc '${command}'`,
      },
    });
    expect(
      observedSkillReads({ stream, directory, skillPaths: { atlas: `${directory}/${operand}` } }),
    ).toEqual([]);
  }
  const stream = JSON.stringify({
    type: "item.completed",
    item: {
      item_type: "command_execution",
      status: "completed",
      exit_code: 1,
      command: `/bin/zsh -lc 'cat ${operand}'`,
    },
  });
  expect(
    observedSkillReads({ stream, directory, skillPaths: { atlas: `${directory}/${operand}` } }),
  ).toEqual([]);
});

test("credits direct skill reads in successful compound commands", () => {
  const directory = "/private/tmp/run/workspace";
  const skillPath = `${directory}/.agents/skills/atlas-engineering/SKILL.md`;
  const item = (command: string) =>
    JSON.stringify({
      type: "item.completed",
      item: {
        item_type: "command_execution",
        status: "completed",
        exit_code: 0,
        command,
      },
    });
  for (const body of [
    `cat '${skillPath}' && rg --files`,
    `pwd && cat .agents/skills/atlas-engineering/SKILL.md`,
    `cat '${skillPath}' && echo 'a && b'`,
  ]) {
    expect(
      observedSkillReads({
        stream: item(`/bin/zsh -lc ${JSON.stringify(body)}`),
        directory,
        skillPaths: { atlas: skillPath },
      }),
    ).toEqual(["atlas"]);
  }
  for (const body of [
    `cd /elsewhere && cat .agents/skills/atlas-engineering/SKILL.md`,
    `false || cat '${skillPath}'`,
    `echo "cat '${skillPath}'"`,
    `cat '${skillPath}' && false || true`,
  ]) {
    expect(
      observedSkillReads({
        stream: item(`/bin/zsh -lc ${JSON.stringify(body)}`),
        directory,
        skillPaths: { atlas: skillPath },
      }),
    ).toEqual([]);
  }
});

test("confirms a completed skill read from its exact output when a later command fails", () => {
  const skillPath = "/private/tmp/run/home/.agents/skills/names/SKILL.md";
  const content =
    "---\nname: names\ndescription: Synthetic name conventions.\n---\nUse full names.\n";
  const stream = JSON.stringify({
    type: "item.completed",
    item: {
      item_type: "command_execution",
      status: "completed",
      exit_code: 1,
      aggregated_output: content,
      command: `/bin/zsh -lc "cat '${skillPath}' && rg absent ."`,
    },
  });
  expect(
    observedSkillReads({
      stream,
      skillPaths: { names: skillPath },
      skillContents: { names: content },
    }),
  ).toEqual(["names"]);
  expect(
    observedSkillReads({
      stream,
      skillPaths: { names: skillPath },
      skillContents: { names: `${content}Changed.` },
    }),
  ).toEqual([]);
  expect(observedSkillReads({ stream, skillPaths: { names: skillPath } })).toEqual([]);
});

test("credits Claude skill invocations and direct reads of any copy of a skill", async () => {
  const { claudeSkillReads } = await import("./skillReads");
  const locations = {
    "home:names": ["/h/.agents/skills/names/SKILL.md", "/h/.claude/skills/names/SKILL.md"],
    "home:review": ["/h/.claude/skills/review/SKILL.md"],
  };
  expect(
    claudeSkillReads({
      locations,
      actions: [
        { tool: "Skill", path: null, command: "names" },
        { tool: "Read", path: "/h/.claude/skills/review/SKILL.md", command: null },
        { tool: "Read", path: "/h/.claude/skills/other/SKILL.md", command: null },
      ],
    }),
  ).toEqual(["home:names", "home:review"]);
  expect(
    claudeSkillReads({
      locations,
      actions: [{ tool: "Bash", path: null, command: "cat /h/.agents/skills/names/SKILL.md" }],
    }),
  ).toEqual([]);
});
