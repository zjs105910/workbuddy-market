import { readFile, readdir } from "node:fs/promises";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import Ajv2020 from "ajv/dist/2020.js";
import addFormats from "ajv-formats";
import { load as loadYaml } from "js-yaml";

const here = dirname(fileURLToPath(import.meta.url));
const root = resolve(here, "../..");
const registryDir = join(root, "registry");
const schemasDir = join(root, "schemas");

const loadSchema = async (name) => JSON.parse(await readFile(join(schemasDir, name), "utf8"));

const ajv = new Ajv2020({ allErrors: true, strict: false });
addFormats(ajv);
// dispatcher 通过 $id 引用 v1/v2，必须先注册子 schema（ADR-004）
ajv.addSchema(await loadSchema("registry-entry-v1.schema.json"));
ajv.addSchema(await loadSchema("registry-entry-v2.schema.json"));
const validate = ajv.compile(await loadSchema("registry-entry.schema.json"));

const folders = (await readdir(registryDir, { withFileTypes: true }))
  .filter((entry) => entry.isDirectory())
  .map((entry) => entry.name)
  .sort();

const errors = [];
const slugs = new Set();
let legacyPacks = 0;
let legacySkills = 0;
let v2Packs = 0;
let v2Entrypoints = 0;
let v2Capabilities = 0;

for (const folder of folders) {
  const entryPath = join(registryDir, folder, "entry.yaml");
  let entry;

  try {
    entry = loadYaml(await readFile(entryPath, "utf8"));
  } catch (error) {
    errors.push(`${folder}: cannot read entry.yaml (${error.message})`);
    continue;
  }

  if (!validate(entry)) {
    for (const issue of validate.errors ?? []) {
      errors.push(`${folder}${issue.instancePath || "/"}: ${issue.message}`);
    }
  }

  if (entry?.slug !== folder) {
    errors.push(`${folder}: folder name must equal slug "${entry?.slug ?? "missing"}"`);
  }
  if (slugs.has(entry?.slug)) {
    errors.push(`${folder}: duplicate slug "${entry.slug}"`);
  }
  slugs.add(entry?.slug);

  if (entry?.schema_version === 2) {
    // v2 不变量：skill_count 是兼容别名，必须等于 entrypoint_count
    if (entry.skill_count !== entry.entrypoint_count) {
      errors.push(`${folder}: v2 requires skill_count (${entry.skill_count}) === entrypoint_count (${entry.entrypoint_count})`);
    }
    if (entry.capability_count < entry.entrypoint_count && entry.output_mode !== "legacy-pack") {
      errors.push(`${folder}: capability_count (${entry.capability_count}) must be >= entrypoint_count (${entry.entrypoint_count})`);
    }
    v2Packs += 1;
    v2Entrypoints += Number(entry.entrypoint_count ?? 0);
    v2Capabilities += Number(entry.capability_count ?? 0);
  } else {
    legacyPacks += 1;
    legacySkills += Number(entry?.skill_count ?? 0);
  }
}

if (folders.length === 0) errors.push("registry: no entries found");

if (errors.length > 0) {
  console.error(`Registry validation failed with ${errors.length} error(s):`);
  for (const error of errors) console.error(`- ${error}`);
  process.exit(1);
}

console.log(
  `Registry valid: ${folders.length} packs — legacy ${legacyPacks} packs / ${legacySkills} skills; ` +
    `v2 ${v2Packs} packs / ${v2Entrypoints} entrypoints / ${v2Capabilities} capabilities.`,
);
