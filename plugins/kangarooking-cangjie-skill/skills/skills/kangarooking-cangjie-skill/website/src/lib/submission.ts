import { dump as dumpYaml } from "js-yaml";
import type { RegistryEntry, SourceType } from "./catalog";

export interface SubmissionDraft {
  mode: SourceType;
  name: string;
  slug: string;
  summary: string;
  repositoryUrl?: string;
  skillCount: number;
  domains: string;
  languages: string[];
  useCases: string;
}

export interface FileLike {
  name: string;
  size: number;
  webkitRelativePath?: string;
}

export interface FolderValidation {
  valid: boolean;
  skillCount: number;
  acceptedFiles: FileLike[];
  warnings: string[];
  errors: string[];
}

const canonicalRepository = "https://github.com/kangarooking/cangjie-skill";
const forbiddenNames = /(^|\/)(\.env(?:\..*)?|id_rsa|id_ed25519|credentials\.json|.*\.(?:pem|key|p12))$/i;
const ignoredNames = /(^|\/)(\.DS_Store|Thumbs\.db|node_modules)(\/|$)/i;

export function slugify(value: string): string {
  return value
    .normalize("NFKD")
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-+|-+$/g, "")
    .slice(0, 64);
}

export function createRegistryEntry(draft: SubmissionDraft): RegistryEntry {
  const slug = slugify(draft.slug);
  if (!slug || slug !== draft.slug) {
    throw new Error("Slug 只能包含小写英文字母、数字和连字符，且不能以连字符开头或结尾。");
  }
  if (draft.mode === "github" && !isGitHubRepository(draft.repositoryUrl ?? "")) {
    throw new Error("请输入公开的 GitHub 仓库地址，例如 https://github.com/owner/repo。");
  }

  const domains = splitList(draft.domains, /[,，\n]/);
  const useCases = splitList(draft.useCases, /\n/);
  if (domains.length === 0) throw new Error("请至少填写一个领域标签。");
  if (useCases.length === 0) throw new Error("请至少填写一个使用场景。");

  const entry: RegistryEntry = {
    schema_version: 1,
    slug,
    name: draft.name.trim(),
    summary: draft.summary.trim(),
    source_type: draft.mode,
    source_url: draft.mode === "github" ? normalizeRepositoryUrl(draft.repositoryUrl ?? "") : canonicalRepository,
    skill_count: Math.max(1, Math.floor(draft.skillCount)),
    domains,
    language: draft.languages.length > 0 ? draft.languages : ["zh-CN"],
    status: "active",
    quality: "community",
    featured: false,
    use_cases: useCases.slice(0, 6),
  };

  if (draft.mode === "bundled") entry.skill_path = `registry/${slug}/skill`;
  return entry;
}

export function serializeRegistryEntry(entry: RegistryEntry): string {
  return dumpYaml(entry, {
    noRefs: true,
    lineWidth: 100,
    sortKeys: false,
  });
}

export function validateSkillFolder(files: FileLike[]): FolderValidation {
  const warnings: string[] = [];
  const errors: string[] = [];
  const acceptedFiles = files.filter((file) => !ignoredNames.test(file.webkitRelativePath || file.name));
  const paths = acceptedFiles.map((file) => file.webkitRelativePath || file.name);

  const secretFiles = paths.filter((path) => forbiddenNames.test(path));
  if (secretFiles.length > 0) errors.push(`检测到可能包含密钥的文件：${secretFiles.join("、")}`);

  const totalBytes = acceptedFiles.reduce((sum, file) => sum + file.size, 0);
  if (totalBytes > 20 * 1024 * 1024) errors.push("文件夹超过 20 MB，请移除大型原始资料或二进制文件。");

  const skillFiles = paths.filter((path) => /(^|\/)SKILL\.md$/i.test(path));
  if (skillFiles.length === 0) errors.push("没有找到 SKILL.md。每个 Skill 至少需要一个 SKILL.md 文件。");
  if (!paths.some((path) => /(^|\/)README\.md$/i.test(path))) warnings.push("建议添加 README.md，向使用者说明这个 Skill Pack 的范围和安装方式。");

  return {
    valid: errors.length === 0,
    skillCount: skillFiles.length,
    acceptedFiles,
    warnings,
    errors,
  };
}

export function buildGitHubCreateUrl(entry: RegistryEntry, yaml: string): string {
  const url = new URL(`${canonicalRepository}/new/main`);
  url.searchParams.set("filename", `registry/${entry.slug}/entry.yaml`);
  url.searchParams.set("value", yaml);
  url.searchParams.set("message", `registry: add ${entry.slug}`);
  return url.toString();
}

function splitList(value: string, separator: RegExp): string[] {
  return [...new Set(value.split(separator).map((item) => item.trim()).filter(Boolean))];
}

function isGitHubRepository(value: string): boolean {
  try {
    const url = new URL(value);
    return url.protocol === "https:" && url.hostname === "github.com" && url.pathname.split("/").filter(Boolean).length >= 2;
  } catch {
    return false;
  }
}

function normalizeRepositoryUrl(value: string): string {
  return value.trim().replace(/\.git$/, "").replace(/\/$/, "");
}
