/* 社区注册表（v2.11 起；v2.22 拆分）。
   这里只放「读注册表 / 目录缓存」的查询型助手；写入走 api + main 的事件分发。 */

import { CATALOG, REG, cat, filter } from "./state.js";
import { isFav } from "./favorites.js";
import { $ } from "./utils.js";

// 目录缓存里找一条收录源的实时元数据（大小写不敏感；失败记录也算命中）
export function liveOf(repo){
  const c = CATALOG || {};
  const k = String(repo||"").toLowerCase();
  for(const key in (c.repos||{})) if(key.toLowerCase() === k) return c.repos[key];
  for(const key in (c.errors||{})) if(key.toLowerCase() === k) return {error:c.errors[key]};
  return null;
}

export function regPass(e){
  if(cat !== "全部" && e.category !== cat) return false;
  if(filter === "done" && !isRegInstalled(e.repo)) return false;
  if(filter === "todo" && isRegInstalled(e.repo)) return false;
  if(filter === "fav" && !isFav(e.repo)) return false;   // 我的收藏（v2.21）
  const q = $("#q").value.trim().toLowerCase();
  if(!q) return true;
  const hay = [e.displayName,e.displayNameEn,e.repo,e.description,e.category,(e.keywords||[]).join(" ")]
    .join(" ").toLowerCase();
  return hay.includes(q);
}

export function isRegInstalled(repo){
  return !!(REG.installedRepos && REG.installedRepos[repo]);
}

export function regTrustOf(repo){
  // v2.23 fail-closed：注册表条目缺 trust / 值不认识 → 一律当 external，
  // 绝不默认成 reviewed（v2.21 的 `|| "reviewed"` 是 fail-open，已修）。
  const e = (REG.plugins||[]).find(p => p.repo === repo);
  const t = e ? e.trust : "external";
  return (t === "official" || t === "reviewed") ? t : "external";
}
