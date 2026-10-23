/* 更新中心（v2.21，评审 #15；v2.22 拆分；v2.26 一键全更新；
   v2.36 增加市场本体自更新检查）。聚合所有「已装且上游有新提交」的
   社区条目：当前装到的 sha 与注册表 latestSha 不同即视为有更新。更新
   动作复用既有的 /api/remote/update（ghpm 事务 + 回滚）；「可更新 N」
   指标芯片（main.js）点击直达本面板。 */

import { REG } from "./state.js";
import { esc, attr, infoBox } from "./utils.js";
import { trustBadge } from "./trust.js";
import { api } from "./api.js";

export function regUpdatable(){
  const out = [];
  for(const e of (REG.plugins||[])){
    const inst = REG.installedRepos && REG.installedRepos[e.repo];
    if(!inst) continue;                       // 没装过的谈不上更新
    const cur = (inst.sha_short||"").toLowerCase();
    const lat = String(e.latestSha||"").slice(0,7).toLowerCase();
    if(cur && lat && cur !== lat){
      out.push({repo:e.repo, displayName:e.displayName||e.repo,
                current:cur, latest:lat, trust:e.trust});
    }
  }
  return out;
}

export async function showUpdateCenter(){
  const upd = regUpdatable();
  // v2.36：市场本体自更新检查（/api/selfupdate，服务端缓存 600s）。
  // 失败如实渲染原因 —— 绝不把「查不到」伪装成「已是最新」。
  let selfSec;
  try{
    const su = await api("/api/selfupdate");
    if(su.updateAvailable === null || su.updateAvailable === undefined){
      selfSec = '<div class="grp"><h5>市场本体</h5>'+
        '<div class="note">'+esc(su.error || "检查失败。")+'</div></div>';
    } else if(su.updateAvailable){
      selfSec = '<div class="grp"><h5>市场本体有更新</h5>'+
        '<div class="update-row"><b>WorkBuddy Market</b>'+
        '<code>'+esc(su.current)+'</code><span class="arrow">→</span>'+
        '<code>'+esc(su.latest)+'</code></div>'+
        '<div class="note">'+ (su.howToUpdate||[]).map(esc).join('<br>') +'</div>'+
        '<div class="note">升级只在你确认后由你自己执行，本市场不自我替换运行中的文件。</div></div>';
    } else {
      selfSec = '<div class="grp"><h5>市场本体</h5>'+
        '<div class="note">已是最新版本（'+esc(su.current)+'）。</div></div>';
    }
  }catch(e){
    selfSec = '<div class="grp"><h5>市场本体</h5><div class="note">'+
      esc(e.message || "检查市场更新失败。")+'</div></div>';
  }
  let body;
  if(!upd.length){
    body = selfSec +
      '<div class="note">所有已装插件都是最新的，没有可更新项。</div>';
  } else {
    body = selfSec +
      '<div class="grp"><h5>'+upd.length+' 个插件有更新</h5>'+
      upd.map(u => '<div class="update-row">'+
        '<b>'+esc(u.displayName)+'</b>'+
        '<span class="repo">'+esc(u.repo)+'</span>'+
        '<code>'+esc(u.current)+'</code><span class="arrow">→</span><code>'+esc(u.latest)+'</code>'+
        trustBadge(u.trust)+   // v2.26 fail-closed：缺失/未知 → 未审核
        '<button class="tiny primary" style="margin-left:auto" data-rupdate="'+attr(u.repo)+'">更新</button>'+
        '</div>').join("")+'</div>'+
    '<div style="margin:10px 0 0">'+
      '<button class="primary" data-rupdate-all="1">全部更新（'+upd.length+' 个）</button>'+
    '</div>'+
    '<div class="note">更新走 ghpm，自带事务与回滚；旧版本会先进回收站，可恢复。'+
    '点「全部更新」后各条目作为独立后台任务并行执行（并发上限 4），'+
    '进度见任务弹窗与事件流。</div>';
  }
  return infoBox("更新中心", body);
}
