# -*- coding: utf-8 -*-
"""cli —— ``workbuddy-market`` 命令行入口（v2.12 新增，pyproject console script）。

定位要诚实：本市场是「仓库即市场」——内核的 MARKET_ROOT 就是 clone 的
仓库根（配置、plugins/、.trash/ 都长在那里）。所以这个入口**只在
clone 目录内（或其子目录）有意义**：它向上找 launcher.py，找到就
把参数原样交给 launcher.main()，行为与 ``python launcher.py`` 完全一致；
找不到就明确报错，绝不假装能对任意目录工作。

``python -m workbuddy_market`` 也走这里（__main__.py）。
"""
from __future__ import annotations

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
    root = _find_repo_root()
    if root is None:
        print("workbuddy-market: 当前目录不在 workbuddy-market 的 clone 里"
              "（向上找不到 launcher.py）。", file=sys.stderr)
        print("请 cd 到仓库根目录后再运行；Windows 新手入口：一键启动.cmd",
              file=sys.stderr)
        return 2
    if str(root) not in sys.path:
        sys.path.insert(0, str(root))
    import launcher                        # noqa: PLC0415 —— 仓库根定位后才能导入
    return launcher.main(argv)


if __name__ == "__main__":
    raise SystemExit(main())
