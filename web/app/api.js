/* 本机 API 访问层。
   服务端注入的一次性口令（只存在于 index.html 的 meta 里）。
   所有 /api/* 都要带上它，否则本机任意网页都能替我们点
   「安装 / 卸载 / 清空回收站」。

   v2.24：后端错误统一为结构化载荷（code / stage / category /
   retryable / advice / done），这里把它们挂到抛出的 Error 上，
   供 errorBox() 呈现四段式人话。 */

const MARKET_TOKEN = (document.querySelector('meta[name="market-token"]') || {}).content || "";

export async function api(path, body){
  const headers = {"X-Local-Market-Token": MARKET_TOKEN};
  if(body) headers["Content-Type"] = "application/json";
  const opt = {headers};
  if(body){ opt.method = "POST"; opt.body = JSON.stringify(body); }
  const r = await fetch(path, opt);
  let data = {};
  try { data = await r.json(); } catch(e){}
  if(r.status === 403) throw new Error("本机服务拒绝了这次请求（口令失效，刷新页面即可）");
  if(!r.ok || data.ok === false){
    const err = new Error(data.error || ("HTTP " + r.status));
    err.status = r.status; err.data = data;   // 409 漂移拦截等结构化错误要用
    // v2.24 结构化字段（后端 _api_error_payload 提供；没有就是 undefined）
    err.code = data.code; err.stage = data.stage; err.category = data.category;
    err.retryable = data.retryable; err.advice = data.advice; err.done = data.done;
    throw err;
  }
  return data;
}
