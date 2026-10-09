/* 前端可变状态中枢（v2.22 拆分）。
   ES Module 的 export let 是活绑定：消费方 import 到的值会随
   setState/setReg 等写入同步更新；但**写入只能走 setter** ——
   跨模块直接给导入的绑定赋值是语法错误，这正好把状态变更
   收敛到本模块一处。 */

export let STATE = null;
export let CATALOG = null;
export let CATALOG_STALE = false;
export let cat = "全部";
export let filter = "all";
export let REG = {plugins:null, updatedAt:"", stale:false, source:"", installedRepos:{}, favorites:[]};   // 社区注册表（v2.11；v2.21 增 favorites）
export let tab = "local";   // v2.23 三入口：local=本机技能 / curated=精选市场 / explore=探索 GitHub

export function setState(v){ STATE = v; }
export function setCatalog(c, stale){ CATALOG = c; CATALOG_STALE = !!stale; }
export function setReg(r){ REG = r; }
export function setCat(c){ cat = c; }
export function setFilter(f){ filter = f; }
export function setTab(t){ tab = t; }
