"""目录扫描与 skill 元信息（v2.9 自 market_core.py 逐字迁入，只搬不改）。

注入点注记（方案 §3.2）：`_walk_tree` / `_scan` 是 selftest 崩溃注入 /
I/O 计数的属性注入目标。R3 起注入目标改为本模块命名空间
（`workbuddy_market.scanner._walk_tree`）——包内部互相调用走本模块
全局，patch 这里的名字才是有效的；core 侧调用仍经 core 全局，
patch `core._scan` 对「core 直接调用」依然有效（如 _sync_packaging、
_stage_skill）。两条路径各自独立，selftest 第 19 节已按此调整。
"""
from __future__ import annotations

import os
import re
import stat
from pathlib import Path

from .errors import ScanError
from .hasher import fingerprint_from_index
from .paths import SKILLS_DIR


def _is_reparse(st) -> bool:
    """Windows 重解析点：符号链接、junction、挂载点都算。

    实测（本机 Python 3.13）：junction 的 `is_symlink()` 返回 **False**，
    但 `st_file_attributes` 带 FILE_ATTRIBUTE_REPARSE_POINT。
    只看 `is_symlink()` 会把 junction 当成普通目录递归进去，
    把技能目录之外的内容带进市场目录 —— 这是实打实能造出来的逃逸路径。
    """
    attr = getattr(st, "st_file_attributes", 0)
    return bool(attr & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0))


def _walk_tree(root: Path, excluded, files: dict, links: list, errors: list) -> None:
    """把一个子树走完，结果写进调用方给的 files / links / errors。

    「一次遍历」的公共实现：单根（_scan）和多根分桶（_scan_many）都走这里，
    免得两份游走逻辑慢慢长歪。

    用 os.scandir 而不是 os.walk：DirEntry 的 stat 结果直接来自目录项、缓存着，
    不用再按路径查一次 —— 既更快，又能顺手拿到文件属性位。

    **软链 / junction 一律跳过、不跟随**：一个指向技能目录之外的重解析点，
    跟随它就会把外部文件的内容带进市场目录（copy2 默认跟随软链）。
    """
    root = Path(root)
    if not root.is_dir():
        return
    stack = [str(root)]
    while stack:
        cur = stack.pop()
        try:
            entries = list(os.scandir(cur))
        except OSError as exc:
            errors.append((cur, str(exc)))      # 读不了这个目录 —— 别当成"空的"
            continue
        for e in entries:
            if excluded is not None and excluded(e.name):
                continue
            try:
                st = e.stat(follow_symlinks=False)
                if e.is_symlink() or _is_reparse(st):
                    links.append(e.path)
                    continue
                if stat.S_ISDIR(st.st_mode):
                    stack.append(e.path)
                    continue
                if not stat.S_ISREG(st.st_mode):
                    continue
            except OSError as exc:
                errors.append((e.path, str(exc)))   # stat 失败同样是"看不见"
                continue
            rel = str(Path(e.path).relative_to(root)).replace("\\", "/")
            files[rel] = (st.st_size, st.st_mtime_ns)


def _raise_if_errors(errors: list, what: str) -> None:
    if errors:
        sample = "、".join(p for p, _ in errors[:3])
        raise ScanError(
            f"{what} 扫描不完整：{len(errors)} 处读取失败（例如 {sample}）。"
            "拒绝在「看不见部分内容」的情况下继续 —— 那会把读失败当成文件不存在。")


def _scan(root: Path, excluded=None, *, on_error: str = "skip") -> tuple:
    """**一次遍历**同时得到：
        files = {相对路径str: (size, mtime_ns)}
        links = 被跳过的重解析点（软链 / junction，绝对路径）

    on_error:
      "skip"（默认）—— 读不了的条目跳过，适合状态展示这类"尽力而为"的用途
      "raise"      —— 有任何一处读失败就抛 ScanError，破坏性操作必须用这个
    """
    files: dict = {}
    links: list = []
    errors: list = []
    _walk_tree(root, excluded, files, links, errors)
    if on_error == "raise":
        _raise_if_errors(errors, f"{Path(root).name}")
    return files, links


def _scan_many(named: dict, excluded=None, *, on_error: str = "raise") -> tuple:
    """一次调用、只走给定的那些子树，并且**按名字分桶**。

    返回 ({name: {rel: (size, mtime)}}, {name: [links]}, errors)

    为什么不是「扫一遍整棵 skills 根再按前缀切」：
      · 市场声明 6 个 skill、而 skills 根下有 400 个别的目录时，整树扫要
        走 2854 个文件（实测 223 ms），而只需要其中 6 个子树；
      · 切分本身也不便宜 —— `_sub_index` 每个 skill 都要遍历一遍**完整**索引，
        6 个 skill 就是 17124 次字典迭代（实测）。
    分桶之后两个问题一起没了：扫描量 = O(声明的那几个 skill)，
    取用时 O(1) 拿到自己的子树。
    """
    buckets: dict = {name: {} for name in named}
    link_buckets: dict = {name: [] for name in named}
    errors: list = []
    for name, root in named.items():
        _walk_tree(root, excluded, buckets[name], link_buckets[name], errors)
    if on_error == "raise":
        _raise_if_errors(errors, "skills 目录")
    return buckets, link_buckets, errors


def file_index(root: Path, excluded=None, *, on_error: str = "skip") -> dict:
    """只要文件索引的便捷包装。"""
    return _scan(root, excluded, on_error=on_error)[0]


class SkillScanCache:
    """一次批量扫描**已声明的那些 skill**，结果按 skill 分桶。

    build_state 会给每个插件的每个 skill 各调一次 classify_skill，而 ui 模式下
    每个 skill 都要一个指纹。v2.3 的做法是「扫一遍整棵 SKILLS_DIR 再按前缀切」，
    在「市场 6 个 skill + skills 根下 400 个无关目录」的场景里实测要扫 2854 个文件
    （223 ms），而且每切一个 skill 都要遍历一遍完整索引（6 个 skill = 17124 次迭代）。

    现在换成：只走声明的那些子树，扫描时就按名字分桶。
      · 扫描量 = O(声明的那几个 skill)
      · `fingerprint(name)` 是 O(1) 取桶
    """

    def __init__(self, names, excluded=None):
        self._names = [str(n) for n in names]
        self._excluded = excluded
        self._buckets = None
        self._links = None
        self.scans = 0
        self.errors: list = []

    def _ensure(self):
        if self._buckets is not None:
            return
        named = {n: SKILLS_DIR / n for n in self._names}
        self._buckets, self._links, self.errors = _scan_many(
            named, self._excluded, on_error="skip")   # UI 用：尽量显示，不因为一处失败就白屏
        self.scans += 1

    def fingerprint(self, sname: str) -> dict:
        """等价于 quick_fingerprint(SKILLS_DIR / sname)，但不单独遍历。"""
        self._ensure()
        return fingerprint_from_index(self._buckets.get(str(sname), {}),
                                      self._links.get(str(sname), ()))


# ---------------------------------------------------------------- skill 元信息

_FM_RE = re.compile(r"^---\s*\n(.*?)\n---\s*\n", re.S | re.M)


def parse_skill_meta(skill_dir: Path) -> dict:
    """从 SKILL.md 的 frontmatter 里取 version/description，取不到就给默认值。"""
    meta = {"version": "1.0.0", "description": ""}
    try:
        text = (Path(skill_dir) / "SKILL.md").read_text(encoding="utf-8", errors="replace")
    except OSError:
        return meta
    m = _FM_RE.match(text)
    if not m:
        return meta
    for line in m.group(1).splitlines():
        if line.startswith("version:"):
            meta["version"] = line.split(":", 1)[1].strip().strip('"').strip("'") or "1.0.0"
        elif line.startswith("description:"):
            meta["description"] = line.split(":", 1)[1].strip().strip('"').strip("'")[:300]
    return meta


# ---------------------------------------------------------------- 打包辅助

def _make_excluder(exclude_names, exclude_globs):
    """返回一个 name -> bool 的排除判定。"""
    import fnmatch

    names = set(exclude_names or [])
    globs = list(exclude_globs or [])

    def excluded(name: str) -> bool:
        if name in names:
            return True
        return any(fnmatch.fnmatch(name, pat) for pat in globs)

    return excluded


def _sub_index(full: dict, prefix: str) -> dict:
    """从一个「以 root 为基准」的整树索引里切出 prefix/ 这一支。

    key 会从 "alpha/SKILL.md" 变回 "SKILL.md"，这样 _sync_tree 完全无感。
    用来把「每个 skill 扫一次目标目录」降成「每个插件扫一次目标目录」。
    """
    p = str(prefix).rstrip("/") + "/"
    n = len(p)
    return {rel[n:]: val for rel, val in full.items() if rel.startswith(p)}
