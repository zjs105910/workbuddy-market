# -*- coding: utf-8 -*-
"""v2.37 root-update fail-closed safety smoke tests for zero-dependency selftest."""
from __future__ import annotations

import os
import shutil
import stat
import tempfile
import zipfile
from pathlib import Path

from . import ck, section


def round27() -> None:
    section("42. v2.37：市场根显式升级 / ZIP 安全与版本校验")
    from workbuddy_market import rootupdate as updater
    from workbuddy_market.selfupdate import compare_versions, parse_tag

    tmp = Path(tempfile.mkdtemp(prefix="wbm-rootupdate-selftest-"))
    try:
        root = tmp / "market"
        version_file = root / "src" / "workbuddy_market" / "version.py"
        version_file.parent.mkdir(parents=True)
        version_file.write_text('MARKET_VERSION = "2.37.0"\n', encoding="utf-8")
        ck("root-update 读取唯一 MARKET_VERSION", updater.read_market_version(root) == "2.37.0")
        version_file.write_text('MARKET_VERSION = "latest"\n', encoding="utf-8")
        ck("root-update 版本未知时 fail-closed", updater.read_market_version(root) is None)

        ck("root-update tag 只接受正式三段版本",
           parse_tag("v2.37.0") == (2, 37, 0) and parse_tag("latest") is None)
        ck("root-update 使用纯版本比较",
           compare_versions("2.37.0", "2.36.0") == 1)

        unsafe = zipfile.ZipInfo("repo/../escape.txt")
        try:
            updater._check_zip_member(unsafe)
            path_safe = False
        except updater.RootUpdateError:
            path_safe = True
        ck("root-update 拒绝 ZIP 路径穿越", path_safe)

        link = zipfile.ZipInfo("repo/link")
        link.create_system = 3
        link.external_attr = (stat.S_IFLNK | 0o777) << 16
        try:
            updater._check_zip_member(link)
            symlink_safe = False
        except updater.RootUpdateError:
            symlink_safe = True
        ck("root-update 拒绝 ZIP 符号链接", symlink_safe)

        archive_path = tmp / "release.zip"
        with zipfile.ZipFile(archive_path, "w") as archive:
            archive.writestr("repo/launcher.py", "# launcher\n")
            archive.writestr("repo/src/workbuddy_market/version.py",
                             'MARKET_VERSION = "2.37.0"\n')
        try:
            updater._extract_verified_zip(archive_path, tmp / "stage")
            zip_ok = True
        except Exception:
            zip_ok = False
        ck("root-update 安全解压单一顶层目录 ZIP", zip_ok)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
