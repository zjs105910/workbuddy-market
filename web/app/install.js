/* 安装 / 卸载 / 远程装更 / 目录刷新 的动作分支（v2.22 拆分）。
   由 main.js 的点击委托分发进来：命中本模块管辖的 data-* 就处理并返回 true。
   供应链确认弹窗（trust 预览、兼容模式勾选、409 漂移放行）全部保留原语义。 */

import { STATE, REG } from "./state.js";
import { api } from "./api.js";
import { $, esc, toast, confirmBox } from "./utils.js";
import { permBlock } from "./trust.js";
import { watchJob, refreshNow } from "./jobs.js";

export async function handleDataAction(t){
  /* ---- 本机插件：补齐 / 更新 ---- */
  if(t.dataset.install){
    const id = t.dataset.install, mode = t.dataset.mode || "missing";
    if(mode === "update"){
      const ok = await confirmBox("更新「"+id+"」？",
        '<div class="note">会覆盖本市场装过、但之后被改动过的那几个 skill。<br>'+
        '旧的那份先移进回收站，可以恢复。<br>'+
        '<b>不是本市场装的 skill 一律不碰。</b></div>', "更新");
      if(!ok) return true;
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
      refreshNow();
    }catch(err){ toast(err.message, true); t.disabled = false; }
    return true;
  }

  /* ---- 本机插件：卸载（先 dryRun 出计划再确认） ---- */
  if(t.dataset.uninstall){
    const id = t.dataset.uninstall;
    let plan;
    try { plan = await api("/api/uninstall", {id, dryRun:true}); }
    catch(err){ toast(err.message, true); return true; }

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
    if(!ok) return true;
    t.disabled = true;
    try{
      const r = await api("/api/uninstall", {id});
      toast(r.moved.length ? ("已移入回收站："+r.moved.join("、")) : "没有需要移除的 skill");
      refreshNow();
    }catch(err){ toast(err.message, true); t.disabled = false; }
    return true;
  }

  /* ---- 远程：一键安装 / 检查更新（含不可变产物链路与 409 漂移放行） ---- */
  if(t.dataset.radd || t.dataset.rupdate){
    // 若从「更新中心」弹窗里点更新，先关掉信息弹窗再走更新确认。
    if($("#cfmNo").style.display === "none") $("#cfm").classList.remove("show");
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
      if(!ok) return true;
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
        if(!ok2) return true;
        try{
          const r2 = await api("/api/remote/add", {repo, allowNonSkill: allowNs, force: true});
          watchJob(r2.jobId, "安装 " + repo);
        }catch(e2){ toast(e2.message, true); }
      } else { toast(err.message, true); }
    }
    return true;
  }

  /* ---- GitHub 目录缓存刷新 ---- */
  if(t.dataset.crefresh){
    t.disabled = true;
    try{
      const r = await api("/api/catalog/refresh", {});
      watchJob(r.jobId, "刷新 GitHub 目录");
    }catch(err){ toast(err.message, true); t.disabled = false; }
    return true;
  }

  return false;
}
