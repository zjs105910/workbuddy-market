/* 收藏（v2.21，评审 #13；v2.22 拆分）。
   本机持久化：收藏的是「社区目录里的上游 repo」，与 installed 解耦。
   Local-first —— 数据只在 STATE_HOME/favorites.json，不上传。 */

import { REG } from "./state.js";

export function favSet(){ return new Set((REG.favorites||[]).map(r => String(r).toLowerCase())); }
export function isFav(repo){ return favSet().has(String(repo).toLowerCase()); }
