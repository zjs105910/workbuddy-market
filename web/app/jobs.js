/* 长任务进度弹窗（v2.22 拆分）。
   watchJob 轮询 /api/job/<id>，完成时回调「主刷新」——
   主刷新在 main.js 里定义，通过 bindRefresh 反向注册，
   避免 jobs → main → jobs 的循环导入。 */

import { api } from "./api.js";
import { $, toast } from "./utils.js";

const jobs = {};
let _refresh = null;

export function bindRefresh(fn){ _refresh = fn; }
function refreshNow(){ if(_refresh) _refresh(); }

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
      j.ok ? toast(title+" 完成") : toast(title+" 失败，看输出", true);
      refreshNow();
    }
  }, 700);
}
