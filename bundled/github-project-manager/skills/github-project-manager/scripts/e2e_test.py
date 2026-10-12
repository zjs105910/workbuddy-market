# -*- coding: utf-8 -*-
"""端到端验证：真的走网络下载安装，验证 update 的状态收敛与冲突阻断。

用 GHPM_HOME 指向临时目录，绝不碰真实的 ~/.workbuddy。

v4 起不再依赖 `inspect` 拿到 skill 列表 —— 那个走 GitHub API / ungh，
限流时必然为空（实测匿名额度耗尽时 trees 403、ungh 429）。
真正权威的 skill 判断来自 ZIP 中央目录，所以这里改成
「安装 → 从清单读实际结果」，限流时也能跑完整条链路。
"""
import importlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

SCRIPT = Path(__file__).with_name("ghpm.py")
SCRIPTS_DIR = Path(__file__).resolve().parent
PY = sys.executable


def ghpm(home, *args, expect_ok=True):
    env = dict(os.environ)
    env["GHPM_HOME"] = str(home)
    env["GHPM_CACHE_TTL"] = "0"
    r = subprocess.run([PY, str(SCRIPT)] + list(args), capture_output=True,
                       text=True, encoding="utf-8", errors="replace", env=env, timeout=600)
    if expect_ok and r.returncode != 0:
        raise AssertionError("ghpm %s 失败 rc=%d\n%s\n%s"
                             % (" ".join(args), r.returncode, r.stdout[-800:], r.stderr[-400:]))
    return r


def events(text):
    out = []
    for line in text.splitlines():
        if line.startswith("__GHPM__ "):
            out.append(json.loads(line[len("__GHPM__ "):]))
    return out


def json_payload(text):
    """取出命令打的那份 JSON。

    `--json` 的 JSON 后面还会跟一行 __GHPM__ 事件（宿主协议要求），
    直接 json.loads(整个 stdout) 会报 Extra data，所以按行挑。
    """
    for line in reversed(text.splitlines()):
        line = line.strip()
        if not line or line.startswith("__GHPM__"):
            continue
        try:
            return json.loads(line)
        except ValueError:
            continue
    raise AssertionError("输出里找不到 JSON 载荷：\n%s" % text[-500:])


def load_pkg(home):
    """在进程内 import ghpm 包（换 GHPM_HOME 必须先清 sys.modules）。"""
    os.environ["GHPM_HOME"] = str(home)
    for name in [n for n in sys.modules if n == "ghpm" or n.startswith("ghpm.")]:
        del sys.modules[name]
    if str(SCRIPTS_DIR) not in sys.path:
        sys.path.insert(0, str(SCRIPTS_DIR))
    return importlib.import_module("ghpm")


def main():
    home = Path(tempfile.mkdtemp(prefix="ghpm-e2e-"))
    # 小仓库，下载快
    repo = "obra/superpowers"
    try:
        m = load_pkg(home)

        print("== 1) 安装（skill 以 ZIP 中央目录为准）==")
        r = ghpm(home, "inspect", repo)
        ev = events(r.stdout)[-1]
        print("   inspect 见到的 skill 数: %d（限流时为 0，属预期）"
              % len(ev["data"]["skill_names"]))

        r = ghpm(home, "add", repo)
        done = events(r.stdout)[-1]
        print("   安装结果: %s" % done["label"])
        if done["phase"] != "done":
            print("   stdout:", r.stdout[-500:])
            return 1

        skills_dir = home / "skills"
        installed = sorted(p.name for p in skills_dir.iterdir() if p.is_dir())
        reg = json.loads((home / "github-projects.json").read_text(encoding="utf-8"))
        proj = reg["projects"][0]
        names = list(proj["skill_names"])
        print("   磁盘上的 skill (%d): %s" % (len(installed), ", ".join(installed[:8])))
        print("   清单里的 skill (%d)，sha=%s" % (len(names), proj["sha_short"]))
        assert sorted(names) == installed, "清单与实际磁盘必须一致"
        assert proj.get("content_hash"), "v4 应记录源码指纹"
        assert proj.get("skill_hashes"), "v4 应记录 skill 指纹"
        if not names:
            print("   （该仓库不含 skill，跳过后续 skill 相关检查）")
            return 0

        print("\n== 2) verify：刚装完应当一致 ==")
        r = ghpm(home, "verify", "--json")
        v = json_payload(r.stdout)
        print("   %d 个项目：%d 正常 / %d 警告 / %d 失败"
              % (v["checked"], v["summary"]["ok"], v["summary"]["warn"],
                 v["summary"]["fail"]))
        assert v["ok"], "刚装完 verify 不该 FAIL：%s" % v["projects"]

        print("\n== 3) verify：改一个 skill 文件后应被发现 ==")
        victim_file = skills_dir / names[0] / "SKILL.md"
        victim_file.write_text(victim_file.read_text(encoding="utf-8") + "\n<!-- tampered -->\n",
                               encoding="utf-8")
        r = ghpm(home, "verify", "--json", expect_ok=True)
        v2 = json_payload(r.stdout)
        codes = [f["code"] for p in v2["projects"] for f in p["findings"]]
        print("   检出: %s" % sorted(set(codes)))
        assert "skill_modified" in codes, "本地被改过必须检出 skill_modified"

        print("\n== 4) list 时间戳展示 ==")
        r = ghpm(home, "list")
        print("\n".join("   " + l for l in r.stdout.splitlines()[:6]))

        print("\n== 5) doctor ==")
        r = ghpm(home, "doctor", "--no-network")
        for l in r.stdout.splitlines():
            if l.startswith("[") or l.startswith("汇总"):
                print("   " + l)

        print("\n== 6) remove + 撤销 ==")
        r = ghpm(home, "remove", repo)
        print("   " + [l for l in r.stdout.splitlines() if "已移除" in l][0])
        assert not (skills_dir / names[0]).exists(), "remove 后 skill 应消失"
        bd = events(r.stdout)[-1]["data"]["backup"]
        r = ghpm(home, "rollback", bd)
        print("   " + [l for l in r.stdout.splitlines() if "已恢复" in l][0])
        assert (skills_dir / names[0]).exists(), "回滚后 skill 应恢复"

        print("\n== 7) 模拟远端下线一个 skill，验证 update 会收敛 ==")
        reg = json.loads((home / "github-projects.json").read_text(encoding="utf-8"))
        proj = [p for p in reg["projects"] if p["repo"] == repo][0]
        # 真实场景：远端仓库删掉了一个 skill，所以**新包里没有**它，
        # 而本地清单还记着它（上次安装时装的）。这才是会产生差集的情况。
        all_names = list(proj["skill_names"])
        dropped = all_names[-1]
        remaining = all_names[:-1]
        print("   伪造：远端新包不再包含 %s（本地清单仍记着它）" % dropped)

        extracted = Path(tempfile.mkdtemp(prefix="ghpm-ext-"))
        for n in remaining:
            d = extracted / "skills" / n
            d.mkdir(parents=True, exist_ok=True)
            (d / "SKILL.md").write_text("---\nname: %s\n---\n" % n, encoding="utf-8")

        data = m.load()
        info = {"branch": "main", "sha": "newsha", "sha_short": "newsha",
                "stars": 0, "desc": "", "pushed_at": "", "msg": ""}
        plan = m.build_install_plan(repo, proj["name"], "main", info, extracted, data, False)
        print("   远端 skill 数: %d，本地清单 skill 数: %d"
              % (len(plan.new_skills), len(plan.old_skills)))
        print("   plan.removed_skills = %s" % plan.removed_skills)
        assert plan.removed_skills == [dropped], \
            "应识别出 %s 为已下线，实际 %s" % (dropped, plan.removed_skills)
        targets = m.install_targets(plan)
        assert (skills_dir / dropped) in targets, "被删的 skill 必须在事务目标里"
        m.apply_install_plan(plan, info, data)
        assert not (skills_dir / dropped).exists(), "%s 应被删除" % dropped
        print("   ✓ %s 已从磁盘移除，清单同步收敛" % dropped)
        after = json.loads((home / "github-projects.json").read_text(encoding="utf-8"))
        got = [p for p in after["projects"] if p["repo"] == repo][0]["skill_names"]
        assert dropped not in got, "清单里不该再有 %s" % dropped
        assert sorted(got) == sorted(remaining), "清单应与远端一致"
        print("   ✓ 清单已与远端一致（%d 个 skill）" % len(got))
        shutil.rmtree(extracted, ignore_errors=True)

        print("\n== 8) 收尾 verify：远端下线后本地也应一致 ==")
        r = ghpm(home, "verify", "--json")
        v3 = json_payload(r.stdout)
        codes3 = [f["code"] for p in v3["projects"] for f in p["findings"]]
        assert v3["ok"], "收敛后不应有 FAIL：%s" % codes3
        print("   ✓ %d 个项目全部一致" % v3["checked"])

        print("\n全部端到端检查通过 ✓")
        return 0
    finally:
        shutil.rmtree(home, ignore_errors=True)


if __name__ == "__main__":
    try:
        sys.exit(main())
    except AssertionError as e:
        print("\n失败: %s" % e)
        sys.exit(1)
