/* 卡片渲染：本机插件 / GitHub 收录源 / 社区目录 / 全网搜索（v2.22 拆分）。
   只做「数据 → HTML 字符串」；事件交给 main.js 的统一委托分发。 */

import { STATE, CATALOG, CATALOG_STALE, REG, cat, filter, tab } from "./state.js";
import { liveOf, regPass, regTrustOf, isRegInstalled } from "./registry.js";
import { isFav } from "./favorites.js";
import { trustBadge } from "./trust.js";
import { $, esc, attr, fmtNum, iconOf } from "./utils.js";
import { api } from "./api.js";
import { cardShot } from "./screenshots.js";

/* ---------------- 过滤 ---------------- */
function pass(p){
  if(filter === "fav") return false;   // 收藏只对社区目录有意义（v2.21）
  if(cat !== "全部" && p.category !== cat) return false;
  if(filter === "done" && !p.installed) return false;
  if(filter === "todo" && p.installed) return false;
  const q = $("#q").value.trim().toLowerCase();
  if(!q) return true;
  const hay = [p.name,p.rawName,p.description,p.category,(p.keywords||[]).join(" ")].join(" ").toLowerCase();
  return hay.includes(q);
}

/* ---------------- GitHub 全网搜索（v2.10） ---------------- */
let GH = {q:null, items:null, state:"idle", error:""}, ghTimer = null;

function cardGh(r){
  const okLink = String(r.htmlUrl||"").indexOf("https://github.com/") === 0;
  const title = okLink
    ? '<a href="'+attr(r.htmlUrl)+'" target="_blank" rel="noopener" style="color:inherit">'+esc(r.repo)+'</a>'
    : esc(r.repo);
  return '<div class="card">'+
    '<div class="card-head">'+
      '<div class="icon">⌕</div>'+
      '<div style="flex:1"><h3>'+title+'</h3>'+
        '<div class="meta">'+
          trustBadge("external")+
          (r.stars ? '<span>★ '+fmtNum(r.stars)+'</span>' : '')+
          (r.language ? '<span>'+esc(r.language)+'</span>' : '')+
          (r.pushedAt ? '<span>更新于 '+esc(r.pushedAt)+'</span>' : '')+
          (r.archived ? '<span class="tag warn">已归档</span>' : '')+
        '</div></div>'+
    '</div>'+
    '<p class="desc">'+esc(r.description)+'</p>'+
    '<div class="card-foot"><span class="state">○ 未安装</span>'+
      '<button class="tiny primary" data-radd="'+attr(r.repo)+'">一键安装</button></div>'+
  '</div>';
}

function ghEnsure(q){
  if(GH.q === q && (GH.state === "loading" || GH.state === "done")){ ghPaint(); return; }
  clearTimeout(ghTimer);
  GH = {q, items:null, state:"pending", error:""};
  ghPaint();
  ghTimer = setTimeout(async () => {
    GH.state = "loading"; ghPaint();
    try{
      const r = await api("/api/gh/search?q=" + encodeURIComponent(GH.q));
      if($("#q").value.trim() !== GH.q) return;   // 用户已改词，丢弃过期结果
      GH.items = r.items || []; GH.state = "done";
    }catch(err){ GH.error = err.message; GH.state = "error"; }
    ghPaint();
  }, 550);
}

function ghPaint(){
  const box = $("#ghGrid"), st = $("#ghState");
  if(!box) return;
  if(GH.state === "pending"){ st.textContent = "即将搜索 GitHub…"; box.innerHTML = ""; return; }
  if(GH.state === "loading"){ st.textContent = "正在搜索 GitHub…"; box.innerHTML = ""; return; }
  if(GH.state === "error"){ st.textContent = "搜索失败：" + GH.error; box.innerHTML = ""; return; }
  st.textContent = GH.items.length
    ? GH.items.length + " 个结果 · 确认来源后可一键安装"
    : "GitHub 上也没有匹配的仓库";
  box.innerHTML = GH.items.map(cardGh).join("");
}

/* ---------------- 卡片 ---------------- */
function safetyBar(u){
  const c = u.counts || {};
  const out = [];
  if(c.safe) out.push('<span class="sf ok">可安全卸载 '+c.safe+'</span>');
  if(c.modified) out.push('<span class="sf warn">被改过 '+c.modified+'</span>');
  const foreign = (c.foreign||0) + (c.other_plugin||0);
  if(foreign) out.push('<span class="sf">非本市场 '+foreign+' · 不会动</span>');
  if(c.absent) out.push('<span class="sf">未安装 '+c.absent+'</span>');
  return out.length ? '<div class="safety">'+out.join("")+'</div>' : "";
}

function cardLocal(p){
  const u = p.uninstall || {counts:{}};
  const cls = p.installed ? "on" : (p.partial ? "part" : "");
  const stTxt = p.installed ? '<span class="state ok">● 已装好 '+p.installedRatio+'</span>'
              : p.partial   ? '<span class="state warn">● 装了 '+p.installedRatio+'</span>'
              : '<span class="state">○ 未安装</span>';

  const rows = (p.skillDetail||[]).map(d => {
    const k = d.kind;
    const tag = k === "safe" ? '<span class="tag ok">可卸载</span>'
              : k === "modified" ? '<span class="tag warn">被改过</span>'
              : k === "foreign" ? '<span class="tag grey">非本市场</span>'
              : k === "other_plugin" ? '<span class="tag grey">别的插件</span>'
              : '<span class="tag grey">未装</span>';
    return '<div class="row"><code>'+esc(d.skill)+'</code>'+tag+'</div>';
  }).join("");

  const hasMissing = (u.counts.absent||0) > 0;
  const hasModified = (u.counts.modified||0) > 0;
  let btns = '<button class="tiny" data-path="'+attr(p.id)+'">定位</button>';
  if(hasMissing){
    btns += '<button class="tiny primary" data-install="'+p.id+'" data-mode="missing">补齐</button>';
  } else if(hasModified){
    btns += '<button class="tiny primary" data-install="'+p.id+'" data-mode="update">更新</button>';
  }
  if((u.counts.safe||0) > 0 || hasModified){
    btns += '<button class="tiny danger" data-uninstall="'+p.id+'">卸载…</button>';
  }

  return '<div class="card '+cls+'">'+
    '<div class="card-head">'+
      '<div class="icon">'+iconOf(p.category)+'</div>'+
      '<div style="flex:1"><h3>'+esc(p.name)+'</h3>'+
        '<div class="meta"><span>'+esc(p.category)+'</span><span>v'+esc(p.version)+'</span>'+
        '<span>'+p.skills.length+' skill</span></div></div>'+
    '</div>'+
    '<p class="desc">'+esc(p.description)+'</p>'+
    (p.keywords&&p.keywords.length ? '<div class="kw">'+p.keywords.map(k=>'<i>'+esc(k)+'</i>').join("")+'</div>' : '')+
    safetyBar(u)+
    '<div><button class="toggle" data-toggle="'+p.id+'">▾ 看 '+p.skills.length+' 个 skill 的状态</button></div>'+
    '<div class="sk" id="sk-'+p.id+'">'+rows+'</div>'+
    '<div class="card-foot">'+stTxt+btns+'</div>'+
  '</div>';
}

function cardRemote(r){
  const stTxt = r.installed
    ? '<span class="state ok">● 已装 '+r.installedSkills+' 个 skill · '+esc(r.installedSha)+'</span>'
    : '<span class="state">○ 未安装</span>';
  const lv = liveOf(r.rawName);
  const stars = (lv && lv.stars) ? lv.stars : r.stars;
  const meta = '<span>'+esc(r.category)+'</span>'+trustBadge(regTrustOf(r.rawName))+
          (r.skillCount ? '<span>'+r.skillCount+' skill</span>' : '')+
          (stars ? '<span>★ '+fmtNum(stars)+'</span>' : '')+
          (lv && lv.pushedAt ? '<span>更新于 '+esc(lv.pushedAt)+'</span>' : '')+
          (lv && lv.error ? '<span class="tag warn">刷新失败</span>' : '');
  return '<div class="card '+(r.installed?"on":"")+'">'+
    '<div class="card-head">'+
      '<div class="icon">'+iconOf(r.category)+'</div>'+
      '<div style="flex:1"><h3>'+esc(r.name)+'</h3>'+
        '<div class="meta">'+meta+'</div></div>'+
    '</div>'+
    '<p class="desc">'+esc(r.description)+'</p>'+
    '<div class="kw"><i>'+esc(r.rawName)+'</i>'+
      (r.keywords||[]).map(k=>'<i>'+esc(k)+'</i>').join("")+'</div>'+
    '<div class="card-foot">'+stTxt+
      (r.installed
        ? '<button class="tiny" data-rupdate="'+attr(r.rawName)+'">检查更新</button>'
        : '<button class="tiny primary" data-radd="'+attr(r.rawName)+'">一键安装</button>')+
    '</div></div>';
}

function cardRegistry(e){
  const inst = isRegInstalled(e.repo);
  const info = inst ? REG.installedRepos[e.repo] : null;
  const fav = isFav(e.repo);
  const stTxt = inst
    ? '<span class="state ok">● 已装 '+esc(info.name||"")+(info.sha_short? ' · '+esc(info.sha_short):"")+'</span>'
    : '<span class="state">○ 未安装</span>';
  const okLink = String(e.homepage||"").indexOf("https://") === 0
    || String(e.repo||"").indexOf("/") > 0;
  const href = e.homepage && String(e.homepage).indexOf("https://") === 0
    ? e.homepage : "https://github.com/"+e.repo;
  const title = okLink
    ? '<a href="'+attr(href)+'" target="_blank" rel="noopener" style="color:inherit">'+esc(e.displayName)+'</a>'
    : esc(e.displayName);
  const shots = (e.screenshots||[]).slice(0,1);   // 卡片只放首图，完整画廊在详情
  const shotsHtml = shots.length
    ? '<div class="shots">'+shots.map(s => cardShot(s, e.displayName)).join("")+'</div>'
    : '';
  // v2.23：成套产物字段 → 主按钮走不可变产物链路（哈希校验），
  // 文案如实 —— 有审核记录才说「审核」，只有哈希就叫「固定产物」。
  const hasPkg = !!(e.packageUrl && e.packageHash);
  const instLabel = hasPkg ? "安装固定产物" : "一键安装";
  const instTitle = hasPkg ? "下载后按收录时固定的 SHA-256 逐包校验，不符即拒绝"
                           : "走 ghpm 源码安装（自带事务与回滚）";
  return '<div class="card">'+
    '<div class="card-head">'+
      '<div class="icon">'+iconOf(e.category)+'</div>'+
      '<div style="flex:1"><h3>'+title+'</h3>'+
        '<div class="meta">'+
          '<span>'+esc(e.category)+'</span>'+
          trustBadge(e.trust)+   // v2.23 fail-closed：缺失/未知 → 未审核，绝不默认已审核
          (e.license ? '<span>'+esc(e.license)+'</span>' : '')+
          (e.qualityScore ? '<span>质 '+e.qualityScore+'</span>' : '')+
          '<code style="font-size:11px">'+esc(e.repo)+'</code>'+
          (e.stars ? '<span>★ '+fmtNum(e.stars)+'</span>' : '')+
          (e.pushedAt ? '<span>更新于 '+esc(e.pushedAt)+'</span>' : '')+
        '</div></div>'+
    '</div>'+
    shotsHtml+
    '<p class="desc">'+esc(e.description)+'</p>'+
    '<div class="kw">'+(e.keywords||[]).map(k=>'<i>'+esc(k)+'</i>').join("")+
      '<i>社区目录</i></div>'+
    '<div class="card-foot">'+stTxt+
      '<button class="tiny fav'+(fav?" on":"")+'" data-fav="'+attr(e.repo)+'" title="收藏">'+(fav?"♥ 已收藏":"♡ 收藏")+'</button>'+
      '<button class="tiny" data-regdetail="'+attr(e.repo)+'">详情</button>'+
      (inst
        ? '<button class="tiny" data-rupdate="'+attr(e.repo)+'">检查更新</button>'
        : '<button class="tiny primary" data-radd="'+attr(e.repo)+'" title="'+attr(instTitle)+'">'+instLabel+'</button>')+
    '</div>'+
  '</div>';
}

/* ---------------- 总渲染（v2.23：按三入口 tab 分区） ---------------- */
export function renderCards(){
  const local = (STATE.plugins||[]).filter(pass);
  const remote = (STATE.remotes||[]).filter(pass);
  // 社区目录（v2.11）：注册表条目，与本机收录源大小写去重后展示
  const regRepos = new Set((STATE.remotes||[]).map(r => String(r.rawName||"").toLowerCase()));
  const regAll = (REG.plugins||[]).filter(e => !regRepos.has(String(e.repo||"").toLowerCase()));
  const comm = regAll.filter(regPass);
  const q = $("#q").value.trim();
  let h = "";

  if(tab === "local"){
    // ---- 入口一：本机技能（管理自己的 Skills）
    h += '<div class="sec-title">本机插件 <span class="n">'+local.length+' 个 · 内容就在本市场里，装到 ~/.workbuddy/skills</span></div>';
    h += local.length ? '<div class="grid">'+local.map(cardLocal).join("")+'</div>'
                      : '<div class="empty">没有符合条件的本机插件。'+
                        '本机 skill 不在这里？编辑 market.config.json 收录后点「重新打包」。</div>';
  }

  if(tab === "curated"){
    // ---- 入口二：精选市场（经过收录审核的社区插件）
    let rsub = REG.plugins && REG.plugins.length
      ? (REG.stale ? REG.plugins.length+' 个收录 · 数据非最新' : REG.plugins.length+' 个收录') : '';
    if(REG.updatedAt) rsub += ' · 注册表 '+esc(REG.updatedAt);
    if(REG.source && REG.source !== "cache" && REG.source.indexOf("github.com") < 0)
      rsub += '（'+esc(REG.source)+'）';
    h += '<div class="sec-title">精选市场（社区目录） <span class="n">'+rsub+'</span></div>';
    h += comm.length ? '<div class="grid">'+comm.map(cardRegistry).join("")+'</div>'
                     : '<div class="empty">社区目录没有匹配的条目</div>';
  }

  if(tab === "explore"){
    // ---- 入口三：探索 GitHub（收录源 + 全网搜索，明确标注未审核来源）
    let sub = remote.length+' 个 · 由 ghpm 下载安装，联网可用';
    if(CATALOG && CATALOG.refreshedAt){
      sub += ' · 目录数据 '+esc(String(CATALOG.refreshedAt).slice(0,16).replace("T"," "))+
             (CATALOG_STALE ? '（已过期）' : '')+'（每日自动刷新）';
    }
    sub += ' <button class="tiny" data-crefresh="1">刷新目录</button>';
    h += '<div class="sec-title">GitHub 收录源 <span class="n">'+sub+'</span></div>';
    h += remote.length ? '<div class="grid">'+remote.map(cardRemote).join("")+'</div>'
                       : '<div class="empty">没有符合条件的 GitHub 源</div>';
    // 本地（含收录源）零匹配且关键词够长 → 兜底全网搜索（结果一律未审核）
    if(!remote.length && q.length >= 2){
      h += '<div class="sec-title">GitHub 全网搜索 <span class="n" id="ghState"></span></div>'+
           '<div class="grid" id="ghGrid"></div>';
    }
  }

  $("#content").innerHTML = h;
  if(tab === "explore" && !remote.length && q.length >= 2) ghEnsure(q);
}
