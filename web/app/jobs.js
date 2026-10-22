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
  // v2.36.1 用户实测「取消不了啊」：后端 /api/job/<id>/cancel（进程树终止 +
  // canceled 双窗口检查）一直都在，前端从来没接 —— 下载慢时用户只能干等。
  // 运行中显示「取消任务」，点击即终止整棵 ghpm 进程树。
  const jc = $("#jobCancel");
  jc.hidden = false; jc.disabled = false;
  jc.onclick = async () => {
    jc.disabled = true;
    $("#jobLabel").textContent = "取消中…";
    try{ await api("/api/job/"+jid+"/cancel", {}); }catch(e){ jc.disabled = false; }
  };

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
      $("#jobCancel").hidden = true;
      $("#jobLabel").textContent = (j.ok ? "✓ " : "✗ ") + (j.label || "");
      $("#jobBar").style.width = "100%";
      $("#jobBar").style.background = j.ok ? "var(--ok)" : "var(--bad)";
      // 2026-10-14 用户实测反馈：「装完了看不到装在哪里」——安装类任务
      // 完成时把落盘位置说清楚（工件/ghpm 都装进 WorkBuddy 技能目录），
      // 「本机技能」页的社区安装分区与只读清单也能看到它们。
      // v2.35：移除类任务说明备份去向（ghpm remove 自带备份与回滚）。
      if(j.ok && title.indexOf("安装 ") === 0){
        // v2.36.1：兼容模式可以 0 skill（仅源码副本）——后端 label 带
        // 「未含 skill」标记，toast 按实际落盘位置如实说，不再写「装入 skills」。
        if(String(j.label||"").indexOf("未含 skill") >= 0){
          toast(title+" 完成 · 仓库未含 skill，仅保留源码副本（本机技能页·社区安装可移除）");
        } else {
          toast(title+" 完成 · 已装入 "+((STATE.wbHome||"~/.workbuddy")+"/skills")+
                "，本机技能页可查看");
        }
      } else if(j.ok && title.indexOf("移除 ") === 0){
        toast(title+" 完成 · ghpm 已保留备份，可用 ghpm rollback 恢复");
      } else {
        // v2.36.1：用户主动取消如实说「已取消」，不再显示成失败。
        j.ok ? toast(title+" 完成")
             : toast(title+(j.canceled ? " 已取消" : " 失败，看输出"), !j.canceled);
      }
      refreshNow();
    }
  }, 700);
}
