"""原子写与 JSON 读写（v2.8 自 market_core.py 逐字迁入，只搬不改）。"""
from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path

from .errors import ConfigError


def _fsync_dir(path: Path) -> None:
    """POSIX 上 fsync 目录项。

    `os.replace` 之后，文件**内容**已经 fsync 过了，但「rename 这个目录项」
    本身要不要落盘，取决于父目录有没有 fsync。断电场景下可能出现
    「内容在、改名没生效」或者反过来。Windows 没有这个语义（也不允许
    对目录 open），直接跳过。
    """
    if os.name == "nt":
        return
    try:
        fd = os.open(str(path), os.O_RDONLY)
    except OSError:
        return
    try:
        os.fsync(fd)
    except OSError:
        pass
    finally:
        try:
            os.close(fd)
        except OSError:
            pass


def atomic_write_bytes(path: Path, data: bytes, *, durable: bool = False) -> None:
    """唯一临时文件 → fsync → os.replace（可选再 fsync 父目录）。

    durable=True 用于「丢了会很难受」的少数文件（ownership / 注册表 / 事务日志）。
    普通打包产物没必要付这个代价。
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=str(path.parent), prefix=".tmp-", suffix=path.suffix)
    try:
        with os.fdopen(fd, "wb") as fh:
            fh.write(data)
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp, path)
        if durable:
            _fsync_dir(path.parent)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def atomic_write_text(path: Path, text: str, *, durable: bool = False) -> None:
    """唯一临时文件 → fsync → os.replace，避免半截 JSON。"""
    atomic_write_bytes(path, text.encode("utf-8"), durable=durable)


def write_text_if_changed(path: Path, text: str, *, durable: bool = False) -> bool:
    """内容一样就不写。

    原子写要走 fsync，是个真开销（实测 8 次约 80ms）。而 plugin.json /
    README / 市场索引 / 状态文件在绝大多数同步里内容是一样的 —— 跳过它们
    能让「什么都没变」的那次同步几乎零写盘。返回是否真的写了。
    """
    try:
        if path.is_file() and path.read_text(encoding="utf-8") == text:
            return False
    except (OSError, UnicodeDecodeError):
        pass
    atomic_write_text(path, text, durable=durable)
    return True


def read_json(path: Path, default=None, *, strict: bool = False):
    """读 JSON。

    strict=False（默认）：容错，读不到/坏了就返回 default。
    strict=True：关键文件（配置、索引）用它，坏了直接抛，并带上
    行列出错信息 —— 否则「配置写坏了」会表现成「配置不存在」，很难查。
    """
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        if strict:
            raise ConfigError(f"{path.name} 不存在（{path}）") from None
        return default
    except UnicodeDecodeError as exc:
        if strict:
            raise ConfigError(f"{path.name} 不是合法 UTF-8：{exc}") from exc
        return default
    except ValueError as exc:
        if strict:
            raise ConfigError(f"{path.name} 不是合法 JSON：{exc}") from exc
        return default
    except OSError as exc:
        if strict:
            raise ConfigError(f"{path.name} 读取失败：{exc}") from exc
        return default
