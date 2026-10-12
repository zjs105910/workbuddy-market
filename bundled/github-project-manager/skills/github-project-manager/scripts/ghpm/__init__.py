# -*- coding: utf-8 -*-
"""ghpm - GitHub 开源项目管理工具 v4.0

管理从 GitHub 下载到本机的开源项目（尤其是 skill 包）：
预检、安装、列出、扫描发现、检查更新、一键更新、移除、回滚、校验、诊断。

包结构（v4 相对 v3.2 单文件 2721 行的拆分）：

    config.py       路径 / 环境变量 / 安全上限
    errors.py       错误码与异常
    models.py       TreeStats / SourceIndex / RepoInfo / InstallPlan
    util.py         时间戳、原子写、单次遍历、指纹、事件输出
    pathguard.py    路径 containment（删除类操作统一收口）
    lock.py         写锁 + 心跳租约
    registry.py     清单读写与迁移
    discovery.py    skill 发现（与体积统计共用一次遍历）
    remote.py       Provider（api / ungh / atom）+ 解析器 + 缓存 + 下载
    archive.py      ZIP 索引、安全上限、文件名校验、安全解压
    transaction.py  事务与回滚
    installer.py    resolve → fetch → inspect → plan → apply
    verifier.py     数据完整性检查
    commands/       各命令
    cli.py          argparse 与分发

调用入口保持兼容：``python scripts/ghpm.py <cmd>`` 行为与 v3.2 一致，
``__GHPM__`` 事件协议只增不改。也可以 ``import ghpm`` 直接用下面的公开 API
（本文件把它们再导出，测试与宿主的用法不需要改）。
"""
from __future__ import annotations

__version__ = "4.0.0"

from . import config, errors, models, util  # noqa: F401  子模块可直取

# ---- 基础 ----
from .config import (WB, SKILLS, REGISTRY, CACHE, LOCK, MIB,      # noqa: F401
                     CACHE_TTL, CACHE_MAX_FILES, REGISTRY_SCHEMA_VERSION,
                     DISK_SAFETY_BYTES, MAX_ZIP_ENTRIES, MAX_ZIP_UNCOMPRESSED,
                     MAX_ZIP_FILE_SIZE, MAX_ZIP_RATIO, FP_CONTENT_MAX,
                     LOCK_LEASE_SEC, LOCK_HEARTBEAT_SEC, backup_mode, fetch_workers)
from .errors import (E_ALREADY, E_BAD_ARCHIVE, E_CANCELLED, E_CONFLICT,  # noqa: F401
                     E_INVALID_SPEC, E_LOCKED, E_NETWORK, E_NOT_FOUND, E_NOT_SKILL,
                     E_TIMEOUT, E_UNSAFE_PATH, E_WRITE, BadArchiveError, ConflictError,
                     HttpError, NotSkillError, UnsafePathError)
from .models import InstallPlan, RepoInfo, SourceIndex, TreeStats  # noqa: F401
from .util import (atomic_copy, atomic_write_bytes, classify_write_error,  # noqa: F401
                   dir_size_mb, disk_free_bytes, emit, ensure_disk_space,
                   estimate_install_bytes, fmt_ts, format_bytes, iter_tree, now,
                   path_size_bytes, remove_path, run, safe_key, scan_tree,
                   tree_fingerprint)

# ---- 安全与锁 ----
from .pathguard import (is_within, remove_managed_path, skill_dir,  # noqa: F401
                        validate_managed_path, validate_skill_name)
from .lock import (Heartbeat, LockSession, acquire_lock, lock_heartbeat_age,  # noqa: F401
                   lock_is_stale, pid_alive, read_lock, release_lock)

# ---- 清单 ----
from .registry import (dir_ts, drop_project, empty_registry, find_project,  # noqa: F401
                       find_skill_conflicts, load, migrate_registry, persist_checked_at,
                       project_id, save, skill_owner_map, source_dir_for, upsert_project)

# ---- 远程 ----
from .remote import (AtomProvider, GitHubApiProvider, RemoteProvider,  # noqa: F401
                     RemoteResolver, UnghProvider, atom_latest, cache_clear,
                     classify_net_error, curl_download, curl_json, download_repo_zip,
                     fetch_repo_infos, parse_repo, repo_info, repo_skill_index,
                     repo_skill_names, ungh_files, ungh_meta)

# ---- 归档 / 事务 / 安装 ----
from .archive import (check_zip_limits, check_zip_names, fetch_zip,  # noqa: F401
                      safe_extract, zip_content_index)
from .transaction import (Transaction, move_or_copy_tree, read_manifest,  # noqa: F401
                          report_rollback, restore_backup)
from .installer import (apply_install_plan, build_install_plan, commit_registry,  # noqa: F401
                        install, install_targets, plan_root)
from .discovery import find_skill_dirs, index_source_tree, match_skill_path  # noqa: F401

# ---- 数据校验 ----
from .verifier import find_orphans, verify_all, verify_project  # noqa: F401

# ---- 命令 ----
from .commands.basic import cmd_doctor, cmd_list, cmd_rollback, cmd_unlock  # noqa: F401
from .commands.inspect import cmd_inspect  # noqa: F401
from .commands.add import cmd_add  # noqa: F401
from .commands.update import UpdateRequest, UpdateResult, Updater, cmd_update  # noqa: F401
from .commands.remove import cmd_remove  # noqa: F401
from .commands.scan import cmd_scan  # noqa: F401
from .commands.verify import cmd_verify  # noqa: F401
from .cli import cmd_check, main  # noqa: F401

__all__ = ["main", "config", "errors", "models", "util", "__version__"]
