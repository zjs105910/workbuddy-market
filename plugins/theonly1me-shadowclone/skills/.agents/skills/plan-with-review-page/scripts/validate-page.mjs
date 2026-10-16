#!/usr/bin/env node
import { readFile } from "node:fs/promises";

const statuses = ["todo", "doing", "done", "blocked", "skipped"];
const dashes = new RegExp(`[${String.fromCharCode(0x2013, 0x2014)}]`);
const mermaidUrl = "https://cdn.jsdelivr.net/npm/mermaid@12.1.0/dist/mermaid.min.js";
const mermaidIntegrity = "sha384-EbBpjO7rlR6eqZEcG7GaPpyk9H9WrMyPWX4d3KvPYltgt8Z8l0z6R56B1qP40pR4";

function readPlan(html) {
  const blocks = [
    ...html.matchAll(/<script type="application\/json" id="plan">([\s\S]*?)<\/script>/g),
  ];

  if (blocks.length !== 1) {
    return {
      error: `found ${blocks.length} plan blocks, keep exactly one JSON block with the id plan`,
    };
  }

  try {
    return { plan: JSON.parse(blocks[0][1]) };
  } catch (error) {
    return { error: `the plan block is not valid JSON: ${error.message}` };
  }
}

function textValues(value, at) {
  if (typeof value === "string") {
    return [[at, value]];
  }

  if (Array.isArray(value)) {
    return value.flatMap((entry, index) => textValues(entry, `${at}[${index}]`));
  }

  if (value !== null && typeof value === "object") {
    return Object.entries(value).flatMap(([key, entry]) =>
      textValues(entry, at ? `${at}.${key}` : key),
    );
  }

  return [];
}

const filled = (value) => typeof value === "string" && value.trim().length > 0;

function validate(html) {
  const { plan, error } = readPlan(html);

  if (error) {
    return [error];
  }

  const errors = [];
  const steps = Array.isArray(plan.steps) ? plan.steps : [];
  const decisions = Array.isArray(plan.decisions) ? plan.decisions : [];

  for (const key of ["title", "goal", "planPath", "updated"]) {
    if (!filled(plan[key])) {
      errors.push(`${key} must be filled in`);
    }
  }

  if (steps.length === 0) {
    errors.push("steps must list at least one step");
  }

  for (const [index, step] of steps.entries()) {
    if (!statuses.includes(step?.status)) {
      errors.push(`steps[${index}].status must be one of ${statuses.join(", ")}`);
    }

    if (!filled(step?.text)) {
      errors.push(`steps[${index}].text must be filled in`);
    }

    if ((step?.status === "skipped" || step?.status === "blocked") && !filled(step.note)) {
      errors.push(`steps[${index}] is ${step.status}, so its note must give the reason`);
    }
  }

  if (!Array.isArray(plan.decisions)) {
    errors.push("decisions must be a list");
  }

  for (const [index, decision] of decisions.entries()) {
    for (const key of ["question", "answer", "source"]) {
      if (!filled(decision?.[key])) {
        errors.push(`decisions[${index}].${key} must be filled in`);
      }
    }
  }

  if (!Array.isArray(plan.open) || plan.open.some((entry) => typeof entry !== "string")) {
    errors.push("open must be a list of questions");
  }

  if (typeof plan.diagram !== "string") {
    errors.push("diagram must be Mermaid source, or empty when there is no diagram");
  }

  for (const [at, text] of textValues(plan, "")) {
    if (text.startsWith("TEMPLATE:")) {
      errors.push(`${at} still has template text, replace it`);
    }

    if (dashes.test(text)) {
      errors.push(`${at} has an em or en dash, use a comma, a period, or parentheses`);
    }
  }

  for (const [url] of html.matchAll(/https?:\/\/[^\s"'<>)]+/g)) {
    if (url !== mermaidUrl) {
      errors.push(`${url} loads from the network, keep the page self-contained`);
    }
  }

  if (html.includes(mermaidUrl) && !html.includes(mermaidIntegrity)) {
    errors.push("the Mermaid script must keep its pinned integrity hash");
  }

  return errors;
}

async function main(files) {
  if (files.length === 0) {
    console.error("Usage: validate-page.mjs <page.html>...");

    return 2;
  }

  let total = 0;

  for (const file of files) {
    let html;

    try {
      html = await readFile(file, "utf8");
    } catch (error) {
      console.error(`${file}: cannot read the file (${error.code ?? error.message})`);

      return 2;
    }

    for (const message of validate(html)) {
      console.log(`${file}: error ${message}`);
      total += 1;
    }
  }

  const plural = (count, word) => `${count} ${word}${count === 1 ? "" : "s"}`;

  console.log(`validate-page: ${plural(total, "error")} in ${plural(files.length, "file")}`);

  return total > 0 ? 1 : 0;
}

process.exitCode = await main(process.argv.slice(2));
