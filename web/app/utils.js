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

/* ---- v2.24：结构化错误弹窗（四段式人话 + 重试/日志/诊断三按钮） ----
   后端 _api_error_payload 给出 code/stage/category/retryable/advice/done；
   拿不到结构化字段（如 fetch 本身失败）就如实降级为通用文案，
   绝不编造「已完成/未受影响」。 */
const CATEGORY_CAUSE = {
  network:    "网络连接失败，或 GitHub 一侧不可达 / 限流。",
  config:     "market.config.json 缺失或格式不对。",
  concurrency:"另一个市场操作正在进行（文件锁被占用）。",
  integrity:  "文件扫描不完整 —— 内核主动中止，防止误删。",
  internal:   "市场服务内部错误。",
};

export function errorBox(title, err, retry){
  const d = (err && err.data) || {};
  const code = err && err.code;
  const category = err && err.category;
  const what = (err && err.message) || "操作失败";
  const cause = d.advice && category ? (CATEGORY_CAUSE[category] || "原因未知。") : (CATEGORY_CAUSE[category] || "");
  // 「已完成什么」：只有后端明确说了才展示 —— 宁可含糊不可撒谎。
  const doneLine = d.done
    ? '<div class="grp"><h5>已完成 / 未完成</h5><p class="desc" style="margin:0">'+esc(d.done)+'</p></div>'
    : '<div class="grp"><h5>已完成 / 未完成</h5><p class="desc" style="margin:0">无法确认 —— 请以「本机技能」页的实际状态与事件流为准。</p></div>';
  const next = d.advice
    ? esc(d.advice)
    : '稍后重试；反复失败时点「查看详细日志」看事件流，或运行 <code>python launcher.py --status</code>。';
  const meta = code
    ? '<div class="meta" style="margin:4px 0 10px"><span>错误码 '+esc(code)+'</span>'+
      (err.stage ? '<span>阶段 '+esc(err.stage)+'</span>' : '')+
      (category ? '<span>类别 '+esc(category)+'</span>' : '')+'</div>'
    : '';
  let html = meta +
    '<div class="grp"><h5>发生了什么</h5><p class="desc" style="margin:0">'+esc(what)+'</p></div>'+
    (cause ? '<div class="grp"><h5>可能原因</h5><p class="desc" style="margin:0">'+esc(cause)+'</p></div>' : '')+
    doneLine+
    '<div class="grp"><h5>下一步</h5><p class="desc" style="margin:0">'+next+'</p></div>';

  return new Promise(resolve => {
    $("#cfmTitle").textContent = title;
    $("#cfmBody").innerHTML = html;
    // 按钮排布：cfmNo = 次要动作区（重试 / 日志 / 诊断 塞进来），cfmYes = 关闭
    const noBtn = $("#cfmNo");
    noBtn.style.display = "";
    noBtn.textContent = "关闭";
    const extra = document.createElement("span");
    extra.style.cssText = "flex:1;display:flex;gap:8px;flex-wrap:wrap";
    extra.innerHTML =
      (retry ? '<button class="tiny primary" id="ebRetry">重试</button>' : '')+
      '<button class="tiny" id="ebLog">查看详细日志</button>'+
      '<button class="tiny" id="ebCopy">复制诊断</button>';
    noBtn.parentNode.insertBefore(extra, noBtn);
    const cleanup = () => {
      extra.remove();
      $("#cfm").classList.remove("show");
    };
    $("#cfmYes").onclick = () => { cleanup(); resolve("close"); };
    noBtn.onclick = () => { cleanup(); resolve("close"); };
    const rb = $("#ebRetry");
    if(rb) rb.onclick = () => { cleanup(); resolve("retry"); };
    $("#ebLog").onclick = () => {
      cleanup();
      document.getElementById("drawer").classList.add("show");
      resolve("log");
    };
    $("#ebCopy").onclick = async () => {
      const diag = {
        title, code: code || null, category: category || null,
        stage: (err && err.stage) || null, message: what,
        httpStatus: (err && err.status) || null,
        time: new Date().toISOString(), source: "WorkBuddy Market Web",
      };
      try{
        await navigator.clipboard.writeText(JSON.stringify(diag, null, 2));
        toast("诊断信息已复制（已脱敏，不含路径）");
      }catch(e){ toast("复制失败：浏览器剪贴板不可用", true); }
    };
    $("#cfm").onclick = e => { if(e.target.id === "cfm"){ cleanup(); resolve("close"); } };
  });
}

/* ---- v2.24：Escape 关弹窗（可访问性） ---- */
document.addEventListener("keydown", (e) => {
  if(e.key !== "Escape") return;
  const box = document.getElementById("cfm");
  if(box && box.classList.contains("show")){
    const no = document.getElementById("cfmNo");
    const yes = document.getElementById("cfmYes");
    (no.style.display === "none" ? yes : no).click();
  }
});
