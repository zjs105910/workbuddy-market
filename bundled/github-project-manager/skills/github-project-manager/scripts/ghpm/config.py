# -*- coding: utf-8 -*-
"""ghpm 全局配置：路径、环境变量、安全上限。

所有路径常量在 **import 时**从环境变量解析一次（GHPM_HOME 等）。
需要换目录（测试）时，请清掉 sys.modules 里的 ``ghpm*`` 再重新 import，
不要指望改环境变量能让已经 import 的模块换路径 —— 那正是 v3.2 用
GHPM_HOME 做测试隔离时最容易踩的坑。

v4 说明：可变的旋钮（BACKUP_MODE / FETCH_WORKERS）不要 from-import 出值，
请用 backup_mode() / fetch_workers() 在**调用时**读，否则测试改了 config
里的值而别的模块拿到的还是旧副本。
"""
from __future__ import annotations

import os
import re
from pathlib import Path

# ---------- 路径 ----------
HOME = Path.home()
WB = Path(os.environ.get("GHPM_HOME") or (HOME / ".workbuddy"))
SKILLS = WB / "skills"
REGISTRY = WB / "github-projects.json"
CACHE = WB / ".ghpm-cache"
LOCK = WB / ".ghpm.lock"

# ---------- 正则 ----------
# 只用于「从自由文本里捞 URL」（SKILL.md / README 扫描）。parse_repo 走 urlparse 严格校验。
GH_RE = re.compile(r"https://github\.com/([A-Za-z0-9_.-]+)/([A-Za-z0-9_.-]+)")
OWNER_RE = re.compile(r"^[A-Za-z0-9](?:[A-Za-z0-9_.-]*)$")

# ---------- 网络 ----------
TIMEOUT = os.environ.get("GHPM_TIMEOUT") or "180"
# 下载源：第一个为主源，其余为镜像前缀（主源不可达时依次回退，仿 DSH fallbackRegistries）
CODELOAD = "https://codeload.github.com/%s/zip/refs/heads/%s"
DEFAULT_MIRRORS = ["", "https://ghfast.top/", "https://gh-proxy.com/"]
_env_mirrors = [p.strip() for p in (os.environ.get("GHPM_MIRRORS") or "").split(",") if p.strip()]
MIRROR_PREFIXES = _env_mirrors or list(DEFAULT_MIRRORS)
if MIRROR_PREFIXES[0] != "":
    MIRROR_PREFIXES = [""] + MIRROR_PREFIXES   # 主源永远排第一

GH_TOKEN = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN") or ""

# ---------- 缓存 ----------
# 远程信息缓存：check/inspect/scan/update 预检用它挡住重复请求。
# 装/更新本身必须拿最新 sha，永远 ttl=0。设 GHPM_CACHE_TTL=0 可全局关闭。
try:
    CACHE_TTL = float(os.environ.get("GHPM_CACHE_TTL", "60"))
except Exception:
    CACHE_TTL = 60.0
CACHE_MAX_FILES = 200

# ---------- 清单 ----------
# v4：新增 content_hash / skill_hashes，用于 verify 发现「本地被改过」。
REGISTRY_SCHEMA_VERSION = 4

# ---------- 体积常量 ----------
MIB = 1024 * 1024
# 预检留出固定余量，覆盖清单临时文件、目录元数据和压缩率估算误差。
DISK_SAFETY_BYTES = 64 * MIB

# ---------- ZIP 安全上限 ----------
# codeload 官方包一般远低于这些值；镜像不是我们自己运维的，所以自己设天花板。
# 单 skill 仓库偶尔带大 fixture（几百 MB），单文件上限给到 512 MB。
MAX_ZIP_ENTRIES = 100_000
MAX_ZIP_UNCOMPRESSED = int(os.environ.get("GHPM_MAX_ZIP_UNCOMPRESSED", 2 * 1024 * MIB))
MAX_ZIP_FILE_SIZE = int(os.environ.get("GHPM_MAX_ZIP_FILE_SIZE", 512 * MIB))
# 压缩比上限：合法文本（尤其日志 / 语料 / 重复 JSON）能到几百倍，
# 所以阈值放得比较宽松，只拦真正的压缩炸弹。
MAX_ZIP_RATIO = 2000

# ---------- 并发 ----------
BACKUP_MODES = ("link", "rename", "copy")
_BACKUP_MODE_RAW = (os.environ.get("GHPM_BACKUP_MODE") or "link").strip().lower()
BACKUP_MODE = _BACKUP_MODE_RAW if _BACKUP_MODE_RAW in BACKUP_MODES else "link"

try:
    FETCH_WORKERS = max(1, min(16, int(os.environ.get("GHPM_WORKERS", "8"))))
except Exception:
    FETCH_WORKERS = 8


def backup_mode() -> str:
    """备份介质。**调用时**读 config.BACKUP_MODE，方便测试与宿主动态切换。

    v3.2 只有 link / copy；v4 加了 rename（同卷整目录 rename，O(1)，
    代价是写入期间原目录不在原位）。这里必须把三种都放行 ——
    校验写成只认 link/copy 的话，rename 会被静默降级成 link，
    测试和用户都会以为它生效了。
    """
    return BACKUP_MODE if BACKUP_MODE in BACKUP_MODES else "link"


def fetch_workers() -> int:
    """批量查询并发数。同样在调用时读，避免别处缓存了旧值。"""
    try:
        return max(1, min(16, int(FETCH_WORKERS)))
    except Exception:
        return 8


# ---------- 指纹 ----------
# 指纹用于 verify 判断「本地 skill 是否被手动改过」。
# 小于该阈值的文件连内容一起哈希，大文件只记路径+大小（避免 verify 变成全量读盘）。
FP_CONTENT_MAX = 64 * 1024

# ---------- 锁 ----------
# 心跳：长任务（下载几百 MB）期间周期性 touch 锁文件续租。
# 陈旧判定仍以「持有者进程是否还活着」为准，心跳只在拿不到 pid 结论时兜底。
LOCK_HEARTBEAT_SEC = 5.0
LOCK_LEASE_SEC = float(os.environ.get("GHPM_LOCK_LEASE") or 900)
