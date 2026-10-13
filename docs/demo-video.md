# 可复现产品演示视频

项目通过两步生成可复现演示：`scripts/record_demo.py` 启动仓库中的真实 Python 服务和网页前端，在 Playwright Chromium 中执行用户流程；`scripts/package_demo_video.py` 再统一字幕样式、画面取景和音频响度，并输出横屏 16:9 与竖屏 9:16 两个 MP4。正式版同时提供独立 SRT 中文字幕与 SHA-256 manifest。

## 视频展示内容

1. 项目定位与本机优先理念
2. 本机技能卡片和关键词搜索
3. 精选社区市场与来源、信任、权限、兼容性四问
4. GitHub 探索入口
5. 在临时 WorkBuddy 目录中安装合成 Skill
6. 安全卸载与回收站
7. 引导访问 GitHub、Star、提交 Issue 和参与贡献

## 为什么这是可复现的真实演示

- UI 和服务端直接来自当前 checkout，不是动画模拟的 UI，也不是预制假截图。
- 演示数据包括脚本现场生成的两个合成 Skill，以及当前提交中 `registry/plugins.json` 的精选条目快照；动态星数、更新时间和远程截图会被去掉以减少漂移。
- 脚本绝不复制开发者本机的 `market.config.json` 或 `plugins/`，安装目录指向临时 `WBM_HOME`；结束后自动清理整个临时环境。
- 合成数据会被标明为演示用途。社区条目详情只用于真实详情 UI 展示，视频不会下载或安装远端第三方 Skill。
- 普通话旁白由 espeak-ng/espeak 生成；背景音乐由 FFmpeg 生成，不下载第三方音乐资产。
- 后期处理只调整取景、章节/字幕样式和响度；竖屏版本把同一段真实界面演示放在可读区域，上下区域用于项目定位、合成数据/隐私说明与社区入口。
- `demo-manifest.json` 记录版本、源 commit、镜头时间，以及横屏/竖屏 MP4 与 SRT 的 SHA-256。

## 本地生成

依赖：Python 3.10+、FFmpeg/ffprobe、espeak-ng（含普通话语音）、Playwright、Chromium、Pillow 和 Noto CJK 字体。

```bash
python -m pip install playwright pillow
python -m playwright install chromium
# Ubuntu/Debian
sudo apt-get install ffmpeg espeak-ng fonts-noto-cjk

python scripts/record_demo.py \
  --output dist/workbuddy-market-demo.mp4 \
  --subtitles dist/workbuddy-market-demo.zh-CN.srt \
  --manifest dist/demo-manifest.json
python scripts/package_demo_video.py \
  --input dist/workbuddy-market-demo.mp4 \
  --subtitles dist/workbuddy-market-demo.zh-CN.srt \
  --manifest dist/demo-manifest.json \
  --output dist/workbuddy-market-demo.mp4 \
  --vertical-output dist/workbuddy-market-demo-vertical.mp4
```

## 在 GitHub 获取演示视频

- `Demo video` 工作流成功后会将横屏 MP4、竖屏 MP4、SRT 与 manifest 保存为 30 天的 Actions artifact。
- 正式版本打上与 `src/workbuddy_market/version.py` 完全一致的 `vX.Y.Z` tag 后，`Release` 工作流会从 tagged source 录制并后期处理两个版本，将横屏/竖屏 MP4、中文字幕、manifest、wheel、sdist、安装器与 `SHA256SUMS.txt` 一起发布。
- Release 工作流会先跑 Windows/Linux/macOS 验证矩阵；版本标签与 `CHANGELOG.md` 不匹配、测试失败或演示录制/后期处理失败时都不会发布。

完整发布步骤见 [正式 Release 发布流程](release-process.md)。

## 分享与转化

请根据平台选择横屏或竖屏正式 Release 附件，再配上项目首页。视频保留明确的行动入口：先用安全模式试用；遇到问题提交可复现的 Issue；确认有用后再 Star；有能力的用户可提交文档、测试或注册表收录 PR。

不要把演示用的合成 Skill 描述成可直接投入生产的插件；它们只是验证安装流程与展示界面的 fixture。
