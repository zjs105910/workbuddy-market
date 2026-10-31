# -*- coding: utf-8 -*-
"""importer —— 离线导入任意 skill 安装包（v2.39 新增）。

v2.38 的离线安装只覆盖「精选市场收录条目」（必须有注册表钉死的
packageHash 可比对）。用户实测需求更进一步：手上有一个**任意来源**的
skill 安装包（GitHub Download ZIP、Release 产物、别人发来的 zip），
在市场里点按钮、选文件、直接装。

本模块就是那条链：

    选择 zip → 流式上传到暂存区（不落 skills 目录）
      → 分类：Market Package（带 manifest.json）｜原始仓库 zip
      → Market Package：prepare_package（同一套 unpack/verify 管线）
        原始 zip：unpack_zip（zip-slip / 链接 / bomb 防线）
                  → find_skill_layout 定位 skill 根（三种收录形态）
                  → pack_package 就地打成 Market Package
      → 预览（skills 清单 / 权限风险 / 兼容性）→ 用户显式确认
      → commit：install_package_skills 两阶段事务安装（与在线链同一条）
      → 记录 imports.json（显示名 / 来源 zip），state.py 合并出
        via="import" 的社区卡片 —— 装过的东西看得见、卸得掉
        （卸载走 plugin_uninstall_plan 的所有权回退，市场是管理者）。

安全纪律（与全项目同一口径）：

  · 上传内容是**不可信输入**：zip 防线全在 unpack_zip / prepare_package
    里，本模块不自己解 zip；大小上限与 artifact 同一值；
  · 暂存区在系统临时目录，30 分钟 TTL 就地清扫，绝不进 SKILLS_DIR；
  · commit 必须 confirmed=True —— 未经收录审核的包，风险确认不可跳过；
  · 安装编排经 market_core 晚绑定（注入点纪律 R5）。
"""
from __future__ import annotations

import hashlib
import json
import re
import shutil
import tempfile
import time
from pathlib import Path

from .errors import ArtifactError
from .fsutil import atomic_write_text, read_json
from .paths import IMPORTS_PATH
from .version import MARKET_VERSION

MAX_IMPORT_BYTES = 256 * 1024 * 1024        # 与 artifact 同一总量上限（zip bomb 防线）
UPLOAD_CHUNK = 1024 * 1024
STAGING_TTL = 30 * 60                       # 暂存包存活时间（秒），上传时顺手清扫

_SLUG_RE = re.compile(r"[^a-z0-9]+")


# ---------------------------------------------------------------- 暂存区

def staging_root() -> Path:
    """上传暂存根：系统临时目录，绝不进 SKILLS_DIR / 市场根。"""
    p = Path(tempfile.gettempdir()) / "wbm-import-staging"
    p.mkdir(parents=True, exist_ok=True)
    return p


def sweep_staging(now: float | None = None, max_age: float = STAGING_TTL) -> int:
    """清扫过期暂存（zip + 解包工作目录 + 记录 json）。返回清掉的数量。"""
    now = time.time() if now is None else now
    root = staging_root()
    removed = 0
    for rec in root.glob("*.json"):
        try:
            data = json.loads(rec.read_text(encoding="utf-8"))
            created = float(data.get("createdAt") or 0)
        except (OSError, ValueError):
            created = 0
        if created and now - created <= max_age:
            continue
        sid = rec.stem
        if re.fullmatch(r"[0-9a-f]{16}", sid or ""):
            shutil.rmtree(root / sid, ignore_errors=True)
            (root / f"{sid}.zip").unlink(missing_ok=True)
        rec.unlink(missing_ok=True)
        removed += 1
    return removed


# ---------------------------------------------------------------- 记录

def record_import(pid: str, meta: dict) -> None:
    """登记一次离线导入（显示名 / 来源 zip），供 state.py 合并卡片。"""
    data = read_json(IMPORTS_PATH, {}) or {}
    if not isinstance(data, dict):
        data = {}
    meta = dict(meta)
    meta.setdefault("installedAt", time.strftime("%Y-%m-%dT%H:%M:%S%z"))
    data[pid] = meta
    IMPORTS_PATH.parent.mkdir(parents=True, exist_ok=True)
    atomic_write_text(IMPORTS_PATH, json.dumps(data, ensure_ascii=False, indent=1))


def list_imports() -> dict:
    return read_json(IMPORTS_PATH, {}) or {}


# ---------------------------------------------------------------- 布局识别

def find_skill_layout(root: Path) -> tuple[Path | None, list[str]]:
    """定位 zip 解包后的 skill 根（与 build_artifacts 的三种收录形态同口径）。

    形态 a：root/skills/<name>/SKILL.md —— root 即包源；
    形态 b：直接子目录里有 SKILL.md —— 需要重组进 staging/skills/<name>；
    形态 c：root 本身是 skill —— 单 skill，用文件名 slug；
    都不是 → (None, [])（调用方诚实报错）。
    """
    root = Path(root)
    skills_dir = root / "skills"
    if skills_dir.is_dir():
        names = sorted(p.name for p in skills_dir.iterdir()
                       if p.is_dir() and (p / "SKILL.md").is_file())
        if names:
            return root, names
    subs = sorted(p for p in root.iterdir()
                  if p.is_dir() and (p / "SKILL.md").is_file()) if root.is_dir() else []
    if subs:
        return None, [p.name for p in subs]      # 形态 b：调用方负责重组
    if (root / "SKILL.md").is_file():
        return root, []                          # 形态 c：调用方命名
    return None, []


def _slug(text: str, fallback: str = "import") -> str:
    s = _SLUG_RE.sub("-", str(text or "").lower()).strip("-")
    return (s or fallback)[:40]


# ---------------------------------------------------------------- 上传分类

def stage_upload(read, total: int, *, name_hint: str = "",
                 repo: str = "", registry_lookup=None) -> dict:
    """流式接收上传的 zip → 分类 → 打包/校验 → 返回预览（不装）。

    ``read(chunk)`` 是请求体的分块读取口（服务端传 rfile.read），本模块
    不碰 HTTP；自检直接喂 BytesIO 包一层即可离线测完全部链路。

    返回 {"ok", stagingId, kind, name, pid, version, skills, risk,
          compatibility, packageHash, warnings, pinned}；内容不合法 /
    超限 / zip 攻击面 → {"ok": False, "error": ...}。
    """
    import secrets
    from .artifact import prepare_package, unpack_zip  # noqa: PLC0415

    if total > MAX_IMPORT_BYTES:
        return {"ok": False,
                "error": f"zip 超过大小上限（{total} 字节 > {MAX_IMPORT_BYTES}），已拒绝"}
    sweep_staging()

    sid = secrets.token_hex(8)
    sroot = staging_root()
    zip_path = sroot / f"{sid}.zip"
    work = sroot / sid
    h = hashlib.sha256()
    got = 0
    remaining = total
    try:
        with zip_path.open("wb") as fh:
            while remaining > 0:
                chunk = read(min(UPLOAD_CHUNK, remaining))
                if not chunk:
                    zip_path.unlink(missing_ok=True)
                    return {"ok": False,
                            "error": f"接收中断（声明 {total} 字节，实收 {got}）"}
                got += len(chunk)
                remaining -= len(chunk)
                fh.write(chunk)
                h.update(chunk)
        if got != total:
            zip_path.unlink(missing_ok=True)
            return {"ok": False, "error": f"接收字节数不符（声明 {total}，实收 {got}）"}

        zip_name = Path(name_hint or "import.zip").name
        stem = Path(zip_name).stem or "import"

        # ---- 分类一：Market Package（带根级 manifest.json）
        import zipfile as _zf  # noqa: PLC0415
        with _zf.ZipFile(zip_path) as zf:
            names = zf.namelist()
        is_pkg = "manifest.json" in names
        if is_pkg:
            prep = prepare_package(zip_path, work / "prep")
            if not prep.get("ok"):
                return {"ok": False,
                        "error": "包校验未通过（整包拒绝）："
                                 + "；".join(prep.get("errors", [])),
                        "errors": prep.get("errors", [])}
            manifest = prep["manifest"]
            skills = [str(s).split("/", 1)[1] for s in manifest.get("skills", [])
                      if isinstance(s, str) and "/" in str(s)]
            pid = str(manifest.get("id") or "") or f"import-{_slug(stem)}"
            version = str(manifest.get("version") or "0.0.0")
            kind = "package"
            pkg_rel = "prep/pkg"
        else:
            # ---- 分类二：原始仓库 zip —— 解包（攻击面防线全在 unpack_zip）
            unpacked = work / "unpacked"
            unpack_zip(zip_path, unpacked)
            src_root, names_b = find_skill_layout(unpacked)
            if src_root is not None and names_b:
                kind_src = src_root                      # 形态 a
            elif names_b:                                # 形态 b：重组
                kind_src = work / "pkgsrc"
                for n in names_b:
                    shutil.copytree(unpacked / n, kind_src / "skills" / n)
            elif src_root is not None:                   # 形态 c
                kind_src = work / "pkgsrc"
                slug = _slug(stem)
                shutil.copytree(unpacked, kind_src / "skills" / slug)
                names_b = [slug]
            else:
                shutil.rmtree(work, ignore_errors=True)
                zip_path.unlink(missing_ok=True)
                return {"ok": False,
                        "error": "zip 里没有可识别的 skill：需要根目录 / skills/ 子目录 / "
                                 "任意一级子目录里存在 SKILL.md（本市场按 Skill 协议安装）"}
            from .packaging import pack_package  # noqa: PLC0415
            packed = pack_package(
                kind_src, work / "pkg", pid=f"import-{_slug(stem)}",
                name=stem, version="0.0.0",
                source={"type": "import", "origin": zip_name})
            manifest = packed["manifest"]
            skills = list(names_b)
            pid = f"import-{_slug(stem)}"
            version = "0.0.0"
            pkg_rel = "pkg"
            kind = "import"

        from .packaging import compatibility_report, risk_summary  # noqa: PLC0415
        from .adapters.workbuddy import detect_host_version  # noqa: PLC0415
        hv = detect_host_version()
        pkg_hash = str(prep.get("packageHash") if is_pkg else packed["packageHash"])

        # ---- 收录钉死哈希（repo 上下文给了就比对 —— 严格链，对不上拒绝）
        pinned = False
        if repo and callable(registry_lookup):
            reg = registry_lookup() or {}
            entry = next((e for e in reg.get("plugins", [])
                          if str(e.get("repo", "")).casefold() == str(repo).casefold()),
                         None)
            from .hasher import normalize_sha256  # noqa: PLC0415
            want = normalize_sha256((entry or {}).get("packageHash"))
            got_ph = normalize_sha256(pkg_hash)
            if want:
                if got_ph != want:
                    shutil.rmtree(work, ignore_errors=True)
                    zip_path.unlink(missing_ok=True)
                    return {"ok": False,
                            "error": f"这个 zip 与「{repo}」收录审核固定的产物不是同一份"
                                     f"（packageHash 不符，整包拒绝）。请下载该条目收录时的"
                                     f"固定产物 zip，或去掉来源仓库按「未审核导入」重新评估。"}
                pinned = True

        record = {"kind": kind, "name": stem, "pid": pid, "version": version,
                  "skills": skills, "packageHash": pkg_hash,
                  "pkgRel": pkg_rel,
                  "zipName": zip_name, "repo": str(repo or ""),
                  "pinned": pinned, "createdAt": time.time()}
        (sroot / f"{sid}.json").write_text(
            json.dumps(record, ensure_ascii=False), encoding="utf-8")
        return {"ok": True, "stagingId": sid, "kind": kind, "name": stem,
                "pid": pid, "version": version, "skills": skills,
                "packageHash": pkg_hash,
                "risk": risk_summary(manifest),
                "compatibility": compatibility_report(manifest, host_version=hv),
                "warnings": [], "pinned": pinned,
                "marketVersion": MARKET_VERSION}
    except ArtifactError as exc:
        shutil.rmtree(work, ignore_errors=True)
        zip_path.unlink(missing_ok=True)
        return {"ok": False, "error": str(exc)}
    except (OSError, ValueError) as exc:
        shutil.rmtree(work, ignore_errors=True)
        zip_path.unlink(missing_ok=True)
        return {"ok": False, "error": f"导入失败：{exc}"}


# ---------------------------------------------------------------- 提交

def commit_import(staging_id: str, *, confirmed: bool, mode: str = "update") -> dict:
    """把暂存包真正装进 ~/.workbuddy/skills（两阶段事务，与在线链同一条）。

    confirmed 必须显式为 True —— 未经收录审核的包，风险确认不可跳过；
    pinned（与收录固定哈希比对通过）的包同样走确认，语义统一。
    默认 mode="update"：同一来源再次导入（上游更新后重新下载）覆盖自己
    之前导入的那份（旧件进回收站可恢复）；foreign 一律不碰（除非显式
    mode="force"，前端不提供）。
    """
    import market_core as _core  # noqa: PLC0415 —— 注入点晚绑定（R5）
    sid = str(staging_id or "")
    if not re.fullmatch(r"[0-9a-f]{16}", sid):
        return {"ok": False, "error": "stagingId 非法"}
    rec_path = staging_root() / f"{sid}.json"
    rec = read_json(rec_path, {})
    if not isinstance(rec, dict) or not rec.get("pid"):
        return {"ok": False, "error": "暂存包不存在或已过期，请重新选择文件导入"}
    if not confirmed:
        return {"ok": False,
                "error": "未经风险确认：请先看清包的权限与兼容性预览，勾选确认后再安装"}
    mode = mode if mode in ("missing", "update", "force") else "missing"
    pkg_dir = staging_root() / sid / str(rec.get("pkgRel") or "pkg")
    skills_dir = pkg_dir / "skills"
    skills = [str(s) for s in rec.get("skills", [])]
    if not skills or not skills_dir.is_dir():
        return {"ok": False, "error": "暂存包内容缺失，请重新选择文件导入"}
    r = _core.install_package_skills(
        skills_dir, skills=skills, pid=str(rec["pid"]),
        version=str(rec.get("version") or "0.0.0"),
        package_hash=str(rec.get("packageHash") or "") or None, mode=mode)
    if r.get("ok"):
        record_import(str(rec["pid"]), {
            "name": str(rec.get("name") or rec["pid"]),
            "via": "import", "zipName": str(rec.get("zipName") or ""),
            "repo": str(rec.get("repo") or ""),
            "pinned": bool(rec.get("pinned")),
            "skills": skills,
            "packageHash": str(rec.get("packageHash") or ""),
        })
        shutil.rmtree(staging_root() / sid, ignore_errors=True)
        rec_path.unlink(missing_ok=True)
    return r
