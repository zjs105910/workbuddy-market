#!/usr/bin/env python3
"""Record a reproducible WorkBuddy Market demo using the real app and isolated synthetic data.

Dependencies: Playwright + Chromium, ffmpeg/ffprobe, and espeak-ng (Mandarin voice).
This script never copies a developer's market.config.json or local plugins directory.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import wave
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
WIDTH, HEIGHT = 1280, 720
TARGET_SECONDS, MAX_SECONDS = 72, 90

SCENES = [
    {"key": "intro", "title": "WorkBuddy Market",
     "narration": "WorkBuddy Market，把本机 Skills 变成可发现、可管理的插件市场。"},
    {"key": "local", "title": "本机技能 · 集中管理",
     "narration": "本机技能卡片让常用工具集中展示，方便浏览和管理。"},
    {"key": "search", "title": "关键词搜索 · 更快发现",
     "narration": "输入关键词，快速找到想要的技能。"},
    {"key": "curated", "title": "精选市场 · 社区发现",
     "narration": "精选市场展示社区技能，也可探索更多公开仓库。"},
    {"key": "inspect", "title": "安装前 · 先看四问",
     "narration": "安装前先看来源、信任、权限与兼容性。权限声明不是沙箱，仍需自行判断。"},
    {"key": "explore", "title": "探索 GitHub · 扩展发现",
     "narration": "探索入口可搜索更多公开技能；结果取决于 GitHub 可用性。"},
    {"key": "install", "title": "真实流程 · 隔离演示安装",
     "narration": "这里安装合成演示 Skill，只写入临时环境，不触碰真实配置。"},
    {"key": "uninstall", "title": "可恢复操作 · 降低误删风险",
     "narration": "卸载前检查归属与内容变化，符合条件的技能进入回收站。"},
    {"key": "outro", "title": "一起把 WorkBuddy Skills 生态做起来",
     "narration": "喜欢这个项目，欢迎点 Star、提 Issue、贡献文档或测试。"},
]


def require_binary(*names: str) -> str:
    for name in names:
        found = shutil.which(name)
        if found:
            return found
    raise RuntimeError("Missing required executable: " + " or ".join(names))


def copy_demo_runtime(market_root: Path, state_root: Path) -> None:
    """Copy only tracked app assets; never copy private config or plugin folders."""
    market_root.mkdir(parents=True)
    for name in ("web", "registry"):
        source = ROOT / name
        if not source.is_dir():
            raise RuntimeError(f"Required tracked directory is missing: {name}")
        shutil.copytree(source, market_root / name,
                        ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
    shutil.copy2(ROOT / "market.config.example.json",
                 market_root / "market.config.example.json")

    registry = json.loads(
        (market_root / "registry" / "plugins.json").read_text(encoding="utf-8"))
    entries = []
    for source_entry in registry.get("plugins", [])[:3]:
        entry = dict(source_entry)
        for volatile in ("stars", "pushedAt", "latestSha", "refreshedAt", "screenshots"):
            entry.pop(volatile, None)
        entries.append(entry)
    if not entries:
        raise RuntimeError("The checked-in community registry has no usable entries")

    config = json.loads(
        (market_root / "market.config.example.json").read_text(encoding="utf-8"))
    config["name"] = "WorkBuddy Market · 演示环境"
    config["localPlugins"] = [{
        "name": "demo-release-helper",
        "displayName": "发布助手（演示）",
        "category": "开发工具",
        "version": "1.0.0",
        "description": "合成演示 Skill：整理变更摘要与 Release 草稿，不含真实用户内容。",
        "keywords": ["Release", "CHANGELOG", "演示"],
        "skills": ["release-helper", "change-summary"],
    }]
    config["remoteSources"] = []
    (market_root / "market.config.json").write_text(
        json.dumps(config, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    synthetic_skills = {
        "release-helper": (
            "---\nname: release-helper\n"
            "description: Synthetic demo Skill for drafting release notes.\n"
            "---\n\n# Release Helper · Demo only\n\n"
            "This synthetic Skill demonstrates local packaging and installation.\n"
            "It contains no credentials, private paths, or real user content.\n"),
        "change-summary": (
            "---\nname: change-summary\n"
            "description: Synthetic demo Skill for summarizing repository changes.\n"
            "---\n\n# Change Summary · Demo only\n\n"
            "This synthetic Skill is a recording fixture, not a production integration.\n"),
    }
    for skill_name, text in synthetic_skills.items():
        folder = market_root / "plugins" / "demo-release-helper" / "skills" / skill_name
        folder.mkdir(parents=True, exist_ok=True)
        (folder / "SKILL.md").write_text(text, encoding="utf-8")

    # A fresh cache makes the curated portion deterministic and avoids network calls.
    state_root.mkdir(parents=True, exist_ok=True)
    cache = {
        "schema": 1,
        "fetchedAt": datetime.now(timezone.utc).isoformat(),
        "fetchedAtEpoch": time.time(),
        "source": "demo-fixture",
        "updatedAt": registry.get("updatedAt", ""),
        "skipped": 0,
        "plugins": entries,
    }
    (state_root / "registry.json").write_text(
        json.dumps(cache, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (market_root / ".codebuddy-plugin").mkdir(exist_ok=True)


def synthesize(text: str, path: Path, voice_bin: str) -> float:
    subprocess.run(
        [voice_bin, "-v", "zh", "-s", "190", "-p", "45", "-w", str(path), text],
        check=True, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
    with wave.open(str(path), "rb") as audio:
        return audio.getnframes() / audio.getframerate()


def fmt_srt(seconds: float) -> str:
    ms = max(0, int(round(seconds * 1000)))
    hours, ms = divmod(ms, 3_600_000)
    minutes, ms = divmod(ms, 60_000)
    whole, millis = divmod(ms, 1000)
    return f"{hours:02d}:{minutes:02d}:{whole:02d},{millis:03d}"


def write_srt(events: list[dict], duration: float, path: Path) -> None:
    blocks = []
    for number, event in enumerate(events, start=1):
        start = max(0.0, float(event["start"]))
        end = min(duration, start + float(event["voice_seconds"]) + 0.45)
        if end > start:
            blocks.append(
                f"{number}\n{fmt_srt(start)} --> {fmt_srt(end)}\n{event['narration']}\n")
    path.write_text("\n".join(blocks) + "\n", encoding="utf-8")


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def probe_duration(ffprobe: str, video: Path) -> float:
    value = subprocess.check_output(
        [ffprobe, "-v", "error", "-show_entries", "format=duration",
         "-of", "default=noprint_wrappers=1:nokey=1", str(video)], text=True).strip()
    return float(value)


def render_mp4(ffmpeg: str, raw_video: Path, voice_files: list[Path],
               events: list[dict], output: Path, duration: float) -> None:
    filters, voice_labels = [], []
    command = [ffmpeg, "-hide_banner", "-loglevel", "error", "-y",
               "-i", str(raw_video)]
    for index, wav_path in enumerate(voice_files):
        command += ["-i", str(wav_path)]
        delay = max(0, int(round(events[index]["start"] * 1000)))
        label = f"voice{index}"
        filters.append(
            f"[{index + 1}:a]aresample=48000,adelay={delay}|{delay},"
            f"volume=1.0[{label}]")
        voice_labels.append(f"[{label}]")

    music_index = len(voice_files) + 1
    music_expr = (
        "aevalsrc=0.020*sin(2*PI*110*t)+0.013*sin(2*PI*164.81*t)+"
        "0.009*sin(2*PI*220*t)+0.004*sin(2*PI*329.63*t)"
        f":s=48000:d={duration:.3f}")
    command += ["-f", "lavfi", "-i", music_expr]
    fade_start = max(0.0, duration - 2.5)
    filters.append(
        f"[{music_index}:a]volume=0.7,afade=t=in:st=0:d=1.3,"
        f"afade=t=out:st={fade_start:.3f}:d=2.5,pan=stereo|c0=c0|c1=c0[music]")
    inputs = "".join(voice_labels) + "[music]"
    filters.append(
        f"{inputs}amix=inputs={len(voice_files) + 1}:duration=longest:"
        "dropout_transition=0:normalize=0,alimiter=limit=0.94[aout]")
    output.parent.mkdir(parents=True, exist_ok=True)
    command += [
        "-filter_complex", ";".join(filters),
        "-map", "0:v:0", "-map", "[aout]",
        "-c:v", "libx264", "-preset", "fast", "-crf", "21",
        "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "160k",
        "-movflags", "+faststart", "-t", f"{duration:.3f}", str(output),
    ]
    subprocess.run(command, check=True)


def title_card(page, final: bool = False) -> None:
    if final:
        page.set_content(
            """<!doctype html><html lang="zh-CN"><meta charset="utf-8">
            <style>
            *{box-sizing:border-box}body{margin:0;width:100vw;height:100vh;display:flex;
            align-items:center;justify-content:center;overflow:hidden;color:#eef7ff;
            font-family:"Noto Sans CJK SC","Microsoft YaHei",sans-serif;
            background:radial-gradient(circle at 75% 25%,#123f6d 0,transparent 36%),
            linear-gradient(135deg,#08101f,#101b31 55%,#071321)}
            main{width:1020px;padding:62px;border:1px solid #28496c;border-radius:28px;
            background:rgba(8,22,42,.72);box-shadow:0 20px 80px #0007}
            .k{color:#70dbff;letter-spacing:4px;font-size:18px}
            h1{font-size:43px;line-height:1.25;margin:22px 0}
            p{font-size:24px;color:#b8cce3;line-height:1.7;margin:12px 0}
            .url{margin-top:34px;font-size:23px;color:#71dcff}
            .cta{margin-top:18px;font-size:17px;color:#8faac5}
            </style><main><div class="k">OPEN SOURCE · LOCAL FIRST</div>
            <h1>一起把 WorkBuddy Skills 生态做起来</h1>
            <p>免费试用 · 看懂权限 · 安全管理</p>
            <div class="url">github.com/zjs105910/workbuddy-market</div>
            <div class="cta">觉得有用就点 Star · 遇到问题提 Issue · 欢迎贡献 PR</div>
            </main></html>""", wait_until="domcontentloaded")
    else:
        page.set_content(
            """<!doctype html><html lang="zh-CN"><meta charset="utf-8">
            <style>
            *{box-sizing:border-box}body{margin:0;width:100vw;height:100vh;display:flex;
            align-items:center;justify-content:center;overflow:hidden;color:#eef7ff;
            font-family:"Noto Sans CJK SC","Microsoft YaHei",sans-serif;
            background:radial-gradient(circle at 78% 24%,#145087 0,transparent 34%),
            linear-gradient(135deg,#070e1c,#10203a 58%,#071321)}
            main{width:980px;padding:68px;border-left:4px solid #49d3ff}
            .k{color:#71ddff;letter-spacing:5px;font-size:18px}
            h1{font-size:66px;margin:28px 0 16px;letter-spacing:-1px}
            p{font-size:27px;color:#bdd3e8;line-height:1.65;margin:8px 0}
            .chips{margin-top:35px;color:#8daecb;font-size:18px}
            </style><main><div class="k">WORKBUDDY · LOCAL FIRST</div>
            <h1>WorkBuddy Market</h1>
            <p>把本机 Skills 变成可发现、可管理的插件市场</p>
            <div class="chips">安全预览　·　可验证安装　·　事务恢复</div>
            </main></html>""", wait_until="domcontentloaded")


def caption(page, heading: str, text: str) -> None:
    page.evaluate(
        """payload => {
          let box = document.getElementById("wbm-demo-caption");
          if (!box) {
            box = document.createElement("div");
            box.id = "wbm-demo-caption";
            Object.assign(box.style, {
              position:"fixed", left:"50%", bottom:"16px",
              transform:"translateX(-50%)", width:"min(1120px, calc(100vw - 60px))",
              zIndex:"2147483647", boxSizing:"border-box", padding:"13px 22px 14px",
              borderRadius:"12px", color:"#f6fbff", background:"rgba(5,15,29,.94)",
              borderLeft:"4px solid #51d5ff", boxShadow:"0 10px 28px #0007",
              fontFamily:'"Noto Sans CJK SC","Microsoft YaHei",sans-serif',
              pointerEvents:"none"
            });
            document.body.appendChild(box);
          }
          box.replaceChildren();
          const h = document.createElement("div");
          h.textContent = payload.heading;
          Object.assign(h.style,{fontSize:"14px",letterSpacing:"1px",color:"#73dcff",
            marginBottom:"4px",fontWeight:"700"});
          const p = document.createElement("div");
          p.textContent = payload.text;
          Object.assign(p.style,{fontSize:"20px",lineHeight:"1.45",color:"#f4f8ff"});
          box.append(h,p);
        }""", {"heading": heading, "text": text})


def clear_caption(page) -> None:
    page.evaluate(
        """() => { const e = document.getElementById("wbm-demo-caption"); if (e) e.remove(); }""")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=ROOT / "dist" / "workbuddy-market-demo.mp4")
    parser.add_argument("--subtitles", type=Path, default=None)
    parser.add_argument("--manifest", type=Path, default=None)
    args = parser.parse_args()

    ffmpeg = require_binary("ffmpeg")
    ffprobe = require_binary("ffprobe")
    voice_bin = require_binary("espeak-ng", "espeak")
    try:
        from playwright.sync_api import sync_playwright
    except ImportError as exc:
        raise RuntimeError("Install Playwright: python -m pip install playwright") from exc

    output = args.output.resolve()
    subtitles = (args.subtitles or output.with_name(output.stem + ".zh-CN.srt")).resolve()
    manifest_path = (args.manifest or output.with_name("demo-manifest.json")).resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    subtitles.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.parent.mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory(prefix="workbuddy-market-demo-") as tmp_name:
        tmp = Path(tmp_name)
        market_root = tmp / "market"
        state_root = tmp / "state"
        workbuddy_home = tmp / "workbuddy-home"
        workbuddy_home.mkdir(parents=True)
        copy_demo_runtime(market_root, state_root)

        os.environ.update({
            "WBM_MARKET_ROOT": str(market_root),
            "WBM_STATE_HOME": str(state_root),
            "WBM_HOME": str(workbuddy_home),
            "WBM_CATALOG_OFF": "1",
            "WBM_TIMEOUT": "10",
            "PYTHONDONTWRITEBYTECODE": "1",
        })
        import market_server as server

        token = "demo-recording-token"
        httpd = server.make_server(0, token=token)
        thread = threading.Thread(target=httpd.serve_forever, daemon=True)
        thread.start()
        base_url = f"http://127.0.0.1:{httpd.server_address[1]}"

        raw_dir = tmp / "raw-video"
        raw_dir.mkdir()
        voice_dir = tmp / "voice"
        voice_dir.mkdir()
        voice_files, voice_seconds = [], []
        for index, scene in enumerate(SCENES):
            wav_path = voice_dir / f"{index:02d}-{scene['key']}.wav"
            voice_seconds.append(synthesize(scene["narration"], wav_path, voice_bin))
            voice_files.append(wav_path)

        events, errors, video_ref = [], [], None
        recording_started = time.monotonic()
        try:
            with sync_playwright() as playwright:
                browser = playwright.chromium.launch(headless=True)
                context = browser.new_context(
                    viewport={"width": WIDTH, "height": HEIGHT}, device_scale_factor=1,
                    record_video_dir=str(raw_dir),
                    record_video_size={"width": WIDTH, "height": HEIGHT})
                page = context.new_page()
                video_ref = page.video
                page.on("pageerror", lambda error: errors.append(str(error)))

                def narrate(index: int) -> None:
                    scene = SCENES[index]
                    events.append({
                        "key": scene["key"], "title": scene["title"],
                        "narration": scene["narration"],
                        "start": max(0.0, time.monotonic() - recording_started),
                        "voice_seconds": voice_seconds[index],
                    })
                    caption(page, scene["title"], scene["narration"])
                    page.wait_for_timeout(int((voice_seconds[index] + 0.45) * 1000))

                title_card(page)
                narrate(0)

                clear_caption(page)
                page.goto(base_url, wait_until="domcontentloaded")
                page.wait_for_selector("#content .card", timeout=30000)
                page.wait_for_timeout(400)
                if "本机插件市场" not in page.title():
                    raise RuntimeError(f"Unexpected app title: {page.title()}")
                narrate(1)

                clear_caption(page)
                page.fill("#q", "发布")
                page.wait_for_timeout(400)
                narrate(2)

                clear_caption(page)
                page.fill("#q", "")
                page.click("#tab-curated")
                page.wait_for_timeout(600)
                if page.locator("[data-regdetail]").count() < 1:
                    raise RuntimeError("Curated registry did not render a detail entry")
                narrate(3)

                clear_caption(page)
                page.locator("[data-regdetail]").first.click()
                page.wait_for_selector("#cfm.show", timeout=8000)
                detail_text = page.locator("#cfmBody").inner_text()
                required = ("来自哪里", "是否可信", "能做什么", "能否安装")
                if not all(label in detail_text for label in required):
                    raise RuntimeError("Pre-install detail modal did not show all four questions")
                narrate(4)
                clear_caption(page)
                page.keyboard.press("Escape")
                page.wait_for_timeout(250)

                page.click("#tab-explore")
                page.wait_for_timeout(350)
                narrate(5)

                clear_caption(page)
                page.click("#tab-local")
                page.wait_for_timeout(350)
                install_button = page.locator("[data-install]").first
                if install_button.count() < 1:
                    raise RuntimeError("Demo local Skill install button is missing")
                install_button.click()
                page.wait_for_function(
                    "document.querySelector('#toast') && document.querySelector('#toast').classList.contains('show')",
                    timeout=30000)
                if not page.locator("#toast").inner_text().strip():
                    raise RuntimeError("Install returned an empty result message")
                narrate(6)

                clear_caption(page)
                page.wait_for_function(
                    "(() => { const t = document.querySelector('#toast'); return !t || !t.classList.contains('show'); })()",
                    timeout=12000)
                uninstall_button = page.locator("[data-uninstall]").first
                if uninstall_button.count() < 1:
                    raise RuntimeError("Managed demo Skill did not expose safe uninstall")
                uninstall_button.click()
                page.wait_for_selector("#cfm.show", timeout=8000)
                narrate(7)
                clear_caption(page)
                page.locator("#cfmYes").click()
                page.wait_for_function(
                    "document.querySelector('#toast') && document.querySelector('#toast').classList.contains('show')",
                    timeout=30000)
                trash_candidates = [state_root / "trash", market_root / ".trash"]
                if not any(p.exists() for p in trash_candidates):
                    raise RuntimeError("Expected recoverable trash state was not created")

                clear_caption(page)
                title_card(page, final=True)
                narrate(8)
                elapsed = time.monotonic() - recording_started
                if elapsed < TARGET_SECONDS:
                    page.wait_for_timeout(int((TARGET_SECONDS - elapsed) * 1000))
                final_elapsed = time.monotonic() - recording_started
                context.close()
                browser.close()
                if final_elapsed > MAX_SECONDS:
                    raise RuntimeError(f"Demo took {final_elapsed:.1f}s; max is {MAX_SECONDS}s")
                raw_candidates = sorted(raw_dir.glob("*.webm"))
                if not raw_candidates:
                    raise RuntimeError("Playwright did not produce a browser recording")
                raw_video = raw_candidates[0]
        finally:
            httpd.shutdown()
            httpd.server_close()
            thread.join(timeout=3)

        if errors:
            raise RuntimeError("Browser JavaScript errors: " + "; ".join(errors[:3]))
        raw_duration = probe_duration(ffprobe, raw_video)
        if raw_duration < 60 or raw_duration > MAX_SECONDS + 2:
            raise RuntimeError(f"Unexpected raw recording duration: {raw_duration:.1f}s")

        render_mp4(ffmpeg, raw_video, voice_files, events, output, raw_duration)
        write_srt(events, raw_duration, subtitles)

    version_text = (ROOT / "src" / "workbuddy_market" / "version.py").read_text(encoding="utf-8")
    match = re.search(r'MARKET_VERSION\s*=\s*["\']([^"\']+)["\']', version_text)
    if not match:
        raise RuntimeError("Could not determine MARKET_VERSION")
    commit = os.environ.get("GITHUB_SHA", "")
    if not commit:
        try:
            commit = subprocess.check_output(
                ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
        except Exception:
            commit = "unknown"
    final_duration = probe_duration(ffprobe, output)
    manifest = {
        "project": "WorkBuddy Market",
        "version": match.group(1),
        "sourceCommit": commit,
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "durationSeconds": round(final_duration, 3),
        "resolution": f"{WIDTH}x{HEIGHT}",
        "video": output.name,
        "videoSha256": sha256(output),
        "subtitles": subtitles.name,
        "subtitlesSha256": sha256(subtitles),
        "narration": "Mandarin TTS generated with espeak-ng/espeak",
        "backgroundMusic": "Original low-volume procedural ambient synth bed",
        "dataSource": (
            "Checked-in community registry snapshot with volatile metrics removed; "
            "synthetic local Skills created in a temporary isolated environment"),
        "privacy": (
            "No local market.config.json, local plugins, WorkBuddy profile, credentials, "
            "or private Skill contents are copied into the recording."),
        "scenes": [
            {"key": event["key"], "title": event["title"],
             "startSeconds": round(event["start"], 3), "narration": event["narration"]}
            for event in events
        ],
    }
    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"PASS: real app UI recording -> {output}")
    print(f"PASS: Mandarin narration + subtitles -> {subtitles}")
    print(f"PASS: reproducibility/privacy manifest -> {manifest_path}")
    print(f"Duration: {final_duration:.1f}s; SHA-256: {manifest['videoSha256']}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"FAIL: {exc}", file=sys.stderr)
        raise
