#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""privacy-audit.py —— 开源发布前隐私 / 凭据审计（纯标准库，跨平台）。

背景
----
2026-10-07 外部隐私评审的第 7 步：别再靠人工检查邮箱 / 密钥有没有混进公开仓库。
CI（.github/workflows/ci.yml）每次 push / PR 自动跑一遍；本地发布前建议再跑：

    python scripts/privacy-audit.py             # 扫 Git 跟踪的文件（当前树）
    python scripts/privacy-audit.py --history   # 额外扫 git log -p --all（含提交元数据）

检查项
------
E-MAIL            邮箱。放行 @users.noreply.github.com 与 example.com 等占位域。
PHONE             大陆手机号（1[3-9] + 9 位）。带前后数字界：10 位 epoch 秒不够长、
                  13 位毫秒时间戳被 (?!\\d) 挡住，都不会误报。
PRIVATE-KEY       -----BEGIN ... PRIVATE KEY-----。
CREDENTIAL        ghp_ / github_pat_ / AKIA / sk- / xox... 等已知凭据前缀。
SECRET-KV         api_key|secret|token|password|authorization : <20+ 位疑似随机串>
                  （值必须同时含字母和数字，纯单词 / 路径不算）。
USER-PATH-WIN     C:\\Users\\<名>（放行 Public / Default / Shared）。
USER-PATH-POSIX   /Users/<名>、/home/<名>（放行 user / runner / ubuntu 等公共占位名）。

例外机制
--------
某行确实需要写上述内容时，行内带上 `pa:allow` 标记即整行放行；
汇总时会打印放行行数，防止例外被悄悄滥用。

退出码：0 干净；1 有发现；2 环境问题（不在 git 仓库里等）。
发现即失败 —— 与内核「扫描 fail-closed，绝不把看不见当不存在」同一哲学。
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path

ALLOW_MARKER = "pa:allow"

# ---------- 规则 ----------

_EMAIL = re.compile(
    r"[A-Za-z0-9._%+-]+@[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)*\.[A-Za-z]{2,}"
)
_EMAIL_ALLOW_SUFFIX = "@users.noreply.github.com"
_EMAIL_ALLOW_DOMAINS = {
    "example.com", "example.org", "example.net", "example.edu",
    "domain.com", "yourdomain.com", "your-domain.com", "invalid",
}

_PHONE = re.compile(r"(?<!\d)1[3-9]\d{9}(?!\d)")

_PRIVATE_KEY = re.compile(
    r"-----BEGIN [A-Z0-9 ]{0,40}PRIVATE KEY(?: BLOCK)?-----"
)

_CREDENTIAL = re.compile(
    r"\b(?:ghp_[A-Za-z0-9]{16,}"
    r"|github_pat_[A-Za-z0-9_]{20,}"
    r"|AKIA[0-9A-Z]{16}"
    r"|sk-[A-Za-z0-9_-]{16,}"
    r"|xox[baprs]-[A-Za-z0-9-]{10,})"
)

_SECRET_KV = re.compile(
    r"(?i)\b(?:api[_-]?key|secret|token|password|passwd|authorization)\b"
    r"\s*[:=]\s*[\"']?([A-Za-z0-9+/_~.=-]{20,})"
)

_WIN_PATH = re.compile(
    r"(?i)\b[C-Z]:[\\/]+Users[\\/]+"
    r"(?!public(?:[\\/]|\b)|default(?:[\\/]|\b)|shared(?:[\\/]|\b))"
    r"[A-Za-z0-9_.\-]{1,40}"
)
_POSIX_PATH = re.compile(
    r"(?<![A-Za-z0-9.])(?:/Users|/home)/"
    r"(?!public(?:/|\b)|default(?:/|\b)|shared(?:/|\b)|user(?:/|\b)"
    r"|runner(?:/|\b)|ubuntu(?:/|\b)|admin(?:/|\b)|git(?:/|\b)"
    r"|workbuddy(?:/|\b))"
    r"[A-Za-z0-9_.\-]{1,40}"
)

RULE_KINDS = (
    "E-MAIL", "PHONE", "PRIVATE-KEY", "CREDENTIAL",
    "SECRET-KV", "USER-PATH-WIN", "USER-PATH-POSIX",
)


# ---------- 基础设施 ----------

def _git(*args: str) -> str:
    proc = subprocess.run(
        ["git", *args],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    if proc.returncode != 0:
        sys.stderr.write(
            "[privacy-audit] git %s 失败：%s\n"
            % (" ".join(args), proc.stderr.decode("utf-8", "replace").strip())
        )
        raise SystemExit(2)
    return proc.stdout.decode("utf-8", "replace")


def _email_allowed(addr: str) -> bool:
    a = addr.lower()
    if a.endswith(_EMAIL_ALLOW_SUFFIX):
        return True
    return a.rsplit("@", 1)[-1] in _EMAIL_ALLOW_DOMAINS


def _kv_allowed(value: str) -> bool:
    return any(c.isdigit() for c in value) and any(c.isalpha() for c in value)


def scan_text(text: str, label: str, findings: list, skipped: list) -> None:
    for lineno, line in enumerate(text.splitlines(), 1):
        if ALLOW_MARKER in line:
            skipped.append((label, lineno))
            continue
        for m in _EMAIL.finditer(line):
            if not _email_allowed(m.group(0)):
                findings.append((label, lineno, "E-MAIL", m.group(0)))
        for m in _PHONE.finditer(line):
            findings.append((label, lineno, "PHONE", m.group(0)))
        for m in _PRIVATE_KEY.finditer(line):
            findings.append((label, lineno, "PRIVATE-KEY", m.group(0)))
        for m in _CREDENTIAL.finditer(line):
            findings.append((label, lineno, "CREDENTIAL", m.group(0)))
        for m in _SECRET_KV.finditer(line):
            if _kv_allowed(m.group(1)):
                findings.append((label, lineno, "SECRET-KV", m.group(0)))
        for m in _WIN_PATH.finditer(line):
            findings.append((label, lineno, "USER-PATH-WIN", m.group(0)))
        for m in _POSIX_PATH.finditer(line):
            findings.append((label, lineno, "USER-PATH-POSIX", m.group(0)))


# ---------- 入口 ----------

def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description="开源发布前隐私 / 凭据审计（发现即失败，退出码 1）")
    parser.add_argument(
        "--history", action="store_true",
        help="额外扫描 git log -p --all 的完整历史补丁流（含提交元数据）")
    args = parser.parse_args(argv)

    toplevel = Path(_git("rev-parse", "--show-toplevel").strip())
    files = [f for f in _git("ls-files", "-z").split("\0") if f]

    findings: list = []
    skipped: list = []
    scanned = 0
    for rel in files:
        path = toplevel / rel
        if not path.is_file():
            continue  # index 里登记了但工作区已删（还没 commit），没有内容可扫
        raw = path.read_bytes()
        if b"\x00" in raw[:8192]:
            continue  # 二进制文件不扫
        scanned += 1
        scan_text(raw.decode("utf-8", "replace"), rel, findings, skipped)

    patches = 0
    if args.history:
        patch_text = _git(
            "log", "-p", "--all", "--no-color", "--no-ext-diff", "--no-renames")
        patches = patch_text.count("\ndiff --git ")
        scan_text(patch_text, "<git-history>", findings, skipped)

    if findings:
        print("[privacy-audit] 发现 %d 处命中：" % len(findings))
        for label, lineno, kind, snippet in findings:
            print("  %s:%s: [%s] %s" % (label, lineno, kind, snippet[:100]))
        if args.history:
            print("[privacy-audit] <git-history> 条目可用 git log -S '<内容>' "
                  "定位具体提交。")
        print("[privacy-audit] 确认是误报时，在该行加 `%s` 标记放行。" % ALLOW_MARKER)
        return 1

    tail = "；另扫历史 %d 个补丁" % patches if args.history else ""
    extra = "（%d 行带放行标记）" % len(skipped) if skipped else ""
    print("[privacy-audit] 干净：%d 个跟踪文件%s%s，未命中任何规则。"
          % (scanned, tail, extra))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
