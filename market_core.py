# -*- coding: utf-8 -*-
"""market_core —— WorkBuddy 本机插件市场的内核兼容层（v2.19，R6 收尾）。

v2.19 起本文件只是一个**兼容 shim**：真正的实现全部在
src/workbuddy_market/ 包里。这里保留三样东西：

  1. 全部迁出符号的 re-export —— 第三方 `import market_core` 不破坏，
     selftest 的 core.X 属性注入语义不变；
  2. say() 与 v2.7 运行时迁移（import 时自动触发一次）；
  3. quick_fingerprint / tree_hash / tree_hash_from_index —— 它们依赖
     core._scan（selftest 崩溃注入点）与 hash_chunk_bytes()（读配置），
     按「_scan 注入点纪律」**故意留驻 core**（R3 起的既定决策）。

版本号只有一个来源：src/workbuddy_market/version.py 的 MARKET_VERSION。
每轮代码评审对应一个次版本号；v1 → v2.18 各轮的详细变更见
docs/versions.md（v2 → v2.11）与 CHANGELOG.md（v2.12 起）。

v2.19（R6 收尾）：installed_skill_names / installed_repos / build_state 迁
workbuddy_market.state；sync_packaging / deep_check / selfcheck / main /
resolve_open_request 迁 workbuddy_market.application（组合层）。
注入点晚绑定纪律（R5）：state / application 对 crash 注入矩阵盯防的
入口（plugin_uninstall_plan / _scan / recover_transactions / say）在
函数体内经 core 命名空间调用 —— patch core.X 的拦截语义与迁移前一致。
"""
from __future__ import annotations

import hashlib
import json
import os
import shutil
import sys
from pathlib import Path

# ------------------------------------------------------- 基础设施包（v2.8，R2）
#
# 路径 / 错误 / 原子写 / 哈希 / 锁 / 日志 / 配置 / 扫描 / sync / catalog /
# registry / trash / ownership / transactions / installer / uninstaller /
# artifact / adapters.workbuddy / state / application 已逐字迁入
# src/workbuddy_market/。market_core 仍是唯一兼容入口：re-export 全部
# 迁出符号，selftest 的 core.X 属性注入不受影响。

# --- sys.path 引导：src 布局，未安装 pip 包时也能直接 import ---
_SRC_DIR = Path(__file__).resolve().parent / "src"
if str(_SRC_DIR) not in sys.path:
    sys.path.insert(0, str(_SRC_DIR))

from workbuddy_market.paths import (          # noqa: E402,F401
    _DEPRECATED_ENVS_USED, _LEGACY_LAYOUT,
    MARKET_ROOT, STATE_HOME,
    CONFIG_PATH, MANIFEST_DIR, MANIFEST_PATH, PLUGINS_DIR, WEB_DIR,
    STATE_PATH, LOG_PATH, BACKUP_DIR, TRASH_DIR, TX_DIR, OWNERSHIP_PATH,
    LOCK_PATH, LOG_LOCK_PATH, CATALOG_PATH, REGISTRY_PATH,
    WB, SKILLS_DIR, KNOWN_PATH, GITHUB_REGISTRY, GHPM_PY,
    LOG_MAX_BYTES, LOG_KEEP, BACKUP_KEEP, HASH_CHUNK_BYTES,
)
from workbuddy_market.errors import (         # noqa: E402,F401
    ConfigError, FileLockTimeout, ScanError, ArtifactError,
)
from workbuddy_market.fsutil import (         # noqa: E402,F401
    _fsync_dir, atomic_write_bytes, atomic_write_text, write_text_if_changed,
    read_json,
)
from workbuddy_market.hasher import (         # noqa: E402,F401
    fingerprint_from_index, sha256_file, _same_content, normalize_sha256,
)
from workbuddy_market.locking import (        # noqa: E402,F401
    FileLock, locked, _HELD, _NullLock,
)
from workbuddy_market.logging import (        # noqa: E402,F401
    now_iso, _rotate_log, log, _tail_lines, tail_log,
)
from workbuddy_market.version import (        # noqa: E402,F401
    OWNERSHIP_SCHEMA, TX_SCHEMA, STATE_VERSION, MARKET_VERSION,
)
from workbuddy_market.config import (         # noqa: E402,F401
    CLASSIFY_PURPOSES, EXACT_PURPOSES,
    _ID_RE, _REPO_RE, _VER_RE, WINDOWS_RESERVED,
    validate_id, validate_version, ensure_child, collision_key,
    _check_collision, _check_number, validate_repo,
    validate_config, load_config, verify_mode, needs_exact, hash_chunk_bytes,
)
from workbuddy_market.scanner import (        # noqa: E402,F401
    _is_reparse, _walk_tree, _raise_if_errors, _scan, _scan_many,
    file_index, SkillScanCache, _FM_RE, parse_skill_meta,
    _make_excluder, _sub_index,
)
from workbuddy_market.sync import _sync_tree  # noqa: E402,F401
from workbuddy_market.catalog import (        # noqa: E402,F401  （v2.10 新增）
    GH_API, CATALOG_TTL, GH_TIMEOUT,
    SEARCH_LIMIT_DEFAULT, SEARCH_LIMIT_MAX, MAX_QUERY, CATALOG_SCHEMA,
    _gh_request, normalize_repo_payload, validate_query,
    fetch_meta, search_repos, catalog_path,
    load_catalog, save_catalog, is_stale, refresh_catalog,
)
from workbuddy_market.registry import (       # noqa: E402,F401  （v2.11 新增）
    REGISTRY_REPO, REGISTRY_BRANCH, REGISTRY_FILENAME, REGISTRY_TTL,
    REGISTRY_TIMEOUT, REGISTRY_SCHEMA, REGISTRY_RAW_URL, REGISTRY_API_URL,
    ENV_REGISTRY_URL, _registry_http_get, registry_routes,
    local_registry_file, parse_registry, registry_path,
    load_registry_cache, save_registry_cache, get_registry,
)

from workbuddy_market.trash import (         # noqa: E402,F401  （v2.12 R4 新增）
    TRASH_INDEX_PATH, _TRASH_NAME_BAD, _load_trash_index, _save_trash_index,
    _trash_entry, _measure, TrashIndex, move_to_trash, trash_config,
    trash_stats, _safe_mtime, prune_trash,
)
from workbuddy_market.ownership import (     # noqa: E402,F401  （v2.12 R4 新增）
    load_ownership, save_ownership, record_owner, _market_id, forget_owner,
)
from workbuddy_market.transactions import (  # noqa: E402,F401  （v2.12 R4 新增）
    _TX_ACTIVE, tx_path, tx_save, tx_begin, tx_note_staged, tx_note_committed,
    tx_note_removed, tx_drop, tx_settled, tx_release, tx_close, tx_list,
    recover_transactions,
)
from workbuddy_market.installer import (     # noqa: E402,F401  （v2.14 R5 新增）
    INSTALL_MODES, _stage_dir, _sweep_staging, _stage_skill, _commit_staged,
    install_local_plugin, install_package_skills,
)
from workbuddy_market.artifact import (      # noqa: E402,F401  （v2.16 新增）
    MAX_ARTIFACT_BYTES, ARTIFACT_TIMEOUT, _artifact_open,
    download_artifact, unpack_zip, prepare_package, install_from_entry,
)
from workbuddy_market.adapters.workbuddy import (   # noqa: E402,F401  （v2.17 新增）
    WORKBUDDY_ADAPTER_VERSION, read_known, _read_known, read_known_or_die,
    _read_known_or_die, backup_known, _prune_backups, is_registered,
    entry_for, _entry_for, commit_known, _commit_known,
    register, unregister, capabilities, known_health,
)
from workbuddy_market.uninstaller import (   # noqa: E402,F401  （v2.14 R5 新增）
    classify_skill, inspect_skill, plugin_uninstall_plan, uninstall_local_plugin,
    dropped,
)
from workbuddy_market.state import (         # noqa: E402,F401  （v2.19 R6 收尾新增）
    installed_skill_names, installed_repos, build_state,
)
from workbuddy_market.application import (   # noqa: E402,F401  （v2.19 R6 收尾新增）
    sync_packaging, _sync_packaging, build_plugin_json, _plugin_readme,
    OPEN_TARGETS, resolve_open_request, deep_check, selfcheck, main,
)

# re-export 纪律（R4 起的既定决策，v2.19 依然成立）：
#   · 注入点晚绑定要求 re-export 在先 —— state / application 对
#     plugin_uninstall_plan / _scan / recover_transactions / say 的调用
#     在函数体内 `import market_core` 后经本命名空间进行；
#   · WorkBuddy 宿主格式（v2.17）整体在 adapters/workbuddy.py，patch
#     注册链路的读请落点该模块；
#   · quick_fingerprint / tree_hash* 定义在本文件（见下方），其余全部迁包。


# ---------------------------------------------------------------- 小工具
# now_iso / _rotate_log / log 已迁 workbuddy_market.logging（v2.8 R2），此处 re-export。


def say(msg: str = "") -> None:
    print(msg, flush=True)


# ------------------------------------------------------- 运行时迁移（v2.7，R1）

# v2.6 布局散落在仓库根的运行时文件 → v2.7 STATE_HOME 布局。
# 两个 .lock 没有持久语义，不迁移：留在原地是无害遗留（新锁直接在 locks/ 重建）。
_RUNTIME_MIGRATIONS = (
    (".market-state.json", "state.json", False),
    (".ownership.json", "ownership.json", False),
    (".market-log.ndjson", "logs/market.ndjson", False),
    (".market-log.ndjson.1", "logs/market.ndjson.1", False),
    (".market-log.ndjson.2", "logs/market.ndjson.2", False),
    (".market-tx", "tx", True),
    (".backups", "backups", True),
    (".trash", "trash", True),
)


def migrate_runtime_files(quiet: bool = False) -> dict:
    """把 v2.6 留在仓库根的运行时文件搬进 STATE_HOME（v2.7 布局）。

    · 幂等：调用两遍结果一致；目标已存在时以 STATE_HOME 为准，
      仓库侧原件**保留不删**（绝不洗掉用户的文件，工程约定 5）。
    · 原子：同卷走 os.replace；跨卷（C: ↔ D: 等）OSError 退回 shutil.move。
    · 失败不致命：单条失败记入 errors 并告警，下次启动自动重试剩余项。
    · 仅 v2.7 布局生效；legacy 布局（旧自检 / harness）恒为 no-op。
    import market_core 时自动调用一次，也可手工调用检查返回值。
    """
    result = {"mode": "legacy" if _LEGACY_LAYOUT else "v2.7",
              "moved": [], "skipped": [], "errors": []}
    if _LEGACY_LAYOUT:
        return result
    for old_name, new_rel, _is_dir in _RUNTIME_MIGRATIONS:
        src = MARKET_ROOT / old_name
        dst = STATE_HOME / new_rel
        if not src.exists() and not src.is_symlink():
            continue
        if dst.exists() or dst.is_symlink():
            result["skipped"].append({"src": str(src), "dst": str(dst)})
            continue
        try:
            dst.parent.mkdir(parents=True, exist_ok=True)
            try:
                os.replace(src, dst)
            except OSError:
                shutil.move(str(src), str(dst))     # 跨卷回退
            result["moved"].append({"src": str(src), "dst": str(dst)})
        except OSError as exc:
            result["errors"].append({"src": str(src), "error": str(exc)})
    if result["moved"] and not quiet:
        # 全新环境里 logs/ 可能还不存在（.market-log.ndjson 不在迁移清单时）——
        # log() 不会自建父目录，这里补上，保证迁移留痕不静默丢失。
        LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
        LOG_LOCK_PATH.parent.mkdir(parents=True, exist_ok=True)
        log("info", "runtime_migrated", json.dumps(result, ensure_ascii=False))
    if result["errors"] and not quiet:
        log("warn", "runtime_migration_failed",
            json.dumps(result["errors"], ensure_ascii=False))
    return result


def _warn_deprecated_envs() -> None:
    """旧 GHPM_* 环境变量每进程只提醒一次（stderr + 事务日志各一条）。"""
    if not _DEPRECATED_ENVS_USED:
        return
    detail = "; ".join(f"{old} -> {new}" for old, new in _DEPRECATED_ENVS_USED)
    print(f"WARNING: deprecated environment variable(s): {detail}", file=sys.stderr)
    try:
        log("warn", "deprecated_env", detail)
    except Exception:
        pass


# ---------------------------------------------------------------- 文件索引 / 指纹
# _is_reparse / _walk_tree / _raise_if_errors / _scan / _scan_many /
# file_index / SkillScanCache / parse_skill_meta / _make_excluder / _sub_index
# 已迁 workbuddy_market.scanner（v2.9 R3），此处 re-export。
# 注意：包内互调（file_index→_scan、_scan_many→_walk_tree 等）走 scanner
# 命名空间，patch `core._scan/_walk_tree` 只对 core 侧直接调用有效
# （如 _sync_packaging / _stage_skill / prune_trash）；需要拦截包内路径时
# patch workbuddy_market.scanner 里的名字（selftest 第 19 节已按此调整）。


def quick_fingerprint(root: Path, excluded=None) -> dict:
    """廉价指纹：只看文件数 / 总字节 / mtime_ns 的**和与最大值**，不读内容。

    ⚠️ 定位：**候选状态**判定，不是「内容没改」的证明。

    只比 max(mtime_ns) 有个真实盲区：A 文件 mtime=1000（最大），B 文件 mtime=100，
    用户改了 B（内容变了、大小没变、mtime 仍 <= 1000）—— files / bytes / max
    三者可以完全不变。所以这里再加一个 mtime_ns_sum：**任何一个文件的时间戳变了，
    和就会变**，能堵掉绝大多数这类情况（已经不依赖「最大值恰好是那个文件」）。

    但它仍然只是启发式：内容变了而 size 与 mtime 都原样（刻意构造/工具回写）
    依然可能骗过它。因此**破坏性操作一律不用它** —— 见 needs_exact()。
    """
    files, links = _scan(root, excluded)
    return fingerprint_from_index(files, links)


def tree_hash_from_index(root: Path, index: dict, chunk_size: int | None = None) -> str:
    """从**已经扫好的**索引算内容指纹（仍然要读文件内容，但不重扫目录）。"""
    h = hashlib.sha256()
    cs = chunk_size or hash_chunk_bytes()
    base = Path(root)
    for rel in sorted(index):
        h.update(rel.encode("utf-8"))
        h.update(b"\0")
        try:
            h.update(sha256_file(base / rel, cs))
        except OSError:
            h.update(b"<unreadable>")
        h.update(b"\0")
    return h.hexdigest()


def tree_hash(root: Path, excluded=None, chunk_size: int | None = None,
              *, on_error: str = "raise") -> str:
    """目录内容指纹：只跟内容有关（含相对路径），不含时间戳。

    用来判断「这个 skill 还是不是我当初装进去的那个」。**要读全部文件**，
    所以只在需要精确判定时调用（install / uninstall / strict 状态检查）。

    on_error 默认 "raise"：这个哈希会被用来决定「能不能安全卸载」或
    「要不要覆盖」，扫不全时给一个"看起来对得上"的值比报错危险得多。
    """
    return tree_hash_from_index(root, file_index(root, excluded, on_error=on_error),
                                chunk_size)


# ------------------------------------------------------- 模块末尾：迁移触发点
# 放在最后是有意的：迁移要写日志，必须等 FileLock / FileLockTimeout 全部定义完；
# 且对 import 本模块的 market_server / launcher / selftest 同样生效。
_warn_deprecated_envs()
migrate_runtime_files()

if __name__ == "__main__":
    raise SystemExit(main())
