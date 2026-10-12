# -*- coding: utf-8 -*-
"""ghpm v4.0 回归测试。全部在临时 GHPM_HOME 里跑，不碰真实 ~/.workbuddy。

覆盖 v3.2 的 P0（不能回退）：
  1. update 后远端已删除的 skill 必须从磁盘消失（状态收敛）
  2. rollback 必须拿写锁（与 install 互斥）
  3. remove 的 source_dir 越界必须被拒（不能 rmtree 任意目录）
  4. skill 冲突必须阻断安装，--force 才覆盖
  外加：ZIP 炸弹拦截、parse_repo 严格化、原子写唯一 tmp、硬链接备份。

v4.0 新增：
  5. 一次遍历：build_install_plan 不再反复扫描目录树
  6. update --all 复用批量预检的 RepoInfo（消灭 N+1 远程请求）
  7. Windows 保留设备名（NUL/CON）必须在解压前拦下
  8. 源码用 move 而不是再 copy 一遍
  9. verify 能发现「GitHub 没更新但本地被改过」
 10. 锁心跳：查不到进程时按租约判断，不抢活锁
 11. rename 备份模式：O(1) 搬走原目录，回滚搬回来

注意：拆分之后 monkeypatch 要打在**定义处**（ghpm.remote.repo_info /
ghpm.installer.fetch_zip …），打在包属性（ghpm.repo_info）上不会影响
模块内部的调用 —— 这是从单文件拆成包之后唯一需要改的测试习惯。
"""
import importlib
import io
import json
import os
import shutil
import sys
import tempfile
import time
import zipfile
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent


def load_ghpm(home: Path):
    """在指定 GHPM_HOME 下重新加载 ghpm 包。

    路径常量是在 import 时从环境变量解析的，所以换目录必须清掉
    sys.modules 里的整个 ghpm 包（含所有子模块）再 import ——
    只重新 exec 顶层 __init__ 是不够的，子模块会带着旧路径留在缓存里。
    """
    os.environ["GHPM_HOME"] = str(home)
    for name in [n for n in sys.modules if n == "ghpm" or n.startswith("ghpm.")]:
        del sys.modules[name]
    if str(SCRIPTS) not in sys.path:
        sys.path.insert(0, str(SCRIPTS))
    return importlib.import_module("ghpm")


def quiet():
    """把 stdout 吞掉（ghpm 会打进度行和 __GHPM__ 事件，测试里不需要）。"""
    return io.StringIO()


# ---------- 断言小工具 ----------

class Failed(Exception):
    pass


def ok(cond, msg):
    if not cond:
        raise Failed(msg)


def eq(a, b, msg=""):
    if a != b:
        raise Failed("%s：期望 %r，实际 %r" % (msg or "不相等", b, a))


# ---------- 构造一个假的 skill 包 ----------

def make_skill_pkg(root: Path, skills, extra_files=True):
    """在 root 下造出 skills/<name>/SKILL.md。skills 是 skill 名列表。"""
    root.mkdir(parents=True, exist_ok=True)
    for n in skills:
        d = root / "skills" / n
        d.mkdir(parents=True, exist_ok=True)
        (d / "SKILL.md").write_text(
            "---\nname: %s\ndescription: test\n---\n\n# %s\n" % (n, n), encoding="utf-8")
        (d / "run.py").write_text("print('%s')\n" % n, encoding="utf-8")
    if extra_files:
        (root / "README.md").write_text("# test repo\n", encoding="utf-8")


def info_dict(sha="bbb"):
    return {"branch": "main", "sha": sha, "sha_short": sha[:7], "stars": 1,
            "desc": "", "pushed_at": "", "msg": ""}


# ---------- v3.2 回归 ----------

def test_parse_repo_strict():
    """parse_repo 必须严格：多段路径、带查询串、http 都要拒绝。"""
    home = Path(tempfile.mkdtemp(prefix="ghpm-t-"))
    try:
        m = load_ghpm(home)
        eq(m.parse_repo("alice/utils"), "alice/utils", "裸 owner/repo")
        eq(m.parse_repo("https://github.com/alice/utils"), "alice/utils", "标准 URL")
        eq(m.parse_repo("https://github.com/alice/utils/"), "alice/utils", "尾部斜杠")
        eq(m.parse_repo("https://github.com/alice/utils.git"), "alice/utils", ".git 后缀")
        eq(m.parse_repo("git@github.com:alice/utils.git"), "alice/utils", "SSH 形式")  # pa:allow

        # 这些在 v3.1 会被误接受
        for bad in ("https://github.com/foo/bar/xxxx",
                    "https://github.com/foo/bar?tab=readme",
                    "https://github.com/foo/bar#frag",
                    "http://github.com/foo/bar",
                    "https://gitlab.com/foo/bar",
                    "https://github.com/foo",
                    "https://github.com/foo/bar/baz/qux"):
            try:
                got = m.parse_repo(bad)
                raise Failed("parse_repo 应该拒绝 %r，实际返回 %r" % (bad, got))
            except ValueError:
                pass
    finally:
        shutil.rmtree(home, ignore_errors=True)


def test_removed_skills_converge():
    """P0-1：远端删掉 foo 之后，本地 skills/foo 必须消失，清单也不再含它。"""
    home = Path(tempfile.mkdtemp(prefix="ghpm-t-"))
    try:
        m = load_ghpm(home)
        skills = home / "skills"
        skills.mkdir(parents=True)
        # 模拟「已安装过 foo 和 bar」
        for n in ("foo", "bar"):
            d = skills / n
            d.mkdir()
            (d / "SKILL.md").write_text("x", encoding="utf-8")
        m.save({"schema_version": 3, "projects": [{
            "name": "pkg", "repo": "alice/pkg", "sha": "aaa",
            "skill_names": ["foo", "bar"],
            "source_dir": str(home / "pkg-source"),
        }]})
        # 解压根在独立临时目录（真实流程就是这样），src_dir 在 WB 下
        extracted = Path(tempfile.mkdtemp(prefix="ghpm-ext-"))
        make_skill_pkg(extracted, ["bar"])    # 远端现在只剩 bar

        data = m.load()
        info = info_dict()
        plan = m.build_install_plan("alice/pkg", "pkg", "main", info, extracted, data, False)
        eq(plan.removed_skills, ["foo"], "removed_skills 应识别出 foo")
        eq(plan.new_skills, ["bar"], "new_skills")
        ok((skills / "foo").exists(), "前置条件：foo 应该还在")

        out = sys.stdout
        sys.stdout = quiet()
        try:
            m.apply_install_plan(plan, info, data)
        finally:
            sys.stdout = out

        ok(not (skills / "foo").exists(), "foo 应随远端下线被删除")
        ok((skills / "bar").exists(), "bar 应保留")
        ok((home / "pkg-source").is_dir(), "源码副本应存在")
        ok((home / "pkg-source" / "skills" / "bar" / "SKILL.md").is_file(),
           "源码副本内容应来自新版本")
        after = m.load()
        eq(after["projects"][0]["skill_names"], ["bar"], "清单里不应再有 foo")
        eq(after["projects"][0]["skill_hashes"].get("bar", ""), plan.skill_hashes["bar"],
           "清单应记录 skill 指纹")
        shutil.rmtree(extracted, ignore_errors=True)
    finally:
        shutil.rmtree(home, ignore_errors=True)


def test_removed_skill_rollback():
    """删掉的 skill 也必须可回滚 —— 删除是破坏性操作，不能不可逆。"""
    home = Path(tempfile.mkdtemp(prefix="ghpm-t-"))
    try:
        m = load_ghpm(home)
        skills = home / "skills"
        skills.mkdir(parents=True)
        d = skills / "foo"
        d.mkdir()
        (d / "SKILL.md").write_text("old content", encoding="utf-8")
        m.save({"schema_version": 3, "projects": [{
            "name": "pkg", "repo": "alice/pkg", "sha": "aaa",
            "skill_names": ["foo"], "source_dir": str(home / "pkg-source"),
        }]})
        src = home / "pkg-source"
        make_skill_pkg(src, [])     # 远端没有 skill 了

        data = m.load()
        info = info_dict()
        plan = m.build_install_plan("alice/pkg", "pkg", "main", info, src, data, True)
        eq(plan.removed_skills, ["foo"], "应识别 foo 为已下线")

        # 手动走 apply，但在删除后立刻抛错，模拟写到一半失败
        tx = m.Transaction("alice/pkg", "pkg", "update")
        tx.track(m.install_targets(plan))
        bd = tx.begin()
        try:
            m.remove_managed_path(skills / "foo", "skill 目录")
            raise RuntimeError("模拟写入失败")
        except RuntimeError:
            res = tx.rollback()
        eq(res["failed"], [], "回滚不应有失败项：%s" % res["failed"])
        ok((skills / "foo").exists(), "回滚后 foo 应重新出现")
        eq((skills / "foo" / "SKILL.md").read_text(encoding="utf-8"),
           "old content", "回滚后内容应是旧的")
        shutil.rmtree(bd, ignore_errors=True)
    finally:
        shutil.rmtree(home, ignore_errors=True)


def test_conflict_blocks_install():
    """P0-4：skill 被别的项目占用时必须拒绝安装，--force 才覆盖。"""
    home = Path(tempfile.mkdtemp(prefix="ghpm-t-"))
    try:
        m = load_ghpm(home)
        skills = home / "skills"
        (skills / "foo").mkdir(parents=True)
        (skills / "foo" / "SKILL.md").write_text("owner A", encoding="utf-8")
        m.save({"schema_version": 3, "projects": [{
            "name": "a", "repo": "alice/proj-a", "sha": "x", "skill_names": ["foo"],
            "source_dir": str(home / "a-source"),
        }]})

        src = home / "b-src"
        make_skill_pkg(src, ["foo"])

        data = m.load()
        info = info_dict("yyy")
        plan = m.build_install_plan("bob/proj-b", "proj-b", "main", info, src, data, False)
        eq(len(plan.conflicts), 1, "应检出 1 个冲突")
        eq(plan.conflicts[0], {"skill": "foo", "owner": "alice/proj-a"}, "冲突详情")
        err = m.ConflictError(plan.conflicts)
        ok("foo" in str(err), "异常信息应包含冲突的 skill 名：%s" % err)

        # apply_install_plan 本身不判冲突（install 已在上游拦了），
        # 但 install 路径必须拦。这里直接验证 inspect 与 install 用同一个检测函数。
        conflicts = m.find_skill_conflicts("bob/proj-b", ["foo"], m.load())
        eq(len(conflicts), 1, "find_skill_conflicts 与 plan 结果必须一致")
        eq(m.find_skill_conflicts("alice/proj-a", ["foo"], m.load()), [],
           "自己拥有自己的 skill 不算冲突")
    finally:
        shutil.rmtree(home, ignore_errors=True)


def test_remove_path_containment():
    """P0-3：source_dir 越界的清单记录必须被 remove 拒绝，且不能删掉外部目录。"""
    home = Path(tempfile.mkdtemp(prefix="ghpm-t-"))
    victim = Path(tempfile.mkdtemp(prefix="ghpm-victim-"))
    try:
        (victim / "important.txt").write_text("don't delete me", encoding="utf-8")
        m = load_ghpm(home)
        m.save({"schema_version": 3, "projects": [{
            "name": "evil", "repo": "mallory/evil", "sha": "x", "skill_names": [],
            "source_dir": str(victim),     # 越界指向临时目录
        }]})

        try:
            m.remove_managed_path(victim, "source_dir")
            raise Failed("越界路径本应被拒绝")
        except m.UnsafePathError:
            pass
        ok(victim.exists(), "越界目标目录不能被删")

        args = type("A", (), {"name": "evil"})()
        buf = quiet()
        old = sys.stdout
        sys.stdout = buf
        try:
            m.cmd_remove(args)
        except m.UnsafePathError:
            pass
        finally:
            sys.stdout = old
        out = buf.getvalue()
        ok("E_UNSAFE_PATH" in out, "应报 E_UNSAFE_PATH，实际输出：%s" % out[-300:])
        ok(victim.exists(), "cmd_remove 不能删掉 WB 之外的目录")
        ok((victim / "important.txt").exists(), "受害目录内容必须完好")
    finally:
        shutil.rmtree(home, ignore_errors=True)
        shutil.rmtree(victim, ignore_errors=True)


def test_restore_backup_containment():
    """回滚也要做路径校验：坏 manifest 不能借回滚删掉 WB 外的东西。"""
    home = Path(tempfile.mkdtemp(prefix="ghpm-t-"))
    victim = Path(tempfile.mkdtemp(prefix="ghpm-victim-"))
    try:
        (victim / "x.txt").write_text("safe", encoding="utf-8")
        m = load_ghpm(home)
        bd = home / ".ghpm-backup-bogus-1"
        bd.mkdir()
        (bd / "_manifest.json").write_text(json.dumps({
            "version": 4, "name": "bogus", "repo": "x/y", "op": "install",
            "at": m.now(),
            "items": {str(victim): {"existed": False, "backup": None, "kind": "dir"}},
        }), encoding="utf-8")
        res = m.restore_backup(bd)
        ok(victim.exists(), "越界的回滚项必须被跳过，目标目录不能被删")
        ok(len(res["failed"]) >= 1, "越界项应记入 failed")
    finally:
        shutil.rmtree(home, ignore_errors=True)
        shutil.rmtree(victim, ignore_errors=True)


def test_rollback_takes_lock():
    """P0-2：rollback 必须和 install/update 互斥。"""
    home = Path(tempfile.mkdtemp(prefix="ghpm-t-"))
    try:
        m = load_ghpm(home)
        src = home / "s"
        src.mkdir()
        (src / "f.txt").write_text("v1", encoding="utf-8")
        tx = m.Transaction("a/b", "b", "install")
        tx.track([src])
        bd = tx.begin()
        tx.commit(purge=False)

        # 假装另一个进程正持有写锁
        payload = {"pid": os.getpid(), "epoch": time.time(), "at": m.now(),
                   "op": "install a/b", "token": "someone-else"}
        m.LOCK.parent.mkdir(parents=True, exist_ok=True)
        m.LOCK.write_text(json.dumps(payload), encoding="utf-8")

        args = type("A", (), {"backup": str(bd)})()
        buf = quiet()
        old = sys.stdout
        sys.stdout = buf
        err = None
        try:
            m.cmd_rollback(args)
        except RuntimeError as e:
            err = e
        finally:
            sys.stdout = old
            m.LOCK.unlink(missing_ok=True)
        ok(err is not None, "有别人持锁时 rollback 必须失败")
        ok("E_LOCKED" in str(err), "应报 E_LOCKED，实际：%s" % err)
        eq((src / "f.txt").read_text(encoding="utf-8"), "v1", "被拒绝时不应改动文件")

        buf = quiet()
        sys.stdout = buf
        try:
            m.cmd_rollback(args)
        finally:
            sys.stdout = old
        ok("E_LOCKED" not in buf.getvalue(), "无锁时应能回滚")
    finally:
        shutil.rmtree(home, ignore_errors=True)


def test_atomic_write_unique_tmp():
    """原子写必须用唯一临时名，且不留 .tmp 垃圾。"""
    home = Path(tempfile.mkdtemp(prefix="ghpm-t-"))
    try:
        m = load_ghpm(home)
        dest = home / "x.json"
        m.atomic_write_bytes(dest, '{"a":1}')
        eq(json.loads(dest.read_text(encoding="utf-8"))["a"], 1, "内容")
        leftovers = list(home.glob("*.tmp"))
        eq(leftovers, [], "不应留下 .tmp 文件")
    finally:
        shutil.rmtree(home, ignore_errors=True)


def test_backup_uses_hardlink():
    """备份应走硬链接（快且省空间），跨卷/不支持时自动降级为复制。"""
    home = Path(tempfile.mkdtemp(prefix="ghpm-t-"))
    try:
        m = load_ghpm(home)
        src = home / "big"
        src.mkdir()
        (src / "f.bin").write_bytes(b"x" * 1024)
        tx = m.Transaction("a/b", "b", "install")
        tx.track([src])
        bd = tx.begin()
        backed = bd / "big" / "f.bin"
        ok(backed.exists(), "备份文件应存在")
        if m.config.backup_mode() == "link":
            try:
                eq(os.stat(backed).st_ino, os.stat(src / "f.bin").st_ino,
                   "link 模式下应是同一个 inode")
            except AttributeError:
                pass    # Windows 没有 ino，跳过
        shutil.rmtree(bd, ignore_errors=True)
        ok(src.exists(), "link 备份不应搬走原目录")

        # copy 模式必须也能工作
        old_mode = m.config.BACKUP_MODE
        m.config.BACKUP_MODE = "copy"
        try:
            tx2 = m.Transaction("a/b", "b", "install")
            tx2.track([src])
            bd2 = tx2.begin()
            ok((bd2 / "big" / "f.bin").exists(), "copy 模式也要备份成功")
            shutil.rmtree(bd2, ignore_errors=True)
        finally:
            m.config.BACKUP_MODE = old_mode
    finally:
        shutil.rmtree(home, ignore_errors=True)


def test_zip_bomb_limits():
    """ZIP 条目数 / 单文件大小 / 压缩比上限必须在解压前拦下。"""
    home = Path(tempfile.mkdtemp(prefix="ghpm-t-"))
    try:
        m = load_ghpm(home)

        class FakeInfo:
            def __init__(self, size, comp, name="f", is_dir=False):
                self.file_size, self.compress_size = size, comp
                self.filename, self._d = name, is_dir
            def is_dir(self):
                return self._d

        many = [FakeInfo(1, 1, "f%d" % i) for i in range(m.MAX_ZIP_ENTRIES + 1)]
        try:
            m.check_zip_limits(many)
            raise Failed("条目数超限应被拒")
        except m.BadArchiveError:
            pass

        try:
            m.check_zip_limits([FakeInfo(m.MAX_ZIP_FILE_SIZE + 1, 1, "big.bin")])
            raise Failed("单文件超限应被拒")
        except m.BadArchiveError:
            pass

        chunk = m.MAX_ZIP_UNCOMPRESSED // 4 + 1
        try:
            m.check_zip_limits([FakeInfo(chunk, 1, "a%d" % i) for i in range(8)])
            raise Failed("总展开体积超限应被拒")
        except m.BadArchiveError:
            pass

        try:
            m.check_zip_limits([FakeInfo(64 * m.MIB, 1024, "bomb.bin")])
            raise Failed("压缩炸弹应被拒")
        except m.BadArchiveError:
            pass

        res = m.check_zip_limits([FakeInfo(1024, 50, "a.txt"),
                                  FakeInfo(4096, 60, "b.txt")])
        eq(res["entry_count"], 2, "正常包条目数")
        eq(res["uncompressed_size"], 5120, "正常包展开体积")
    finally:
        shutil.rmtree(home, ignore_errors=True)


def test_zip_slip_still_blocked():
    """zip slip 防护不能因为重构被弄丢。"""
    home = Path(tempfile.mkdtemp(prefix="ghpm-t-"))
    try:
        m = load_ghpm(home)
        zpath = home / "evil.zip"
        with zipfile.ZipFile(zpath, "w") as zf:
            zf.writestr("../escaped.txt", "pwned")
        out = home / "out"
        out.mkdir()
        with zipfile.ZipFile(zpath) as zf:
            try:
                m.safe_extract(zf, out)
                raise Failed("zip slip 应被拦截")
            except m.BadArchiveError:
                pass
        ok(not (home / "escaped.txt").exists(), "不能有文件逃出解压目录")
    finally:
        shutil.rmtree(home, ignore_errors=True)


def test_manifest_records_nonexistent_targets():
    """v3 的核心保证不能回退：不存在的目标也要进 manifest。"""
    home = Path(tempfile.mkdtemp(prefix="ghpm-t-"))
    try:
        m = load_ghpm(home)
        missing = home / "skills" / "brand-new"
        tx = m.Transaction("a/b", "b", "install")
        tx.track([missing])
        bd = tx.begin()
        mf = m.read_manifest(bd)
        entry = mf["items"][str(missing)]
        eq(entry["existed"], False, "不存在的目标应记 existed=false")
        res = m.restore_backup(bd)
        eq(res["failed"], [], "回滚不应失败")
        ok(not missing.exists(), "回滚后应仍不存在")
        shutil.rmtree(bd, ignore_errors=True)
    finally:
        shutil.rmtree(home, ignore_errors=True)


def test_install_targets_include_removed():
    """removed_skills 必须进入事务目标，否则删除不可回滚。"""
    home = Path(tempfile.mkdtemp(prefix="ghpm-t-"))
    try:
        m = load_ghpm(home)
        plan = m.InstallPlan(repo="a/b", name="b", branch="main",
                             old_skills=["foo", "bar"], new_skills=["bar"],
                             removed_skills=["foo"])
        targets = m.install_targets(plan)
        ok((home / "skills" / "foo") in targets, "被删的 foo 必须在事务目标里")
        ok((home / "skills" / "bar") in targets, "bar 必须在事务目标里")
    finally:
        shutil.rmtree(home, ignore_errors=True)


def test_now_is_utc_iso():
    """时间戳必须是带时区的 UTC ISO 8601，且展示层能正确转本地。"""
    home = Path(tempfile.mkdtemp(prefix="ghpm-t-"))
    try:
        m = load_ghpm(home)
        s = m.now()
        ok(s.endswith("+00:00"), "now() 应带 +00:00 时区，实际 %s" % s)
        ok("T" in s, "now() 应是 ISO 格式，实际 %s" % s)
        out = m.fmt_ts(s)
        ok(len(out) == 19 and out[4] == "-", "fmt_ts 应输出 YYYY-MM-DD HH:MM:SS，实际 %s" % out)
        eq(m.fmt_ts(""), "-", "空值")
        eq(m.fmt_ts("坏时间"), "坏时间", "认不出的原样返回")
        eq(m.fmt_ts("2026-01-01 12:00:00"), m.fmt_ts("2026-01-01T12:00:00"),
           "新旧两种格式应指向同一时刻")
    finally:
        shutil.rmtree(home, ignore_errors=True)


def test_validate_skill_name():
    home = Path(tempfile.mkdtemp(prefix="ghpm-t-"))
    try:
        m = load_ghpm(home)
        for bad in ("", "..", ".", "a/b", "a\\b", "a\0b"):
            try:
                m.validate_skill_name(bad)
                raise Failed("非法 skill 名 %r 应被拒" % bad)
            except m.UnsafePathError:
                pass
        eq(m.validate_skill_name(" story-cover "), "story-cover", "两侧空白应裁掉")
    finally:
        shutil.rmtree(home, ignore_errors=True)


def test_fetch_repo_infos_is_concurrent():
    """批量查询必须真的并发，且能正确区分成功与失败。"""
    home = Path(tempfile.mkdtemp(prefix="ghpm-t-"))
    try:
        m = load_ghpm(home)

        def fake_repo_info(repo, ttl=0):
            if repo == "bad/one":
                raise RuntimeError("boom")
            time.sleep(0.05)
            return m.RepoInfo(repo=repo, branch="main", sha="s-" + repo,
                              sha_short="s", stars=0)

        # 拆包之后要打在定义处：ghpm.remote.fetch_repo_infos 用的是本模块的全局名
        m.remote.repo_info = fake_repo_info
        repos = ["a/%d" % i for i in range(20)] + ["bad/one"]
        t0 = time.time()
        ok_map, err_map = m.fetch_repo_infos(repos, ttl=0)
        dt = time.time() - t0
        eq(len(ok_map), 20, "应有 20 个成功")
        eq(list(err_map.keys()), ["bad/one"], "应有 1 个失败")
        ok(dt < 0.6, "并发没生效，耗时 %.2fs" % dt)

        ok2, err2 = m.fetch_repo_infos(["x/y"], ttl=0)
        eq(len(ok2), 1, "单个 repo 应走短路")
        eq(err2, {}, "单个 repo 不应有错误")
    finally:
        shutil.rmtree(home, ignore_errors=True)


# ---------- v4.0 新增 ----------

def test_source_tree_indexed_in_one_pass():
    """v4-1：找 skill + 量体积必须只用一次遍历。

    这是评审 P0#1 落地的判据：v3.2 是 find_skill_dirs 走一遍、
    path_size_bytes(root) 再走一遍、每个 skill 子目录又各走一遍。
    实测（2100 文件 / 100 skill）放大 2.02x；合并后只应剩 1 次。
    """
    home = Path(tempfile.mkdtemp(prefix="ghpm-t-"))
    ext = Path(tempfile.mkdtemp(prefix="ghpm-ext-"))
    try:
        m = load_ghpm(home)
        root = ext / "repo"
        make_skill_pkg(root, ["a", "b", "c"])
        (root / "docs").mkdir()
        (root / "docs" / "guide.md").write_text("x" * 5000, encoding="utf-8")

        calls = {"n": 0}
        real_scan = m.util.iter_tree
        real_scan_tree = m.util.scan_tree

        def counting_iter_tree(*a, **kw):
            calls["n"] += 1
            return real_scan(*a, **kw)

        # index_source_tree / scan_tree / tree_fingerprint 都走 iter_tree，
        # 数它就是数「遍历次数」
        m.discovery.iter_tree = counting_iter_tree
        try:
            index = m.discovery.index_source_tree(root, fallback="repo")
            eq(calls["n"], 1, "index_source_tree 只应遍历一次，实际 %d 次" % calls["n"])
        finally:
            m.discovery.iter_tree = real_scan

        eq(index.names, ["a", "b", "c"], "技能清单")
        total = sum(index.skill_bytes.values())
        full = m.path_size_bytes(root)
        ok(total < full, "skill 体积之和应小于整树体积（docs 不算在内）")
        eq(m.path_size_bytes(root / "skills" / "a"), index.skill_bytes["a"],
           "每个 skill 的体积必须与单独扫描一致")

        # build_install_plan 也必须只走一次：传 index 进去就不再重复扫描
        def _no_rescan(*a, **kw):
            raise Failed("estimate_install_bytes 不该再自己扫一遍（应复用 index）")

        calls["n"] = 0
        m.util.scan_tree = _no_rescan
        try:
            data = {"schema_version": 4, "projects": []}
            plan = m.build_install_plan("o/r", "r", "main", info_dict(), root, data,
                                        False, index=index)
        finally:
            m.util.scan_tree = real_scan_tree
        eq(plan.new_skills, ["a", "b", "c"], "plan 的技能清单")
        ok(plan.required_bytes > 0, "磁盘预检要算得出体积")
    finally:
        shutil.rmtree(home, ignore_errors=True)
        shutil.rmtree(ext, ignore_errors=True)


def test_find_skill_dirs_compat():
    """技能发现规则不能因为并进一次遍历而改变（含单 skill 仓库与嵌套路径）。"""
    home = Path(tempfile.mkdtemp(prefix="ghpm-t-"))
    try:
        m = load_ghpm(home)
        root = home / "multi"
        make_skill_pkg(root, ["x", "y"])
        # 仓库里 skills 目录不一定在顶层
        nested = root / "packages" / "k" / "skills" / "z"
        nested.mkdir(parents=True)
        (nested / "SKILL.md").write_text("---\nname: z\n---", encoding="utf-8")
        eq([n for n, _ in m.find_skill_dirs(root)], ["x", "y", "z"], "多 skill 包")

        single = home / "single"
        single.mkdir()
        (single / "SKILL.md").write_text("---\nname: from-meta\n---", encoding="utf-8")
        pairs = m.find_skill_dirs(single, fallback="fallback-name")
        eq([n for n, _ in pairs], ["from-meta"], "单 skill 仓库应取 frontmatter 的 name")

        empty = home / "empty"
        empty.mkdir()
        eq(m.find_skill_dirs(empty), [], "没有 SKILL.md 就是空")
    finally:
        shutil.rmtree(home, ignore_errors=True)


def test_update_reuses_repo_info():
    """v4-2：update --all 必须复用批量预检拿到的 RepoInfo，不再 N+1 请求。

    v3.2 实测：5 个仓库 10 次 repo_info（≈20 个 HTTP）。修好后应是 5 次。
    """
    home = Path(tempfile.mkdtemp(prefix="ghpm-t-"))
    ext = Path(tempfile.mkdtemp(prefix="ghpm-ext-"))
    try:
        m = load_ghpm(home)
        projects = [{"name": "r%d" % i, "repo": "o/r%d" % i, "sha": "old%d" % i,
                     "sha_short": "old%d" % i, "skill_names": [],
                     "source_dir": str(home / ("r%d-source" % i))} for i in range(3)]
        m.save({"schema_version": 4, "projects": projects})

        calls = []

        def fake_repo_info(repo, ttl=0):
            calls.append((repo, ttl))
            return m.RepoInfo(repo=repo, branch="main", sha="new", sha_short="new",
                              stars=1)

        def fake_fetch_zip(repo, branch, require_skill=False):
            tmp = Path(tempfile.mkdtemp(prefix="ghpm-zip-", dir=str(ext)))
            root = tmp / "repo"
            name = "s-" + repo.split("/")[-1]
            d = root / "skills" / name
            d.mkdir(parents=True)
            (d / "SKILL.md").write_text("---\nname: %s\n---" % name, encoding="utf-8")
            return tmp, root, {"entry_count": 1, "uncompressed_size": 1,
                               "root_prefix": "repo"}

        m.remote.repo_info = fake_repo_info
        m.installer.repo_info = fake_repo_info
        m.installer.fetch_zip = fake_fetch_zip

        args = type("A", (), {"all": True, "name": None, "dry_run": False,
                              "force": False, "fresh": True})()
        buf = quiet()
        old = sys.stdout
        sys.stdout = buf
        try:
            m.cmd_update(args)
        finally:
            sys.stdout = old

        eq(len(calls), 3, "3 个仓库只应查 3 次 repo_info（预检），实际 %d 次" % len(calls))
        ok(all(t == 0 for _, t in calls), "预检必须是 ttl=0（结果要被 install 复用）")
        after = m.load()
        eq(len(after["projects"]), 3, "三个项目都应在清单里")
        for p in after["projects"]:
            eq(p["sha"], "new", "%s 应被更新到新 sha" % p["repo"])
        ok((home / "r0-source" / "skills" / "s-r0" / "SKILL.md").is_file(),
           "源码副本应落盘")
    finally:
        shutil.rmtree(home, ignore_errors=True)
        shutil.rmtree(ext, ignore_errors=True)


def test_update_info_freshness_window():
    """v4-2b：复用的信息超出保鲜窗口时，必须为那个仓库单独补查一次。

    这是对评审建议的修正 —— 「预检完一次性批量写」会让后面几个仓库
    拿着几分钟前的 sha 安装，所以这里保留逐仓库事务 + 保鲜窗口。
    """
    home = Path(tempfile.mkdtemp(prefix="ghpm-t-"))
    try:
        m = load_ghpm(home)
        m.save({"schema_version": 4, "projects": [
            {"name": "r0", "repo": "o/r0", "sha": "old", "sha_short": "old",
             "skill_names": [], "source_dir": str(home / "r0-source")}]})

        calls = []

        def fake_repo_info(repo, ttl=0):
            calls.append(ttl)
            return m.RepoInfo(repo=repo, branch="main", sha="same", sha_short="same")

        m.remote.repo_info = fake_repo_info
        m.commands.update.repo_info = fake_repo_info

        req = m.commands.update.UpdateRequest(names=["o/r0"], fresh=True)
        up = m.commands.update.Updater({"schema_version": 4, "projects": []}, req,
                                       reuse_sec=0)      # 窗口为 0 → 必须补查
        latest = {"o/r0": m.RepoInfo(repo="o/r0", sha="x", sha_short="x")}
        info, err = up._info_for("o/r0", latest, time.time())
        ok(err is None, "补查不应报错")
        eq(info.get("sha"), "same", "应使用补查结果而不是过期的预检结果")
        eq(len(calls), 1, "应恰好补查 1 次")

        # 窗口内则复用，不再补查
        calls.clear()
        up2 = m.commands.update.Updater({"schema_version": 4, "projects": []}, req,
                                        reuse_sec=600)
        info2, _ = up2._info_for("o/r0", latest, time.time())
        eq(info2.get("sha"), "x", "窗口内应复用预检结果")
        eq(len(calls), 0, "窗口内不应补查")
    finally:
        shutil.rmtree(home, ignore_errors=True)


def test_zip_device_names_blocked():
    """v4-3：Windows 保留设备名必须在解压前拦下。

    标准库会剥掉 `..`、绝对路径、ADS，但**不管**设备名：
    条目叫 NUL 时解压不报错，文件却被系统吞掉（实测目录里啥都没有，
    而 (dest/"NUL").exists() 反而是 True）—— 这是静默丢数据。
    """
    home = Path(tempfile.mkdtemp(prefix="ghpm-t-"))
    try:
        m = load_ghpm(home)

        class FakeInfo:
            def __init__(self, name):
                self.filename = name
            def is_dir(self):
                return False

        # 控制字符：任何平台都拒绝
        try:
            m.check_zip_names([FakeInfo("bad\x07name.txt")])
            raise Failed("含控制字符的条目名应被拒")
        except m.BadArchiveError:
            pass

        # 绝对路径 / 盘符
        for bad in ("/etc/passwd", "C:/Windows/system32/evil.dll"):
            try:
                m.check_zip_names([FakeInfo(bad)])
                raise Failed("绝对路径条目应被拒：%s" % bad)
            except m.BadArchiveError:
                pass

        if os.name == "nt":
            for bad in ("NUL", "con", "CON.txt", "aux/child.txt", "COM1", "lpt2.log"):
                try:
                    m.check_zip_names([FakeInfo(bad)])
                    raise Failed("Windows 设备名条目应被拒：%s" % bad)
                except m.BadArchiveError:
                    pass
            # 正常名字不受影响
            res = m.check_zip_names([FakeInfo("repo-main/skills/foo/SKILL.md"),
                                     FakeInfo("console.txt"), FakeInfo("lock/note.md")])
            eq(res["checked"], 3, "正常条目应通过")

        # safe_extract 内部也要拦（防止绕过 fetch_zip 直接调用）
        out = home / "out"
        out.mkdir()
        z = home / "dev.zip"
        with zipfile.ZipFile(z, "w") as zf:
            zf.writestr("NUL", "silently swallowed")
        with zipfile.ZipFile(z) as zf:
            if os.name == "nt":
                try:
                    m.safe_extract(zf, out)
                    raise Failed("safe_extract 应拦下设备名条目")
                except m.BadArchiveError:
                    pass
            else:
                m.safe_extract(zf, out)     # 非 Windows 上 NUL 是合法文件名
    finally:
        shutil.rmtree(home, ignore_errors=True)


def test_source_is_moved_not_copied_twice():
    """v4-4：解压根应被 rename 进 source_dir，而不是再整棵拷一遍。"""
    home = Path(tempfile.mkdtemp(prefix="ghpm-t-"))
    try:
        m = load_ghpm(home)
        # WB（=home）与解压根都在同一个临时卷下，rename 应成功
        extracted = Path(tempfile.mkdtemp(prefix="ghpm-ext-"))
        make_skill_pkg(extracted, ["one"])

        data = {"schema_version": 4, "projects": []}
        info = info_dict()
        plan = m.build_install_plan("o/one", "one", "main", info, extracted, data, False)

        buf = quiet()
        old = sys.stdout
        sys.stdout = buf
        try:
            m.apply_install_plan(plan, info, data)
        finally:
            sys.stdout = old

        eq(plan.new_skills, ["one"], "应装上 one")
        ok((home / "one-source").is_dir(), "源码应落到 source_dir")
        ok(not extracted.exists(), "解压根应被搬走（rename），而不是原地留下再拷一份")
        ok((home / "skills" / "one" / "SKILL.md").is_file(), "skill 应已安装")
        ok((home / "one-source" / "skills" / "one" / "run.py").is_file(),
           "源码副本内容应完整")
    finally:
        shutil.rmtree(home, ignore_errors=True)


def test_verify_detects_local_modification():
    """v4-5：verify 必须能发现「GitHub 没更新，但本地 skill 被手改过」。

    只比对 sha 是发现不了的 —— sha 描述的是远端。
    """
    home = Path(tempfile.mkdtemp(prefix="ghpm-t-"))
    try:
        m = load_ghpm(home)
        extracted = Path(tempfile.mkdtemp(prefix="ghpm-ext-"))
        make_skill_pkg(extracted, ["alpha"])

        data = {"schema_version": 4, "projects": []}
        info = info_dict()
        plan = m.build_install_plan("o/pkg", "pkg", "main", info, extracted, data, False)

        buf = quiet()
        old = sys.stdout
        sys.stdout = buf
        try:
            m.apply_install_plan(plan, info, data)
        finally:
            sys.stdout = old

        res = m.verify_all(m.load())
        eq(res["summary"]["fail"], 0, "刚装完不应有 FAIL：%s" % res)
        eq(res["ok"], True, "刚装完应判定为 ok（warn 不算失败）")

        # 手动改一个 skill 文件 → 指纹必须变
        target = home / "skills" / "alpha" / "run.py"
        target.write_text("print('tampered')\n", encoding="utf-8")
        res2 = m.verify_all(m.load())
        codes = [f["code"] for p in res2["projects"] for f in p["findings"]]
        ok("skill_modified" in codes,
           "应检出 skill_modified，实际 codes=%s" % codes)

        # 删掉一个 skill 目录 → 必须是 FAIL（清单有、磁盘没有）
        shutil.rmtree(home / "skills" / "alpha")
        res3 = m.verify_all(m.load())
        codes3 = [f["code"] for p in res3["projects"] for f in p["findings"]]
        ok("skill_missing" in codes3, "应检出 skill_missing，实际 %s" % codes3)
        eq(res3["ok"], False, "缺文件必须让 verify 失败")
    finally:
        shutil.rmtree(home, ignore_errors=True)


def test_lock_lease_when_pid_unknown():
    """v4-6：查不出进程时不抢活锁；租约过期后才当陈旧锁。"""
    home = Path(tempfile.mkdtemp(prefix="ghpm-t-"))
    try:
        m = load_ghpm(home)
        now_t = time.time()

        # 心跳很新 + 进程查不出来 → 不能当陈旧锁
        fresh = {"pid": 999999999, "epoch": now_t, "heartbeat": now_t, "token": "t"}
        m.lock.pid_alive = lambda pid: None
        eq(m.lock.lock_is_stale(fresh), False, "心跳新鲜时不该判陈旧")

        # 心跳过期 → 可以清
        old = {"pid": 999999999, "epoch": now_t - 100000,
               "heartbeat": now_t - 100000, "token": "t"}
        eq(m.lock.lock_is_stale(old), True, "租约过期应判陈旧")

        # 进程明确活着 → 永远不陈旧（哪怕心跳很旧）
        m.lock.pid_alive = lambda pid: True
        eq(m.lock.lock_is_stale(old), False, "进程活着就不是陈旧锁")

        # 进程明确死了 → 陈旧
        m.lock.pid_alive = lambda pid: False
        eq(m.lock.lock_is_stale(fresh), True, "进程已退出就是陈旧锁")

        # 心跳线程不该碰别人的锁
        m.lock.pid_alive = lambda pid: None
        hb = m.lock.Heartbeat("someone-else", interval=0.05).start()
        try:
            m.LOCK.parent.mkdir(parents=True, exist_ok=True)
            m.LOCK.write_text(json.dumps({"token": "mine"}), encoding="utf-8")
            before = m.LOCK.stat().st_mtime
            time.sleep(0.2)
            eq(m.LOCK.stat().st_mtime, before, "不是自己的锁就不该续租")
        finally:
            hb.stop()
            m.LOCK.unlink(missing_ok=True)
    finally:
        shutil.rmtree(home, ignore_errors=True)


def test_rename_backup_mode_roundtrip():
    """v4-7：rename 备份模式 O(1) 搬走原目录，回滚能完整搬回来。"""
    home = Path(tempfile.mkdtemp(prefix="ghpm-t-"))
    try:
        m = load_ghpm(home)
        m.config.BACKUP_MODE = "rename"
        try:
            src = home / "skills" / "foo"
            src.mkdir(parents=True)
            (src / "SKILL.md").write_text("v1", encoding="utf-8")
            (src / "sub").mkdir()
            (src / "sub" / "big.bin").write_bytes(b"x" * 4096)

            tx = m.Transaction("o/r", "r", "update")
            tx.track([src])
            bd = tx.begin()

            ok(not src.exists(), "rename 模式下原目录应被搬走（事务期间不在原位）")
            mf = m.read_manifest(bd)
            eq(mf["items"][str(src)]["mode"], "rename", "manifest 应记录 rename 模式")
            eq(mf["items"][str(src)]["existed"], True, "existed 必须为 True")

            # 模拟半截写入
            src.mkdir(parents=True)
            (src / "SKILL.md").write_text("half-written", encoding="utf-8")

            res = tx.rollback()
            eq(res["failed"], [], "回滚不应失败：%s" % res["failed"])
            eq((src / "SKILL.md").read_text(encoding="utf-8"), "v1", "内容应是旧的")
            ok((src / "sub" / "big.bin").is_file(), "子目录内容也要回来")
            ok(not (bd / "foo").exists(), "rename 回滚后备份里的目录已被搬走")
            shutil.rmtree(bd, ignore_errors=True)
        finally:
            m.config.BACKUP_MODE = "link"
    finally:
        shutil.rmtree(home, ignore_errors=True)


def test_repo_info_dict_compat():
    """v4-8：RepoInfo 必须同时支持属性与 dict 访问（事件载荷/缓存/老调用都靠它）。"""
    home = Path(tempfile.mkdtemp(prefix="ghpm-t-"))
    try:
        m = load_ghpm(home)
        info = m.RepoInfo(repo="a/b", branch="dev", sha="0123456789abcdef")
        eq(info["sha"], "0123456789abcdef", "dict 式读取")
        eq(info.get("stars"), 0, "get 默认值")
        eq(info.get("nope", 7), 7, "未知键返回默认值")
        eq("branch" in info, True, "in 判断")
        info["stars"] = 5
        eq(info.stars, 5, "dict 式写入应落到属性")

        info.fill_short_sha()
        eq(info.sha_short, "0123456", "sha_short 由 sha 现算")

        d = info.to_dict()
        eq(sorted(d.keys()), sorted(list(m.models.REPO_INFO_FIELDS)), "to_dict 字段")
        back = m.RepoInfo.from_dict(d)
        eq(back.sha, info.sha, "from_dict 往返")

        # 备用源合并：不许把已知值覆盖成空
        merged = m.RepoInfo(repo="a/b", branch="dev", sha="s", stars=7277)
        merged.merge_fallback({"stars": 0, "desc": "d", "branch": "main"})
        eq(merged.stars, 7277, "不该把 ★ 抹成 0")
        eq(merged.desc, "d", "空字段应被补上")
        eq(merged.branch, "dev", "有 sha 时不该被备用源的 branch 覆盖")
    finally:
        shutil.rmtree(home, ignore_errors=True)


# ---------- runner ----------

TESTS = [
    test_parse_repo_strict,
    test_now_is_utc_iso,
    test_validate_skill_name,
    test_atomic_write_unique_tmp,
    test_backup_uses_hardlink,
    test_manifest_records_nonexistent_targets,
    test_install_targets_include_removed,
    test_removed_skills_converge,
    test_removed_skill_rollback,
    test_conflict_blocks_install,
    test_remove_path_containment,
    test_restore_backup_containment,
    test_rollback_takes_lock,
    test_zip_bomb_limits,
    test_zip_slip_still_blocked,
    test_fetch_repo_infos_is_concurrent,
    # v4.0
    test_source_tree_indexed_in_one_pass,
    test_find_skill_dirs_compat,
    test_update_reuses_repo_info,
    test_update_info_freshness_window,
    test_zip_device_names_blocked,
    test_source_is_moved_not_copied_twice,
    test_verify_detects_local_modification,
    test_lock_lease_when_pid_unknown,
    test_rename_backup_mode_roundtrip,
    test_repo_info_dict_compat,
]


def main():
    only = sys.argv[1] if len(sys.argv) > 1 else None
    passed, failed = 0, []
    for t in TESTS:
        if only and only not in t.__name__:
            continue
        try:
            t()
            print("  PASS  %s" % t.__name__)
            passed += 1
        except Failed as e:
            print("  FAIL  %s\n          %s" % (t.__name__, e))
            failed.append(t.__name__)
        except Exception as e:
            import traceback
            print("  ERROR %s\n          %s" % (t.__name__, e))
            traceback.print_exc()
            failed.append(t.__name__)
    print("\n%d passed, %d failed" % (passed, len(failed)))
    if failed:
        print("failed: %s" % ", ".join(failed))
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
