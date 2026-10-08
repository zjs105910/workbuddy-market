# -*- coding: utf-8 -*-
"""adapters.workbuddy —— WorkBuddy 宿主适配层（v2.17 新增，R6 半程）。

这个包从 v1 起就知道很多 WorkBuddy 的内部细节：known_marketplaces.json
的形状、marketplace 条目字段、备份目录约定…… v2.16 之前这些知识散落在
market_core 的注册段里。宿主程序未来最容易变化的就是这些东西
（WorkBuddy 5.x / 6.x 的市场协议、安装位置、条目格式），所以现在把
**所有「WorkBuddy 宿主格式」的读写收进这一层**，内核只经它触碰宿主。

职责（全部自 market_core.py 逐字迁入，v2.17）：

  · known_marketplaces.json 的读取（含 strict 口径：坏了宁可报错也不覆盖）；
  · 备份（纳秒戳）与轮转；
  · 条目构造（directory 型市场）；
  · 乐观合并写入（_commit_known，与 WorkBuddy 自身写入竞争的防线）；
  · register / unregister 编排；
  · capabilities()：宿主能力矩阵（未来版本探测的落点）；
  · known_health()：known 文件的健康检查（deep_check 消费）。

注入点纪律（R4/R5 延续）：register() 依赖 core 的 _sync_packaging（注入点），
在调用点晚绑定 ``import market_core``。本模块内部的互调（register →
_commit_known → _read_known_or_die）走**本模块命名空间** —— selftest 的
patch 落点随迁 ``workbuddy_market.adapters.workbuddy``（与 R4 把
ownership/trash 的 patch 落点迁到包内同一先例）。core 侧名字全部
re-export，``core.register`` / ``core._read_known_or_die`` 仍是同一对象，
但 **patch 语义随迁**：要拦截注册链路里的读，请 patch 本模块。

未来 WorkBuddy 6.x 若改了市场格式，改这一个文件就够了 —— 这就是
adapter 的意义。
"""
from __future__ import annotations

import json
import shutil
import time
from datetime import datetime, timezone
from pathlib import Path

from ..config import ConfigError, load_config
from ..fsutil import atomic_write_text, read_json
from ..locking import locked
from ..logging import log
from ..paths import BACKUP_DIR, BACKUP_KEEP, KNOWN_PATH, MARKET_ROOT

WORKBUDDY_ADAPTER_VERSION = 1

# 宿主能力矩阵：未来探测宿主版本后按版本收紧/放开。
# 现在如实标注当前已实现/已验证的能力（v2.17 口径）。
_CAPABILITIES = {
    "marketplace_register": True,      # 写 known_marketplaces.json
    "marketplace_unregister": True,
    "directory_market": True,          # directory 型市场源
    "skill_install_location": True,    # 直写 ~/.workbuddy/skills
    "security_scan": False,            # 宿主侧安装前扫描：未验证，不虚报
    "skill_enable": False,             # 宿主侧启用/禁用开关：未实现
    "auto_update": False,              # 宿主自动更新本市场：显式关闭
}


def capabilities() -> dict:
    """宿主能力矩阵（诚实口径：没验证过的能力一律 False，不虚报）。"""
    return dict(_CAPABILITIES)


# ---------------------------------------------------------------- known 读取

def read_known(strict: bool = False) -> dict:
    """读 known_marketplaces.json。

    strict=True 时，文件存在但读不出来会**抛 ConfigError**，而不是当成空表。
    这一点很关键：如果当成空表，register() 就会拿一个只含自己一条的记录
    去覆盖原文件 —— 用户其它几个市场（包括 WorkBuddy 自带的）会被直接抹掉。
    宁可报错让用户去 .backups 里恢复，也不能替用户把数据删了。
    """
    data = read_json(KNOWN_PATH, None, strict=strict)
    if data is None:
        return {}
    if not isinstance(data, dict):
        if strict:
            raise ConfigError(f"{KNOWN_PATH.name} 的顶层必须是一个对象，实际是 {type(data).__name__}")
        return {}
    return data


def read_known_or_die() -> dict:
    """写操作前读 —— 文件坏了就拒绝继续，绝不覆盖。"""
    if not KNOWN_PATH.is_file():
        return {}
    try:
        return read_known(strict=True)
    except ConfigError as exc:
        raise RuntimeError(
            f"拒绝覆盖：{KNOWN_PATH.name} 已损坏，读不出来。\n"
            f"  原因：{exc}\n"
            f"  文件：{KNOWN_PATH}\n"
            f"  备份：{BACKUP_DIR}（挑一份改名成 known_marketplaces.json 即可恢复）\n"
            "  修好或删掉它再重试。"
        ) from exc


def backup_known() -> Path | None:
    """备份 known_marketplaces.json。

    时间戳带纳秒，避免同一秒内两次备份互相覆盖
    （v1 用秒级戳 + 「已存在就返回」会让第二次修改没有备份）。
    """
    if not KNOWN_PATH.is_file():
        return None
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    stamp = time.strftime("%Y%m%d-%H%M%S") + f"-{time.time_ns() % 1_000_000_000:09d}"
    dst = BACKUP_DIR / f"known_marketplaces.{stamp}.json"
    shutil.copy2(KNOWN_PATH, dst)
    log("info", "backup", f"已备份 known_marketplaces.json → {dst.name}")
    return dst


def _prune_backups(keep: int = BACKUP_KEEP) -> None:
    if not BACKUP_DIR.is_dir():
        return
    items = sorted(BACKUP_DIR.glob("known_marketplaces.*.json"))
    if len(items) <= keep:
        return
    for old in items[: len(items) - keep]:
        try:
            old.unlink()
        except OSError:
            pass


def is_registered(cfg: dict | None = None) -> bool:
    cfg = cfg or load_config()
    return cfg.get("marketId") in read_known()


def entry_for(cfg: dict) -> dict:
    """本市场在 known_marketplaces.json 里的条目（directory 型）。"""
    return {
        "manifestName": cfg.get("marketId", "wb-local-market"),
        "type": "directory",
        "source": {"source": "directory", "path": str(MARKET_ROOT)},
        "installLocation": str(MARKET_ROOT),
        "description": cfg.get("description", ""),
        "lastUpdated": datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z"),
        "autoUpdate": False,
        "isBuiltIn": False,
    }


def commit_known(mutate, *, attempts: int = 4, what: str = "修改"):
    """对 known_marketplaces.json 做乐观合并写入。

    WorkBuddy 自己也会改这个文件（autoUpdate 市场刷新 lastUpdated、zip 地址
    换成带内容哈希的版本），而它**不抢我们这把锁**。原来的
    「读 → 改 → 原子写 → 读回校验」只能发现「整个条目消失」，
    发现不了「某个市场的字段在中间被别人改了、又被我们整份覆盖回去」。

    改成：落笔之前再读一次，确认和我们读到的快照一模一样才写；
    不一样就基于最新内容重新合并。这把竞争窗口从「整个读-改-写过程」
    压到了「重读到 replace 之间的几十微秒」。

    返回 (before, candidate)。mutate 返回 False 表示无需改动（提前收工）。
    """
    for attempt in range(attempts):
        before = read_known_or_die()
        candidate = mutate(dict(before))
        if candidate is False:
            return before, None
        latest = read_known_or_die()
        if latest != before:
            log("warn", "register",
                f"{what}前发现 {KNOWN_PATH.name} 已被外部改动"
                f"（第 {attempt + 1} 次），基于最新内容重新合并")
            continue
        backup_known()
        atomic_write_text(KNOWN_PATH,
                          json.dumps(candidate, ensure_ascii=False, indent=2) + "\n",
                          durable=True)
        _prune_backups()
        after = read_known()
        lost = set(before) - set(after)
        if lost:
            log("warn", "register",
                f"检测到写回期间有市场消失：{', '.join(sorted(lost))}（WorkBuddy 可能同时在写）")
        return before, after
    raise RuntimeError(
        f"{what}失败：{KNOWN_PATH.name} 被反复改写（{attempts} 次都撞车）。\n"
        "如果 WorkBuddy 正在运行，稍后再试一次即可；文件没有被写坏。"
    )


# ---------------------------------------------------------------- 注册 / 撤销

def register(force: bool = False) -> bool:
    """把本市场写进 known_marketplaces.json。幂等；返回是否发生了改动。

    WorkBuddy 运行时会自己改写这个文件，所以并发保护有两层：
      · 全程持文件锁 → 防本工具自己的多个进程互相覆盖（lost update）
      · 乐观合并（读 → 改 → 重读 → 比对 → 写）→ 缩小与 WorkBuddy 自身写入的竞争窗口
    """
    import market_core as _core          # noqa: PLC0415 —— _sync_packaging 注入点晚绑定
    with locked():
        cfg = load_config()
        mid = cfg.get("marketId", "wb-local-market")

        if not _core.MANIFEST_PATH.is_file():
            _core._sync_packaging(quiet=True)

        entry = entry_for(cfg)

        # 比较时忽略 lastUpdated，否则每次启动都会重写一遍这个文件
        def _same(a: dict, b: dict) -> bool:
            return ({k: v for k, v in a.items() if k != "lastUpdated"}
                    == {k: v for k, v in b.items() if k != "lastUpdated"})

        def _mutate(known: dict):
            if not force and isinstance(known.get(mid), dict) and _same(known[mid], entry):
                return False
            known[mid] = entry
            return known

        before, after = commit_known(_mutate, what="注册")
        if after is None:
            log("info", "register", "已注册且条目未变，跳过")
            return False
        if mid not in after:
            log("warn", "register", "写回后本市场条目不见了 —— WorkBuddy 可能同时改写了该文件")
            raise RuntimeError("写回校验失败：注册条目未生效（可能和 WorkBuddy 的自动更新撞车，重跑一次即可）")
        log("info", "register", f"已注册市场 {mid} → {MARKET_ROOT}")
        return True


def unregister() -> bool:
    with locked():
        cfg = load_config()
        mid = cfg.get("marketId", "wb-local-market")

        def _mutate(known: dict):
            if mid not in known:
                return False
            del known[mid]
            return known

        before, after = commit_known(_mutate, what="撤销注册")
        if after is None:
            log("info", "unregister", "本来就没注册，跳过")
            return False
        log("info", "unregister", f"已撤销注册 {mid}")
        return True


# ---------------------------------------------------------------- 体检

def known_health() -> str | None:
    """known_marketplaces.json 的健康检查。正常返回 None；有问题返回人话。

    deep_check（core）消费它 —— 宿主格式的问题由 adapter 自己诊断，
    内核不再直接解读这个文件的形状。
    """
    if not KNOWN_PATH.parent.is_dir():
        return f"WorkBuddy 插件目录不存在：{KNOWN_PATH.parent}"
    if KNOWN_PATH.is_file():
        try:
            read_json(KNOWN_PATH, None, strict=True)
        except ConfigError as exc:
            return f"known_marketplaces.json 不可用：{exc}"
    return None


# v2.17 之前的旧名字（market_core / 第三方老脚本可能引用）：同一对象。
_read_known = read_known
_read_known_or_die = read_known_or_die
_entry_for = entry_for
_commit_known = commit_known
