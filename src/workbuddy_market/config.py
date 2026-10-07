"""配置校验与读取（v2.9 自 market_core.py 逐字迁入，只搬不改）。

配置是手写的，一个手滑（"skills": ["../../x"]）不该让程序写到市场目录外面去。
所有来自配置的「名字」都必须先过 validate_id，所有由名字拼出来的路径
都必须再过一次 ensure_child。
"""
from __future__ import annotations

import math
import re
from pathlib import Path

from .errors import ConfigError
from .fsutil import read_json
from .paths import CONFIG_PATH, HASH_CHUNK_BYTES, MARKET_ROOT, SKILLS_DIR

# classify 的用途。用途决定「要不要读到内容」：
#   ui        —— 网页状态，允许用廉价指纹，判错只是显示不准
#   install   —— 决定要不要覆盖，必须准
#   uninstall —— 决定要不要移走用户目录，必须最准
CLASSIFY_PURPOSES = ("ui", "install", "uninstall")
EXACT_PURPOSES = ("install", "uninstall")

_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
_REPO_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,99}/[A-Za-z0-9][A-Za-z0-9._-]{0,99}$")
_VER_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9.+_-]{0,63}$")

# Windows 保留设备名（不区分大小写，且带扩展名也算：CON.txt 同样非法）
WINDOWS_RESERVED = {
    "CON", "PRN", "AUX", "NUL",
    *(f"COM{i}" for i in range(1, 10)),
    *(f"LPT{i}" for i in range(1, 10)),
}


def validate_id(value, field: str) -> str:
    """插件名 / skill 名必须是安全的单段标识符。"""
    if not isinstance(value, str):
        raise ConfigError(f"{field} 必须是字符串，实际是 {type(value).__name__}")
    if not _ID_RE.fullmatch(value):
        raise ConfigError(
            f"{field} 非法：{value!r}\n"
            "只允许「字母或数字开头，后跟字母 / 数字 / . _ -」，最长 128 字符；"
            "不允许路径分隔符、盘符、.. 或空白。"
        )
    if value.split(".")[0].upper() in WINDOWS_RESERVED:
        raise ConfigError(f"{field} 使用了 Windows 保留设备名：{value!r}")
    return value


def validate_version(value, field: str) -> str:
    if not isinstance(value, str) or not _VER_RE.fullmatch(value):
        raise ConfigError(f"{field} 不是合法版本号：{value!r}")
    return value


def ensure_child(root: Path, child: Path) -> Path:
    """确认 child 落在 root 之内，否则拒绝。

    这是「最后一道闸」：即使前面某处漏了校验，越界路径也会在这里被拦下。
    """
    r = Path(root).resolve()
    c = Path(child).resolve()
    if c != r and r not in c.parents:
        raise ConfigError(f"路径越界：{c} 不在 {r} 之内")
    return c


def collision_key(value: str) -> str:
    """做「同名判定」用的归一 key。

    主战场是 Windows，而 NTFS 默认大小写不敏感 —— `SKILLS_DIR/Story` 与
    `SKILLS_DIR/story` 在磁盘上就是同一个目录。如果只在字符串层面比较，
    两个条目会互相覆盖，而且是**静默**覆盖。

    所以在**所有平台**上统一 casefold：宁可 Linux 也拒绝这种配置，
    也不要让同一个配置在两套系统上跑出两种行为。
    """
    return str(value).casefold()


def _check_collision(seen: dict, raw: str, where: str, what: str) -> None:
    """seen 的 key 是 casefold 后的名字，value 是第一次出现时的原始写法。"""
    key = collision_key(raw)
    prev = seen.get(key)
    if prev is not None and prev != raw:
        raise ConfigError(
            f"{what}名大小写冲突：{prev!r} 与 {raw!r}（{where}）\n"
            "Windows 文件系统大小写不敏感，这两个名字会指向同一个目录并互相覆盖。\n"
            "请只保留一个写法（本工具在所有平台上都拒绝这种配置，避免跨平台行为不一致）。"
        )
    if prev is not None:
        raise ConfigError(f"{what}名重复：{raw}")
    seen[key] = raw


def _check_number(value, field: str, *, lo: float = 0, integer: bool = False):
    """配置里的数值统一在这里过一遍。

    两个坑：
      · NaN / Infinity 能通过 `isinstance(v, (int, float))` 和大小比较，
        混进内部状态后会让 `int()` 抛异常或者让阈值判断永远为假。
      · `maxSizeBytes: 1.9` 会被后面的 `int(...)` 静默截成 1 —— 用户以为
        自己设了 1.9 字节，实际按 1 字节算。这种「悄悄改写的配置」应当直接拒绝。
    """
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ConfigError(f"{field} 必须是数字。")
    if isinstance(value, float) and not math.isfinite(value):
        raise ConfigError(f"{field} 不能是 NaN 或 Infinity。")
    if integer and not isinstance(value, int):
        raise ConfigError(
            f"{field} 必须是整数（{value!r} 的小数部分会被静默截掉，容易误配）。")
    if value < lo:
        raise ConfigError(f"{field} 必须不小于 {lo}。")
    return value


def validate_repo(value, field: str = "repo") -> str:
    """GitHub 仓库标识 `owner/repo` 的唯一校验入口。

    配置层、API 层、后台任务层共用这一个 —— v2.3 之前只有配置层在用，
    `/api/remote/add` 只判断了「非空」，等于把已有的边界绕过去了。

    拒绝：空、非字符串、超长、不是 owner/repo 形状、任一段以 `-` 开头
    （会被下游当命令行选项）、任一段是 `.` / `..`、含空白或控制字符。
    """
    if not isinstance(value, str):
        raise ConfigError(f"{field} 必须是字符串，实际是 {type(value).__name__}。")
    if not value or value != value.strip():
        raise ConfigError(f"{field} 不能为空或首尾带空白：{value!r}")
    if len(value) > 201:
        raise ConfigError(f"{field} 太长了（{len(value)} 字符）。")
    if not _REPO_RE.fullmatch(value):
        raise ConfigError(
            f"{field} 必须是 owner/repo 形式（只用字母数字 . _ -，两段都要以字母数字开头）：{value!r}")
    owner, _, repo = value.partition("/")
    for seg in (owner, repo):
        if seg in (".", ".."):
            raise ConfigError(f"{field} 里不能出现 {seg!r}：{value!r}")
    return value


def validate_config(cfg: dict) -> list:
    """校验配置结构与安全性，返回 warning 列表；结构性错误直接抛 ConfigError。

    这里只查「结构和安全」，不查「skill 在本机存不存在」——
    后者是 deep_check 的活，因为源不在本机时市场会沿用历史副本，属于正常状态。
    """
    if not isinstance(cfg, dict):
        raise ConfigError("market.config.json 的顶层必须是一个对象。")

    warnings = []

    # --- 市场标识
    mid = cfg.get("marketId")
    if not mid:
        raise ConfigError("配置缺少 marketId。")
    validate_id(mid, "marketId")
    if not isinstance(cfg.get("name", ""), str):
        raise ConfigError("name 必须是字符串。")
    owner = cfg.get("owner", {})
    if not isinstance(owner, dict):
        raise ConfigError("owner 必须是一个对象，例如 {\"name\": \"...\"}。")
    if "schemaVersion" in cfg:
        sv = cfg["schemaVersion"]
        if not isinstance(sv, int) or isinstance(sv, bool) or sv < 1:
            raise ConfigError("schemaVersion 必须是正整数。")

    # --- 本机插件
    plugins = cfg.get("localPlugins", [])
    if not isinstance(plugins, list):
        raise ConfigError("localPlugins 必须是数组。")
    seen_plugins = {}                      # casefold(name) -> 第一次出现的原始写法
    skill_owner = {}                       # casefold(skill) -> (原始写法, 插件原始写法)
    for i, spec in enumerate(plugins):
        where = f"localPlugins[{i}]"
        if not isinstance(spec, dict):
            raise ConfigError(f"{where} 必须是对象。")
        name = validate_id(spec.get("name"), f"{where}.name")
        _check_collision(seen_plugins, name, where, "插件")
        validate_version(spec.get("version", "1.0.0"), f"{where}({name}).version")
        for key in ("description", "description_en", "category", "homepage", "repository", "license"):
            if key in spec and not isinstance(spec[key], str):
                raise ConfigError(f"{where}({name}).{key} 必须是字符串。")
        if "keywords" in spec:
            if not isinstance(spec["keywords"], list) or not all(
                    isinstance(k, str) for k in spec["keywords"]):
                raise ConfigError(f"{where}({name}).keywords 必须是字符串数组。")
        if "author" in spec and not isinstance(spec["author"], dict):
            raise ConfigError(f"{where}({name}).author 必须是对象。")

        skills = spec.get("skills", [])
        if not isinstance(skills, list) or not skills:
            raise ConfigError(f"{where}({name}).skills 必须是非空数组。")
        seen_here = {}
        for s in skills:
            sid = validate_id(s, f"{where}({name}).skills")
            _check_collision(seen_here, sid, f"{where}({name}).skills", "skill")
            key = collision_key(sid)
            prev = skill_owner.get(key)
            if prev is not None and collision_key(prev[1]) != collision_key(name):
                raise ConfigError(
                    f"skill {sid!r} 被两个插件同时声明：{prev[1]} 与 {name}"
                    "（同一个 skill 只能属于一个插件，否则内容会互相覆盖）"
                )
            skill_owner[key] = (prev[0] if prev else sid, name)
            # 最后一道闸：拼出来的路径必须在合法根目录之内
            ensure_path = MARKET_ROOT / "plugins" / name / "skills" / sid
            ensure_child(MARKET_ROOT / "plugins", ensure_path)
            ensure_child(SKILLS_DIR, SKILLS_DIR / sid)

    # --- 远端源
    remotes = cfg.get("remoteSources", [])
    if not isinstance(remotes, list):
        raise ConfigError("remoteSources 必须是数组。")
    seen_repos = {}                        # casefold(repo) -> 原始写法
    for i, spec in enumerate(remotes):
        where = f"remoteSources[{i}]"
        if not isinstance(spec, dict):
            raise ConfigError(f"{where} 必须是对象。")
        repo = spec.get("repo")
        try:
            validate_repo(repo, f"{where}.repo")
        except ConfigError:
            raise ConfigError(f"{where}.repo 必须是 owner/repo 形式：{repo!r}")
        # GitHub 的 owner/repo 也是大小写不敏感的，同样要归一
        _check_collision(seen_repos, repo, where, "远端源")

    # --- 打包 / 回收站 / 校验模式
    pack = cfg.get("packaging", {})
    if not isinstance(pack, dict):
        raise ConfigError("packaging 必须是对象。")
    if pack.get("verify", "auto") not in ("auto", "fast", "strict"):
        raise ConfigError('packaging.verify 只能是 auto / fast / strict。')
    if "hashAlgorithm" in pack and pack["hashAlgorithm"] != "sha256":
        raise ConfigError('packaging.hashAlgorithm 目前只支持 "sha256"。')
    if "hashChunkBytes" in pack:
        _check_number(pack["hashChunkBytes"], "packaging.hashChunkBytes",
                      lo=4096, integer=True)
    for key in ("excludeNames", "excludeGlobs"):
        v = pack.get(key, [])
        if not isinstance(v, list) or not all(isinstance(x, str) for x in v):
            raise ConfigError(f"packaging.{key} 必须是字符串数组。")

    trash = cfg.get("trash", {})
    if not isinstance(trash, dict):
        raise ConfigError("trash 必须是对象。")
    if "maxAgeDays" in trash:
        _check_number(trash["maxAgeDays"], "trash.maxAgeDays", lo=0)
    if "maxSizeBytes" in trash:
        # 必须整数：避免 1.9 被 int() 截成 1 这种「悄悄改配置」
        _check_number(trash["maxSizeBytes"], "trash.maxSizeBytes", lo=0, integer=True)
    if "protectModified" in trash and not isinstance(trash["protectModified"], bool):
        raise ConfigError("trash.protectModified 必须是布尔值。")

    if not plugins and not remotes:
        warnings.append("配置里既没有本机插件也没有 GitHub 源，市场是空的。")

    return warnings


def load_config() -> dict:
    cfg = read_json(CONFIG_PATH, None, strict=True)
    validate_config(cfg)
    return cfg


def verify_mode() -> str:
    """packaging.verify：auto（默认）/ fast / strict。"""
    try:
        cfg = load_config()
    except ConfigError:
        return "auto"
    mode = (cfg.get("packaging") or {}).get("verify", "auto")
    return mode if mode in ("auto", "fast", "strict") else "auto"


def needs_exact(purpose: str) -> bool:
    """这个用途要不要读到文件内容（完整 SHA-256）。

    · strict  —— 一律精确（连网页状态也精确，方便排查）
    · auto / fast —— 只有 install / uninstall 这种会**动用户磁盘**的用途才精确。
      网页状态用廉价指纹，误差只是显示；而 fast 不再能削弱破坏性判定，
      v2 那种「fast 导致 update 漏判 modified」的路子被彻底堵死。
    """
    if purpose not in CLASSIFY_PURPOSES:
        raise ValueError(f"未知用途 {purpose!r}")
    if verify_mode() == "strict":
        return True
    return purpose in EXACT_PURPOSES


def hash_chunk_bytes() -> int:
    """流式 SHA-256 的块大小，来自 packaging.hashChunkBytes。"""
    try:
        cfg = load_config()
    except ConfigError:
        return HASH_CHUNK_BYTES
    v = (cfg.get("packaging") or {}).get("hashChunkBytes", HASH_CHUNK_BYTES)
    if isinstance(v, int) and not isinstance(v, bool) and v >= 4096:
        return v
    return HASH_CHUNK_BYTES
