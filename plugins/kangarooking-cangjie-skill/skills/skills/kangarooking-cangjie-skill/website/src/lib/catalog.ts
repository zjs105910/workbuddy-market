import { readFile, readdir } from "node:fs/promises";
import { join, resolve } from "node:path";
import { load as loadYaml } from "js-yaml";

export type SourceType = "github" | "bundled";
export type Quality = "verified" | "community" | "experimental";
export type RegistryStatus = "active" | "experimental" | "archived";
export type OutputMode = "single" | "pack" | "legacy-pack";

export interface RegistryEntry {
  schema_version: 1 | 2;
  slug: string;
  name: string;
  summary: string;
  source_type: SourceType;
  source_url: string;
  skill_path?: string;
  skill_count: number;
  /** v2 only：宿主可发现入口数；single 恒为 1 */
  entrypoint_count?: number;
  /** v2 only：经验证的能力总数，允许大于入口数 */
  capability_count?: number;
  /** v2 only：single | pack；v1 条目由 getOutputMode 规范化为 legacy-pack，不回写 */
  output_mode?: OutputMode;
  /** v2 pack only：来源路由入口 slug */
  router_entrypoint?: string;
  domains: string[];
  language: string[];
  status: RegistryStatus;
  quality: Quality;
  featured?: boolean;
  use_cases: string[];
  install?: {
    clone?: string;
    copy?: string;
  };
}

/** v1 条目在读取层规范化为 legacy-pack（ADR-004：不回写文件）。 */
export function getOutputMode(entry: RegistryEntry): OutputMode {
  return entry.schema_version === 2 ? (entry.output_mode ?? "legacy-pack") : "legacy-pack";
}

/** 安装后新增的可发现 Skill 入口数 —— 用户做安装决策时真正需要的数字。 */
export function getEntrypointCount(entry: RegistryEntry): number {
  return entry.schema_version === 2 ? (entry.entrypoint_count ?? entry.skill_count) : entry.skill_count;
}

export interface CatalogStats {
  packs: number;
  /** legacy 条目的可发现 Skill 总数（迁移期保持原叙事口径） */
  skills: number;
  domains: number;
  contributors: number;
  /** v2 条目聚合：入口数 / 能力数 / 覆盖条目数 */
  v2Packs: number;
  v2Entrypoints: number;
  v2Capabilities: number;
}

const registryDir = resolve(process.cwd(), "../registry");

let catalogPromise: Promise<RegistryEntry[]> | undefined;

export function loadCatalog(): Promise<RegistryEntry[]> {
  catalogPromise ??= readCatalog();
  return catalogPromise;
}

async function readCatalog(): Promise<RegistryEntry[]> {
  const folders = (await readdir(registryDir, { withFileTypes: true }))
    .filter((entry) => entry.isDirectory())
    .map((entry) => entry.name)
    .sort();

  const entries = await Promise.all(
    folders.map(async (folder) => {
      const raw = await readFile(join(registryDir, folder, "entry.yaml"), "utf8");
      return loadYaml(raw) as RegistryEntry;
    }),
  );

  return entries.sort((a, b) => {
    if (Boolean(a.featured) !== Boolean(b.featured)) return a.featured ? -1 : 1;
    return a.name.localeCompare(b.name, "zh-CN");
  });
}

export function getCatalogStats(entries: RegistryEntry[]): CatalogStats {
  const domains = new Set(entries.flatMap((entry) => entry.domains));
  const contributors = new Set(
    entries.map((entry) => new URL(entry.source_url).pathname.split("/").filter(Boolean)[0]),
  );

  const legacy = entries.filter((entry) => entry.schema_version !== 2);
  const v2 = entries.filter((entry) => entry.schema_version === 2);

  return {
    packs: entries.length,
    skills: legacy.reduce((sum, entry) => sum + entry.skill_count, 0),
    domains: domains.size,
    contributors: contributors.size,
    v2Packs: v2.length,
    v2Entrypoints: v2.reduce((sum, entry) => sum + (entry.entrypoint_count ?? entry.skill_count), 0),
    v2Capabilities: v2.reduce((sum, entry) => sum + (entry.capability_count ?? entry.skill_count), 0),
  };
}

/** 列表页按输出模式筛选（偏好“少而整”的用户可过滤 single）。 */
export function filterByOutputMode(entries: RegistryEntry[], mode?: OutputMode): RegistryEntry[] {
  if (!mode) return entries;
  return entries.filter((entry) => getOutputMode(entry) === mode);
}

export function searchableText(entry: RegistryEntry): string {
  return [
    entry.name,
    entry.slug,
    entry.summary,
    ...entry.domains,
    ...entry.use_cases,
  ]
    .join(" ")
    .toLocaleLowerCase("zh-CN");
}

export function filterCatalog(
  entries: RegistryEntry[],
  options: { query?: string; domain?: string; quality?: string; source?: string },
): RegistryEntry[] {
  const query = options.query?.trim().toLocaleLowerCase("zh-CN") ?? "";

  return entries.filter((entry) => {
    if (query && !searchableText(entry).includes(query)) return false;
    if (options.domain && !entry.domains.includes(options.domain)) return false;
    if (options.quality && entry.quality !== options.quality) return false;
    if (options.source && entry.source_type !== options.source) return false;
    return true;
  });
}
