/* 权限声明与信任分级展示（v2.20 / v2.22 拆分）。
   徽标必须如实 —— 搜索到不等于官方认可。 */

import { esc } from "./utils.js";

/* ---------------- 信任分级（v2.12） ----------------
   official = 官方收录 / reviewed = 社区精选（已人工审核）/ external = 未审核。 */
export function trustBadge(t){
  return t === "official" ? '<span class="tag ok">✓ 官方</span>'
       : t === "reviewed" ? '<span class="tag ok">✓ 已审核</span>'
       : '<span class="tag warn">! 未审核</span>';
}

/* ---------------- 权限声明（v2.20，协议 v0.3） ----------------
   manifest.permissions / 注册表条目 permissions 的展示口径：
   布尔 true = 需要（未限定范围，显眼标 warn）；数组 = 需要且限定范围；
   false = 明确不需要。没声明的键不显示 —— 不替包编造「可能需要」。 */
const PERM_META = {
  filesystem: {icon:"🗂", label:"文件系统"},
  network:    {icon:"🌐", label:"网络访问"},
  shell:      {icon:"💻", label:"Shell 命令"},
  credentials:{icon:"🔐", label:"凭据访问"},
  subprocess: {icon:"📦", label:"子进程"}
};

export function permRows(perms){
  if(!perms || typeof perms !== "object") return "";
  const rows = [];
  for(const k in PERM_META){
    if(!(k in perms)) continue;
    const v = perms[k], m = PERM_META[k];
    if(v === true)
      rows.push('<div class="perm"><span>'+m.icon+' '+m.label+'</span><span class="ptag warn">需要（未限定范围）</span></div>');
    else if(v === false)
      rows.push('<div class="perm"><span>'+m.icon+' '+m.label+'</span><span class="ptag grey">不需要</span></div>');
    else if(Array.isArray(v) && v.length)
      rows.push('<div class="perm"><span>'+m.icon+' '+m.label+'</span><span class="ptag">'+esc(v.join("、"))+'</span></div>');
  }
  return rows.join("");
}

export function permBlock(perms){
  const rows = permRows(perms);
  if(!rows)
    return '<div class="note">该条目未声明权限清单（协议 v0.3 起支持；哈希校验链不受影响）。</div>';
  return '<div class="grp"><h5>需要的权限</h5>'+rows+'</div>';
}
