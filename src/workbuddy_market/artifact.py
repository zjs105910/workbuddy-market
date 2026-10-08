# -*- coding: utf-8 -*-
"""artifact —— 不可变 Market Package 的分发链（v2.16 新增）。

v2.15 冻结了协议（docs/plugin-spec.md v0.2）：分发单元 = CI 构建的
**不可变 artifact**，安装端只信哈希。本轮把链路真正闭环：

    Registry（packageUrl + packageHash）
      → download_artifact   流式下载 + 边下边算 sha256 + 超限即断
      → unpack_zip          zip-slip / 链接成员 / zip bomb 三道防线
      → verify_package      packaging 纯函数层，按攻击面校验
      → install_package_skills（installer 两阶段事务安装）

在此之前安装走的是「Registry → GitHub repo → ghpm → 当前 HEAD」，
装到的是活的代码；这条新链装到的是**审核时固定的那一份字节** ——
上游漂移在 artifact 链路里天然不存在（哈希钉死的就是那一份）。

安全纪律：

  · **哈希对不上没有放行一说。** packageHash 是审核时固定的那一份，
    对不上就是整包拒绝 —— 没有 --allow-non-skill 那种 force 出口；
  · 下载流式分块，内存 O(chunk)，绝不把整个包读进内存（约定 8/19）；
  · zip 是不可信输入，按攻击面处理：zip-slip / 绝对路径 / 链接成员 /
    解压总量上限，全部 fail-closed，失败清理无半截状态；
  · 条目没有成套的 artifact 字段 → 诚实报错，绝不静默退回 ghpm
    （「看起来走了校验链、实际走的是 clone」是最坏的降级方式）。

网络接缝只有一个：``_artifact_open(url)``（返回 response 对象）。
自检 monkeypatch 这个名字给假流，离线测完全部链路（老纪律）。
"""
from __future__ import annotations

import hashlib
import os
import re
import shutil
import time
import urllib.request
import zipfile
from pathlib import Path

from .config import ConfigError, ensure_child
from .errors import ArtifactError
from .hasher import normalize_sha256
from .logging import log
from .version import MARKET_VERSION

MAX_ARTIFACT_BYTES = 256 * 1024 * 1024     # 下载与解压共用的总量上限（zip bomb 防线）
ARTIFACT_TIMEOUT = 120.0                   # 下载超时（秒）—— 包比注册表大得多
DOWNLOAD_CHUNK = 1024 * 1024               # 流式分块（与 hasher 同一量级）

_URL_RE = re.compile(r"^https?://", re.IGNORECASE)


# ---------------------------------------------------------------- 接缝

def _artifact_open(url: str, timeout: float = ARTIFACT_TIMEOUT):
    """artifact 下载的唯一网络接缝。测试 monkeypatch 这个名字。

    返回 response 对象（支持上下文管理器 + read(chunk)），由调用方
    流式消费 —— 接缝本身不做任何缓冲，保证「假接缝」与真网络行为一致。
    """
    req = urllib.request.Request(url, headers={
        "User-Agent": f"workbuddy-market/{MARKET_VERSION}",
    })
    return urllib.request.urlopen(req, timeout=timeout)


# ---------------------------------------------------------------- 下载

def download_artifact(url: str, dest_dir, *, expected_hash=None,
                      size_limit: int = MAX_ARTIFACT_BYTES,
                      timeout: float = ARTIFACT_TIMEOUT,
                      fetch=None) -> dict:
    """流式下载 artifact，边下边算 sha256，超限即断。

    · 内存 O(chunk)（约定 8/19）；.part 临时文件 + os.replace 原子落位；
    · expected_hash 给了就对不上即失败 —— 供应链校验，无放行出口；
      落位文件名取内容哈希前 16 位（不可变命名：同一份内容永远同一名字）；
    · size_limit 超限立即断流：恶意 zip 可以声明很小、实际巨大，
      所以在**读取路径**上数，不信任 Content-Length。
    · 失败清理 .part，绝不留半截文件。

    返回 {"ok", "path", "sha256", "bytes"}；失败抛 ArtifactError / OSError。
    """
    url = str(url or "")
    if not _URL_RE.match(url):
        raise ArtifactError(f"artifact URL 必须是 http(s)：{url[:120]!r}")
    want = normalize_sha256(expected_hash) if expected_hash is not None else None
    if expected_hash is not None and want is None:
        raise ArtifactError(f"expected_hash 不是合法的 sha256：{expected_hash!r}")
    if fetch is None:
        fetch = _artifact_open
    dest_dir = Path(dest_dir)
    dest_dir.mkdir(parents=True, exist_ok=True)
    part = dest_dir / f".artifact-{os.getpid()}-{time.time_ns() % 1_000_000:06d}.part"
    h = hashlib.sha256()
    total = 0
    try:
        with fetch(url, timeout=timeout) as resp:
            with part.open("wb") as fh:
                while True:
                    chunk = resp.read(DOWNLOAD_CHUNK)
                    if not chunk:
                        break
                    total += len(chunk)
                    if total > size_limit:
                        raise ArtifactError(
                            f"artifact 超过大小上限（>{size_limit} 字节），已中止下载")
                    fh.write(chunk)
                    h.update(chunk)
        got = h.hexdigest()
        if want and got != want:
            raise ArtifactError(
                f"artifact 哈希不符：期望 {want[:12]}…，实际 {got[:12]}…"
                "（供应链校验，无放行）")
        final = dest_dir / f"{got[:16]}.zip"
        os.replace(part, final)
        return {"ok": True, "path": final, "sha256": got, "bytes": total}
    except BaseException:
        try:
            part.unlink()
        except OSError:
            pass
        raise


# ---------------------------------------------------------------- 解包

def unpack_zip(zip_path, dest_dir, *, size_limit: int = MAX_ARTIFACT_BYTES) -> dict:
    """安全解包 zip（不可信输入，按攻击面处理）。

    防线（任何一项触发即整包拒绝，清理 dest_dir 无半截状态）：

      1. zip-slip：成员名带 ``..`` 段 / 绝对路径 / 盘符 → 拒绝，
         且每个目标路径再过 ``ensure_child()``（穿越零容忍，与全项目同一道闸）；
      2. 反斜杠归一：Windows 下造出的恶意 zip 可用 ``\\`` 绕过 ``/`` 检查，
         统一替换成 ``/`` 再判；
      3. 链接 / 非常规成员：Unix mode 高位存在且不是普通文件 / 目录 → 拒绝
         （与「链接防线三层闭环」同一纪律 —— 解包阶段绝不产生重解析点）；
      4. zip bomb：累计解压字节数超 size_limit → 拒绝。声明值（file_size）
         与实际写出量都数，声明可以撒谎，实际写出数不了。

    返回 {"ok", "dir", "files", "bytes"}；失败抛 ArtifactError。
    """
    zip_path, dest_dir = Path(zip_path), Path(dest_dir)
    shutil.rmtree(dest_dir, ignore_errors=True)
    dest_dir.mkdir(parents=True, exist_ok=True)
    files = bytes_total = 0
    try:
        with zipfile.ZipFile(zip_path) as zf:
            for zi in zf.infolist():
                name = zi.filename
                if not isinstance(name, str) or not name.strip():
                    raise ArtifactError(f"zip 成员名非法：{name!r}")
                if name.startswith(("/", "\\")) or re.match(r"^[A-Za-z]:", name):
                    raise ArtifactError(f"zip 成员是绝对路径（zip-slip）：{name!r}")
                norm = name.replace("\\", "/")
                if ".." in norm.split("/"):
                    raise ArtifactError(f"zip 成员含 .. 段（zip-slip）：{name!r}")
                mode = zi.external_attr >> 16
                ftype = mode & 0o170000
                # 注意：只看类型位。很多 zip 的 external_attr 只有纯权限位
                # （如 0o600<<16，类型位为 0）—— 那是普通文件，不能误杀。
                if ftype and ftype not in (0o100000, 0o040000):
                    raise ArtifactError(
                        f"zip 含符号链接 / 非常规成员，拒绝解包：{name!r}")
                target = ensure_child(dest_dir, dest_dir / norm)
                if zi.is_dir() or norm.endswith("/"):
                    target.mkdir(parents=True, exist_ok=True)
                    continue
                declared = int(zi.file_size)
                if bytes_total + declared > size_limit:
                    raise ArtifactError(
                        f"zip 解压总量超过上限（>{size_limit} 字节），拒绝（zip bomb 防线）")
                target.parent.mkdir(parents=True, exist_ok=True)
                with zf.open(zi) as src, target.open("wb") as dst:
                    while True:
                        chunk = src.read(DOWNLOAD_CHUNK)
                        if not chunk:
                            break
                        bytes_total += len(chunk)
                        if bytes_total > size_limit:
                            raise ArtifactError(
                                f"zip 实际解压量超过上限（>{size_limit} 字节），拒绝")
                        dst.write(chunk)
                files += 1
        return {"ok": True, "dir": dest_dir, "files": files, "bytes": bytes_total}
    except ArtifactError:
        shutil.rmtree(dest_dir, ignore_errors=True)
        raise
    except (OSError, zipfile.BadZipFile, ConfigError) as exc:
        shutil.rmtree(dest_dir, ignore_errors=True)
        raise ArtifactError(f"zip 解包失败：{exc}") from exc


# ---------------------------------------------------------------- 编排

def prepare_package(source, work_dir, *, expected_package_hash=None,
                    expected_manifest_hash=None, force: bool = False,
                    size_limit: int = MAX_ARTIFACT_BYTES,
                    timeout: float = ARTIFACT_TIMEOUT,
                    fetch=None) -> dict:
    """artifact（http(s) URL 或本地 zip 路径）→ 解包 → verify → 可安装的包目录。

    哈希语义（两回事，别混）：

      · ``packageHash``（manifest 口径）= 包**内容**的 content_hash ——
        解包后由 verify_package 重算，与注册表固定值比对。zip 容器
        （压缩 / 条目顺序）不影响它，这才是供应链要钉死的值；
      · zip 文件自身的 sha256 是另一码事，注册表不携带（未来若加
        artifactSha256 字段，走 download_artifact 的 expected_hash）。

    所以这里的校验全部发生在**解包之后**：verify 不过 / packageHash 或
    manifestHash 与注册表固定值不符 → {"ok": False, "errors": [...]}，
    工作目录清理。fail-closed：任何失败路径都不把半截包交出去。
    """
    from .packaging import verify_package          # noqa: PLC0415 —— 避免加重 import 环
    work_dir = Path(work_dir)
    shutil.rmtree(work_dir, ignore_errors=True)
    work_dir.mkdir(parents=True, exist_ok=True)

    def _fail(errors, warnings=()):
        shutil.rmtree(work_dir, ignore_errors=True)
        return {"ok": False, "errors": list(errors), "warnings": list(warnings)}

    try:
        s = str(source or "")
        if _URL_RE.match(s):
            dl = download_artifact(s, work_dir, size_limit=size_limit,
                                   timeout=timeout, fetch=fetch)
            zip_path = Path(dl["path"])
        else:
            zip_path = Path(s)
        pkg_dir = work_dir / "pkg"
        unpack_zip(zip_path, pkg_dir, size_limit=size_limit)
        v = verify_package(pkg_dir, force=force)
        if not v["ok"]:
            return _fail(v["errors"], v["warnings"])
        errors: list[str] = []
        want_pkg = normalize_sha256(expected_package_hash) if expected_package_hash else None
        if want_pkg and v.get("packageHash") != want_pkg:
            errors.append(
                f"包内容哈希（packageHash）与注册表固定值不符："
                f"期望 {want_pkg[:12]}…，实际 {str(v.get('packageHash'))[:12]}…")
        want_man = normalize_sha256(expected_manifest_hash) if expected_manifest_hash else None
        man_hash = (v.get("manifest") or {}).get("integrity", {}).get("manifest")
        if want_man and man_hash != want_man:
            errors.append(
                f"manifest 哈希与注册表固定值不符：期望 {want_man[:12]}…，"
                f"实际 {str(man_hash)[:12]}…")
        if errors:
            return _fail(errors, v["warnings"])
        return {"ok": True, "pkg": pkg_dir, "manifest": v["manifest"],
                "packageHash": v["packageHash"], "warnings": list(v["warnings"])}
    except BaseException:
        shutil.rmtree(work_dir, ignore_errors=True)
        raise


def install_from_entry(entry: dict, *, mode: str = "missing", force: bool = False,
                       progress=None, fetch=None, work_root=None) -> dict:
    """注册表条目 → 不可变 artifact → verify → 两阶段事务安装（v2.16 主链路）。

    · 条目没有成套的 packageUrl + packageHash → ConfigError 诚实报错，
      提示走 ghpm 路线（remote/add）—— 绝不静默降级；
    · 工作目录默认在系统临时目录（装完即删，不污染 SKILLS_DIR / 市场根）；
    · progress 回调接收每一步的人话进度（server 的任务面板直接喂它）。

    注入点纪律（R5）：install_package_skills 经 ``market_core`` 晚绑定调用，
    patch core.X 对这条链路依然生效。
    """
    import market_core as _core          # noqa: PLC0415 —— 注入点晚绑定，见模块 docstring
    entry = entry if isinstance(entry, dict) else {}
    url = str(entry.get("packageUrl") or "")
    ph = normalize_sha256(entry.get("packageHash"))
    if not url or not ph:
        raise ConfigError(
            "该条目没有完整的不可变产物（packageUrl + packageHash），"
            "无法走包安装链路；请改用 ghpm 路线（remote/add）")
    mh = normalize_sha256(entry.get("manifestHash"))
    repo = str(entry.get("repo") or entry.get("displayName") or "registry-entry")
    ver = str(entry.get("version") or "0.0.0")

    def say(msg: str) -> None:
        if progress is not None:
            progress(msg)
        else:
            log("info", "artifact", msg)

    if work_root is None:
        work_root = Path(os.environ.get("TEMP") or os.environ.get("TMP") or "/tmp") / (
            f"wbm-artifact-{os.getpid()}-{time.time_ns() % 1_000_000:06d}")
    work_root = Path(work_root)

    say(f"下载不可变 artifact：{url}")
    try:
        prep = prepare_package(url, work_root, expected_package_hash=ph,
                               expected_manifest_hash=mh, force=force, fetch=fetch)
        if not prep.get("ok"):
            for e in prep.get("errors", []):
                say(f"! {e}")
            return {"ok": False, "error": "artifact 校验未通过（整包拒绝）",
                    "errors": prep.get("errors", [])}
        manifest = prep.get("manifest") or {}
        skills = [str(s).split("/", 1)[1] for s in manifest.get("skills", [])
                  if isinstance(s, str) and "/" in str(s)]
        if not skills:
            return {"ok": False, "error": "包里没有可安装的 skill"}
        say(f"校验通过（packageHash {str(prep.get('packageHash'))[:12]}…），"
            f"开始安装 {len(skills)} 个 skill")
        # install_package_skills 的契约是「skills 根目录」：包内即 <pkg>/skills。
        r = _core.install_package_skills(
            Path(prep["pkg"]) / "skills", skills=skills, pid=repo, version=ver,
            package_hash=ph, mode=mode)
        if r.get("ok"):
            say(f"完成：新增 {len(r.get('added', []))} 更新 "
                f"{len(r.get('updated', []))} 跳过 {len(r.get('skipped', []))} "
                f"非本市场 {len(r.get('foreign', []))} 失败 {len(r.get('failed', []))}")
        return r
    finally:
        shutil.rmtree(work_root, ignore_errors=True)
