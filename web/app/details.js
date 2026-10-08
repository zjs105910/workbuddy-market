/* 注册表条目详情（v2.20；v2.22 拆分）。
   安装之前先了解插件：来源与信任、不可变产物（对账入口）、
   兼容性声明、权限声明 —— 全部来自注册表条目，如实展示。 */

import { esc, attr } from "./utils.js";
import { trustBadge, permBlock } from "./trust.js";
import { galleryShot } from "./screenshots.js";

export function regDetailHtml(e){
  const href = e.homepage && String(e.homepage).indexOf("https://") === 0
    ? e.homepage : "https://github.com/"+e.repo;
  const shots = e.screenshots || [];
  let h = (shots.length
    ? '<div class="grp"><h5>截图（'+shots.length+'）</h5>'+
      '<div class="shots gallery">'+shots.map(s => galleryShot(s, e.displayName)).join("")+'</div></div>'
    : '');
  h += '<div class="grp"><h5>来源与信任</h5><ul>'+
    '<li>仓库：<a href="'+attr(href)+'" target="_blank" rel="noopener">'+esc(e.repo)+'</a></li>'+
    '<li>信任分级：'+trustBadge(e.trust || "reviewed")+'</li>'+
    (e.license ? '<li>许可证：'+esc(e.license)+'</li>' : '')+
    (e.version ? '<li>产物版本：'+esc(e.version)+'</li>' : '')+
    (e.addedAt ? '<li>收录时间：'+esc(e.addedAt)+'</li>' : '')+
    '</ul></div>';
  if(e.packageHash){
    h += '<div class="grp"><h5>不可变产物（可复现安装）</h5><ul>'+
      '<li>packageHash：<code>'+esc(String(e.packageHash).slice(0,16))+'…</code></li>'+
      (e.manifestHash ? '<li>manifestHash：<code>'+esc(String(e.manifestHash).slice(0,16))+'…</code></li>' : '')+
      (e.attestationUrl
        ? '<li>构建证明：<a href="'+attr(e.attestationUrl)+'" target="_blank" rel="noopener">attestation.json</a>'+
          '（记录 sourceCommit 与 packageHash，可与本页对账）</li>'
        : '')+
      '</ul></div>';
  }
  const plat = Array.isArray(e.platforms) && e.platforms.length ? e.platforms.join("、") : "未声明（默认全平台）";
  h += '<div class="grp"><h5>兼容性（声明）</h5><ul>'+
    '<li>平台：'+esc(plat)+'</li>'+
    (e.minWorkBuddyVersion
      ? '<li>WorkBuddy 版本：≥ '+esc(e.minWorkBuddyVersion)+'</li>'
      : '<li>WorkBuddy 版本：未声明</li>')+
    '</ul></div>';
  h += permBlock(e.permissions);
  if(e.descriptionEn) h += '<div class="grp"><h5>English</h5><p class="desc" style="margin:0">'+esc(e.descriptionEn)+'</p></div>';
  return h;
}
