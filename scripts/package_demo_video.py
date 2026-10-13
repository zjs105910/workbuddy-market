#!/usr/bin/env python3
"""Polish a recorded WorkBuddy Market demo into landscape and portrait MP4s."""
from __future__ import annotations
import argparse
import hashlib
import json
import shutil
import subprocess
import tempfile
from datetime import datetime, timezone
from pathlib import Path

FONT = Path("/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc")
BOLD = Path("/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc")

def need(name: str) -> str:
    found = shutil.which(name)
    if not found:
        raise RuntimeError(f"Required executable not found: {name}")
    return found

def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()

def seconds(stamp: str) -> float:
    h, m, s = stamp.replace(",", ".").split(":")
    return int(h) * 3600 + int(m) * 60 + float(s)

def ass_time(value: float) -> str:
    total = max(0, round(value * 100))
    h, rem = divmod(total, 360000)
    m, rem = divmod(rem, 6000)
    s, cs = divmod(rem, 100)
    return f"{h}:{m:02d}:{s:02d}.{cs:02d}"

def ass_escape(value: str) -> str:
    return value.replace("\\", "\\\\").replace("{", "\\{").replace("}", "\\}").replace("\n", "\\N")

def read_srt(path: Path) -> list[dict]:
    events = []
    for block in path.read_text(encoding="utf-8-sig").strip().split("\n\n"):
        lines = [line.rstrip("\r") for line in block.splitlines() if line.strip()]
        if len(lines) < 3 or "-->" not in lines[1]:
            continue
        left, right = [item.strip() for item in lines[1].split("-->", 1)]
        events.append({"start": seconds(left), "end": seconds(right), "text": " ".join(lines[2:])})
    if not events:
        raise RuntimeError(f"No valid subtitles in {path}")
    return events

def write_ass(path: Path, events: list[dict], manifest: dict) -> None:
    lines = [
        "[Script Info]", "ScriptType: v4.00+", "WrapStyle: 2",
        "ScaledBorderAndShadow: yes", "YCbCr Matrix: TV.709",
        "PlayResX: 1280", "PlayResY: 720", "",
        "[V4+ Styles]",
        "Format: Name,Fontname,Fontsize,PrimaryColour,SecondaryColour,OutlineColour,BackColour,Bold,Italic,Underline,StrikeOut,ScaleX,ScaleY,Spacing,Angle,BorderStyle,Outline,Shadow,Alignment,MarginL,MarginR,MarginV,Encoding",
        "Style: Title,Noto Sans CJK SC,18,&H00FFDC70,&H000000FF,&H80302010,&H00000000,-1,0,0,0,100,100,0,0,1,1,0,1,54,54,92,1",
        "Style: Subtitle,Noto Sans CJK SC,27,&H00F6F9FF,&H000000FF,&H90000000,&H00000000,0,0,0,0,100,100,0,0,1,1.2,0.6,2,72,72,17,1",
        "", "[Events]",
        "Format: Layer,Start,End,Style,Name,MarginL,MarginR,MarginV,Effect,Text",
    ]
    scenes = manifest.get("scenes", [])
    for i, event in enumerate(events):
        scene = scenes[i] if i < len(scenes) else {}
        title = scene.get("title") or scene.get("key") or "WorkBuddy Market"
        start, end = ass_time(event["start"]), ass_time(event["end"])
        lines.append(f"Dialogue: 0,{start},{end},Title,,0,0,0,,{ass_escape(f'{i + 1:02d}  /  {title}')}")
        lines.append(f"Dialogue: 1,{start},{end},Subtitle,,0,0,0,,{ass_escape(event['text'])}")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")

def run(command: list[str]) -> None:
    subprocess.run(command, check=True)

def duration(ffprobe: str, path: Path) -> float:
    value = subprocess.check_output(
        [ffprobe, "-v", "error", "-show_entries", "format=duration",
         "-of", "default=noprint_wrappers=1:nokey=1", str(path)], text=True)
    return float(value.strip())

def polish_landscape(ffmpeg: str, source: Path, output: Path, ass: Path) -> None:
    filters = (
        "scale=1365:768:flags=lanczos,crop=1280:720:(in_w-out_w)/2:(in_h-out_h)/2,"
        "drawbox=x=0:y=586:w=iw:h=134:color=0x071321@0.98:t=fill,"
        "drawbox=x=0:y=586:w=iw:h=3:color=0x4fdcff@0.98:t=fill,"
        f"subtitles=filename='{ass}':fontsdir='/usr/share/fonts/opentype/noto':charenc=UTF-8"
    )
    temp_output = output.with_name(output.stem + ".rendering.mp4")
    try:
        run([ffmpeg, "-hide_banner", "-loglevel", "error", "-y", "-i", str(source),
             "-vf", filters, "-map", "0:v:0", "-map", "0:a:0",
             "-af", "loudnorm=I=-16:TP=-1.5:LRA=11",
             "-c:v", "libx264", "-preset", "ultrafast", "-crf", "19",
             "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "192k",
             "-movflags", "+faststart", str(temp_output)])
        temp_output.replace(output)
    finally:
        if temp_output.exists():
            temp_output.unlink()

def make_portrait_overlay(path: Path) -> None:
    from PIL import Image, ImageDraw, ImageFont
    image = Image.new("RGBA", (1080, 1920), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    dark, cyan = (7, 19, 33, 226), (79, 220, 255, 255)
    white, pale, muted = (246, 249, 255, 255), (214, 232, 250, 255), (183, 204, 224, 255)
    draw.rounded_rectangle((48, 64, 1032, 494), radius=34, fill=dark, outline=(76, 126, 166, 160), width=2)
    draw.rounded_rectangle((48, 64, 60, 494), radius=5, fill=cyan)
    draw.rounded_rectangle((48, 1280, 1032, 1828), radius=34, fill=dark, outline=(76, 126, 166, 160), width=2)
    draw.rounded_rectangle((48, 1280, 60, 1828), radius=5, fill=cyan)
    def text(x: int, y: int, value: str, size: int, color, bold: bool = False) -> None:
        draw.text((x, y), value, font=ImageFont.truetype(str(BOLD if bold else FONT), size), fill=color)
    text(92, 112, "WORKBUDDY  ·  LOCAL FIRST", 22, cyan, True)
    text(92, 174, "WorkBuddy Market", 59, white, True)
    text(92, 276, "把本机 Skills 变成可发现、可管理的插件市场", 28, pale)
    text(92, 354, "安全预览  ·  内容校验  ·  可恢复操作", 27, cyan)
    text(92, 420, "真实界面演示；使用临时合成 Skill，不安装远端插件", 21, muted)
    text(92, 1340, "START HERE", 22, cyan, True)
    text(92, 1400, "一起把 WorkBuddy Skills 生态做起来", 38, white, True)
    text(92, 1476, "先试用  ·  再反馈  ·  一起完善", 30, pale)
    text(92, 1555, "Star  ·  Issue  ·  PR", 36, cyan, True)
    text(92, 1640, "github.com/zjs105910/workbuddy-market", 26, white)
    text(92, 1710, "Windows 快速上手、安装说明与安全边界见项目 README", 21, muted)
    image.save(path)

def render_portrait(ffmpeg: str, ffprobe: str, source: Path, output: Path, temp: Path) -> None:
    background, overlay = temp / "portrait-background.png", temp / "portrait-overlay.png"
    run([ffmpeg, "-hide_banner", "-loglevel", "error", "-y", "-ss", "4", "-i", str(source),
         "-vf", "scale=720:1280:force_original_aspect_ratio=increase:flags=lanczos,"
                "crop=720:1280,boxblur=18:5,eq=brightness=-0.23:saturation=0.72",
         "-frames:v", "1", str(background)])
    make_portrait_overlay(overlay)
    temp_output = output.with_name(output.stem + ".rendering.mp4")
    try:
        run([ffmpeg, "-hide_banner", "-loglevel", "error", "-y",
             "-loop", "1", "-framerate", "25", "-i", str(background),
             "-i", str(source), "-i", str(overlay),
             "-filter_complex",
             "[1:v]scale=720:405:flags=lanczos[main];"
             "[0:v][main]overlay=0:413,"
             "drawbox=x=0:y=411:w=iw:h=2:color=0x4fdcff@0.98:t=fill,"
             "drawbox=x=0:y=819:w=iw:h=2:color=0x4fdcff@0.98:t=fill[base];"
             "[2:v]scale=720:1280[ovr];"
             "[base][ovr]overlay=0:0:eof_action=repeat:shortest=0:format=auto,format=yuv420p[v]",
             "-map", "[v]", "-map", "1:a:0", "-t", f"{duration(ffprobe, source):.3f}",
             "-af", "loudnorm=I=-16:TP=-1.5:LRA=11",
             "-c:v", "libx264", "-preset", "ultrafast", "-threads", "4", "-crf", "20",
             "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "192k",
             "-movflags", "+faststart", str(temp_output)])
        temp_output.replace(output)
    finally:
        if temp_output.exists():
            temp_output.unlink()

def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--subtitles", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True, help="Polished 16:9 MP4; may equal --input")
    parser.add_argument("--vertical-output", type=Path, required=True, help="9:16 MP4 for social platforms")
    args = parser.parse_args()
    ffmpeg, ffprobe = need("ffmpeg"), need("ffprobe")
    for path in (args.input, args.subtitles, args.manifest):
        if not path.is_file():
            raise FileNotFoundError(path)
    if not FONT.exists() or not BOLD.exists():
        raise RuntimeError("Noto Sans CJK not found; install fonts-noto-cjk.")
    manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
    events = read_srt(args.subtitles)
    original_hash = sha256(args.input)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.vertical_output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="workbuddy-demo-polish-") as folder:
        temp = Path(folder)
        ass = temp / "captions.ass"
        write_ass(ass, events, manifest)
        rendered = temp / "landscape-polished.mp4"
        polish_landscape(ffmpeg, args.input, rendered, ass)
        rendered.replace(args.output)
        render_portrait(ffmpeg, ffprobe, args.output, args.vertical_output, temp)
    manifest["originalVideoSha256"] = original_hash
    manifest["video"] = args.output.name
    manifest["videoSha256"] = sha256(args.output)
    manifest["verticalVideo"] = args.vertical_output.name
    manifest["verticalResolution"] = "720x1280"
    manifest["verticalVideoSha256"] = sha256(args.vertical_output)
    manifest["postProcessedAt"] = datetime.now(timezone.utc).isoformat()
    manifest["postProcessing"] = {
        "landscape": "6.6% center zoom; branded chapter titles and larger Chinese captions; audio loudness normalized to -16 LUFS / -1.5 dBTP",
        "vertical": "9:16 social layout; blurred background, real landscape app UI, project positioning, synthetic-data/privacy note, and community CTA; 720x1280",
    }
    args.manifest.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"PASS landscape: {args.output} sha256={sha256(args.output)}")
    print(f"PASS portrait: {args.vertical_output} sha256={sha256(args.vertical_output)}")
    print(f"PASS manifest: {args.manifest}")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
