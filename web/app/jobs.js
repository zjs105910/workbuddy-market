/* 长任务进度弹窗（v2.22 拆分）。
   watchJob 轮询 /api/job/<id>，完成时回调「主刷新」——
   主刷新在 main.js 里定义，通过 bindRefresh 反向注册，
   避免 jobs → main → jobs 的循环导入。 */

import { api } from "./api.js";
import { $, toast } from "./utils.js";
import { STATE } from "./state.js";

const jobs = {};
let _refresh = null;

export function bindRefresh(fn){ _refresh = fn; }
export function refreshNow(){ if(_refresh) _refresh(); }

export function watchJob(jid, title){
  $("#veil").classList.add("show");
  $("#jobTitle").textContent = title;
  $("#jobBar").style.width = "0%";
  $("#jobBar").style.background = "var(--accent)";
  $("#jobLabel").textContent = "准备中…";
  $("#jobOut").textContent = "";
  $("#jobClose").disabled = true;
  $("#jobClose").onclick = () => { $("#veil").classList.remove("show"); refreshNow(); };

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
      // 2026-10-14 用户实测反馈：「装完了看不到装在哪里」——安装类任务
      // 完成时把落盘位置说清楚（工件/ghpm 都装进 WorkBuddy 技能目录），
      // 「本机技能」页的社区安装分区与只读清单也能看到它们。
      // v2.35：移除类任务说明备份去向（ghpm remove 自带备份与回滚）。
      if(j.ok && title.indexOf("安装 ") === 0){
        toast(title+" 完成 · 已装入 "+((STATE.wbHome||"~/.workbuddy")+"/skills")+
              "，本机技能页可查看");
      } else if(j.ok && title.indexOf("移除 ") === 0){
        toast(title+" 完成 · ghpm 已保留备份，可用 ghpm rollback 恢复");
      } else {
        j.ok ? toast(title+" 完成") : toast(title+" 失败，看输出", true);
      }
      refreshNow();
    }
  }, 700);
}
