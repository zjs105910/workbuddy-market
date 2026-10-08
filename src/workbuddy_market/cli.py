# -*- coding: utf-8 -*-
"""cli —— ``workbuddy-market`` 命令行入口（v2.12 新增，pyproject console script）。

两层定位（v2.13 起）：

  · ``doctor`` 是唯一**不依赖 clone 布局**的子命令：体检报告在任何目录
    都能跑。在 clone 目录（或其子目录）内运行时，先把仓库根写进
    ``WBM_MARKET_ROOT`` 再导入包 —— pipx 安装的命令行也能体检正确的市场；
    在 clone 外运行时「市场根」一项会如实标 ✗（这正是 doctor 的职责）。
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


def main(argv: list | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    root = _find_repo_root()

    # doctor 先于 launcher 分发：它是包级能力，不依赖 clone 布局。
    # 必须在首次导入 workbuddy_market.paths 之前设置环境变量 ——
    # MARKET_ROOT 在 import 时解析一次，之后改环境变量不生效。
    if argv and argv[0] == "doctor":
        if root is not None:
            os.environ["WBM_MARKET_ROOT"] = str(root)
        from .doctor import main as doctor_main       # noqa: PLC0415
        return doctor_main(argv[1:])

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
