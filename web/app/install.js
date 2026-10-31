/* 安装 / 卸载 / 远程装更 / 目录刷新 的动作分支（v2.22 拆分）。
   由 main.js 的点击委托分发进来：命中本模块管辖的 data-* 就处理并返回 true。
   供应链确认弹窗（trust 预览、兼容模式勾选、409 漂移放行）全部保留原语义。 */

import { STATE, REG } from "./state.js";
import { api, apiUpload } from "./api.js";
import { $, esc, toast, confirmBox, errorBox } from "./utils.js";
import { permBlock } from "./trust.js";
import { regUpdatable } from "./update.js";
import { watchJob, refreshNow } from "./jobs.js";

/* ---- 离线导入（v2.39）：上传 zip → 风险预览 → 显式确认 → 事务安装 ----
   浏览器拿不到本地路径，文件选择器的 File 对象直接二进制上传给本机服务；
   内容安全（zip 防线 / verify / 哈希钉死）全在服务端，前端只如实展示
   预览并把「未经收录审核」的确认做实 —— 确认按钮文案按 pinned 区分。 */
export async function offlineImportFile(file, opts){
  const meta = {repo: (opts && opts.repo) || ""};
  let pv;
  try{
    pv = await apiUpload("/api/import/upload", file, meta);
  }catch(err){
    await errorBox("离线导入：读取安装包失败", err);
    return;
  }
  await confirmAndCommit(pv);
}

async function confirmAndCommit(pv){
  const granted = ((pv.risk && pv.risk.items) || []).filter(it => it.granted);
  const skillsHtml = (pv.skills || []).map(s => '<code>'+esc(s)+'</code>').join("、");
  let html =
    '<div class="note"><b>'+esc(pv.name)+'</b>（'+
    (pv.kind === "package" ? "Market Package" : "原始仓库 zip，已按 Skill 协议自动打包")+
    '）<br>包含 skill：'+ (skillsHtml || "（无）") +'<br>'+
    (pv.pinned
      ? '✓ 与收录审核固定的产物哈希一致（packageHash 校验通过）'
      : '<b>未经收录审核</b>：包内容完整性已逐文件 SHA-256 校验，'+
        '但<b>来源是否可信请自行判断</b>。')+
    '</div>';
  if(granted.length){
    html += '<div class="grp"><h5>包声明的权限（'+granted.length+'）</h5><ul>'+
      granted.map(it => '<li><code>'+esc(it.label)+'</code>'+
        (it.scope ? '（'+esc(it.scope)+'）' : '')+'</li>').join("")+'</ul></div>';
  } else {
    html += '<div class="note">包未声明文件系统 / 网络 / Shell 等敏感权限。</div>';
  }
  html += '<div class="note">安装走两阶段事务（可恢复）；装完在「本机技能 → 社区安装」可卸载。</div>';
  const ok = await confirmBox("确认安装这个离线包？", html,
    pv.pinned ? "安装" : "我已确认来源，安装");
  if(!ok) return;
  try{
    const r = await api("/api/import/commit", {stagingId: pv.stagingId, confirmed: true});
    const parts = [];
    if(r.added && r.added.length) parts.push("新增 "+r.added.length+" 个");
    if(r.updated && r.updated.length) parts.push("更新 "+r.updated.length+" 个");
    if(r.skipped && r.skipped.length) parts.push("跳过 "+r.skipped.length+" 个已有");
    if(r.foreign && r.foreign.length) parts.push("保留 "+r.foreign.length+" 个非本市场");
    if(r.failed && r.failed.length) parts.push("失败 "+r.failed.length+" 个");
    toast(parts.length ? "导入完成："+parts.join("，") : "导入完成",
          (r.failed || []).length > 0);
    refreshNow();
  }catch(err){
    await errorBox("离线导入失败", err);
  }
}

export async function handleDataAction(t){
  /* ---- 更新中心：全部更新（v2.26，一键批量） ---- */
  if(t.dataset.rupdateAll){
    // 从更新中心弹窗里点出来的 —— 先关掉弹窗再启动任务
    if($("#cfmNo").style.display === "none") $("#cfm").classList.remove("show");
    const list = regUpdatable();
    if(!list.length){ toast("没有可更新项"); return true; }
    let started = 0, firstJob = null;
    for(const u of list){
      try{
        const r = await api("/api/remote/update", {repo: u.repo});
        started++;
        if(!firstJob) firstJob = r.jobId;
      }catch(err){
        toast(u.repo + " 更新启动失败：" + err.message, true);
      }
    }
    if(started){
      toast("已开始 " + started + " 个更新任务（并发上限 4，进度见任务弹窗与事件流）");
      if(firstJob) watchJob(firstJob, "批量更新");
    }
    return true;
  }

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
    }catch(err){
      // v2.24：结构化错误弹窗（重试按钮原样再点一次同一动作）
      const act = await errorBox("安装「"+id+"」失败", err, () => t.click());
      if(act === "retry"){ t.disabled = true; }
    }
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
    }catch(err){
      const act = await errorBox("卸载「"+id+"」失败", err, () => t.click());
      if(act === "retry"){ t.disabled = true; }
    }
    return true;
  }

  /* ---- 精选市场：离线安装（v2.38 路径粘贴 / v2.39 文件选择）----
     本机连不上 GitHub 时：把收录条目的固定产物 zip 弄到这台电脑上，
     选文件或粘贴路径导入。选文件走 /api/import/upload（上传时带 repo
     上下文，服务端仍与钉死的 packageHash 比对，不符整包拒绝）；粘贴
     路径走 /api/registry/install-offline（同一条严格链）。 */
  if(t.dataset.roffline){
    const repo = t.dataset.roffline;
    const ok = await confirmBox("离线安装 "+repo+"？",
      '<div class="note">本机连不上 GitHub 也能装：在<b>能联网的设备</b>（手机热点 / '+
      '镜像站都行）下载这个插件收录时的<b>固定产物 zip</b>（「详情」里的产物链接），'+
      '传到这台电脑后，二选一：<br>'+
      '① 点「选择 zip 文件」直接选中（推荐）：<br>'+
      '<input id="offFile" type="file" accept=".zip" style="margin-top:6px"><br>'+
      '② 或粘贴 zip 的完整路径：<br>'+
      '<input id="offZip" type="text" placeholder="粘贴 zip 的完整路径，例如 C:\\下载\\plugin-1.0.0.zip" '+
      'style="width:100%;margin-top:6px;box-sizing:border-box"><br>'+
      '小技巧：资源管理器里按住 <b>Shift</b> 再右键 zip → 「复制文件地址」，直接粘贴。<br>'+
      '<b>校验不会打折</b>：两种方式都会与收录审核固定的 SHA-256 比对，不是那一份就整包拒绝。</div>',
      "下一步");
    if(!ok) return true;
    const f = $("#offFile") && $("#offFile").files && $("#offFile").files[0];
    if(f){
      await offlineImportFile(f, {repo});
      return true;
    }
    const zp = (($("#offZip") && $("#offZip").value) || "").trim().replace(/^"+|"+$/g, "");
    if(!zp){ toast("没有选择文件，也没有填写 zip 路径"); return true; }
    try{
      const r = await api("/api/registry/install-offline", {repo, zipPath: zp});
      watchJob(r.jobId, "离线安装 " + repo);
    }catch(err){
      const act = await errorBox("离线安装 "+repo+" 失败", err, () => t.click());
      if(act === "retry"){ /* 重试按钮会原样再点一次「离线安装」 */ }
    }
    return true;
  }

  /* ---- 远程：一键安装 / 检查更新（含不可变产物链路与 409 漂移放行） ---- */
  if(t.dataset.radd || t.dataset.rupdate){
    // 若从「更新中心」弹窗里点更新，先关掉信息弹窗再走更新确认。
    if($("#cfmNo").style.display === "none") $("#cfm").classList.remove("show");
    const repo = t.dataset.radd || t.dataset.rupdate;
    const isAdd = !!t.dataset.radd;
    let allowNs = false;
    // 2026-10-14 用户实测 P0 修复（二）：这四条判定原先缩在 if(isAdd) 块内，
    // 而块外的路由选择（ep/body）引用 usePkg —— 块级 const 出了块即
    // ReferenceError，被下方 try/catch 吞掉后转 errorBox，而 errorBox 又
    // 不显示（见 utils.js 的修复三）→ 用户点完「安装」界面零反应、零日志。
    // 提升到分支级作用域，安装 / 更新两条路径都看得见。
    const known = (STATE.remotes||[]).some(r => r.rawName === repo);
    const regEntry = (REG.plugins||[]).find(p => p.repo === repo);
    const regKnown = !!regEntry;
    // v2.16：注册表条目带成套 artifact 字段 → 走不可变包安装链路
    const usePkg = !!(regEntry && regEntry.packageUrl && regEntry.packageHash);
    if(isAdd){
      // v2.23 fail-closed：信任说明以条目真实 trust 为准（缺失/未知 = 未审核），
      // 不再用「在注册表里」反推「已人工审核」。
      const trust = regEntry ? (regEntry.trust || "external") : "external";
      const trustNote = trust === "official"
        ? '官方收录'
        : trust === "reviewed" ? '社区精选（已人工审核收录）'
        : '<b>未审核</b>（' + (regKnown ? '收录未审核或信任级别未知' : '搜索结果，未经收录审核') + '）';
      let routeNote = '安装走 ghpm，自带事务与回滚。<b>卸载提示：</b>此来源的技能'
        + '不由本市场的卸载管理（避免误删），移除时请用命令 <code>ghpm remove 项目名</code>。';
      if (usePkg){
        routeNote = '安装走<b>不可变产物</b>：下载后先做 SHA-256 供应链校验'
          + '（与收录审核时固定的哈希比对，不符即整包拒绝），再进事务安装。'
          + '<b>卸载提示：</b>此来源的技能不由本市场的卸载管理（避免误删），'
          + '移除时请用命令 <code>ghpm remove 项目名</code>。';
      } else if (regKnown){
        // v2.35 NEXT_STEPS 任务5：收录在册但**没有固定产物**的条目（14 个
        // pkg=N 条目）——安装前就把「为什么走 ghpm、代价是什么」说清，
        // 与 artifact.install_from_entry 的 ConfigError 人话同口径
        // （绝不静默降级，也绝不事后才说）。
        routeNote = '此收录条目<b>没有固定产物</b>（缺 packageUrl + packageHash）→ '
          + '走 <b>ghpm 源码路线</b>：联网下载<b>当前上游版本</b>，ghpm 自带事务与回滚，'
          + '但<b>无法逐包 SHA-256 对账</b>（装的不一定是收录审核那一份）。'
          + '<b>卸载提示：</b>移除时请用命令 <code>ghpm remove 项目名</code>。';
      }
      // 2026-10-14 用户实测 P0 修复：这里原是 const，随后 135/139 两行
      // `note +=`（ES Modules 恒为严格模式）直接抛
      // 「Assignment to constant variable」——点击处理器静默死亡，
      // 确认弹窗不出现、安装任务不创建（复现与证据见审计报告）。
      // 所有走 data-radd 的安装（GitHub 搜索结果 / 注册表卡片）全中招。
      let note = known
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
      } else {
        // v2.24：非 409 的失败走结构化错误弹窗
        await errorBox((isAdd?"安装 ":"更新 ")+repo+" 失败", err);
      }
    }
    return true;
  }

  /* ---- ghpm 源码链：移除（v2.35 用户实测二修）----
     社区安装分区里 via=ghpm 的卡片用。这些技能的所有权不在本市场（ghpm
     才是管理者，市场代记所有权等于替别人认领文件），市场卸载通路不覆盖
     它们；移除经 ghpm remove —— ghpm 先自动备份再删，失败自动回滚，
     与 add / update 同一套后台任务与进度弹窗。 */
  if(t.dataset.rremove){
    const repo = t.dataset.rremove;
    const ok = await confirmBox("经 ghpm 移除 "+repo+"？",
      '<div class="note">将执行 <code>ghpm remove '+esc(repo)+'</code>：'+
      '把该仓库装进 <code>~/.workbuddy/skills</code> 的技能移除。'+
      '<b>ghpm 会先自动备份</b>（之后可用 <code>ghpm rollback</code> 恢复），'+
      '删除失败会自动还原。<br>'+
      '这些技能不由本市场的卸载管理（避免误删），所以移除走 ghpm 自己的命令。</div>',
      "移除");
    if(!ok) return true;
    try{
      const r = await api("/api/remote/remove", {repo});
      watchJob(r.jobId, "移除 "+repo);
    }catch(err){
      await errorBox("移除 "+repo+" 失败", err, () => t.click());
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
