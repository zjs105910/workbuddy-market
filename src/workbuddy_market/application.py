# -*- coding: utf-8 -*-
"""workbuddy_market.application —— 组合 / 编排层（v2.19 新增，R6 收尾）。

自 market_core.py 逐字迁入（v2.19）：

  · sync_packaging / _sync_packaging          本机 skill → 插件 打包编排
  · build_plugin_json / _plugin_readme        插件清单与 README 构造
  · OPEN_TARGETS / resolve_open_request       「打开目录」白名单（API 层语义）
  · deep_check / selfcheck                    四层一致性深度自检
  · main(argv)                                python market_core.py 的命令入口

纪律（与 R4/R5 迁包同一套，缺一不可）：

  · **只搬不改** —— 函数体除 import 口径外逐字保留；
  · **注入点经 core 晚绑定**：``_sync_packaging`` 调 ``_scan``（crash 注入
    矩阵 + selftest 第 18 节计数盯防）、``sync_packaging`` 调
    ``recover_transactions``（凭证早于磁盘变更的恢复入口）、``main`` 与
    ``_sync_packaging`` 调 ``say``（定义在 core）—— 一律在函数体内
    ``import market_core`` 后经 core 命名空间调用，patch core.X 语义不变；
  · 叶子依赖（fsutil / logging / trash / adapter 等）直接从所属模块导入；
  · deep_check 的 known_health 走 adapter 模块命名空间 —— 拦宿主格式诊断
    的 patch 落点是 ``workbuddy_market.adapters.workbuddy``（v2.17 先例）。

market_core 对以上名字全部 re-export：server / launcher / 第三方脚本照旧
经 ``core.X`` 调用与 patch。
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

from .paths import (
    MARKET_ROOT, PLUGINS_DIR, SKILLS_DIR, MANIFEST_PATH, STATE_PATH,
    WEB_DIR, TRASH_DIR,
)
from .errors import ConfigError
from .fsutil import read_json, write_text_if_changed, atomic_write_text
from .locking import locked
from .logging import now_iso, log
from .version import STATE_VERSION, MARKET_VERSION
from .config import load_config, validate_config, validate_id, ensure_child
from .scanner import _make_excluder, _sub_index, parse_skill_meta
from .sync import _sync_tree
from .trash import (move_to_trash, prune_trash, TRASH_INDEX_PATH,
                    _load_trash_index, _trash_entry)
from .ownership import load_ownership
from .transactions import tx_list
from .adapters.workbuddy import register, unregister, known_health


def sync_packaging(quiet: bool = False) -> dict:
    """把本机 skill 打包成插件 + 生成市场索引。增量同步，可反复跑。"""
    import market_core as core   # 调用点晚绑定（R5 纪律）
    with locked():
        # 上一次如果崩在「已落位、所有权还没写」那一步，这里补上
        rec = core.recover_transactions(quiet=quiet)
        return _sync_packaging(quiet=quiet, recovered=rec["recovered"])


def _sync_packaging(quiet: bool = False, recovered: list | None = None) -> dict:
    import market_core as core   # 注入点晚绑定：_scan / say
    cfg = load_config()
    pack = cfg.get("packaging", {})
    excluded = _make_excluder(pack.get("excludeNames"), pack.get("excludeGlobs"))
    mode = pack.get("verify", "auto")
    if mode not in ("auto", "fast", "strict"):
        mode = "auto"
    # 打包的比对档位仍然只有「比时间戳」和「比内容」两种；
    # auto 在这里等价于 fast —— 真正需要精确的是 install / uninstall
    # 那两条路径（见 needs_exact），打包慢一点没有安全收益。
    strict = mode == "strict"

    PLUGINS_DIR.mkdir(parents=True, exist_ok=True)
    manifest_plugins = []
    report = {"plugins": [], "missing": [], "cachedSkills": [], "copiedSkills": 0,
              "totalSkills": 0, "copiedFiles": 0, "removedFiles": 0, "skippedLinks": 0,
              "bytes": 0, "verify": mode, "recovered": list(recovered or [])}

    # 上次生成、这次配置里已经不要的插件 → 回收站（rename，不是删除）
    wanted = {p["name"] for p in cfg.get("localPlugins", [])}
    for existing in sorted(PLUGINS_DIR.iterdir()):
        if existing.is_dir() and existing.name not in wanted:
            retired = move_to_trash(existing, "retire")
            log("info", "sync",
                f"插件 {existing.name} 已不在配置中，移入回收站 {retired.name if retired else ''}")

    total_bytes = 0
    for spec in cfg.get("localPlugins", []):
        pname = spec["name"]
        pdir = PLUGINS_DIR / pname
        skills_root = pdir / "skills"
        skills_root.mkdir(parents=True, exist_ok=True)

        # 目标侧整树只扫一次，之后按 skill 前缀切片 ——
        # v2 是「每个 skill 扫一次目标目录」，一个 12 skill 的插件要扫 12 次。
        # 切片后：源侧仍是每 skill 一次（内容不同，必须各扫），目标侧收敛成 1 次。
        # on_error="raise"：这一步决定了紧接着要删哪些「多余文件」，
        # 看不到就等于删错 —— 必须 fail-closed。
        dst_all, _dst_links = core._scan(skills_root, excluded, on_error="raise")

        present = []
        for sname in spec.get("skills", []):
            src = SKILLS_DIR / sname
            dst = skills_root / sname
            if not (src / "SKILL.md").is_file():
                report["missing"].append(f"{pname}/{sname}")
                cached = _sub_index(dst_all, sname)
                if (dst / "SKILL.md").is_file():
                    # 本机没有，但市场里还留着上次打包的副本 —— 保留。
                    # 市场是「仓库」不是「镜像」：源没了不该让货架也空掉，
                    # 否则「先卸载、再从市场装回来」这条路根本走不通。
                    present.append(sname)
                    report["cachedSkills"].append(f"{pname}/{sname}")
                    report["totalSkills"] += 1
                    total_bytes += sum(v[0] for v in cached.values())
                    log("warn", "sync", f"{sname} 本机已不存在，沿用市场里的历史副本")
                else:
                    log("warn", "sync", f"{sname} 本机不存在，且没有历史副本，跳过")
                continue
            c, r, sz, nl = _sync_tree(src, dst, excluded, strict=strict,
                                      dst_index=_sub_index(dst_all, sname))
            report["copiedFiles"] += c
            report["removedFiles"] += r
            report["skippedLinks"] += nl
            total_bytes += sz
            present.append(sname)
            report["copiedSkills"] += 1
            report["totalSkills"] += 1

        if not present:
            log("warn", "sync", f"{pname} 没有任何可用 skill，未生成插件")
            report["plugins"].append({"name": pname, "skills": 0, "skipped": True})
            continue

        # 该插件下已经不该存在的 skill 目录（本轮配置删掉了）→ 回收站
        keep = set(present)
        for child in sorted(skills_root.iterdir()):
            if child.is_dir() and child.name not in keep:
                move_to_trash(child, "retire")
                log("info", "sync", f"{pname}: skill {child.name} 已不在配置中，移入回收站")

        plugin_json = build_plugin_json(cfg, spec)
        write_text_if_changed(
            pdir / ".codebuddy-plugin" / "plugin.json",
            json.dumps(plugin_json, ensure_ascii=False, indent=2) + "\n",
        )
        write_text_if_changed(pdir / "README.md", _plugin_readme(cfg, spec, present))

        manifest_plugins.append({
            "name": pname,
            "description": spec.get("description", ""),
            "description_en": spec.get("description_en", ""),
            "version": spec.get("version", "1.0.0"),
            "source": f"./plugins/{pname}",
            "category": spec.get("category", ""),
            "author": plugin_json["author"],
            "keywords": spec.get("keywords", []),
        })
        report["plugins"].append({"name": pname, "skills": len(present), "skillsList": present})
        if not quiet:
            core.say(f"  [打包] {spec.get('displayName', pname)} —— {len(present)} 个 skill")
        log("info", "sync", f"{pname}: 打包 {len(present)} 个 skill")

    manifest = {
        "name": cfg.get("marketId", "wb-local-market"),
        "description": cfg.get("description", ""),
        "owner": cfg.get("owner", {}),
        "plugins": manifest_plugins,
    }
    write_text_if_changed(MANIFEST_PATH, json.dumps(manifest, ensure_ascii=False, indent=2) + "\n")

    # 体积：直接用上面各 skill 索引里累加的值，不再 rglob 全量扫一遍
    report["bytes"] = total_bytes

    state = read_json(STATE_PATH, {}) or {}
    state.update({
        "version": STATE_VERSION,
        "marketVersion": MARKET_VERSION,
        "marketId": manifest["name"],
        "lastSync": now_iso(),
        "pluginCount": len(manifest_plugins),
        "skillCount": report["totalSkills"],
        "cachedCount": len(report["cachedSkills"]),
        "sizeBytes": total_bytes,
    })
    atomic_write_text(STATE_PATH, json.dumps(state, ensure_ascii=False, indent=2) + "\n")
    return report


def build_plugin_json(cfg: dict, spec: dict) -> dict:
    """插件级清单。抽出来是因为 sync 与深度自检都要用同一份构造逻辑。"""
    author = {"name": spec.get("author", {}).get("name", cfg.get("owner", {}).get("name", ""))}
    pj = {
        "name": spec["name"],
        "version": spec.get("version", "1.0.0"),
        "description": spec.get("description", ""),
        "description_zh": spec.get("description", ""),
        "description_en": spec.get("description_en", ""),
        "author": author,
        "keywords": spec.get("keywords", []),
        "category": spec.get("category", ""),
    }
    for key in ("homepage", "repository", "license"):
        if spec.get(key):
            pj[key] = spec[key]
    return pj


def _plugin_readme(cfg: dict, spec: dict, skills: list) -> str:
    lines = [
        f"# {spec.get('displayName', spec['name'])}",
        "",
        spec.get("description", ""),
        "",
        f"- 市场：`{cfg.get('marketId')}`",
        f"- 版本：`{spec.get('version', '1.0.0')}`",
        f"- 分类：{spec.get('category', '—')}",
        "",
        "## 包含的 skill",
        "",
    ]
    for s in skills:
        meta = parse_skill_meta(MARKET_ROOT / "plugins" / spec["name"] / "skills" / s)
        lines.append(f"- **{s}** v{meta['version']} — {meta['description'][:120]}")
    lines += ["", "---", "",
              "此文件由 `launcher.py --sync` 依据 `market.config.json` 自动生成，请勿手改。", ""]
    return "\n".join(lines)


# ---------------------------------------------------------------- 打开目录（白名单）
#
# v2.2 的 /api/open/path 直接 `Path(body["path"])` 交给 explorer / open / xdg-open。
# 实测 `C:\Windows`、用户家目录都能被"打开" —— 虽然没执行 shell，但
# explorer / open 本身就是操作系统行为，不该由任意本机网页来点名。
# 现在只认市场自己地盘里的目标。

OPEN_TARGETS = ("root", "plugins", "web", "trash", "plugin")


def resolve_open_request(payload: dict) -> tuple[Path | None, str]:
    """把请求解析成一个**允许打开**的路径。返回 (path, error)。

    两种写法：
      {"target": "plugin", "id": "novel-writing-suite"}    ← 推荐：服务器自己拼路径
      {"target": "root" | "plugins" | "web" | "trash"}
      {"path": "..."}                                      ← 兼容旧前端，仍要过白名单

    无论哪条路，最终都过一遍 `ensure_child(MARKET_ROOT, ...)`。
    """
    roots = {"root": MARKET_ROOT, "plugins": PLUGINS_DIR,
             "web": WEB_DIR, "trash": TRASH_DIR}
    target = payload.get("target")

    if target == "plugin":
        try:
            pid = validate_id(payload.get("id"), "插件 id")
        except ConfigError as exc:
            return None, str(exc)
        p = PLUGINS_DIR / pid
        try:
            ensure_child(PLUGINS_DIR, p)
        except ConfigError:
            return None, "插件目录越界"
        if not p.is_dir():
            return None, f"插件目录不存在：{pid}"
        return p, ""

    if target is not None:
        if isinstance(target, str) and target in roots:
            return roots[target], ""
        return None, (f"未知的打开目标 {target!r}（可选：{', '.join(OPEN_TARGETS)}）")

    raw = payload.get("path")
    if not raw:
        return MARKET_ROOT, ""
    try:
        return ensure_child(MARKET_ROOT, Path(str(raw))), ""
    except ConfigError:
        return None, "只允许打开市场目录之内的路径"


# ---------------------------------------------------------------- 自检

def deep_check() -> tuple:
    """四层一致性校验：配置 ↔ 索引 ↔ 插件清单 ↔ 实际文件。

    返回 (ok, errors, warnings)。errors 非空即视为不一致。
    """
    errors, warnings = [], []

    # --- 配置层（validate_config 会做结构 + 安全校验，问题直接抛）
    try:
        cfg = load_config()
        warnings += validate_config(cfg)
    except ConfigError as exc:
        return (False, [f"配置不可用：{exc}"], [])

    # --- 暂存残留：上次安装崩在中途留下的
    try:
        leftovers = [d.name for d in SKILLS_DIR.glob(".*.installing-*")] if SKILLS_DIR.is_dir() else []
    except OSError:
        leftovers = []
    if leftovers:
        warnings.append(f"skills 目录里有 {len(leftovers)} 个安装暂存残留 {leftovers[:3]}"
                        "（下次安装会自动清理）")

    # --- 索引层
    if not MANIFEST_PATH.is_file():
        errors.append("市场索引 .codebuddy-plugin/marketplace.json 不存在（先跑 --sync）")
        return (False, errors, warnings)
    try:
        man = read_json(MANIFEST_PATH, None, strict=True)
    except ConfigError as exc:
        return (False, [f"市场索引不可用：{exc}"], warnings)
    if not isinstance(man, dict) or not isinstance(man.get("plugins"), list):
        return (False, ["市场索引结构不对（应有 plugins 数组）"], warnings)

    local = {p["name"]: p for p in cfg.get("localPlugins", [])}
    indexed = {p.get("name"): p for p in man["plugins"]}

    # 配置有、索引没有 → 错误
    for name in local:
        if name not in indexed:
            errors.append(f"配置里的插件 {name} 没有出现在市场索引里")
    # 索引有、配置没有 → 警告（多半是上次同步残留）
    for name in indexed:
        if name not in local:
            warnings.append(f"市场索引里的插件 {name} 已不在 market.config.json 中（重新打包可清掉）")

    # --- 插件清单层 + 文件层
    for name, spec in local.items():
        ip = indexed.get(name)
        src_rel = (ip or {}).get("source") or f"./plugins/{name}"
        pdir = MARKET_ROOT / str(src_rel)[2:]
        if not pdir.is_dir():
            errors.append(f"插件 {name} 的 source 目录不存在：{pdir}")
            continue

        pj_path = pdir / ".codebuddy-plugin" / "plugin.json"
        if not pj_path.is_file():
            errors.append(f"插件 {name} 缺少 .codebuddy-plugin/plugin.json")
        else:
            try:
                pj = read_json(pj_path, None, strict=True)
            except ConfigError as exc:
                errors.append(f"插件 {name} 的 plugin.json 不可用：{exc}")
                pj = None
            if isinstance(pj, dict):
                if pj.get("name") != name:
                    errors.append(f"插件 {name} 的 plugin.json 里 name={pj.get('name')}，不一致")
                want_v = spec.get("version", "1.0.0")
                if ip and ip.get("version") != want_v:
                    errors.append(f"插件 {name} 版本不一致：索引 v{ip.get('version')} vs 配置 v{want_v}")
                if pj.get("version") != want_v:
                    errors.append(f"插件 {name} 版本不一致：plugin.json v{pj.get('version')} vs 配置 v{want_v}")

        # 配置声明 vs 实际打包
        declared = set(spec.get("skills", []))
        sroot = pdir / "skills"
        actual = {p.name for p in sroot.iterdir() if (p / "SKILL.md").is_file()} if sroot.is_dir() else set()
        for miss in sorted(declared - actual):
            if (SKILLS_DIR / miss / "SKILL.md").is_file():
                errors.append(f"插件 {name} 声明了 {miss}，但没有打包进去")
            else:
                warnings.append(f"插件 {name} 声明的 {miss} 在本机 skills 里不存在")
        for extra in sorted(actual - declared):
            warnings.append(f"插件 {name} 里多了未声明的 {extra}（重新打包可清掉）")

    # --- WorkBuddy 侧（v2.17 起经 adapter 诊断宿主格式）
    _known_err = known_health()
    if _known_err:
        errors.append(_known_err)

    # --- 所有权残留
    own = load_ownership()["skills"]
    legacy = 0
    for s, rec in own.items():
        if not (SKILLS_DIR / s / "SKILL.md").is_file():
            warnings.append(f"所有权记录里的 {s} 在本机已不存在（残留记录）")
            continue
        if rec.get("plugin") not in local:
            warnings.append(f"所有权记录里的 {s} 指向已不存在的插件 {rec.get('plugin')}")
        fp = rec.get("fingerprint")
        # 旧记录只有 files/bytes/mtime_ns_max，缺少 mtime_ns_sum —— 结构对不上
        # 就会一直退回完整 SHA-256（正确但慢），所以提示重装补齐
        if not isinstance(fp, dict) or "mtime_ns_sum" not in fp:
            legacy += 1
    if legacy:
        warnings.append(f"{legacy} 条所有权记录没有完整的快速指纹"
                        "（v2.1 之前装的记录）；重装一次即可补上，"
                        "期间状态检查会退回完整 SHA-256")

    # --- 回收站索引安全性
    # 索引是普通 JSON，手工可改。里面的条目名必须都是合法 basename，
    # 否则说明它被改过（或写坏了）—— 这是「越界删除」的唯一入口，必须报出来。
    if TRASH_INDEX_PATH.is_file():
        try:
            tidx = _load_trash_index()
        except Exception:
            tidx = {"items": {}}
        bad = [n for n in tidx.get("items", {}) if _trash_entry(n) is None]
        if bad:
            errors.append(
                f"回收站索引里有 {len(bad)} 个非法条目名 {bad[:3]}"
                "（含路径成分，属于越界删除风险；本工具已拒绝按它访问磁盘，"
                f"可删掉 {TRASH_INDEX_PATH.name} 让它重建）"
            )

    # --- 未完成的事务
    # 挂着待办条目的日志，说明上一次装/卸在「文件已变更、状态还没跟上」那一步
    # 中断了。数据没丢，但账没记上 —— 必须报出来。
    for tx in tx_list():
        pend = tx.get("pendingOwnership") or []
        forget = tx.get("pendingForget") or []
        if pend or forget:
            names = [e.get("skill") if isinstance(e, dict) else e for e in (pend or forget)]
            errors.append(
                f"有未完成的事务 {tx.get('id')}（{tx.get('operation')} "
                f"{tx.get('plugin')}）：{names} 的磁盘状态与所有权记录不一致"
                "（下次打包/安装/启动会自动补账；若内容已被你改过，"
                "本工具会拒绝认领并一直留着这份日志）"
            )

    return (not errors, errors, warnings)


def selfcheck() -> tuple:
    """兼容 v1 的签名：返回 (ok, 问题列表)，只含 error 级。"""
    ok, errors, _warnings = deep_check()
    return (ok, errors)


def main(argv=None) -> int:
    import market_core as core   # 命令入口：全部子命令经 core 命名空间（patch 语义不变）
    argv = list(sys.argv[1:] if argv is None else argv)
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

    cmd = argv[0] if argv else "status"
    if cmd == "recover":
        r = core.recover_transactions(quiet=False,
                                      discard_conflicts="--discard-conflicts" in argv)
        core.say(f"事务恢复：补记所有权 {len(r['recovered'])} 项，"
                 f"清理日志 {len(r['finished'])} 份，清理暂存 {r['stagingSwept']} 个")
        for c in r["conflicts"]:
            core.say(f"  ! 拒绝认领 {c['skill']}：内容已被改动（不是当时 commit 的那一份）")
        for tid, err in r["failed"]:
            core.say(f"  ✗ {tid}：{err}")
        return 0 if not r["failed"] else 1
    if cmd == "sync":
        rep = core.sync_packaging()
        core.say(f"打包完成：{len(rep['plugins'])} 个插件，{rep['copiedSkills']} 个 skill")
        if rep.get("recovered"):
            core.say(f"  顺带补记了上次未完成的所有权：{', '.join(rep['recovered'])}")
        if rep["missing"]:
            core.say("缺失： " + ", ".join(rep["missing"]))
        return 0
    if cmd == "register":
        core.say("已注册。" if core.register() else "已是注册状态，无需改动。")
        return 0
    if cmd == "unregister":
        core.say("已撤销注册。" if core.unregister() else "未注册，无需撤销。")
        return 0
    if cmd == "purge-trash":
        r = core.prune_trash(force=True)
        core.say(f"回收站已清空：移除 {r['removed']} 项，释放 {r['freed'] / 1048576:.1f} MB")
        if r["failed"]:
            core.say(f"  ! 有 {r['failed']} 项删除失败，仍在回收站里："
                     + "、".join(str(i["name"]) for i in r["failedItems"][:3]))
        return 0
    if cmd == "status":
        st = core.build_state()
        core.say(f"市场：{st['marketName']}（{st['marketId']}） v{st['marketVersion']}")
        core.say(f"注册状态：{'已注册' if st['registered'] else '未注册'}")
        core.say(f"本机插件 {st['stats']['localPlugins']} 个 / GitHub 源 {st['stats']['remoteSources']} 个")
        eff = st["stats"]["verifyEffective"]
        core.say(f"校验档位：{st['stats']['verify']}"
                 f"（精确判定：安装 {'是' if eff['install'] else '否'}"
                 f" / 卸载 {'是' if eff['uninstall'] else '否'}）")
        core.say(f"回收站 {st['trash']['count']} 项，{st['trash']['bytes'] / 1048576:.1f} MB")
        ok, errors, warns = core.deep_check()
        core.say(f"深度自检：{'通过' if ok else '发现 ' + str(len(errors)) + ' 个错误'}")
        for e in errors:
            core.say("  ✗ " + e)
        for w in warns[:6]:
            core.say("  ! " + w)
        return 0
    core.say(f"未知命令：{cmd}")
    return 2
