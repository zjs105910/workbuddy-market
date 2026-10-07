"""三层根目录与全部路径常量（v2.8 自 market_core.py 逐字迁入）。

v2.7 起采用三层根目录（「仓库是产品，状态是环境」—— GitHub 开源重构方案 §2）：
  WBM_MARKET_ROOT   市场仓库根：market.config.json / marketplace.json / plugins / web
  WBM_STATE_HOME    运行状态根：state / ownership / tx / trash / backups / locks / logs
  WBM_HOME          WorkBuddy 家目录：skills / known_marketplaces.json
旧名 GHPM_MARKET_ROOT / GHPM_HOME 继续兼容，每进程打一次 deprecation 告警。

运行状态分桶（评审定稿，防同机多 clone 互相污染）：
  · 显式 WBM_STATE_HOME                    → 直接使用（隔离由设置者负责）
  · 仅显式 *MARKET_ROOT（旧自检 / harness）→ 跟随 MARKET_ROOT，文件名沿用 v2.6 旧名，
    完整复刻旧行为（_LEGACY_LAYOUT），迁移逻辑直接跳过
  · 默认（真实使用）                       → ~/.workbuddy-market/markets/<bucket>/
    bucket = <仓库目录名清洗>-<sha256(MARKET_ROOT 绝对路径) 前 12 位>
    目录名人可读，hash 保证同机两个 clone 的锁 / trash / tx 绝不共享。

R2 搬迁注记：v2.7 时本段在 market_core.py 里，仓库根 fallback 是
``Path(__file__).resolve().parent``；迁入 src 布局后改为 ``parents[2]``
（src/workbuddy_market/paths.py → 仓库根），语义不变，是本次搬迁唯一
的必要适配点。
"""
from __future__ import annotations

import hashlib
import os
import re
from pathlib import Path

_DEPRECATED_ENVS_USED: list = []


def _env_root(new_name: str, old_name: str) -> "str | None":
    """新名优先；回退旧名时记录下来，待 log() 可用后统一打一次告警。"""
    v = os.environ.get(new_name)
    if v is not None:
        return v
    v = os.environ.get(old_name)
    if v is not None:
        _DEPRECATED_ENVS_USED.append((old_name, new_name))
        return v
    return None


_WBM_MARKET_ROOT = os.environ.get("WBM_MARKET_ROOT")
_GHPM_MARKET_ROOT = os.environ.get("GHPM_MARKET_ROOT")
_STATE_HOME_EXPLICIT = os.environ.get("WBM_STATE_HOME")

if _WBM_MARKET_ROOT is None and _GHPM_MARKET_ROOT is not None:
    _DEPRECATED_ENVS_USED.append(("GHPM_MARKET_ROOT", "WBM_MARKET_ROOT"))

MARKET_ROOT = Path(
    _WBM_MARKET_ROOT or _GHPM_MARKET_ROOT
    # src/workbuddy_market/paths.py 的上两级 = 仓库根（v2.8 搬迁适配点，
    # v2.7 在 market_core.py 里时是 .parent）
    or Path(__file__).resolve().parents[2]
).resolve()

# legacy 仅指「旧变量名 + 未显式给 WBM_STATE_HOME」的老自检 / harness 场景：
# 完整复刻 v2.6 布局。显式设置**新**变量 WBM_MARKET_ROOT 属于新式用法，
# 一律走 v2.7 布局（默认分桶），不会误入 legacy。
_LEGACY_LAYOUT = (_WBM_MARKET_ROOT is None
                  and _GHPM_MARKET_ROOT is not None
                  and _STATE_HOME_EXPLICIT is None)

if _LEGACY_LAYOUT:
    STATE_HOME = MARKET_ROOT
elif _STATE_HOME_EXPLICIT:
    STATE_HOME = Path(_STATE_HOME_EXPLICIT).resolve()
else:
    def _state_bucket() -> str:
        name = re.sub(r"[^A-Za-z0-9._-]+", "-", MARKET_ROOT.name).strip("-") or "market"
        digest = hashlib.sha256(str(MARKET_ROOT).encode("utf-8")).hexdigest()[:12]
        return f"{name[:40]}-{digest}"
    STATE_HOME = (Path.home() / ".workbuddy-market" / "markets" / _state_bucket()).resolve()

CONFIG_PATH = MARKET_ROOT / "market.config.json"
MANIFEST_DIR = MARKET_ROOT / ".codebuddy-plugin"
MANIFEST_PATH = MANIFEST_DIR / "marketplace.json"
PLUGINS_DIR = MARKET_ROOT / "plugins"
WEB_DIR = MARKET_ROOT / "web"

if _LEGACY_LAYOUT:
    # v2.6 布局：仅存在于旧自检 / 旧 harness 环境，行为不变
    STATE_PATH = MARKET_ROOT / ".market-state.json"
    LOG_PATH = MARKET_ROOT / ".market-log.ndjson"
    BACKUP_DIR = MARKET_ROOT / ".backups"
    TRASH_DIR = MARKET_ROOT / ".trash"
    TX_DIR = MARKET_ROOT / ".market-tx"
    OWNERSHIP_PATH = MARKET_ROOT / ".ownership.json"
    LOCK_PATH = MARKET_ROOT / ".market.lock"
    LOG_LOCK_PATH = MARKET_ROOT / ".market-log.lock"
    CATALOG_PATH = MARKET_ROOT / ".market-catalog.json"
    REGISTRY_PATH = MARKET_ROOT / ".market-registry.json"
else:
    # v2.7 布局：运行状态离开 Git 仓库，收进 STATE_HOME
    STATE_PATH = STATE_HOME / "state.json"
    LOG_PATH = STATE_HOME / "logs" / "market.ndjson"
    BACKUP_DIR = STATE_HOME / "backups"
    TRASH_DIR = STATE_HOME / "trash"
    TX_DIR = STATE_HOME / "tx"
    OWNERSHIP_PATH = STATE_HOME / "ownership.json"
    LOCK_PATH = STATE_HOME / "locks" / "market.lock"
    LOG_LOCK_PATH = STATE_HOME / "locks" / "log.lock"
    CATALOG_PATH = STATE_HOME / "catalog.json"
    REGISTRY_PATH = STATE_HOME / "registry.json"

WB = Path(_env_root("WBM_HOME", "GHPM_HOME") or (Path.home() / ".workbuddy")).resolve()
SKILLS_DIR = WB / "skills"
KNOWN_PATH = WB / "plugins" / "known_marketplaces.json"
GITHUB_REGISTRY = WB / "github-projects.json"

GHPM_PY = SKILLS_DIR / "github-project-manager" / "scripts" / "ghpm.py"
# 注：GHPM_PY 是「可选远端任务执行器」的本机路径常量（不是环境变量），
# R6 拆 api/ 时改名为 REMOTE_JOB_TOOL；__GHPM__ 事件前缀是外部协议适配，保留。

# ---- 体量常量（方案 §3.1 归 paths.py；hasher / logging / registry 都要用） ----
LOG_MAX_BYTES = 10 * 1024 * 1024      # 单份日志上限，超过就 rotate
LOG_KEEP = 2                          # 保留 .1 / .2 两份历史
BACKUP_KEEP = 20                      # known_marketplaces 备份保留份数
HASH_CHUNK_BYTES = 1024 * 1024        # 流式 SHA-256 的默认块大小（可被配置覆盖）
