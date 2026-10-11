# 可复现产品演示视频

本项目的演示视频由 `scripts/record_demo.py` 自动录制：它启动仓库中的真实 Python 服务和网页前端，在 Playwright Chromium 中执行用户流程，再由 FFmpeg 输出 16:9 MP4。视频包含普通话合成旁白、屏幕字幕、独立 SRT 字幕文件与原创合成氛围音乐。

## 视频展示内容

1. 项目开场与本机优先定位
2. 本机技能卡片与关键词搜索
3. 精选社区市场与插件来源/信任/权限/兼容性四问
4. GitHub 探索入口
5. 在临时 WorkBuddy 目录中安装合成 Skill
6. 安全卸载与回收站
7. 引导访问 GitHub、Star、提交 Issue 和参与贡献

## 为什么这是可复现的真实演示

- UI 和服务端直接来自当前 checkout，不是动画模拟的 UI，也不是预制假截图。
- 演示数据包括脚本现场生成的两个合成 Skill，以及当前提交中 `registry/plugins.json` 的精选条目快照；动态星数/更新时间和远程截图会被去掉以减少漂移。
- 脚本绝不复制开发者本机的 `market.config.json` 或 `plugins/`，安装目录指向临时 `WBM_HOME`；结束后自动清理整个临时环境。
- 合成数据标识为演示用途。社区条目详情只用于真实详情 UI 展示，视频不会下载或安装远端第三方 Skill。
- 旁白由 espeak-ng/espeak 生成；背景音乐是 FFmpeg 生成的简约合成氛围音，不下载第三方音乐资产。
- `demo-manifest.json` 记录版本、源 commit、镜头时间与 MP4/SRT 的 SHA-256。

## 本地生成

依赖：Python 3.10+、FFmpeg/ffprobe、espeak-ng（含普通话语音）、Playwright 和 Chromium。

```bash
python -m pip install playwright
python -m playwright install chromium
python scripts/record_demo.py \
  --output dist/workbuddy-market-demo.mp4 \
  --subtitles dist/workbuddy-market-demo.zh-CN.srt \
  --manifest dist/demo-manifest.json
```

在 Ubuntu/Debian 上可先安装系统依赖：

```bash
sudo apt-get install ffmpeg espeak-ng fonts-noto-cjk
```

## 在 GitHub 获取演示视频

- `Demo video` 工作流会在演示脚本、核心 UI 或相关运行时文件更新时运行，也可以在 Actions 页面手动触发。成功后将 MP4、SRT 和 manifest 保存为 30 天的 workflow artifact。
- 正式版本打上与 `src/workbuddy_market/version.py` 完全一致的 `vX.Y.Z` tag 后，`Release` 工作流会再次从 tagged source 录制视频，并将 MP4、中文字幕、manifest、wheel、sdist 和 `SHA256SUMS.txt` 一起发布。
- Release 工作流会先跑 Windows/Linux/macOS 的验证矩阵，版本标签与 `CHANGELOG.md` 不匹配、测试失败或演示录制失败时都不会发布。

完整发布步骤见 [正式 Release 发布流程](release-process.md)。

## 分享与转化

请优先分享正式 Release 中的 MP4 和项目首页。视频已经内置清晰的行动入口：先用安全模式试用；遇到问题提交可复现的 Issue；确认有用后再 Star；有能力的用户可提交文档、测试或注册表收录 PR。

不要把演示用的合成 Skill 描述成可直接投入生产的插件；它们只是验证安装流程与展示界面的 fixture。
