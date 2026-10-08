/* 截图渲染助手（v2.22 拆分）。
   卡片只放首图且可点击放大（data-shot）；详情页是完整画廊（纯展示）。
   统一加 referrerpolicy="no-referrer" —— 不向图床泄露本机页面来源。 */

import { esc, attr } from "./utils.js";

// 卡片用：可点击在新标签页打开原图
export function cardShot(s, alt){
  return '<img src="'+attr(s)+'" alt="'+esc(alt)+'" loading="lazy" '+
         'referrerpolicy="no-referrer" data-shot="'+attr(s)+'">';
}

// 详情画廊用：纯展示
export function galleryShot(s, alt){
  return '<img src="'+attr(s)+'" alt="'+esc(alt)+'" loading="lazy" referrerpolicy="no-referrer">';
}
