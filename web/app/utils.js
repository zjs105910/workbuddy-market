/* 通用小工具：DOM 查询、转义、格式化、toast 与弹窗。
   v2.22 起前端拆为 ES Modules（零运行时依赖不变），本模块是公共底座。 */

export const $ = s => document.querySelector(s);

export const ICON = {"写作":"✍","开发工具":"⚙","自动化":"⟳","官方":"★","合集":"▣","测试":"⌘","设计":"◆","科研":"⚛","效率":"⚡","商业":"¥","安全":"🛡","未分类":"◇"};
export const iconOf = c => ICON[c] || "◇";
export const esc = s => String(s==null?"":s).replace(/[&<>"']/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));
export const attr = s => String(s).replace(/"/g,"&quot;");
export const fmtNum = n => n >= 10000 ? (n/10000).toFixed(1)+"w" : (n>=1000 ? (n/1000).toFixed(1)+"k" : String(n));
export const mb = b => ((b||0)/1048576).toFixed(1)+" MB";

export function toast(msg, bad){
  const t = $("#toast");
  t.textContent = msg;
  t.className = "toast show" + (bad ? " bad" : "");
  clearTimeout(t._t);
  t._t = setTimeout(()=>{ t.className = "toast" + (bad?" bad":""); }, 3400);
}

export function confirmBox(title, html, yesLabel){
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
export function infoBox(title, html){
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
