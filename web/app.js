const $ = s => document.querySelector(s);
let STATE = null, CATALOG = null, CATALOG_STALE = false, cat = "全部", filter = "all", jobs = {};
let GH = {q:null, items:null, state:"idle", error:""}, ghTimer = null;
let REG = {plugins:null, updatedAt:"", stale:false, source:"", installedRepos:{}};   // 社区注册表（v2.11）

const ICON = {"写作":"✍","开发工具":"⚙","自动化":"⟳","官方":"★","合集":"▣","测试":"⌘","设计":"◆","科研":"⚛","效率":"⚡","商业":"¥","安全":"🛡","未分类":"◇"};
const iconOf = c => ICON[c] || "◇";
const esc = s => String(s==null?"":s).replace(/[&<>"']/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));
const attr = s => String(s).replace(/"/g,"&quot;");
const fmtNum = n => n >= 10000 ? (n/10000).toFixed(1)+"w" : (n>=1000 ? (n/1000).toFixed(1)+"k" : String(n));
const mb = b => ((b||0)/1048576).toFixed(1)+" MB";

// 目录缓存里找一条收录源的实时元数据（大小写不敏感；失败记录也算命中）
function liveOf(repo){
  const c = CATALOG || {};
  const k = String(repo||"").toLowerCase();
  for(const key in (c.repos||{})) if(key.toLowerCase() === k) return c.repos[key];
  for(const key in (c.errors||{})) if(key.toLowerCase() === k) return {error:c.errors[key]};
  return null;
}

function toast(msg, bad){
  const t = $("#toast");
  t.textContent = msg;
  t.className = "toast show" + (bad ? " bad" : "");
  clearTimeout(t._t);
  t._t = setTimeout(()=>{ t.className = "toast" + (bad?" bad":""); }, 3400);
}

// 服务端注入的一次性口令。所有 /api/* 都要带上它，
// 否则本机任意网页都能替我们点「安装 / 卸载 / 清空回收站」。
const MARKET_TOKEN = (document.querySelector('meta[name="market-token"]') || {}).content || "";

async function api(path, body){
  const headers = {"X-Local-Market-Token": MARKET_TOKEN};
  if(body) headers["Content-Type"] = "application/json";
  const opt = {headers};
  if(body){ opt.method = "POST"; opt.body = JSON.stringify(body); }
  const r = await fetch(path, opt);
  let data = {};
  try { data = await r.json(); } catch(e){}
  if(r.status === 403) throw new Error("本机服务拒绝了这次请求（口令失效，刷新页面即可）");
  if(!r.ok || data.ok === false){
    const err = new Error(data.error || ("HTTP " + r.status));
    err.status = r.status; err.data = data;   // 409 漂移拦截等结构化错误要用
    throw err;
  }
  return data;
}

function confirmBox(title, html, yesLabel){
  return new Promise(resolve => {
    $("#cfmTitle").textContent = title;
    $("#cfmBody").innerHTML = html;
    $("#cfmYes").textContent = yesLabel || "确定";
    $("#cfmNo").style.display = "";
    $("#cfm").classList.add("show");
    const done = v => { $("#cfm").classList.remove("show"); resolve(v); };
    $("#cfmYes").onclick = () => done(true);
    $("#cfmNo").onclick = () => done(false);
    $("#cfm").onclick = e => { if(e.target.id === "cfm") done(false); };
  });
}

// 单按钮信息弹窗（v2.20）：注册表条目详情用 —— 只读展示，没有「取消」语义。
function infoBox(title, html){
  return new Promise(resolve => {
    $("#cfmTitle").textContent = title;
    $("#cfmBody").innerHTML = html;
    $("#cfmYes").textContent = "关闭";
    $("#cfmNo").style.display = "none";
    $("#cfm").classList.add("show");
    const done = v => { $("#cfm").classList.remove("show"); $("#cfmNo").style.display = ""; resolve(v); };
    $("#cfmYes").onclick = () => done(true);
    $("#cfmNo").onclick = () => done(false);
    $("#cfm").onclick = e => { if(e.target.id === "cfm") done(false); };
  });
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
function permRows(perms){
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
function permBlock(perms){
  const rows = permRows(perms);
  if(!rows)
    return '<div class="note">该条目未声明权限清单（协议 v0.3 起支持；哈希校验链不受影响）。</div>';
  return '<div class="grp"><h5>需要的权限</h5>'+rows+'</div>';
}

/* ---------------- 渲染 ---------------- */
function render(){
  const st = STATE;
  $("#mName").textContent = st.marketName || "本机插件市场";
  $("#mSub").innerHTML = '市场 ID <code>'+st.marketId+'</code> · '+st.stats.localPlugins+
    ' 个本机插件 / '+st.stats.localSkills+' 个 skill · '+st.stats.remoteSources+' 个 GitHub 源';
  $("#fRoot").textContent = st.root;
  $("#fWb").textContent = st.wbHome;

  const b = [];
  if(st.marketVersion) b.push('<span class="badge">v'+st.marketVersion+'</span>');
  b.push(st.registered
    ? '<span class="badge ok"><i class="dot"></i>已注册进 WorkBuddy</span>'
    : '<span class="badge warn"><i class="dot"></i>尚未注册</span>');
  b.push(st.manifestOk
    ? '<span class="badge ok"><i class="dot"></i>市场索引就绪</span>'
    : '<span class="badge bad"><i class="dot"></i>市场索引缺失</span>');
  b.push(st.ghpmOk
    ? '<span class="badge ok"><i class="dot"></i>ghpm 可用</span>'
    : '<span class="badge warn"><i class="dot"></i>ghpm 不可用</span>');
  b.push('<span class="badge">已装本机 skill '+st.stats.installedLocalSkills+'/'+st.stats.localSkills+'</span>');
  b.push('<span class="badge">本市场托管 '+st.stats.ownedSkills+' 个</span>');
  const vm = st.stats.verify || "auto";
  const vmText = vm === "strict" ? "校验档位 strict（全部精确读取）"
               : vm === "fast"   ? "校验档位 fast（状态用指纹，安装/卸载仍精确）"
               : "校验档位 auto（状态用指纹，安装/卸载精确）";
  b.push('<span class="badge'+(vm === "strict" ? ' warn' : '')+'">'+vmText+'</span>');
  $("#badges").innerHTML = b.join("");

  $("#btnTrash").textContent = "回收站" + (st.trash.count ? " ("+st.trash.count+")" : "");

  let hint = "";
  if(!st.registered){
    hint = '<div class="hint">点右上角 <b>「注册到 WorkBuddy」</b>，本市场就会出现在 WorkBuddy 自带的插件面板里，'+
           '之后在那边也能一键安装。注册只会往 <code>known_marketplaces.json</code> 加一条记录，先自动备份，可随时撤销。</div>';
  } else if(st.stats.ownedSkills === 0 && st.stats.localSkills > 0){
    hint = '<div class="hint">本机这 '+st.stats.localSkills+' 个 skill 都<b>不是本市场装的</b>（是别的途径装到你机器上的），'+
           '所以卸载不会动它们 —— 这是刻意的。把一个 skill 删掉、再从市场装回来，它才归本市场托管。</div>';
  }
  $("#hint").innerHTML = hint;

  const cats = ["全部"].concat(st.categories || []);
  $("#cats").innerHTML = cats.map(c =>
    '<div class="chip'+(c===cat?" on":"")+'" data-c="'+c+'">'+c+'</div>').join("");

  $("#btnReg").textContent = st.registered ? "撤销注册" : "注册到 WorkBuddy";
  $("#btnReg").className = st.registered ? "" : "primary";

  renderCards();
}

function pass(p){
  if(cat !== "全部" && p.category !== cat) return false;
  if(filter === "done" && !p.installed) return false;
  if(filter === "todo" && p.installed) return false;
  const q = $("#q").value.trim().toLowerCase();
  if(!q) return true;
  const hay = [p.name,p.rawName,p.description,p.category,(p.keywords||[]).join(" ")].join(" ").toLowerCase();
  return hay.includes(q);
}

function renderCards(){
  const st = STATE;
  const local = (st.plugins||[]).filter(pass);
  const remote = (st.remotes||[]).filter(pass);
  // 社区目录（v2.11）：注册表条目，与本机收录源大小写去重后展示
  const regRepos = new Set((st.remotes||[]).map(r => String(r.rawName||"").toLowerCase()));
  const regAll = (REG.plugins||[]).filter(e => !regRepos.has(String(e.repo||"").toLowerCase()));
  const comm = regAll.filter(regPass);
  let h = "";
  h += '<div class="sec-title">本机插件 <span class="n">'+local.length+' 个 · 内容就在本市场里，装到 ~/.workbuddy/skills</span></div>';
  h += local.length ? '<div class="grid">'+local.map(cardLocal).join("")+'</div>'
                    : '<div class="empty">没有符合条件的本机插件</div>';
  let sub = remote.length+' 个 · 由 ghpm 下载安装，联网可用';
  if(CATALOG && CATALOG.refreshedAt){
    sub += ' · 目录数据 '+esc(String(CATALOG.refreshedAt).slice(0,16).replace("T"," "))+
           (CATALOG_STALE ? '（已过期）' : '')+'（每日自动刷新）';
  }
  sub += ' <button class="tiny" data-crefresh="1">刷新目录</button>';
  h += '<div class="sec-title">GitHub 收录源 <span class="n">'+sub+'</span></div>';
  h += remote.length ? '<div class="grid">'+remote.map(cardRemote).join("")+'</div>'
                     : '<div class="empty">没有符合条件的 GitHub 源</div>';
  // 社区注册表区块（v2.11）：来源与数量如实展示，离线兜底要看得出来
  if(comm.length || (REG.plugins && REG.plugins.length)){
    let rsub = REG.plugins && REG.plugins.length
      ? (REG.stale ? REG.plugins.length+' 个收录 · 数据非最新' : REG.plugins.length+' 个收录') : '';
    if(REG.updatedAt) rsub += ' · 注册表 '+esc(REG.updatedAt);
    if(REG.source && REG.source !== "cache" && REG.source.indexOf("github.com") < 0)
      rsub += '（'+esc(REG.source)+'）';
    h += '<div class="sec-title">社区目录 <span class="n">'+rsub+'</span></div>';
    h += comm.length ? '<div class="grid">'+comm.map(cardRegistry).join("")+'</div>'
                     : '<div class="empty">社区目录没有匹配的条目</div>';
  }
  // 本地（含收录源）零匹配且关键词够长 → 社区目录已并入上方过滤，再兜底全网搜索
  const q = $("#q").value.trim();
  if(!local.length && !remote.length && q.length >= 2){
    h += '<div class="sec-title">GitHub 全网搜索 <span class="n" id="ghState"></span></div>'+
         '<div class="grid" id="ghGrid"></div>';
  }
  $("#content").innerHTML = h;
  if(!local.length && !remote.length && q.length >= 2) ghEnsure(q);
}

/* ---------------- 信任分级（v2.12） ----------------
   official = 官方收录 / reviewed = 社区精选（已人工审核）/ external = 未审核。
   徽标必须如实 —— 搜索到不等于官方认可。 */
function trustBadge(t){
  return t === "official" ? '<span class="tag ok">✓ 官方</span>'
       : t === "reviewed" ? '<span class="tag ok">✓ 已审核</span>'
       : '<span class="tag warn">! 未审核</span>';
}
function regTrustOf(repo){
  const e = (REG.plugins||[]).find(p => p.repo === repo);
  return e ? (e.trust || "reviewed") : "external";
}

/* ---------------- GitHub 全网搜索（v2.10） ---------------- */
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
    '<div><span class="toggle" data-toggle="'+p.id+'">▾ 看 '+p.skills.length+' 个 skill 的状态</span></div>'+
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

/* ---------------- 社区注册表（v2.11） ---------------- */
function regPass(e){
  if(cat !== "全部" && e.category !== cat) return false;
  if(filter === "done" && !isRegInstalled(e.repo)) return false;
  if(filter === "todo" && isRegInstalled(e.repo)) return false;
  const q = $("#q").value.trim().toLowerCase();
  if(!q) return true;
  const hay = [e.displayName,e.displayNameEn,e.repo,e.description,e.category,(e.keywords||[]).join(" ")]
    .join(" ").toLowerCase();
  return hay.includes(q);
}

function isRegInstalled(repo){
  return !!(REG.installedRepos && REG.installedRepos[repo]);
}

function cardRegistry(e){
  const inst = isRegInstalled(e.repo);
  const info = inst ? REG.installedRepos[e.repo] : null;
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
  return '<div class="card">'+
    '<div class="card-head">'+
      '<div class="icon">'+iconOf(e.category)+'</div>'+
      '<div style="flex:1"><h3>'+title+'</h3>'+
        '<div class="meta">'+
          '<span>'+esc(e.category)+'</span>'+
          trustBadge(e.trust || "reviewed")+
          (e.license ? '<span>'+esc(e.license)+'</span>' : '')+
          '<code style="font-size:11px">'+esc(e.repo)+'</code>'+
          (e.stars ? '<span>★ '+fmtNum(e.stars)+'</span>' : '')+
          (e.pushedAt ? '<span>更新于 '+esc(e.pushedAt)+'</span>' : '')+
        '</div></div>'+
    '</div>'+
    '<p class="desc">'+esc(e.description)+'</p>'+
    '<div class="kw">'+(e.keywords||[]).map(k=>'<i>'+esc(k)+'</i>').join("")+
      '<i>社区目录</i></div>'+
    '<div class="card-foot">'+stTxt+
      '<button class="tiny" data-regdetail="'+attr(e.repo)+'">详情</button>'+
      (inst
        ? '<button class="tiny" data-rupdate="'+attr(e.repo)+'">检查更新</button>'
        : '<button class="tiny primary" data-radd="'+attr(e.repo)+'">一键安装</button>')+
    '</div>'+
  '</div>';
}

/* ---------------- 注册表条目详情（v2.20） ----------------
   安装之前先了解插件：来源与信任、不可变产物（对账入口）、
   兼容性声明、权限声明 —— 全部来自注册表条目，如实展示。 */
function regDetailHtml(e){
  const href = e.homepage && String(e.homepage).indexOf("https://") === 0
    ? e.homepage : "https://github.com/"+e.repo;
  let h = '<div class="grp"><h5>来源与信任</h5><ul>'+
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

/* ---------------- 交互 ---------------- */
document.addEventListener("click", async (e) => {
  const t = e.target.closest("[data-c],[data-f],[data-toggle],[data-install],[data-uninstall],[data-radd],[data-rupdate],[data-regdetail],[data-path],[data-crefresh]");
  if(!t) return;

  if(t.dataset.regdetail){
    const entry = (REG.plugins||[]).find(p => p.repo === t.dataset.regdetail);
    if(!entry) return toast("注册表里找不到这个条目", true);
    await infoBox(entry.displayName || entry.repo, regDetailHtml(entry));
    return;
  }

  if(t.dataset.c !== undefined && t.classList.contains("chip")){ cat = t.dataset.c; render(); return; }
  if(t.dataset.f){
    filter = t.dataset.f;
    document.querySelectorAll("#filters .chip").forEach(c=>c.classList.toggle("on", c.dataset.f===filter));
    renderCards(); return;
  }
  if(t.dataset.toggle){
    const el = $("#sk-"+t.dataset.toggle);
    const open = el.classList.toggle("open");
    t.textContent = open ? "▴ 收起" : "▾ 看全部 skill 的状态";
    return;
  }

  if(t.dataset.install){
    const id = t.dataset.install, mode = t.dataset.mode || "missing";
    if(mode === "update"){
      const ok = await confirmBox("更新「"+id+"」？",
        '<div class="note">会覆盖本市场装过、但之后被改动过的那几个 skill。<br>'+
        '旧的那份先移进回收站，可以恢复。<br>'+
        '<b>不是本市场装的 skill 一律不碰。</b></div>', "更新");
      if(!ok) return;
    }
    t.disabled = true;
    try{
      const r = await api("/api/install", {id, mode});
      const parts = [];
      if(r.added.length) parts.push("新增 "+r.added.length+" 个");
      if(r.updated.length) parts.push("更新 "+r.updated.length+" 个");
      if(r.skipped.length) parts.push("跳过 "+r.skipped.length+" 个已有");
      if(r.foreign.length) parts.push("保留 "+r.foreign.length+" 个非本市场");
      if(r.failed.length) parts.push("失败 "+r.failed.length+" 个");
      toast(parts.length ? parts.join("，") : "没有需要处理的 skill", r.failed.length > 0);
      await refresh();
    }catch(err){ toast(err.message, true); t.disabled = false; }
    return;
  }

  if(t.dataset.uninstall){
    const id = t.dataset.uninstall;
    let plan;
    try { plan = await api("/api/uninstall", {id, dryRun:true}); }
    catch(err){ return toast(err.message, true); }

    const groups = [];
    if(plan.removable.length) groups.push(
      '<div class="grp"><h5>将移入回收站（'+plan.removable.length+'）</h5><ul>'+
      plan.removable.map(s=>'<li><code>'+esc(s)+'</code></li>').join("")+'</ul></div>');
    if(plan.modified.length) groups.push(
      '<div class="grp"><h5>被改过，将保留（'+plan.modified.length+'）</h5><ul>'+
      plan.modified.map(s=>'<li><code>'+esc(s)+'</code></li>').join("")+'</ul></div>');
    if(plan.untouched.length) groups.push(
      '<div class="grp"><h5>不是本市场装的，不会动（'+plan.untouched.length+'）</h5><ul>'+
      plan.untouched.map(s=>'<li><code>'+esc(s)+'</code></li>').join("")+'</ul></div>');

    let body = groups.join("");
    if(!plan.removable.length){
      body += '<div class="note">这个插件当前没有「可安全卸载」的 skill，卸载不会有任何改动。</div>';
    }
    body += '<div class="note">移走的东西都在市场的 <code>.trash</code> 里，可以手工恢复。</div>';
    const ok = await confirmBox("卸载「"+id+"」", body, "卸载");
    if(!ok) return;
    t.disabled = true;
    try{
      const r = await api("/api/uninstall", {id});
      toast(r.moved.length ? ("已移入回收站："+r.moved.join("、")) : "没有需要移除的 skill");
      await refresh();
    }catch(err){ toast(err.message, true); t.disabled = false; }
    return;
  }

  if(t.dataset.radd || t.dataset.rupdate){
    const repo = t.dataset.radd || t.dataset.rupdate;
    const isAdd = !!t.dataset.radd;
    let allowNs = false;
    if(isAdd){
      const known = (STATE.remotes||[]).some(r => r.rawName === repo);
      const regEntry = (REG.plugins||[]).find(p => p.repo === repo);
      const regKnown = !!regEntry;
      // v2.16：注册表条目带成套 artifact 字段 → 走不可变包安装链路
      const usePkg = !!(regEntry && regEntry.packageUrl && regEntry.packageHash);
      const trust = regEntry ? (regEntry.trust || "external") : "external";
      const trustNote = trust === "official"
        ? '官方收录'
        : regKnown ? '社区精选（已人工审核收录）' : '<b>未审核</b>（搜索结果，未经收录审核）';
      let routeNote = '安装走 ghpm，自带事务与回滚。';
      if (usePkg){
        routeNote = '安装走<b>不可变产物</b>：下载后先做 SHA-256 供应链校验'
          + '（与收录审核时固定的哈希比对，不符即整包拒绝），再进事务安装。';
      }
      const note = known
        ? '<div class="note">会联网下载，并写入 <code>~/.workbuddy/skills</code>。<br>'+routeNote+'</div>'
        : '<div class="note">来源：'+trustNote+'。会联网下载并写入 <code>~/.workbuddy/skills</code>，'+routeNote+'</div>';
      // v2.20 风险预览：包声明的权限在**下载之前**就摆出来 ——
      // 数据来自注册表条目（CI 从打包 manifest 固化回写）。
      if (usePkg) note += permBlock(regEntry.permissions);
      if(!regKnown){
        // 供应链收紧（v2.12）：非收录仓库默认只装符合 Skill 协议的内容，
        // 兼容模式必须在这里显式勾选放行。
        note += '<label style="display:flex;gap:6px;align-items:flex-start;margin-top:8px;cursor:pointer">'+
          '<input type="checkbox" id="cbCompat" style="margin-top:3px">'+
          '<span>兼容模式：允许非标准 Skill 仓库（内容未经协议校验，<b>风险自负</b>）</span></label>';
      }
      const ok = await confirmBox("从 GitHub 安装 "+repo+"？", note, "安装");
      if(!ok) return;
      allowNs = !regKnown && !!($("#cbCompat") && $("#cbCompat").checked);
    }
    try{
      const ep = isAdd ? (usePkg ? "/api/registry/install" : "/api/remote/add")
                       : "/api/remote/update";
      const body = isAdd ? (usePkg ? {repo} : {repo, allowNonSkill: allowNs})
                         : {repo};
      const r = await api(ep, body);
      watchJob(r.jobId, (isAdd?"安装 ":"更新 ")+repo);
    }catch(err){
      // 409：注册表收录仓库的上游已前移（供应链固定校验，v2.12）。
      // 把差异摆清楚让用户决定 —— 继续装的是当前版本，不是审核那一份。
      if(isAdd && err.status === 409 && err.data && err.data.drift){
        const d = err.data.drift;
        const ok2 = await confirmBox("上游已前移：" + repo,
          '<div class="note">审核时固定在 <code>'+esc(String(d.sourceCommit).slice(0,12))+'…</code>，'+
          '上游已推进到 <code>'+esc(String(d.latestSha).slice(0,12))+'…</code>。<br>'+
          '继续安装装到的是<b>当前版本</b>（内容可能与收录审核时不同）。</div>', "仍要安装");
        if(!ok2) return;
        try{
          const r2 = await api("/api/remote/add", {repo, allowNonSkill: allowNs, force: true});
          watchJob(r2.jobId, "安装 " + repo);
        }catch(e2){ toast(e2.message, true); }
      } else { toast(err.message, true); }
    }
    return;
  }

  if(t.dataset.crefresh){
    t.disabled = true;
    try{
      const r = await api("/api/catalog/refresh", {});
      watchJob(r.jobId, "刷新 GitHub 目录");
    }catch(err){ toast(err.message, true); t.disabled = false; }
    return;
  }

  if(t.dataset.path){
    try{ await api("/api/open/path", {target: "root"}); }catch(err){ toast(err.message, true); }
    return;
  }
});

document.addEventListener("input", (e) => { if(e.target.id === "q") renderCards(); });

$("#btnSync").onclick = async (e) => {
  e.target.disabled = true;
  try{
    const r = (await api("/api/sync", {})).report;
    let msg = "已重新打包："+r.plugins+" 个插件 / "+r.skills+" 个 skill";
    msg += r.copiedFiles ? ("，更新 "+r.copiedFiles+" 个文件") : "，内容无变化";
    if(r.skippedLinks){
      msg += "。注意：跳过了 "+r.skippedLinks+" 个符号链接 / junction（不跟随）";
    }
    if(r.missing && r.missing.length){
      msg += "（"+r.missing.length+" 个源不在本机，沿用市场里的历史副本）";
    }
    toast(msg);
    await refresh();
  }catch(err){ toast(err.message, true); }
  finally{ e.target.disabled = false; }
};

$("#btnReg").onclick = async (e) => {
  e.target.disabled = true;
  try{
    if(STATE.registered){
      const ok = await confirmBox("撤销注册？",
        '<div class="note">只是把本市场从 <code>known_marketplaces.json</code> 里移除，'+
        '插件文件和已装的 skill 都不动。</div>', "撤销注册");
      if(!ok){ e.target.disabled = false; return; }
      await api("/api/unregister", {});
      toast("已撤销注册");
    } else {
      const r = await api("/api/register", {});
      toast(r.changed ? "注册完成 —— 打开 WorkBuddy 的插件面板就能看到本市场" : "已是注册状态");
    }
    await refresh();
  }catch(err){ toast(err.message, true); }
  finally{ e.target.disabled = false; }
};

$("#btnTrash").onclick = async () => {
  const t = STATE.trash, pol = t.policy || {};
  const html = '<div class="grp"><h5>当前回收站</h5><ul>'+
    '<li>共 '+t.count+' 项，'+mb(t.bytes)+'</li>'+
    '<li>自动清理阈值：超过 '+(pol.max_age_days||0)+' 天，或总量超过 '+mb(pol.max_bytes||0)+'</li>'+
    '</ul></div>'+
    '<div class="note">回收站里是卸载 / 覆盖时移走的 skill 目录，可以手工恢复。<br>'+
    '位置：<code>'+esc(STATE.root)+'\\.trash</code><br>'+
    '清空只影响这个目录，不会碰 <code>~/.workbuddy/skills</code>。</div>';
  const ok = await confirmBox("回收站", html, "清空回收站");
  if(!ok) return;
  try{
    const r = await api("/api/trash/purge", {});
    toast("已清空回收站，释放 "+mb(r.result.freed));
    await refresh();
  }catch(err){ toast(err.message, true); }
};

$("#btnLog").onclick = async () => { $("#drawer").classList.add("show"); await loadLog(); };
$("#btnLogClose").onclick = () => $("#drawer").classList.remove("show");

async function loadLog(){
  try{
    const r = await api("/api/log");
    const items = r.items || [];
    $("#logList").innerHTML = items.length ? items.map(ev =>
      '<div class="ev"><span class="t">'+(ev.at||"").slice(11,19)+'</span>'+
      '<span class="lv '+esc(ev.level||"info")+'">'+esc(ev.level||"info")+'</span>'+
      '<span class="d">'+esc(ev.event||"")+(ev.detail?' · '+esc(ev.detail):'')+'</span></div>'
    ).join("") : '<div class="empty">暂无事件</div>';
  }catch(err){ toast(err.message, true); }
}

function watchJob(jid, title){
  $("#veil").classList.add("show");
  $("#jobTitle").textContent = title;
  $("#jobBar").style.width = "0%";
  $("#jobBar").style.background = "var(--accent)";
  $("#jobLabel").textContent = "准备中…";
  $("#jobOut").textContent = "";
  $("#jobClose").disabled = true;
  $("#jobClose").onclick = () => { $("#veil").classList.remove("show"); refresh(); };

  jobs[jid] = setInterval(async () => {
    let j;
    try{ j = await api("/api/job/"+jid); }catch(e){ return; }
    $("#jobBar").style.width = (j.percent||0)+"%";
    $("#jobLabel").textContent = j.label || "";
    $("#jobOut").textContent = (j.lines||[]).slice(-60).join("\n");
    $("#jobOut").scrollTop = $("#jobOut").scrollHeight;
    if(j.status === "done"){
      clearInterval(jobs[jid]); delete jobs[jid];
      $("#jobClose").disabled = false;
      $("#jobLabel").textContent = (j.ok ? "✓ " : "✗ ") + (j.label || "");
      $("#jobBar").style.width = "100%";
      $("#jobBar").style.background = j.ok ? "var(--ok)" : "var(--bad)";
      toast(j.ok ? (title+" 完成") : (title+" 失败，看输出"), !j.ok);
      await refresh();
    }
  }, 700);
}

async function refresh(){
  try{ STATE = await api("/api/state"); }
  catch(err){ toast("读取状态失败："+err.message, true); return; }
  try{
    const c = await api("/api/catalog");
    CATALOG = c.catalog || {}; CATALOG_STALE = !!c.stale;
  }catch(e){ CATALOG = null; CATALOG_STALE = false; }   // 目录缓存失败不挡主界面
  try{
    const g = await api("/api/registry");
    REG = {plugins: g.plugins || [], updatedAt: g.updatedAt || "",
           stale: !!g.stale, source: g.source || "",
           installedRepos: g.installedRepos || {}};   // 社区目录失败也不挡主界面
  }catch(e){ REG = {plugins:null, updatedAt:"", stale:false, source:"", installedRepos:{}}; }
  render();
}

refresh();
setInterval(() => { if($("#drawer").classList.contains("show")) loadLog(); }, 5000);
