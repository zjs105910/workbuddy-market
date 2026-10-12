# -*- coding: utf-8 -*-
"""内部数据结构。

v3.2 里这些概念全是裸 dict（``info["sha"]``、``info["sha_short"]``…），
字段拼错只能在运行期炸，IDE 也补不出来。v4 起改成 dataclass：

- ``TreeStats``    一次遍历的目录统计，替代反复 rglob
- ``SourceIndex``  解压根的「技能清单 + 体积」，一次遍历同时产出
- ``RepoInfo``     远程仓库元信息；**保留 dict 式访问**，老调用与事件载荷不受影响
- ``InstallPlan``  一次安装要做的全部事情，纯数据

``RepoInfo`` 之所以继续支持 ``info["sha"]``，是因为它同时是 ``__GHPM__``
事件载荷（宿主已经按 JSON 解析），也是缓存文件的内容 —— 为了少踩兼容坑，
先让新旧两种访问方式都能用，再逐步把内部访问迁到属性上。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

# RepoInfo 的字段顺序即缓存 JSON / 事件载荷里的字段顺序
REPO_INFO_FIELDS = ("repo", "branch", "sha", "sha_short", "stars",
                    "desc", "pushed_at", "msg")


@dataclass(slots=True)
class TreeStats:
    """一棵树的规模统计。dirs/files 分开记，是为了 doctor 与日志里能区分
    「很多小文件」和「几个大文件」——两者的磁盘行为完全不同。"""

    files: int = 0
    dirs: int = 0
    bytes: int = 0

    def as_dict(self) -> dict:
        return {"files": self.files, "dirs": self.dirs, "bytes": self.bytes}


@dataclass(slots=True)
class SourceIndex:
    """解压根的扫描结果：技能清单 + 体积，来自**同一次**遍历。

    v3.2 是 find_skill_dirs(root) 走一遍 rglob("*.md")、
    path_size_bytes(root) 再走一遍、每个 skill 子目录又各走一遍。
    """

    root: Path
    stats: TreeStats = field(default_factory=TreeStats)
    # [(skill 名, 目录)]，按名字排序，与 v3.2 find_skill_dirs 的返回顺序一致
    skills: list = field(default_factory=list)
    # {skill 名: 该目录占用的字节数}；不在 stats 里的（外部直接喂路径）为 0
    skill_bytes: dict = field(default_factory=dict)

    @property
    def names(self) -> list:
        return [n for n, _ in self.skills]

    @property
    def pairs(self) -> list:
        return list(self.skills)


@dataclass(slots=True)
class RepoInfo:
    """远程仓库元信息。字段与 v3.2 的 dict 一一对应。"""

    repo: str = ""
    branch: str = "main"
    sha: str = ""
    sha_short: str = ""
    stars: int = 0
    desc: str = ""
    pushed_at: str = ""
    msg: str = ""

    # ---- dict 兼容层：老的 info["sha"] / info.get("stars") 继续可用 ----
    def __getitem__(self, key):
        if key in REPO_INFO_FIELDS:
            return getattr(self, key)
        raise KeyError(key)

    def __setitem__(self, key, value) -> None:
        if key not in REPO_INFO_FIELDS:
            raise KeyError(key)
        setattr(self, key, value)

    def __contains__(self, key) -> bool:
        return key in REPO_INFO_FIELDS

    def get(self, key, default=None):
        return getattr(self, key) if key in REPO_INFO_FIELDS else default

    def keys(self):
        return list(REPO_INFO_FIELDS)

    def values(self):
        return [getattr(self, k) for k in REPO_INFO_FIELDS]

    def items(self):
        return [(k, getattr(self, k)) for k in REPO_INFO_FIELDS]

    def to_dict(self) -> dict:
        return {k: getattr(self, k) for k in REPO_INFO_FIELDS}

    @classmethod
    def from_dict(cls, d) -> "RepoInfo":
        if isinstance(d, RepoInfo):
            return d
        d = d or {}
        return cls(*[d.get(k, cls.__dataclass_fields__[k].default)
                     for k in REPO_INFO_FIELDS])

    def fill_short_sha(self) -> "RepoInfo":
        """补 sha_short。始终由 sha 现算，避免两个字段各自为政。"""
        self.sha_short = self.sha[:7] if self.sha else (self.sha_short or "")
        return self

    # ---- 合并：备用源拿不到 stars/desc 时不要覆盖已有值 ----
    def merge_fallback(self, other: dict) -> "RepoInfo":
        for k, v in (other or {}).items():
            if k in REPO_INFO_FIELDS and v and not getattr(self, k, None):
                if k == "branch" and self.sha:
                    continue
                setattr(self, k, v)
        return self


@dataclass
class InstallPlan:
    """一次安装/更新要做的全部事情。纯数据，不含任何副作用。

    v4 新增 content_hash / skill_hashes：apply 完成后由 installer 回填，
    写进清单供 ``ghpm verify`` 判断本地是否被手动改过。
    """

    repo: str
    name: str
    branch: str
    old_sha: str = ""
    new_sha: str = ""
    old_skills: list = field(default_factory=list)
    new_skills: list = field(default_factory=list)
    added_skills: list = field(default_factory=list)      # 远端新增
    removed_skills: list = field(default_factory=list)    # 远端已删除 → 必须删本地
    updated_skills: list = field(default_factory=list)    # 两边都有，内容要刷新
    kept_skills: list = field(default_factory=list)       # 名字撞上别的项目，保留不动
    conflicts: list = field(default_factory=list)
    source_dir: Path | None = None
    extracted_root: Path | None = None    # 临时解压根，apply 时搬进 source_dir
    required_bytes: int = 0
    pairs: list = field(default_factory=list)             # [(skill名, 源目录)]
    is_update: bool = False
    skill_stats: dict = field(default_factory=dict)        # {skill名: 字节数}
    content_hash: str = ""                                 # 源码树指纹
    skill_hashes: dict = field(default_factory=dict)       # {skill名: 指纹}
    source_stats: dict = field(default_factory=dict)       # 写入后源码树规模（复用遍历结果）

    def summary(self) -> dict:
        return {"repo": self.repo, "branch": self.branch,
                "added": self.added_skills, "removed": self.removed_skills,
                "updated": self.updated_skills, "kept": self.kept_skills,
                "conflicts": self.conflicts}
