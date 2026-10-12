# -*- coding: utf-8 -*-
"""v2.31 自带市场（bundled/ + 根清单 + README 表格标记）契约测试。

背景：`.codebuddy-plugin/marketplace.json` 一路两用——上游是「短命令自带
市场」清单（相对路径引用 bundled/），本机是 `--sync` 生成的运行时清单。
入库的那份必须有门禁盯防：引用的插件目录真实存在、plugin.json 齐全、
README 表格标记成对——否则短命令装出来就是坏的，还不容易发现。
"""
from __future__ import annotations

import json
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
MARKET_JSON = REPO_ROOT / ".codebuddy-plugin" / "marketplace.json"
BUNDLED_DIR = REPO_ROOT / "bundled"


def _market() -> dict:
    """读「入库版」根清单。

    注意必须走 git 索引而不是工作区文件：开发机上 --sync 会把工作区文件
    重写成本机运行时清单（wb-local-market），那份不是上游自带市场。
    """
    import subprocess
    r = subprocess.run(["git", "show", ":.codebuddy-plugin/marketplace.json"],
                       capture_output=True, cwd=REPO_ROOT)
    if r.returncode == 0:
        return json.loads(r.stdout.decode("utf-8"))
    # 非 git 环境（罕见）：退回工作区文件
    return json.loads(MARKET_JSON.read_text(encoding="utf-8"))


def test_marketplace_json_parses():
    m = _market()
    assert m["name"] == "workbuddy-market"
    assert isinstance(m.get("plugins"), list) and m["plugins"]


def test_marketplace_plugins_point_to_bundled():
    """每个条目的 source 必须指向 bundled/ 下真实存在的目录（防手滑改回 plugins/）。"""
    m = _market()
    for entry in m["plugins"]:
        src = entry.get("source", "")
        assert src.startswith("./bundled/"), f"source 必须指向 bundled/: {src}"
        dest = REPO_ROOT / src.lstrip("./")
        assert dest.is_dir(), f"source 目录不存在: {dest}"


def test_bundled_plugins_have_manifest_and_skill():
    """strict:true 默认要求 plugin.json；没有 SKILL.md 的插件装了也没用。"""
    for name in [e["name"] for e in _market()["plugins"]]:
        base = BUNDLED_DIR / name
        assert (base / ".codebuddy-plugin" / "plugin.json").is_file(), name
        skills = list((base / "skills").rglob("SKILL.md")) if (base / "skills").is_dir() else []
        assert skills, f"{name} 的 bundled 副本里没有任何 SKILL.md"


def test_bundled_plugin_json_names_consistent():
    """bundled 内 plugin.json 的 name 与市场条目一致，避免宿主端 id 对不上。"""
    for entry in _market()["plugins"]:
        pj = json.loads(
            (BUNDLED_DIR / entry["name"] / ".codebuddy-plugin" / "plugin.json")
            .read_text(encoding="utf-8"))
        assert pj.get("name") == entry["name"]


def test_readme_registry_table_markers_present():
    """README 两份都必须有成对的表格标记（render_registry_readme.py 的替换锚点）。"""
    for name in ("README.md", "README_EN.md"):
        text = (REPO_ROOT / name).read_text(encoding="utf-8")
        start = text.find("<!-- registry-table:start -->")
        end = text.find("<!-- registry-table:end -->")
        assert start != -1 and end != -1 and end > start, name


def test_render_script_smoke_on_readmes():
    """渲染脚本对当前 README 跑一遍必须成功（防标记区间被改坏后 CI 才炸）。"""
    import subprocess
    import sys
    r = subprocess.run(
        [sys.executable, str(REPO_ROOT / "scripts" / "render_registry_readme.py")],
        capture_output=True, text=True, timeout=120, cwd=REPO_ROOT)
    assert r.returncode == 0, r.stderr[-500:]
    # 幂等：跑第二遍不再改动
    r2 = subprocess.run(
        [sys.executable, str(REPO_ROOT / "scripts" / "render_registry_readme.py")],
        capture_output=True, text=True, timeout=120, cwd=REPO_ROOT)
    assert r2.returncode == 0 and "changed files: none" in r2.stdout
