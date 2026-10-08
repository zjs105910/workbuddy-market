/* 前端入口（v2.22 拆分）：总渲染、事件委托、主刷新、启动引导。
   index.html 以 <script type="module"> 加载本文件 —— module 脚本
   默认 defer，DOM 已就绪，与旧的 body 末尾脚本时序一致。 */

import { STATE, REG, cat, setState, setCatalog, setReg, setCat, setFilter } from "./state.js";
import { api } from "./api.js";
import { $, esc, mb, toast, confirmBox, infoBox } from "./utils.js";
import { renderCards } from "./plugins.js";
import { regUpdatable, showUpdateCenter } from "./update.js";
import { regDetailHtml } from "./details.js";
import { isFav } from "./favorites.js";
import { bindRefresh } from "./jobs.js";
import { handleDataAction } from "./install.js";

/* ---------------- 顶部与骨架渲染 ---------------- */
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

  // 更新中心（v2.21）：有可更新插件时才露出，点击弹出聚合视图。
  const updCount = regUpdatable().length;
  const bu = $("#btnUpdate");
  if(bu){ bu.style.display = updCount ? "" : "none"; bu.textContent = "更新中心 ("+updCount+")"; }

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

/* ---------------- 主刷新 ---------------- */
async function refresh(){
  try{ setState(await api("/api/state")); }
  catch(err){ toast("读取状态失败："+err.message, true); return; }
  try{
    const c = await api("/api/catalog");
    setCatalog(c.catalog || {}, !!c.stale);
  }catch(e){ setCatalog(null, false); }   // 目录缓存失败不挡主界面
  try{
    const g = await api("/api/registry");
    setReg({plugins: g.plugins || [], updatedAt: g.updatedAt || "",
            stale: !!g.stale, source: g.source || "",
            installedRepos: g.installedRepos || {},
            favorites: g.favorites || []});   // 社区目录失败也不挡主界面
  }catch(e){ setReg({plugins:null, updatedAt:"", stale:false, source:"", installedRepos:{}, favorites:[]}); }
  render();
}

/* ---------------- 事件流抽屉 ---------------- */
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

/* ---------------- 事件委托（点击） ---------------- */
document.addEventListener("click", async (e) => {
  const t = e.target.closest("[data-c],[data-f],[data-toggle],[data-install],[data-uninstall],[data-radd],[data-rupdate],[data-regdetail],[data-path],[data-crefresh],[data-fav],[data-shot],[data-updatecenter]");
  if(!t) return;

  if(t.dataset.fav){
    // 收藏 / 取消收藏（v2.21）：本机持久化，Local-first。
    const repo = t.dataset.fav;
    const on = !isFav(repo);
    try{
      const r = await api("/api/favorites", {repo, on});
      setReg({...REG, favorites: r.favorites || []});
      toast((on?"已收藏 ":"已取消收藏 ")+repo);
      renderCards();
    }catch(err){ toast(err.message, true); }
    return;
  }

  if(t.dataset.shot){
    // 点击截图在新标签页打开原图（只收 GitHub 系域名的 https，安全）。
    try{ window.open(t.dataset.shot, "_blank", "noopener"); }
    catch(err){ toast("无法打开截图", true); }
    return;
  }

  if(t.dataset.updatecenter){
    await showUpdateCenter();
    return;
  }

  if(t.dataset.regdetail){
    const entry = (REG.plugins||[]).find(p => p.repo === t.dataset.regdetail);
    if(!entry) return toast("注册表里找不到这个条目", true);
    await infoBox(entry.displayName || entry.repo, regDetailHtml(entry));
    return;
  }

  if(t.dataset.c !== undefined && t.classList.contains("chip")){ setCat(t.dataset.c); render(); return; }
  if(t.dataset.f){
    setFilter(t.dataset.f);
    document.querySelectorAll("#filters .chip").forEach(c=>c.classList.toggle("on", c.dataset.f===t.dataset.f));
    renderCards(); return;
  }
  if(t.dataset.toggle){
    const el = $("#sk-"+t.dataset.toggle);
    const open = el.classList.toggle("open");
    t.textContent = open ? "▴ 收起" : "▾ 看全部 skill 的状态";
    return;
  }

  if(t.dataset.path){
    try{ await api("/api/open/path", {target: "root"}); }catch(err){ toast(err.message, true); }
    return;
  }

  // 安装 / 卸载 / 远程装更 / 目录刷新 → install.js
  if(await handleDataAction(t)) return;
});

document.addEventListener("input", (e) => { if(e.target.id === "q") renderCards(); });

/* ---------------- 顶部按钮 ---------------- */
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

$("#btnUpdate").onclick = async () => { await showUpdateCenter(); };

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

/* ---------------- 启动 ---------------- */
bindRefresh(refresh);
refresh();
setInterval(() => { if($("#drawer").classList.contains("show")) loadLog(); }, 5000);
