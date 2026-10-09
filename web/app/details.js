/* 注册表条目详情：安装前「四问」（v2.23；v2.20 起源/信任/产物/兼容/权限）。
   四个问题按用户视角组织：
     ① 来自哪里 —— 上游仓库、固定 sourceCommit、维护者信息（有来源才展示）；
     ② 是否可信 —— 官方 / 已审核 / 未审核 + 真实审核范围（没有就写
        「审核范围未提供」，绝不推断）；
     ③ 能做什么 —— 权限声明（明示：声明 ≠ 运行时限制，审核 ≠ 绝对安全）；
     ④ 能否安装 —— 版本、平台兼容、WorkBuddy 最低版本、校验字段；
        字段缺失显示「未声明」，绝不伪造为兼容。
   全部来自注册表条目，如实展示；信任 fail-closed —— 缺失/未知一律「未审核」。 */

import { esc, attr } from "./utils.js";
import { trustBadge, permRows } from "./trust.js";
import { galleryShot } from "./screenshots.js";

export function regDetailHtml(e){
  const href = e.homepage && String(e.homepage).indexOf("https://") === 0
    ? e.homepage : "https://github.com/"+e.repo;
  const shots = e.screenshots || [];
  let h = (shots.length
    ? '<div class="grp"><h5>截图（'+shots.length+'）</h5>'+
      '<div class="shots gallery">'+shots.map(s => galleryShot(s, e.displayName)).join("")+'</div></div>'
    : '');

  /* ---- ① 来自哪里？ ---- */
  h += '<div class="grp"><h5>① 来自哪里？</h5><ul>'+
    '<li>上游仓库：<a href="'+attr(href)+'" target="_blank" rel="noopener">'+esc(e.repo)+'</a></li>'+
    (e.sourceCommit
      ? '<li>收录时固定提交：<code>'+esc(String(e.sourceCommit).slice(0,12))+'…</code>'+
        '（审核看的是这一份）</li>'
      : '')+
    (e.homepage && String(e.homepage).indexOf("https://") === 0 && e.homepage !== href
      ? '<li>主页：<a href="'+attr(e.homepage)+'" target="_blank" rel="noopener">'+esc(e.homepage)+'</a></li>'
      : '')+
    (e.addedAt ? '<li>收录时间：'+esc(e.addedAt)+'</li>' : '')+
    '</ul></div>';

  /* ---- ② 是否可信？（fail-closed：缺失/未知 = 未审核） ---- */
  const rv = (e.review && typeof e.review === "object") ? e.review : null;
  const scope = [];
  if(rv && rv.status) scope.push('状态 '+esc(rv.status));
  if(rv && rv.method) scope.push('方式 '+esc(rv.method));
  if(rv && rv.reviewedAt) scope.push('时间 '+esc(rv.reviewedAt));
  h += '<div class="grp"><h5>② 是否可信？</h5><ul>'+
    '<li>信任分级：'+trustBadge(e.trust)+'</li>'+
    '<li>审核范围：'+(scope.length ? scope.join(' · ') : '<b>审核范围未提供</b>（不代表已审核，也不代表未审核 —— 数据里没有，如实展示）')+'</li>'+
    (e.license ? '<li>许可证：'+esc(e.license)+'</li>' : '<li>许可证：未声明</li>')+
    '</ul>'+
    '<div class="note">「已审核」指收录时人工看过来源与内容，<b>不等于绝对安全</b>；'+
    '「未审核」表示没有人工背书，安装前请自查仓库与脚本。</div></div>';

  /* ---- 不可变产物（可复现安装的对账入口，归入「能否安装」的证据链） ---- */

  /* ---- ③ 能做什么？（权限声明） ---- */
  h += '<div class="grp"><h5>③ 能做什么？（权限声明）</h5>' +
    (permRows(e.permissions) ||
      '<div class="note">该条目未声明权限清单（协议 v0.3 起支持；未声明 ≠ 不需要，'+
      '哈希校验链不受影响）。</div>') +
    '</div>';
  h += '<div class="note">权限声明是对插件行为的<b>描述</b>，不是运行时沙箱 —— '+
       'WorkBuddy 不会在运行时强制限制这些能力；声明「不需要」也不代表绝对不碰。'+
       '安装前建议结合仓库脚本内容自行判断。</div>';

  /* ---- ④ 能否安装？ ---- */
  const plat = Array.isArray(e.platforms) && e.platforms.length
    ? e.platforms.join("、") : "未声明（默认按全平台对待）";
  const hasPkg = !!(e.packageUrl && e.packageHash);
  h += '<div class="grp"><h5>④ 能否安装？</h5><ul>'+
    '<li>产物版本：'+(e.version ? esc(e.version) : '未声明')+'</li>'+
    '<li>平台：'+esc(plat)+'</li>'+
    '<li>WorkBuddy 版本：'+(e.minWorkBuddyVersion ? '≥ '+esc(e.minWorkBuddyVersion) : '未声明')+'</li>'+
    (hasPkg
      ? '<li>校验：收录时固定的 <code>packageHash</code>'+(e.manifestHash ? ' + <code>manifestHash</code>' : '')+
        '，安装时逐包 SHA-256 比对，不符即整包拒绝</li>'
      : '<li>校验：<b>无固定产物</b>（安装走 ghpm 源码链路，自带事务与回滚，但无法逐包哈希对账）</li>')+
    (e.attestationUrl
      ? '<li>构建证明：<a href="'+attr(e.attestationUrl)+'" target="_blank" rel="noopener">attestation.json</a>'+
        '（记录 sourceCommit 与 packageHash，可对账；<b>构建证明不是数字签名</b>）</li>'
      : '')+
    '</ul></div>';

  if(e.descriptionEn) h += '<div class="grp"><h5>English</h5><p class="desc" style="margin:0">'+esc(e.descriptionEn)+'</p></div>';
  return h;
}
