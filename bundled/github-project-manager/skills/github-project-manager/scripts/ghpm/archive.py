# -*- coding: utf-8 -*-
"""ZIP：索引、安全上限、文件名校验、安全解压、下载编排。

安全模型是**两层**，缺一不可：

1. 解压前扫中央目录（``zip_content_index``）：不落盘就能判断有没有 skill、
   条目数、展开体积，以及能不能过安全上限。此时失败成本为零。
2. 解压前的条目校验（``check_zip_limits`` + ``check_zip_names``）与
   逐条 containment 校验（``safe_extract``）。

为什么标准库的防护不够：``zipfile.extractall`` 从 Python 3.6 起已经会把
``..``、绝对路径、盘符剥掉，也会把 ``:`` ``<`` ``>`` ``|`` ``?`` ``*``
换成 ``_``（实测确认），所以 zip slip 本身不靠我们挡。它**不管**的是
Windows 保留设备名：条目叫 ``NUL`` / ``CON`` / ``COM1`` 时解压不报错，
但文件被系统设备吞掉 —— 实测解压后目录里什么都没有，
``(dest/"NUL").exists()`` 却是 True。这属于**静默丢数据**，
比报错更难查，所以在 nt 上单独拦一道。
"""
from __future__ import annotations

import errno
import os
import re
import shutil
import tempfile
import zipfile
from pathlib import Path, PurePosixPath

from . import config
from .errors import E_BAD_ARCHIVE, E_NETWORK, E_NOT_SKILL, E_WRITE, BadArchiveError, NotSkillError
from .discovery import match_skill_path
from .remote import download_repo_zip
from .util import DISK_SAFETY_BYTES, emit, ensure_disk_space, format_bytes

# Windows 保留设备名（不区分大小写，带扩展名也算：CON.txt 依然是 CON）
WINDOWS_RESERVED = ({"con", "prn", "aux", "nul"}
                    | {"com%d" % i for i in range(1, 10)}
                    | {"lpt%d" % i for i in range(1, 10)})
_DRIVE_RE = re.compile(r"^[A-Za-z]:")


def zip_content_index(zf: zipfile.ZipFile, fallback: str = "") -> dict:
    """只读 ZIP 中央目录，不解压即可判断 skill、条目数和展开体积。"""
    infos = [i for i in zf.infolist() if not i.is_dir()]
    parsed = []
    for info in infos:
        parts = tuple(p for p in PurePosixPath(info.filename.replace("\\", "/")).parts
                      if p not in ("", "."))
        if parts:
            parsed.append((info, parts))
    roots = {parts[0] for _, parts in parsed}
    root_prefix = next(iter(roots)) if len(roots) == 1 else ""
    skills = {}
    top_skill = False
    for info, parts in parsed:
        rel = parts[1:] if root_prefix and parts[0] == root_prefix else parts
        if len(rel) == 1 and rel[0].lower() == "skill.md":
            top_skill = True
        name = match_skill_path(rel)
        if name and name not in skills:
            skills[name] = "/".join(rel)
    if not skills and top_skill:
        skills[fallback or root_prefix or "skill"] = "SKILL.md"
    return {
        "skills": skills,
        "skill_count": len(skills),
        "entry_count": len(infos),
        "uncompressed_size": sum(max(0, int(i.file_size)) for i in infos),
        "root_prefix": root_prefix,
        "inspection_mode": "zip-index",
    }


def check_zip_limits(infos) -> dict:
    """ZIP 结构安全上限：条目数、单文件大小、总展开体积、压缩比。

    只看 uncompressed_size 不够：一个 42 MB 的 zip 可以展开成 42 GB（zip bomb），
    也可以有十万个空目录条目把 inode 吃光。这里在解压**之前**全部拦下，
    此时还没落任何盘，失败是零成本的。
    """
    total = 0
    for info in infos:
        if info.is_dir():
            continue
        total += max(0, int(info.file_size))
    if len(infos) > config.MAX_ZIP_ENTRIES:
        raise BadArchiveError("ZIP 条目数量异常：%d 个（上限 %d）"
                              % (len(infos), config.MAX_ZIP_ENTRIES))
    if total > config.MAX_ZIP_UNCOMPRESSED:
        raise BadArchiveError("ZIP 展开体积过大：%s（上限 %s）"
                              % (format_bytes(total),
                                 format_bytes(config.MAX_ZIP_UNCOMPRESSED)))
    for info in infos:
        if info.is_dir():
            continue
        size = max(0, int(info.file_size))
        if size > config.MAX_ZIP_FILE_SIZE:
            raise BadArchiveError("ZIP 内单文件过大：%s（%s，上限 %s）"
                                  % (info.filename, format_bytes(size),
                                     format_bytes(config.MAX_ZIP_FILE_SIZE)))
        comp = max(1, int(info.compress_size))
        if size / comp > config.MAX_ZIP_RATIO and size > 16 * config.MIB:
            # 合法高压缩文本也能到几百倍，所以阈值很宽松，且只对大文件生效。
            raise BadArchiveError("ZIP 压缩比异常（疑似压缩炸弹）：%s 压缩后 %s，展开 %s"
                                  % (info.filename, format_bytes(comp), format_bytes(size)))
    return {"uncompressed_size": total, "entry_count": len(infos)}


def check_zip_names(infos) -> dict:
    """条目**名字**的合法性：控制字符、NUL、绝对路径 / 盘符、Windows 设备名。

    这些都不是「会不会逃出目录」的问题（那个由 safe_extract 的 containment 管），
    而是「解出来根本不是你看到的东西」：设备名会被系统吞掉、盘符会被剥掉、
    控制字符在日志里看不出差别。宁可整包拒绝，也不装一份缺文件和原包对不上的副本。
    """
    nt = os.name == "nt"
    checked = 0
    for info in infos:
        name = getattr(info, "filename", "") or ""
        checked += 1
        norm = name.replace("\\", "/")
        if "\x00" in name or any(ord(c) < 32 for c in name):
            raise BadArchiveError("压缩包里有含控制字符的文件名，已中止：%r" % name[:120])
        if norm.startswith("/") or _DRIVE_RE.match(norm.split("/", 1)[0] or ""):
            raise BadArchiveError("压缩包里有绝对路径条目，已中止解压：%s" % name[:120])
        if nt:
            for part in PurePosixPath(norm).parts:
                if part in ("", ".", ".."):
                    continue
                # CON.txt / "CON " 在 Windows 上依然指向设备，所以取扩展名前的词干
                stem = part.split(".")[0].rstrip(" .").lower()
                if stem in WINDOWS_RESERVED:
                    raise BadArchiveError(
                        "压缩包里有 Windows 保留设备名（解压会被系统吞掉、文件静默丢失）：%s"
                        % name[:120])
    return {"checked": checked}


def safe_extract(zf: zipfile.ZipFile, out: Path) -> None:
    """解压前的最后一道 containment 校验。

    zipfile.extractall 本身已经会剥掉 ``..`` 和绝对路径，但那不等于我们可以
    假设条目名安全 —— 镜像不是我们自己运维的，而且中央目录里的名字与实际
    落盘行为之间隔着标准库的实现细节。这里逐条 resolve 后比对目标目录，
    越界就整包中止（此时还没解压任何东西）。
    """
    out = Path(out)
    base = out.resolve()
    infos = zf.infolist()
    check_zip_names(infos)
    for info in infos:
        try:
            p = (out / info.filename).resolve()
        except Exception:
            raise BadArchiveError("压缩包条目名无法解析：%s" % str(info.filename)[:120])
        if p == base:
            continue
        if str(p).startswith(str(base) + os.sep):
            continue
        raise BadArchiveError("压缩包里有越界路径，已中止解压：%s" % info.filename)
    zf.extractall(out)


def fetch_zip(repo: str, branch: str, require_skill: bool = False) -> tuple:
    """下载并预扫描 ZIP，再按需解压；返回（临时目录、仓库根目录、ZIP 索引）。

    失败时的三类归因必须分开，因为处置方式完全不同：
    - E_NOT_SKILL / E_BAD_ARCHIVE：换镜像没用（结构性），直接失败
    - 磁盘满：换镜像也没用，提示清理磁盘
    - 其它（网络 / 下到错误页）：换下一个镜像
    """
    tmp = Path(tempfile.mkdtemp(prefix="ghpm-"))
    z = tmp / "src.zip"

    def on_attempt(i, label, url):
        emit("downloading", "下载中 · " + label, percent=25 + i * 6)

    def validate(dest):
        if not zipfile.is_zipfile(dest):
            raise RuntimeError("响应不是有效的 zip 包")

    try:
        try:
            download_repo_zip(repo, branch, z, on_attempt=on_attempt, validate=validate)
        except Exception:
            shutil.rmtree(tmp, ignore_errors=True)
            emit("failed", "下载失败", percent=100, code=E_NETWORK,
                 hint="已自动试过主源和镜像仍失败。检查代理设置（http_proxy/https_proxy），"
                      "或稍后重试。")
            raise

        out = tmp / "unzipped"
        try:
            with zipfile.ZipFile(z) as zf:
                index = zip_content_index(zf, fallback=repo.split("/")[-1])
                if require_skill and not index["skills"]:
                    raise NotSkillError("%s 仓库 %s 不含 skills/*/SKILL.md"
                                        % (E_NOT_SKILL, repo))
                # 安全上限必须在解压前查；此时失败零成本
                check_zip_limits(zf.infolist())
                check_zip_names(zf.infolist())
                unpack_need = index["uncompressed_size"] + max(
                    DISK_SAFETY_BYTES, int(index["uncompressed_size"] * 0.10))
                ensure_disk_space(out, unpack_need, "解压 ZIP 时")
                safe_extract(zf, out)
        except NotSkillError as e:
            shutil.rmtree(tmp, ignore_errors=True)
            emit("failed", "仓库里没有可装的 skill（ZIP 索引已确认）", percent=100,
                 code=E_NOT_SKILL, detail=str(e),
                 hint="仍可加 --allow-non-skill 只安装源码")
            raise
        except BadArchiveError as e:
            # 结构性问题换镜像也没用（而且镜像更可能是问题来源），直接失败。
            shutil.rmtree(tmp, ignore_errors=True)
            emit("failed", "压缩包不安全或已损坏", percent=100, code=E_BAD_ARCHIVE,
                 detail=str(e),
                 hint="已中止解压，未改动任何文件。若确认仓库合法，可用 "
                      "GHPM_MAX_ZIP_UNCOMPRESSED / GHPM_MAX_ZIP_FILE_SIZE 放宽上限。")
            raise
        except OSError as e:
            if e.errno == errno.ENOSPC:
                shutil.rmtree(tmp, ignore_errors=True)
                emit("failed", "磁盘空间不足", percent=100, code=E_WRITE,
                     detail=str(e), hint="清理磁盘空间后重试；尚未改动 skills 或清单。")
                raise
            shutil.rmtree(tmp, ignore_errors=True)
            emit("failed", "解压失败", percent=100, code=E_WRITE, detail=str(e)[:160])
            raise

        indexed_root = out / index["root_prefix"] if index.get("root_prefix") else None
        if indexed_root and indexed_root.is_dir():
            root = indexed_root
        else:
            dirs = [p for p in out.iterdir() if p.is_dir()]
            root = dirs[0] if len(dirs) == 1 else out
        return tmp, root, index
    except Exception:
        shutil.rmtree(tmp, ignore_errors=True)
        raise
