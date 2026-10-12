# -*- coding: utf-8 -*-
"""基础命令：list / unlock / rollback / doctor。"""
from __future__ import annotations

import json
import os
import shutil
import sys
import time
from pathlib import Path

from .. import config
from ..errors import E_LOCKED, E_UNSAFE_PATH, E_WRITE, UnsafePathError
from ..lock import (acquire_lock, lock_heartbeat_age, pid_alive, read_lock,
                    release_lock)
from ..pathguard import validate_managed_path
from ..registry import load, migrate_registry
from ..remote import _http_code
from ..transaction import restore_backup
from ..util import (disk_free_bytes, emit, fmt_ts, format_bytes, path_size_bytes, run)


def cmd_list(args):
    data = load()
    ps = data["projects"]
    if args.json:
        print(json.dumps(data, ensure_ascii=False))
        return
    if not ps:
        print("清单为空。用 `ghpm add <repo>` 添加，或 `ghpm scan` 自动发现。")
        return
    print("共 %d 个受管项目\n" % len(ps))
    for p in ps:
        print("  %-24s %-38s %s" % (p.get("name", "?"), p.get("repo", "?"),
                                    p.get("sha_short", "-")))
        if p.get("desc"):
            print("      %s" % p["desc"])
        if p.get("skill_names"):
            print("      skills: %s" % ", ".join(p["skill_names"]))
        print("      安装 %s  版本更新 %s  最近检查 %s"
              % (fmt_ts(p.get("installed_at")), fmt_ts(p.get("updated_at")),
                 fmt_ts(p.get("checked_at"))))
        print()


# ---------- unlock ----------

def cmd_unlock(args):
    """清锁。v2 是无条件 unlink —— 那会绕过 token 锁，把正在写盘的进程的锁
    直接抹掉，让第二个进程并发写 skills。这里改成先确认持有者是否还活着。

    v4 起判定多了一层租约：连进程都查不出来（tasklist 缺失 / 无权限）时，
    心跳还新的锁同样拒绝清除 —— 拿不准就不要动。
    """
    from ..lock import _lock_path, lock_is_stale
    force = bool(getattr(args, "force", False))
    lock = _lock_path()
    if not lock.exists():
        print("当前没有锁")
        return
    st = read_lock()
    if not st:
        try:
            lock.unlink()
            print("锁文件内容无法解析（不是有效锁），已清除")
        except Exception as e:
            print("删除锁文件失败：%s" % e)
        return

    pid = st.get("pid")
    alive = pid_alive(pid)
    hb = lock_heartbeat_age(st, None)
    if alive is True and not force:
        emit("failed", "锁仍被占用，拒绝清除", percent=100, code=E_LOCKED,
             detail="持有者 pid=%s（%s，开始于 %s）" % (pid, st.get("op", "?"), st.get("at", "?")),
             hint="该进程正在写 skills 目录，强删会导致并发写入。等它结束再试；"
                  "确认它已僵死且不会恢复时用 `ghpm unlock --force`。")
        raise RuntimeError("%s 锁仍被进程 %s 持有，未清除" % (E_LOCKED, pid))
    if alive is None and not lock_is_stale(st, None) and not force:
        emit("failed", "无法确认锁的持有者是否还活着，拒绝清除", percent=100, code=E_LOCKED,
             detail="pid=%s（%.0f 秒前还有心跳）" % (pid, hb),
             hint="进程查询不可用（缺 tasklist / 无权限），而心跳仍在租约内。"
                  "确认没有 ghpm 在跑就用 `ghpm unlock --force`。")
        raise RuntimeError("%s 锁的持有者状态未知，未清除" % E_LOCKED)

    if alive is not False and force:
        print("  [警告] 持有者可能仍在运行，按 --force 强行清锁，可能造成并发写入。",
              file=sys.stderr)
    if pid == os.getpid():
        release_lock(st.get("token"))
    else:
        try:
            lock.unlink()
        except Exception as e:
            print("删除锁文件失败：%s" % e)
            print("无妨 —— 锁的持有者进程结束后会被自动判定为陈旧锁。")
            return
    print("锁已清除")


# ---------- rollback ----------

def cmd_rollback(args):
    """把某次备份恢复到原位，并逐项报告失败。

    v3.1 这里直接 restore_backup，没拿写锁 —— 于是 install 正在写 skills/foo 时，
    另一个进程可以同时把 foo 覆盖回旧版，两边都以为自己是最后一次写入。
    回滚同样是写操作，必须和 install/update/remove/scan 互斥。
    """
    bd = Path(args.backup)
    if not bd.exists():
        emit("failed", "备份目录不存在", percent=100, code="E_NOT_FOUND", detail=str(bd))
        print("备份目录不存在：%s" % bd, file=sys.stderr)
        return
    # 备份目录本身也要在 WB 内，否则 restore_backup 里的 strict 校验会全量拒绝，
    # 结果就是「什么都没恢复」——先在这里给出明确原因。
    try:
        bd = validate_managed_path(bd, config.WB, "备份目录")
    except UnsafePathError as e:
        emit("failed", "备份路径越界", percent=100, code=E_UNSAFE_PATH, detail=str(e),
             hint="回滚只允许操作 %s 之内的备份目录。" % config.WB)
        raise

    with _RollbackLock(bd):
        result = restore_backup(bd)
        restored = result["restored"]
        failed = result["failed"]
        if restored:
            print("已恢复 %d 项：" % len(restored))
            for r in restored:
                print("  " + r)
        if result.get("skipped"):
            print("有 %d 项因路径越界被跳过（清单可能被手工改坏）："
                  % len(result["skipped"]), file=sys.stderr)
            for item in result["skipped"]:
                print("  %s: %s" % (item.get("path", "?"), item.get("error", "?")),
                      file=sys.stderr)
        if failed:
            print("有 %d 项恢复失败，备份已保留：" % len(failed), file=sys.stderr)
            for item in failed:
                print("  %s: %s" % (item.get("path", "?"), item.get("error", "未知错误")),
                      file=sys.stderr)
            emit("failed", "回滚不完整", percent=100, code=E_WRITE, backup=str(bd),
                 data={"rollback": result})
            raise RuntimeError("%s 回滚不完整" % E_WRITE)
        if not restored:
            print("没有可恢复的内容：%s" % bd)
            emit("done", "没有可恢复的内容", percent=100, ok=True,
                 backup=str(bd), data={"rollback": result})
            return
        emit("done", "回滚完成 · %d 项" % len(restored), percent=100, ok=True,
             data={"rollback": result})


class _RollbackLock:
    """回滚的写锁。单独写一个小上下文，是为了让「拿不到锁」也能 emit E_LOCKED
    （LockSession 也会抛，但这里的提示文案是回滚专属的）。"""

    def __init__(self, bd: Path):
        self.bd = bd
        self.holder: dict = {}

    def __enter__(self):
        self.lock, self.holder = acquire_lock("rollback %s" % self.bd.name)
        if not self.lock:
            emit("failed", "有另一个任务正在修改，请稍后再试", percent=100, code=E_LOCKED,
                 detail="占用者：%s" % self.holder.get("op", "?"),
                 hint="回滚会写 skills 目录，必须等写任务结束。")
            raise RuntimeError("%s %s 当前无法回滚" % (E_LOCKED, self.bd.name))
        return self

    def __exit__(self, *exc):
        release_lock(self.holder.get("token"))


# ---------- doctor ----------

def _doctor_item(name: str, status: str, detail: str, hint: str = "") -> dict:
    item = {"name": name, "status": status, "detail": detail}
    if hint:
        item["hint"] = hint
    return item


def _doctor_api() -> dict:
    """短超时探测 GitHub API，并返回额度信息。"""
    cmd = ["curl", "-sSL", "--max-time", "10", "-w", "\n__HTTP__%{http_code}",
           "-H", "Accept: application/vnd.github+json"]
    if config.GH_TOKEN:
        cmd += ["-H", "Authorization: Bearer %s" % config.GH_TOKEN]
    cmd.append("https://api.github.com/rate_limit")
    r = run(cmd)
    code = _http_code(r.stdout)
    body = r.stdout.rsplit("__HTTP__", 1)[0] if "__HTTP__" in (r.stdout or "") else r.stdout
    if r.returncode != 0:
        raise RuntimeError(r.stderr.strip()[:160] or "curl 请求失败")
    if not code.isdigit() or int(code) >= 400:
        raise RuntimeError("HTTP %s" % (code or "?"))
    data = json.loads(body)
    core = (data.get("resources") or {}).get("core") or data.get("rate") or {}
    return {"remaining": core.get("remaining"), "limit": core.get("limit")}


def cmd_doctor(args):
    """只读诊断运行环境、网络、清单、锁、缓存、备份与磁盘。"""
    checks = []
    py_ok = sys.version_info >= (3, 10)
    checks.append(_doctor_item("Python", "OK" if py_ok else "FAIL",
                               "%d.%d.%d" % sys.version_info[:3],
                               "需要 Python 3.10+" if not py_ok else ""))

    curl = shutil.which("curl")
    if curl:
        try:
            r = run([curl, "--version"])
            version = (r.stdout or "").splitlines()[0] if r.returncode == 0 else curl
            checks.append(_doctor_item("curl", "OK", version))
        except Exception as e:
            checks.append(_doctor_item("curl", "FAIL", str(e)[:160]))
    else:
        checks.append(_doctor_item("curl", "FAIL", "PATH 中未找到 curl",
                                   "安装 curl 并确保命令可用"))

    checks.append(_doctor_item("GITHUB_TOKEN", "OK" if config.GH_TOKEN else "WARN",
                               "已配置" if config.GH_TOKEN else "未配置（GitHub API 仅 60 次/小时）",
                               "频繁检查时建议配置 GITHUB_TOKEN" if not config.GH_TOKEN else ""))

    if getattr(args, "no_network", False):
        checks.append(_doctor_item("GitHub API", "SKIP", "按 --no-network 跳过"))
    elif not curl:
        checks.append(_doctor_item("GitHub API", "FAIL", "无法探测：curl 不可用"))
    else:
        try:
            rate = _doctor_api()
            detail = "连接正常"
            if rate.get("remaining") is not None:
                detail += "，额度 %s/%s" % (rate["remaining"], rate.get("limit", "?"))
            checks.append(_doctor_item("GitHub API", "OK", detail))
        except Exception as e:
            checks.append(_doctor_item("GitHub API", "FAIL", str(e)[:160],
                                       "检查网络、代理或 token 后重试"))

    anchor = config.WB
    while not anchor.exists() and anchor.parent != anchor:
        anchor = anchor.parent
    writable = os.access(anchor, os.W_OK)
    checks.append(_doctor_item("WorkBuddy 目录", "OK" if writable else "FAIL",
                               "%s（%s）" % (config.WB, "可写" if writable else "不可写")))

    if not config.REGISTRY.exists():
        checks.append(_doctor_item("Registry", "OK", "尚未创建，将在首次安装时生成 schema v%d"
                                   % config.REGISTRY_SCHEMA_VERSION))
    else:
        try:
            raw = json.loads(config.REGISTRY.read_text(encoding="utf-8"))
            version = raw.get("schema_version", 1) if isinstance(raw, dict) else "?"
            migrated = migrate_registry(raw)
            status = "OK" if version == config.REGISTRY_SCHEMA_VERSION else "WARN"
            checks.append(_doctor_item("Registry", status,
                                       "schema v%s，%d 个项目（当前目标 v%d）"
                                       % (version, len(migrated.get("projects", [])),
                                          config.REGISTRY_SCHEMA_VERSION),
                                       "下次成功写入清单时会自动迁移到当前版本"
                                       if status == "WARN" else ""))
        except Exception as e:
            checks.append(_doctor_item("Registry", "FAIL", str(e)[:160],
                                       "先备份损坏文件，再运行任一写命令触发留档恢复"))

    lock = config.LOCK
    if not lock.exists():
        checks.append(_doctor_item("写锁", "OK", "当前无锁"))
    else:
        st = read_lock()
        mtime = None
        try:
            mtime = lock.stat().st_mtime
        except OSError:
            pass
        hb = lock_heartbeat_age(st, mtime) if st else float("inf")
        hb_txt = ("心跳 %.0fs 前" % hb) if hb != float("inf") else "无心跳记录"
        if not st:
            checks.append(_doctor_item("写锁", "WARN", "锁文件损坏（%s）" % hb_txt,
                                       "确认没有 ghpm 任务后运行 `ghpm unlock`"))
        elif pid_alive(st.get("pid")) is True:
            checks.append(_doctor_item("写锁", "WARN",
                                       "pid=%s 正在执行 %s（%s）"
                                       % (st.get("pid"), st.get("op", "?"), hb_txt)))
        else:
            checks.append(_doctor_item("写锁", "WARN",
                                       "发现陈旧锁 pid=%s（%s）" % (st.get("pid", "?"), hb_txt),
                                       "运行 `ghpm unlock` 清理"))

    cache_files = list(config.CACHE.glob("repo-*.json")) if config.CACHE.is_dir() else []
    cache_size = sum(path_size_bytes(p) for p in cache_files)
    cache_status = "WARN" if len(cache_files) > config.CACHE_MAX_FILES else "OK"
    checks.append(_doctor_item("缓存", cache_status,
                               "%d 个文件，%s" % (len(cache_files), format_bytes(cache_size))))

    skill_count = 0
    if config.SKILLS.is_dir():
        skill_count = sum(1 for p in config.SKILLS.iterdir()
                          if p.is_dir() and (p / "SKILL.md").is_file())
    checks.append(_doctor_item("Skills 目录", "OK",
                               "%s，%d 个标准 skill" % (config.SKILLS, skill_count)))

    backups = [p for p in config.WB.glob(".ghpm-backup-*")
               if p.is_dir()] if config.WB.is_dir() else []
    old_cutoff = time.time() - 7 * 24 * 3600
    old_backups = [p for p in backups if p.stat().st_mtime < old_cutoff]
    if old_backups:
        checks.append(_doctor_item("事务备份", "WARN", "%d 个备份，其中 %d 个超过 7 天"
                                   % (len(backups), len(old_backups)),
                                   "确认无需回滚后再手动处理旧备份"))
    else:
        checks.append(_doctor_item("事务备份", "OK",
                                   "%d 个（无超过 7 天的旧备份）" % len(backups)))

    try:
        free = disk_free_bytes(config.WB)
        min_free = int(float(os.environ.get("GHPM_DOCTOR_MIN_FREE_MB", "1024")) * config.MIB)
        status = "OK" if free >= min_free else "WARN"
        checks.append(_doctor_item("磁盘空间", status, "可用 %s" % format_bytes(free),
                                   "建议至少保留 %s" % format_bytes(min_free)
                                   if status == "WARN" else ""))
    except Exception as e:
        checks.append(_doctor_item("磁盘空间", "FAIL", str(e)[:160]))

    summary = {s: sum(1 for x in checks if x["status"] == s)
               for s in ("OK", "WARN", "FAIL", "SKIP")}
    payload = {"ok": summary["FAIL"] == 0, "checks": checks, "summary": summary,
               "schema_version": config.REGISTRY_SCHEMA_VERSION,
               "backup_mode": config.backup_mode()}
    if getattr(args, "json", False):
        print(json.dumps(payload, ensure_ascii=False))
        return

    print("GHPM Doctor\n")
    for item in checks:
        print("[%s] %-14s %s" % (item["status"], item["name"], item["detail"]))
        if item.get("hint"):
            print("       建议：%s" % item["hint"])
    print("\n汇总：%d OK，%d WARN，%d FAIL，%d SKIP（备份介质 %s）"
          % (summary["OK"], summary["WARN"], summary["FAIL"], summary["SKIP"],
             config.backup_mode()))
    print("数据完整性请用 `ghpm verify`（doctor 只看运行环境能不能用）。")
    emit("done", "诊断完成", percent=100, ok=payload["ok"], data=payload)
