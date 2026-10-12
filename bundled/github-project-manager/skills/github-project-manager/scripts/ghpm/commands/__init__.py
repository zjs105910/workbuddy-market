# -*- coding: utf-8 -*-
"""ghpm 的命令实现。

一层一个文件，CLI（cli.py）只做「参数 → 请求」，具体逻辑交给：
    install   → installer.install
    update    → commands.update.Updater
    remove    → commands.remove（事务 + containment）
    scan      → commands.scan（事务 + 并发查询）
    inspect   → 只读预检
    verify    → verifier（清单 ↔ 磁盘 ↔ 远端）
    doctor    → 环境诊断
每个命令都只负责「翻译参数 + 渲染结果」，不再各自承担业务逻辑。
"""
