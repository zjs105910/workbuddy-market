# -*- coding: utf-8 -*-
"""privacy-audit 路径规则：runner 占位名放行、真实用户名不放行（2026-10-12 评审）。

背景：2026-10-12 定时 --history 审计 38 处命中中 4 处是 GitHub runner 的
8.3 短路径占位名（C:\\Users\\RUNNER~1 等）——WIN 正则的放行名单漏了
runner，POSIX 正则无 (?i) 挡不住大写 RUNNER~1。修复后用例钉死两个方向：
占位名放行不得扩大到真实用户名；E-MAIL 规则不得被本次改动放松。
"""
import importlib.util
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
_SCRIPT = _REPO_ROOT / "scripts" / "privacy-audit.py"

_spec = importlib.util.spec_from_file_location("privacy_audit", _SCRIPT)
pa = importlib.util.module_from_spec(_spec)
sys.modules.setdefault("privacy_audit", pa)
_spec.loader.exec_module(pa)


def _kinds(line):
    findings = []
    pa.scan_text(line, "t", findings, [])
    return sorted(k for _, _, k, _ in findings)


class TestRunnerPlaceholderAllowed:
    """GitHub runner 占位名不报红（此前 4 处误报的回归钉子）。"""

    def test_win_83_short_name(self):
        assert _kinds(r"注释 C:\Users\RUNNER~1\... 说明") == []
        assert _kinds("msg C:/Users/RUNNER~1/x end") == []

    def test_win_plain_and_admin(self):
        assert _kinds(r"C:\Users\RUNNER 和 C:\Users\runneradmin\AppData") == []

    def test_posix_83_and_plain(self):
        assert _kinds("/Users/RUNNER~1/x") == []
        assert _kinds("/Users/RUNNER") == []
        assert _kinds("/home/runner/x") == []
        assert _kinds("/Users/runner/x") == []

    def test_mixed_case_runner(self):
        assert _kinds(r"C:\Users\Runner~1\x") == []


class TestRealUserStillFlagged:
    """放行不得扩大化：真实用户名形态仍必须报红。"""

    def test_win_real_name(self):
        # 审计夹具：断言该形态必须报红，非真实泄露（行尾标记供审计放行）
        assert _kinds(r"C:\Users\zhangsan\x") == ["USER-PATH-WIN"]  # pa:allow

    def test_posix_real_name(self):
        # 审计夹具：同上
        assert _kinds("/Users/zhangsan") == ["USER-PATH-POSIX"]  # pa:allow

    def test_runner_like_name_not_allowed(self):
        # runnerfan 不是 runner 占位名的已知形态，不得搭车放行（审计夹具）
        assert _kinds(r"C:\Users\runnerfan\x") == ["USER-PATH-WIN"]  # pa:allow

    def test_public_still_allowed(self):
        assert _kinds(r"C:\Users\Public\x") == []
        assert _kinds("/Users/workbuddy/x") == []


class TestEmailUnchanged:
    """本次改动不得影响 E-MAIL 规则的松紧。"""

    def test_personal_email_flagged(self):
        # 审计夹具：占位样例邮箱（非 allowlist 域，必须报红）
        assert _kinds("contact someone@fake-mail.test") == ["E-MAIL"]  # pa:allow

    def test_noreply_allowed(self):
        assert _kinds("a 328969776+zjs105910@users.noreply.github.com b") == []

    def test_github_machine_addrs_allowed(self):
        # 平台机器地址非个人邮箱（审计夹具：SSH/系统通知形态）
        assert _kinds("parse git@github.com:alice/utils.git") == []  # pa:allow
        assert _kinds("from noreply@github.com") == []  # pa:allow

    def test_similar_personal_addr_still_flagged(self):
        # git@github.com 放行不得搭车放行真实个人地址（审计夹具）
        assert _kinds("git@my-github.com") == ["E-MAIL"]  # pa:allow
        assert _kinds("someone@gitee.com") == ["E-MAIL"]  # pa:allow


class TestPhoneInsideHexDigest:
    """PHONE 命中完整嵌在 ≥32 位十六进制摘要串内不算手机号（2026-10-13 实锤）。

    PR #8 CI：registry/plugins.json 的 manifestHash（SHA-256）中段的连续
    11 位数字被 PHONE 命中——数字界只看数字，摘要两侧的 a-f 字母拦不住。
    修复：命中落在 ≥32 位 hex 长串内按摘要处理。
    """

    def test_sha256_manifest_hash_not_flagged(self):
        # PR #8 CI 实锤的那一行（公开仓库里的注册表哈希，非隐私数据）
        line = ('      "manifestHash": '
                '"6c14201605144a53ec773f0513f2563504ea42ea0f696cacc7f29e3d3456ddb9",')
        assert _kinds(line) == []

    def test_md5_digest_with_phone_run_not_flagged(self):
        # 32+ 位 hex 长串中段夹着 11 位连续数字，同样按摘要放行
        assert _kinds("deadbeefdeadbeef13812345678cafebabecafebabe") == []

    def test_short_hex_prefix_still_flagged(self):
        # 豁免只针对 ≥32 位长串：短 hex 前缀（cafe，4 位）夹不住真手机号
        assert _kinds("cafe13812345678") == ["PHONE"]  # pa:allow

    def test_plain_phone_still_flagged(self):
        # 常规上下文里的手机号照常报红（审计夹具：占位号段）
        assert _kinds("联系电话 13812345678") == ["PHONE"]  # pa:allow

    def test_timestamp_boundary_unchanged(self):
        # 原有数字界行为不得被本次改动放松：10/13 位时间戳仍放行
        assert _kinds("epoch 1791857799 end") == []
        assert _kinds("ms 1791857799123 end") == []
