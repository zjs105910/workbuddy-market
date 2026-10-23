import type { RegistryEntry } from "./catalog";
import { getEntrypointCount, getOutputMode } from "./catalog";

export const INSTALL_GUIDE_URL = "https://kangarooking.github.io/cangjie-skill/install/cangjie-skill.md";

/** 按输出模式生成安装提示词（方案 §11.5：install 按 output_mode 分支）。 */
export function getAgentInstallPrompt(entry: RegistryEntry, guideUrl = INSTALL_GUIDE_URL): string {
  const source = entry.source_type === "bundled" && entry.skill_path
    ? `${entry.source_url} 中的 ${entry.skill_path}`
    : entry.source_url;

  const mode = getOutputMode(entry);
  const entrypoints = getEntrypointCount(entry);

  let hint = "";
  if (mode === "single") {
    hint = `该 pack 为 single 模式：安装后只新增 1 个 Skill 入口（内含 ${entry.capability_count ?? "多"} 张按需加载的能力卡），整目录复制即可。`;
  } else if (mode === "pack") {
    hint = `该 pack 为 compact pack 模式：安装后新增 ${entrypoints} 个 Skill 入口（含 1 个来源路由入口 ${entry.router_entrypoint ?? ""}），各入口目录需分别复制。`.replace("  ", " ");
  } else {
    hint = `安装后新增 ${entrypoints} 个 Skill。`;
  }

  return `请根据 ${guideUrl}，从 ${source} 安装 ${entry.slug}。${hint}`;
}
