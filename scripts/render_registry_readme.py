# -*- coding: utf-8 -*-
"""render_registry_readme —— 把 registry/plugins.json 渲染成 README 收录清单表格。

v2.31 新增。参考 blatwo/workbuddy-marketplace 的「已收录插件」表格展示：
用户打开仓库第一眼就能看到市场里有什么，而不是先读完安装文档。

设计约束：
  · 只替换 README.md / README_EN.md 中成对标记之间的内容
    （<!-- registry-table:start --> ... <!-- registry-table:end -->），
    标记缺失 = README 结构被改坏，如实报错退出，绝不盲目追加；
  · 只读静态字段（repo / displayName / description / category / trust /
    homepage），动态字段（stars 等）不进表格——它们每天都在变，
    放进 README 会让每次 daily refresh 都产生无意义 diff；
  · 无网络依赖：数据源就是仓库内的 registry/plugins.json；
  · Windows CI 管道非 UTF-8，输出必须 reconfigure（踩坑 #33）。

用法（CI 内，registry.yml 的 daily refresh 同一 PR 里顺带刷新）：

    python scripts/render_registry_readme.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

if sys.stdout and hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")   # CI runner 管道非 UTF-8（踩坑 #33）
    sys.stderr.reconfigure(encoding="utf-8")

REPO_ROOT = Path(__file__).resolve().parent.parent
REGISTRY_FILE = REPO_ROOT / "registry" / "plugins.json"

START = "<!-- registry-table:start -->"
END = "<!-- registry-table:end -->"

# (文件, 语言) —— zh 用中文列名与描述，en 用英文列名与英文描述（缺失时回退中文）
TARGETS = [
    (REPO_ROOT / "README.md", "zh"),
    (REPO_ROOT / "README_EN.md", "en"),
]

_TRUST_LABEL = {
    "zh": {"official": "官方", "curated": "精选", "reviewed": "已审"},
    "en": {"official": "Official", "curated": "Curated", "reviewed": "Reviewed"},
}


def _esc(text: str) -> str:
    """表格单元格转义：竖线和换行会破坏 Markdown 表格。"""
    return text.replace("|", "\\|").replace("\n", " ").strip()


def render_table(registry: dict, lang: str) -> str:
    plugins = registry.get("plugins") or []
    if not plugins:
        raise SystemExit("注册表里没有条目，拒绝渲染空表格")

    if lang == "zh":
        header = "| 插件 | 说明 | 分类 | 信任级 |"
        sep = "| --- | --- | --- | --- |"
        caption = f"> 共 **{len(plugins)}** 个收录条目，由每日 CI 从人工审核的注册表自动刷新本表格。"
        fallback_desc = "（暂无描述）"
    else:
        header = "| Plugin | Description | Category | Trust |"
        sep = "| --- | --- | --- | --- |"
        caption = (f"> **{len(plugins)}** listed plugins; this table is refreshed "
                   "daily by CI from the human-reviewed registry.")
        fallback_desc = "(no description)"

    rows = [header, sep]
    trust_labels = _TRUST_LABEL[lang]
    for entry in plugins:
        repo = entry.get("repo") or ""
        if not repo:
            continue
        name = entry.get("displayName") or repo
        url = entry.get("homepage") or f"https://github.com/{repo}"
        if lang == "en":
            desc = entry.get("descriptionEn") or entry.get("description") or fallback_desc
        else:
            desc = entry.get("description") or fallback_desc
        category = entry.get("category") or ("社区" if lang == "zh" else "Community")
        trust = trust_labels.get(entry.get("trust") or "", trust_labels["reviewed"])
        rows.append(f"| [{_esc(name)}]({_esc(url)}) | {_esc(desc)} | "
                    f"{_esc(category)} | {trust} |")

    return caption + "\n\n" + "\n".join(rows) + "\n"


def replace_between(text: str, block: str, path: Path) -> str:
    """替换 START/END 标记之间的内容；标记缺失或不成对就报错。"""
    s = text.find(START)
    e = text.find(END)
    if s == -1 or e == -1 or e < s:
        raise SystemExit(f"{path.name} 缺少成对的 {START!r} / {END!r} 标记——"
                         "先在 README 里补上标记区间再跑本脚本")
    return text[:s + len(START)] + "\n\n" + block + "\n" + text[e:]


def main() -> int:
    registry = json.loads(REGISTRY_FILE.read_text(encoding="utf-8"))
    changed = []
    for path, lang in TARGETS:
        if not path.is_file():
            print(f"::error::{path.name} 不存在")
            return 2
        table = render_table(registry, lang)
        new_text = replace_between(path.read_text(encoding="utf-8"), table, path)
        if new_text != path.read_text(encoding="utf-8"):
            path.write_text(new_text, encoding="utf-8", newline="\n")
            changed.append(path.name)
            print(f"updated: {path.name}")
        else:
            print(f"unchanged: {path.name}")
    print(f"done ({len(registry.get('plugins') or [])} entries); "
          f"changed files: {', '.join(changed) if changed else 'none'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
