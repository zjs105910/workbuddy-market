# -*- coding: utf-8 -*-
"""cli —— ``workbuddy-market`` 命令行入口（v2.12 新增，pyproject console script）。

两层定位（v2.13 起，v2.20 扩展）：

  · ``doctor`` 与 ``verify`` 是不依赖 clone 布局的**包级子命令**：
    doctor 在任何目录体检市场；verify（v2.20）对任意 Market Package
    做完整校验 + 风险预览。在 clone 目录（或其子目录）内运行时，先把
    仓库根写进 ``WBM_MARKET_ROOT`` 再导入包 —— pipx 安装的命令行也能
    体检正确的市场；在 clone 外运行时「市场根」一项会如实标 ✗
    （这正是 doctor 的职责）。
  · 其余子命令仍是「仓库即市场」：向上找 launcher.py，找到就把参数
    原样交给 launcher.main()（与 ``python launcher.py`` 完全一致）；
    找不到就明确报错并指向 doctor，绝不假装能对任意目录工作。

``python -m workbuddy_market`` 也走这里（__main__.py）。
"""
from __future__ import annotations

import os
import sys
from pathlib import Path


def _find_repo_root(start: Path | None = None) -> Path | None:
    """从 cwd 向上找 launcher.py 所在的仓库根。"""
    cur = (start or Path.cwd()).resolve()
    for cand in (cur, *cur.parents):
        if (cand / "launcher.py").is_file() and (cand / "src" / "workbuddy_market").is_dir():
            return cand
    return None


def _verify_main(argv: list) -> int:
    """``workbuddy-market verify <pkg>`` —— 包校验 + 风险预览（v2.20）。

    退出码：0 = 校验通过；1 = 校验失败（errors 非空）；2 = 用法/路径错误。
    zip 会先解到临时目录再验（与安装链同一套 unpack 防线），用完即删。
    """
    import argparse
    import json
    import shutil
    import tempfile

    ap = argparse.ArgumentParser(
        prog="workbuddy-market verify",
        description="校验一个 Market Package（zip 或解包目录），输出风险预览与兼容性报告")
    ap.add_argument("package", help="包路径：.zip 或解包后的目录（含 manifest.json）")
    ap.add_argument("--json", action="store_true", help="以 JSON 输出（便于脚本消费）")
    args = ap.parse_args(argv)

    from .adapters.workbuddy import detect_host_version   # noqa: PLC0415
    from .artifact import unpack_zip                      # noqa: PLC0415
    from .errors import ArtifactError                     # noqa: PLC0415
    from .packaging import (                              # noqa: PLC0415
        compatibility_report, risk_summary, verify_package)

    path = Path(args.package)
    if not (path.is_dir() or (path.is_file() and path.suffix.lower() == ".zip")):
        print(f"verify: 路径不存在或既不是 zip 也不是目录：{path}", file=sys.stderr)
        return 2

    host_version = detect_host_version()
    tmpdir = None
    try:
        if path.is_file():
            tmpdir = tempfile.mkdtemp(prefix="wbm-verify-")
            pkg = Path(tmpdir) / "pkg"
            try:
                unpack_zip(path, pkg)
            except ArtifactError as exc:
                print(f"verify: zip 解包失败（按攻击面拒绝）：{exc}", file=sys.stderr)
                return 1
        else:
            pkg = path

        v = verify_package(pkg, host_version=host_version)
        manifest = v.get("manifest") or {}
        risk = risk_summary(manifest)
        compat = compatibility_report(manifest, host_version=host_version)

        if args.json:
            print(json.dumps(
                {"ok": v["ok"], "errors": v["errors"], "warnings": v["warnings"],
                 "packageHash": v.get("packageHash"), "hostVersion": host_version,
                 "risk": risk, "compatibility": compat},
                ensure_ascii=False, indent=2))
            return 0 if v["ok"] else 1

        hv = host_version or "未知（未探测到 last-launch.json / WORKBUDDY_VERSION）"
        print(f"校验对象：{path}")
        print(f"宿主版本：{hv}")
        print(f"完整性（manifest 自哈希 + 逐文件 SHA-256 + 链接防线）："
              f"{'✓ 通过' if v['ok'] else '✗ 未通过'}"
              + (f"  packageHash {str(v.get('packageHash'))[:16]}…" if v.get("packageHash") else ""))
        for err in v["errors"]:
            print(f"  ✗ {err}")
        for warn in v["warnings"]:
            print(f"  △ {warn}")
        print(f"风险预览：{'未声明权限' if not risk['declared'] else 'level=' + risk['level']}")
        for it in risk["items"]:
            mark = "✓" if it["granted"] else "✗"
            scope = f"（{it['scope']}）" if it["scope"] else ""
            print(f"  {mark} {it['label']}{scope if it['granted'] else ' —— 不需要'}")
        print("兼容性：")
        for c in compat["checks"]:
            mark = {True: "✓", False: "✗", None: "△ 未知"}[c["ok"]]
            print(f"  {mark} {c['label']} —— {c['detail']}")
        return 0 if v["ok"] else 1
    finally:
        if tmpdir:
            shutil.rmtree(tmpdir, ignore_errors=True)


def main(argv: list | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    # Windows 控制台默认代码页（GBK / cp1252）打不出中文 —— argparse 的
    # --help 会直接 UnicodeEncodeError（CI 的 package job 实测）。
    # 必须在**任何打印之前**（含 argparse 自身的 --help 输出）重配。
    for _stream in (sys.stdout, sys.stderr):
        try:
            _stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass
    root = _find_repo_root()

    # doctor 先于 launcher 分发：它是包级能力，不依赖 clone 布局。
    # 必须在首次导入 workbuddy_market.paths 之前设置环境变量 ——
    # MARKET_ROOT 在 import 时解析一次，之后改环境变量不生效。
    if argv and argv[0] == "doctor":
        if root is not None:
            os.environ["WBM_MARKET_ROOT"] = str(root)
        from .doctor import main as doctor_main       # noqa: PLC0415
        return doctor_main(argv[1:])

    # verify 同为包级能力（v2.20）：对任意 Market Package（zip 或解包
    # 目录）做完整校验并输出风险预览 / 兼容性报告 —— 可验证安装的
    # 命令行入口，与 Web 端风险预览同一套纯函数。
    if argv and argv[0] == "verify":
        return _verify_main(argv[1:])

    if root is None:
        print("workbuddy-market: 当前目录不在 workbuddy-market 的 clone 里"
              "（向上找不到 launcher.py）。", file=sys.stderr)
        print("体检诊断在任何目录都可用：workbuddy-market doctor",
              file=sys.stderr)
        print("管理操作请 cd 到仓库根目录后再运行；Windows 新手入口：一键启动.cmd",
              file=sys.stderr)
        return 2
    if str(root) not in sys.path:
        sys.path.insert(0, str(root))
    import launcher                        # noqa: PLC0415 —— 仓库根定位后才能导入
    return launcher.main(argv)


if __name__ == "__main__":
    raise SystemExit(main())
