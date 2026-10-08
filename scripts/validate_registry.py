"""注册表收录契约校验器（stdlib，零第三方依赖）。

契约文件：registry/registry-schema.json（收录契约 v2，version 字段独立
于 plugins.json 里的 runtime 字段 schema=1 —— 那个由
src/workbuddy_market/registry.py 的 REGISTRY_SCHEMA 治理，运行时解析
刻意宽松；本脚本才是收录/合并的**门禁**）。

为什么 stdlib 手写而不是 pip install jsonschema：
  · 本项目纪律 —— CI 与本机一条路、零依赖；jsonschema 在 CI 里能装，
    但贡献者 clone 下来就应该能一键校验自己的 PR；
  · 契约里真正有牙齿的是**跨字段规则**（查重、trust↔review 一致性、
    截图域名白名单、homepage↔repo 对应），纯 JSON Schema 表达不了，
    反正要写代码。

用法：
  python scripts/validate_registry.py                    # 校验 registry/plugins.json
  python scripts/validate_registry.py path/to/file.json  # 校验任意一份
退出码：0 = 通过（可有 warning）；1 = 有 error（CI 门禁失败）。

规则分级：
  error   —— 违反契约，必须修（CI 拒绝合并）
  warning —— 允许存在但如实报出（如缺 license、缺兼容性声明；
             契约鼓励补全，不阻塞早期收录）
"""

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_REGISTRY = ROOT / "registry" / "plugins.json"
SCHEMA_FILE = ROOT / "registry" / "registry-schema.json"

CONTRACT_VERSION = 2

# 与 src/workbuddy_market/registry.py 的 _GITHUB_IMAGE_HOSTS 同一口径
# （截图威胁模型是外链追踪 / 图片源劫持，不是哈希）。改白名单必须两边同步。
GITHUB_IMAGE_HOSTS = (
    "github.com",
    "raw.githubusercontent.com",
    "user-images.githubusercontent.com",
    "avatars.githubusercontent.com",
    "media.githubusercontent.com",
    "objects.githubusercontent.com",
)

REPO_RE = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")
SHA1_RE = re.compile(r"^[0-9a-f]{40}$")
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
DATE_RE = re.compile(r"^[0-9]{4}-[0-9]{2}-[0-9]{2}$")
HTTPS_RE = re.compile(r"^https://\S+$")
WBVER_RE = re.compile(r"^[><=]*\s*[0-9]+(\.[0-9]+){0,2}$")
LICENSE_RE = re.compile(r"^[A-Za-z0-9.+-]{3,}$")

CATEGORIES = ("官方", "开发工具", "自动化", "合集", "测试", "设计",
              "科研", "效率", "商业", "安全", "写作", "未分类")
TRUSTS = ("official", "reviewed", "external")
REVIEW_STATUS = ("reviewed", "pending", "rejected")
PLATFORMS = ("windows", "macos", "linux")
PERM_KEYS = ("filesystem", "network", "shell", "credentials", "subprocess")

REQUIRED = ("repo", "displayName", "category", "description", "keywords",
            "addedAt", "trust", "review", "sourceCommit")


def _is_str(v):
    return isinstance(v, str)


def _https_host(url: str) -> str:
    """https URL 的 host（无则空串）。宽松解析足够域名校验用。"""
    if not _is_str(url) or not HTTPS_RE.match(url):
        return ""
    rest = url[len("https://"):].split("/", 1)[0].lower()
    return rest[:-1] if rest.endswith(".") else rest


def _github_image_host(url: str) -> bool:
    """与 registry.py 同口径：https + 白名单后缀精确匹配（防 evil-github.com）。"""
    host = _https_host(url)
    return any(host == h or host.endswith("." + h) for h in GITHUB_IMAGE_HOSTS)


def validate_registry(data, warnings=None):
    """校验一份已解析的 plugins.json。

    返回 (errors, warnings)，两者都是人类可读字符串列表
    （"plugins[3].trust: 不在枚举内 …"）。调用方给 warnings 传 list 可复用。
    """
    errors = []
    if warnings is None:
        warnings = []

    if not isinstance(data, dict):
        return ["顶层必须是 JSON 对象"], warnings
    if data.get("schema") != 1:
        errors.append(f"schema 必须是 1（runtime 格式版本，由 REGISTRY_SCHEMA 治理），得到 {data.get('schema')!r}")
    if not DATE_RE.match(str(data.get("updatedAt", ""))):
        errors.append("updatedAt 缺失或不是 YYYY-MM-DD")
    plugins = data.get("plugins")
    if not isinstance(plugins, list) or not plugins:
        errors.append("plugins 必须是非空数组")
        return errors, warnings

    known_top = {"schema", "updatedAt", "_comment", "plugins"}
    for k in data:
        if k not in known_top:
            errors.append(f"顶层多余字段 {k!r}（契约 additionalProperties=false）")

    seen_repos = {}
    n_no_license = n_no_compat = 0
    for i, e in enumerate(plugins):
        tag = f"plugins[{i}]"
        if not isinstance(e, dict):
            errors.append(f"{tag}: 必须是对象")
            continue
        where = f"{tag}({e.get('repo', '?')})"

        # ---- 必填 + 未知字段
        for k in REQUIRED:
            if k not in e:
                errors.append(f"{where}: 缺必填字段 {k}")
        known = {"repo", "displayName", "displayNameEn", "category", "description",
                 "descriptionEn", "keywords", "homepage", "addedAt", "license",
                 "trust", "review", "sourceCommit", "permissions", "screenshots",
                 "platforms", "minWorkBuddyVersion", "packageUrl", "packageHash",
                 "manifestHash", "packageSize", "version", "attestationUrl",
                 "stars", "pushedAt", "latestSha", "refreshedAt"}
        for k in e:
            if k not in known:
                errors.append(f"{where}: 未知字段 {k!r}（契约 additionalProperties=false；"
                              f"加字段要先升 registry-schema.json 的 version）")

        # ---- 静态身份
        repo = e.get("repo")
        if _is_str(repo):
            if not REPO_RE.match(repo):
                errors.append(f"{where}: repo 不是 owner/repo 形状")
            key = repo.lower()
            if key in seen_repos:
                errors.append(f"{where}: repo 与 plugins[{seen_repos[key]}] 大小写重复"
                              f"（查重走 casefold，与 collision_key 同纪律）")
            else:
                seen_repos[key] = i
        name = e.get("displayName")
        if not _is_str(name) or not (1 <= len(name) <= 80):
            errors.append(f"{where}: displayName 必须 1..80 字符")
        desc = e.get("description")
        if not _is_str(desc) or not (8 <= len(desc) <= 400):
            errors.append(f"{where}: description 必须 8..400 字符（运行时 _clean_text 上限 400）")
        cat = e.get("category")
        if cat not in CATEGORIES:
            errors.append(f"{where}: category {cat!r} 不在枚举 {CATEGORIES}")
        kw = e.get("keywords")
        if not isinstance(kw, list) or not (1 <= len(kw) <= 12) or not all(_is_str(k) and k for k in kw):
            errors.append(f"{where}: keywords 必须是 1..12 个非空字符串")
        elif len(set(kw)) != len(kw):
            warnings.append(f"{where}: keywords 有重复项")
        if "displayNameEn" in e and (not _is_str(e["displayNameEn"]) or not (1 <= len(e["displayNameEn"]) <= 120)):
            errors.append(f"{where}: displayNameEn 必须 1..120 字符")
        if "descriptionEn" in e and (not _is_str(e["descriptionEn"]) or len(e["descriptionEn"]) > 600):
            errors.append(f"{where}: descriptionEn 必须 ≤600 字符")
        if "license" in e and (not _is_str(e["license"]) or not LICENSE_RE.match(e["license"])):
            errors.append(f"{where}: license 形状不对（SPDX id，如 MIT / Apache-2.0）")
        elif "license" not in e:
            warnings.append(f"{where}: 缺 license（契约建议补全：官方/精选来源应可证许可）")
            n_no_license += 1
        if not DATE_RE.match(str(e.get("addedAt", ""))):
            errors.append(f"{where}: addedAt 缺失或不是 YYYY-MM-DD")

        # ---- 信任与审核（一致性）
        trust = e.get("trust")
        if trust not in TRUSTS:
            errors.append(f"{where}: trust {trust!r} 不在枚举 {TRUSTS}")
        rv = e.get("review")
        if not isinstance(rv, dict):
            errors.append(f"{where}: review 必须是对象")
        else:
            if rv.get("status") not in REVIEW_STATUS:
                errors.append(f"{where}: review.status {rv.get('status')!r} 不在枚举 {REVIEW_STATUS}")
            if not DATE_RE.match(str(rv.get("reviewedAt", ""))):
                errors.append(f"{where}: review.reviewedAt 缺失或不是 YYYY-MM-DD")
            if not _is_str(rv.get("method")) or not rv["method"]:
                errors.append(f"{where}: review.method 缺失")
            extra = set(rv) - {"status", "reviewedAt", "method"}
            if extra:
                errors.append(f"{where}: review 多余字段 {sorted(extra)}")
            if trust == "official" and rv.get("status") != "reviewed":
                errors.append(f"{where}: trust=official 但 review.status={rv.get('status')!r}"
                              f"（官方收录必须过审）")
        sc = e.get("sourceCommit", "")
        if not (_is_str(sc) and SHA1_RE.match(sc)):
            errors.append(f"{where}: sourceCommit 必须是 40 位小写十六进制"
                          f"（收录时固定的 sourceCommit 是漂移拦截的锚点）")

        # ---- 链接与截图
        hp = e.get("homepage")
        if "homepage" in e:
            if not _is_str(hp) or not HTTPS_RE.match(hp):
                errors.append(f"{where}: homepage 必须 https URL")
            elif _is_str(repo) and hp.lower().startswith("https://github.com/"):
                path = hp[len("https://github.com/"):].strip("/").lower()
                if path != repo.lower():
                    errors.append(f"{where}: homepage 指向 {path} 但 repo 是 {repo.lower()}（不一致）")
        shots = e.get("screenshots")
        if "screenshots" in e:
            if not isinstance(shots, list) or len(shots) > 12:
                errors.append(f"{where}: screenshots 最多 12 张")
            else:
                for s in shots:
                    if not _github_image_host(s):
                        errors.append(f"{where}: 截图域名不在 GitHub 系白名单"
                                      f"（与 registry.py 同口径，fail-closed）：{s!r}")
                        break

        # ---- 权限声明（协议 v0.3 口径）
        perms = e.get("permissions")
        if "permissions" in e:
            if not isinstance(perms, dict) or not perms:
                errors.append(f"{where}: permissions 必须是非空对象（协议 v0.3）")
            else:
                for pk, pv in perms.items():
                    if pk not in PERM_KEYS:
                        errors.append(f"{where}: permissions.{pk} 不是已知键 {PERM_KEYS}")
                    elif not (isinstance(pv, bool)
                              or (isinstance(pv, list) and pv and all(_is_str(x) and x for x in pv))):
                        errors.append(f"{where}: permissions.{pk} 必须是布尔或非空字符串数组")

        # ---- 兼容性（声明缺省 = 全平台默认，但如实报 warning）
        plat = e.get("platforms")
        if "platforms" in e and (not isinstance(plat, list) or not plat
                                 or any(p not in PLATFORMS for p in plat)
                                 or len(set(plat)) != len(plat)):
            errors.append(f"{where}: platforms 必须是 windows/macos/linux 的去重非空数组")
        mwb = e.get("minWorkBuddyVersion")
        if "minWorkBuddyVersion" in e and (not _is_str(mwb) or not WBVER_RE.match(mwb)):
            errors.append(f"{where}: minWorkBuddyVersion 形状不对（如 5.7 / >=5.7.3）")
        if "platforms" not in e and "minWorkBuddyVersion" not in e:
            n_no_compat += 1

        # ---- 产物（v2.16 成套采纳：有 url 就必须有 hash，反之亦然）
        pu, ph = e.get("packageUrl"), e.get("packageHash")
        if ("packageUrl" in e) != ("packageHash" in e):
            errors.append(f"{where}: packageUrl / packageHash 必须成对出现"
                          f"（不可变产物链路靠成套字段）")
        if "packageUrl" in e and (not _is_str(pu) or not HTTPS_RE.match(pu)):
            errors.append(f"{where}: packageUrl 必须 https URL")
        if "packageHash" in e and (not _is_str(ph) or not SHA256_RE.match(ph)):
            errors.append(f"{where}: packageHash 必须是 64 位小写十六进制")
        if "manifestHash" in e and (not _is_str(e["manifestHash"]) or not SHA256_RE.match(e["manifestHash"])):
            errors.append(f"{where}: manifestHash 必须是 64 位小写十六进制")
        if "packageSize" in e and (not isinstance(e["packageSize"], int) or e["packageSize"] < 0):
            errors.append(f"{where}: packageSize 必须是非负整数")
        if "attestationUrl" in e and (not _is_str(e["attestationUrl"]) or not HTTPS_RE.match(e["attestationUrl"])):
            errors.append(f"{where}: attestationUrl 必须 https URL")

        # ---- 动态字段（CI 重建）
        if "stars" in e and (not isinstance(e["stars"], int) or e["stars"] < 0):
            errors.append(f"{where}: stars 必须是非负整数")
        for dk in ("pushedAt", "refreshedAt"):
            if dk in e and not DATE_RE.match(str(e[dk])):
                errors.append(f"{where}: {dk} 必须是 YYYY-MM-DD")
        if "latestSha" in e and (not _is_str(e["latestSha"]) or not SHA1_RE.match(e["latestSha"])):
            errors.append(f"{where}: latestSha 必须是 40 位小写十六进制")

    if n_no_compat:
        warnings.append(f"{n_no_compat} 条未声明兼容性（platforms / minWorkBuddyVersion）——"
                        f"未声明时按「默认全平台」对待，建议逐步补全")
    return errors, warnings


def main(argv=None) -> int:
    path = Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_REGISTRY
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        print(f"[registry-contract v{CONTRACT_VERSION}] FAIL：读不了 {path}：{exc}")
        return 1

    # 契约文件自身也要健在且版本匹配 —— 契约与被校验物是同一套治理
    try:
        schema_doc = json.loads(SCHEMA_FILE.read_text(encoding="utf-8"))
        if schema_doc.get("version") != CONTRACT_VERSION:
            print(f"[registry-contract] FAIL：{SCHEMA_FILE.name} version="
                  f"{schema_doc.get('version')!r} 与校验器 v{CONTRACT_VERSION} 不匹配")
            return 1
    except (OSError, ValueError) as exc:
        print(f"[registry-contract v{CONTRACT_VERSION}] FAIL：读不了 {SCHEMA_FILE}：{exc}")
        return 1

    errors, warnings = validate_registry(data)
    n = len(data.get("plugins", []))
    for w in warnings:
        print(f"  warn  {w}")
    if errors:
        for e in errors:
            print(f"  ERROR {e}")
        print(f"\n[registry-contract v{CONTRACT_VERSION}] FAIL：{path.name}"
              f"（{n} 条，{len(errors)} error / {len(warnings)} warn）")
        return 1
    print(f"[registry-contract v{CONTRACT_VERSION}] PASS：{path.name}"
          f"（{n} 条，0 error / {len(warnings)} warn）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
