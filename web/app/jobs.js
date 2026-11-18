/* 长任务进度弹窗（v2.22 拆分）。
   watchJob 轮询 /api/job/<id>，完成时回调「主刷新」——
   主刷新在 main.js 里定义，通过 bindRefresh 反向注册，
   避免 jobs → main → jobs 的循环导入。 */

import { api } from "./api.js";
import { $, esc, toast } from "./utils.js";
import { STATE } from "./state.js";

const jobs = {};
let _refresh = null;
let _outBound = false;
// 弹窗是「单任务视图」：后台可以继续跑多个任务（各自 interval + toast），
// 但只有最后启动的那个能写弹窗 DOM。否则后台任务 A 完成时会把正在显示
// 的任务 B 的进度条设成 100%、隐藏取消按钮（评审 Important 修复）。
let activeJid = null;

export function bindRefresh(fn){ _refresh = fn; }
export function refreshNow(){ if(_refresh) _refresh(); }

/* ---- 任务日志渲染（v2.41）：长 URL 不再把日志框撕成锯齿 ----
   artifact 下载行是一条 200+ 字符的 GitHub URL，pre 的 break-all 会
   在任意字符处断行（downl/oad、文件名单独成行），完全没法读。
   这里把每行先 esc（安全底线），再把 http(s) URL 换成「域名 … 文件名」
   的紧凑显示：hover 看全文、点击复制。步骤标记 [1/4] 也单独高亮。
   信息一条不丢，只是不再难看。 */
function shortUrl(u){
  if(u.length <= 64) return u;
  const m = /^(https?:\/\/[^/]+)(.*)$/.exec(u);
  if(!m) return u;
  const host = m[1];
  const rest = m[2].split(/[?#]/)[0];
  const parts = rest.split("/").filter(Boolean);
  let tail = parts.length ? parts[parts.length - 1] : "";
  if(!tail) return u;
  if(tail.length > 52) tail = tail.slice(0, 24) + "…" + tail.slice(-24);
  const mid = rest.length > tail.length + 1 ? "…/" : "/";
  return host + mid + tail;
}

/* 行尾标点归正文：.,;:!? 一律剥离；) ] } 只在「没有配对左括号」时才剥
   （评审 Minor：wiki 式 URL .../Foo_(bar) 结尾的 ) 是链接的一部分，不能截）。 */
function splitTrailing(whole){
  let end = whole.length;
  while(end > 0){
    const ch = whole[end - 1];
    if(".,;:!?".includes(ch)){ end--; continue; }
    const open = ch === ")" ? "(" : ch === "]" ? "[" : ch === "}" ? "{" : null;
    if(!open) break;
    const prefix = whole.slice(0, end - 1);
    const nOpen = prefix.split(open).length - 1;
    const nClose = prefix.split(ch).length - 1;
    if(nOpen <= nClose){ end--; continue; }   // 这个右括号没有配对 → 句读
    break;                                    // 成对闭合 → 属于 URL
  }
  return [whole.slice(0, end), whole.slice(end)];
}

function renderLines(lines){
  const urlRe = /https?:\/\/[^\s]+/g;
  const stepRe = /^(\[\d+\/\d+\])/;
  return (lines || []).slice(-60).map(raw => {
    const line = String(raw == null ? "" : raw);
    let out = "", last = 0, m;
    urlRe.lastIndex = 0;
    while((m = urlRe.exec(line)) !== null){
      out += esc(line.slice(last, m.index));
      const [url, tailTxt] = splitTrailing(m[0]);
      out += '<span class="jurl" title="' + esc(url) + '" data-url="' + esc(url) + '">'
           + esc(shortUrl(url)) + '</span>' + esc(tailTxt);
      last = m.index + m[0].length;
    }
    out += esc(line.slice(last));
    out = out.replace(stepRe, '<span class="jstep">$1</span>');
    return out;
  }).join("\n");
}

function bindJobOut(){
  if(_outBound) return;
  const box = $("#jobOut");
  if(!box) return;
  box.addEventListener("click", e => {
    const el = e.target.closest && e.target.closest(".jurl");
    if(!el) return;
    const url = el.getAttribute("data-url");
    if(!url) return;
    if(navigator.clipboard && navigator.clipboard.writeText){
      navigator.clipboard.writeText(url).then(
        () => toast("已复制完整链接"),
        () => toast("复制失败，可从悬浮提示中手动复制", true)
      );
    } else {
      toast("请从悬浮提示中手动复制链接");
    }
  });
  _outBound = true;
}

export function watchJob(jid, title){
  activeJid = jid;   // 新任务接管弹窗；旧任务转入纯后台（仍发 toast / 事件流）
  $("#veil").classList.add("show");
  $("#jobTitle").textContent = title;
  $("#jobBar").style.width = "0%";
  $("#jobBar").style.background = "var(--accent)";
  $("#jobLabel").textContent = "准备中…";
  $("#jobOut").innerHTML = "";
  bindJobOut();
  // v2.41：按钮叫「后台继续」，就必须运行中也能点 —— 关掉遮罩，任务照常
  // 在后台跑（轮询 interval 与 DOM 无关），完成时照样出 toast / 事件流。
  // 旧版只有 done 才解禁，等于名不副实：想让任务后台跑时偏偏点不了。
  $("#jobClose").disabled = false;
  $("#jobClose").onclick = () => { $("#veil").classList.remove("show"); refreshNow(); };
  // v2.36.1 用户实测「取消不了啊」：后端 /api/job/<id>/cancel（进程树终止 +
  // canceled 双窗口检查）一直都在，前端从来没接 —— 下载慢时用户只能干等。
  // 运行中显示「取消任务」，点击即终止整棵 ghpm 进程树。
  const jc = $("#jobCancel");
  jc.hidden = false; jc.disabled = false;
  jc.onclick = async () => {
    jc.disabled = true;
    if(jid === activeJid) $("#jobLabel").textContent = "取消中…";
    try{ await api("/api/job/"+jid+"/cancel", {}); }catch(e){ if(jid === activeJid) jc.disabled = false; }
  };

  jobs[jid] = setInterval(async () => {
    let j;
    try{ j = await api("/api/job/"+jid); }catch(e){ return; }
    // 只有「当前显示」的任务写弹窗；后台任务的完成只出 toast / 事件流。
    const shown = jid === activeJid;
    if(shown){
      $("#jobBar").style.width = (j.percent||0)+"%";
      $("#jobLabel").textContent = j.label || "";
      $("#jobOut").innerHTML = renderLines(j.lines);
      $("#jobOut").scrollTop = $("#jobOut").scrollHeight;
    }
    if(j.status === "done"){
      clearInterval(jobs[jid]); delete jobs[jid];
      if(shown){
        $("#jobClose").disabled = false;
        $("#jobCancel").hidden = true;
        $("#jobLabel").textContent = (j.ok ? "✓ " : "✗ ") + (j.label || "");
        $("#jobBar").style.width = "100%";
        $("#jobBar").style.background = j.ok ? "var(--ok)" : "var(--bad)";
      }
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
