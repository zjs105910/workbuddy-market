# WorkBuddy Market

[简体中文](README.md) · **English**

[![CI](https://github.com/zjs105910/workbuddy-market/actions/workflows/ci.yml/badge.svg?branch=main)](https://github.com/zjs105910/workbuddy-market/actions/workflows/ci.yml)
[![Python 3.10+](https://img.shields.io/badge/Python-3.10%2B-blue.svg)](pyproject.toml)
[![MIT License](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)

**A local-first plugin marketplace for WorkBuddy.** Package local Skills as plugins, browse a curated community registry or search public GitHub repositories, review declared permissions and compatibility, and manage installs, updates, and removals through hash verification and recoverable transactions.

## What it does

- **Package your own Skills** and register the marketplace in WorkBuddy's plugin panel.
- **Discover community Skills** through a curated registry and a GitHub search view.
- **Review before installing**: inspect source, declared permissions, compatibility, and package details.
- **Recover from mistakes**: transaction recovery and a trash area help protect managed Skills during updates and uninstalls.
- **Keep local data local**: the web UI binds to `127.0.0.1`; personal market configuration and local Skill contents are not meant to be committed to this repository.

## Quick start (Windows)

### No Git? Three steps to run (no Git needed, Python 3.10+ still required)

> 1. **Download**: open the [latest release](https://github.com/zjs105910/workbuddy-market/releases/latest) (look for the entry titled `WorkBuddy Market vX.Y.Z`; `registry-artifacts-*` are plugin-artifact pre-releases, not the app) and grab **Source code (zip)** (or the [main-branch ZIP](https://github.com/zjs105910/workbuddy-market/archive/refs/heads/main.zip));
> 2. **Extract**: unzip to any folder;
> 3. **Run**: double-click `安全模式-只开网页.cmd` to browse the marketplace first; when ready to integrate with WorkBuddy, double-click `一键启动.cmd`.

Python 3.10+ is still required (first-run setup checks it and explains what to install). No manual config file needed — it is initialized automatically on first launch.

### Already using CodeBuddy Code / WorkBuddy? One command ✅

Run this in the chat box (or CodeBuddy Code CLI):

```
/plugin marketplace add https://github.com/zjs105910/workbuddy-market.git#marketplace
```

Then browse with `/plugin`, or `/plugin install <plugin>@workbuddy-community-market`. Rebuilt daily by CI from the human-reviewed registry (pinned at sourceCommit); run `/plugin marketplace update` to refresh. Prefer a file? Use the zip import below.

### Curated skills only (zip import)

Just want the curated community skills, no tooling: download the [marketplace zip](https://github.com/zjs105910/workbuddy-market/releases/download/marketplace/workbuddy-marketplace.zip) and add it as a custom marketplace in the WorkBuddy plugin panel. Rebuilt daily by CI from the human-reviewed registry.

> Entry scope: the zip import was verified on the **WorkBuddy desktop plugin panel (5.7.6)**. CodeBuddy Code's marketplace entries (`marketplace.json` URL / Git repo / local path) belong to a different client and do not accept this zip — on CodeBuddy Code, install the full marketplace via pipx and register it instead.

> Trade-off: this path gives you skill distribution only — no pre-install review, no ownership grading, no recoverable uninstall. For the full safety chain, use the full version above.

### Prefer the command line? One command

```bash
pipx install workbuddy-market
workbuddy-market doctor     # health check; list / search to browse the registry
```

(Requires [pipx](https://pipx.pypa.io/); `uv tool install workbuddy-market` is equivalent.)

### With Git

Requirements: Python 3.10+ and Git.

To try the web UI first without registering the marketplace in WorkBuddy:

```powershell
git clone https://github.com/zjs105910/workbuddy-market.git
cd workbuddy-market
.\安全模式-只开网页.cmd
```

The local web UI uses `http://127.0.0.1:8777/` by default. Keep the terminal window open while using it; press `Ctrl+C` in that window to stop the server.

When you are ready to integrate with WorkBuddy, run `一键启动.cmd`. On first-run setup, pressing Enter selects browse-only mode; choose option `2` explicitly to request registration. Packaging and self-check prerequisites still apply.

The launch scripts have Chinese filenames. You can also start from PowerShell with `python launcher.py --no-register` to open the web UI without registering it.

## Screenshots

| Local Skills | Curated marketplace |
| --- | --- |
| ![Local Skills view](docs/screenshots/home-local.png) | ![Curated marketplace view](docs/screenshots/home-curated.png) |

Permission and compatibility details shown before installation:

![Pre-install details](docs/screenshots/detail-four-questions.png)

> Screenshots are captured with synthetic data. Available actions and results depend on your local environment and the source plugin.

## Demo video and download entries

Since v2.28.0, each formal Release ships the demo and install assets together. Three download entries, pick by need:

- **Demo video**: from the [v2.28.0 release](https://github.com/zjs105910/workbuddy-market/releases/tag/v2.28.0) (or the newest `WorkBuddy Market vX.Y.Z` entry) download `workbuddy-market-demo.mp4` (about 80 seconds) and `workbuddy-market-demo.zh-CN.srt` (Chinese subtitles); published with the release, no 30-day expiry;
- **Full marketplace app**: the `WorkBuddy Market vX.Y.Z` release entry for the version you want (wheel / sdist / source zip), or simply `pipx install workbuddy-market`;
- **Curated marketplace zip** (skills only): see the zero-install section above, rebuilt daily under the fixed `marketplace` release.

> Note: `registry-artifacts-*` releases are daily community plugin artifacts (marked as Pre-release), **not** the marketplace app itself. For the app, look for the entry titled `WorkBuddy Market vX.Y.Z`.

- [Reproducible demo: recording steps, subtitles, and privacy boundaries](docs/demo-video.md)
- [Formal Release process](docs/release-process.md)

## Safety notes

- The marketplace checks ownership and content changes before removing a managed Skill; Skills installed elsewhere are not supposed to be removed by this marketplace.
- **Declared permissions and a risk preview are not a runtime sandbox.** Third-party Skills can still execute their own logic. Review their source and origin before installation.
- `安全模式-只开网页.cmd` is for browsing without registering the marketplace. `撤销注册.cmd` removes the marketplace registration from WorkBuddy; this is different from uninstalling Skills.

## Platform status

| Platform | Status |
| --- | --- |
| Windows 10/11 | Primary development and use environment; the repository documents a WorkBuddy 5.7.6 panel test |
| Linux | CI and partial automated checks; real WorkBuddy host integration is not verified |
| macOS | Not verified |

## Documentation and community

- [Detailed usage, configuration, CLI, architecture and self-check commands](ADVANCED_GUIDE.md)
- [FAQ](docs/FAQ.md)
- [Plugin package specification](docs/plugin-spec.md)
- [Security policy](SECURITY.md)
- [Contributing guide](CONTRIBUTING.md)
- [Changelog](CHANGELOG.md)
- [Report a bug or suggest an improvement](https://github.com/zjs105910/workbuddy-market/issues)

Feedback, reproducible bug reports, documentation improvements, and pull requests are welcome. Licensed under MIT.
