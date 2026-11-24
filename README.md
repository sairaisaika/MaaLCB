# MaaLimbus

[English](README_en.md) · [工程 Wiki](docs/wiki/README.md) · [实机验收记录](docs/acceptance.md)

MaaLimbus 是 Limbus Company 的 Windows 自动化开发项目。桌面端使用 MXU 和 ProjectInterface V2，Python Agent 通过 MaaFramework 识别游戏画面并执行任务。

## 这个仓库有什么、没有什么

| 有 | 没有 |
| --- | --- |
| 源码、Pipeline、语言资源、设计文档与中英文 Wiki | 游戏素材：图标、识别模板和游戏截图一张都不带 |
| OCR 模型（MaaCommonAssets，MIT；PaddleOCR，Apache-2.0） | 正式版桌面包：目前只有一个预发布版，见下面「构建」 |
| 只用合成素材的公开测试、[示例配置](docs/examples/config/README.md)、依赖锁文件 | 任何人的账号配置、运行截图和运行记录 |

游戏美术归其权利方所有，本项目无法确认可以再分发。镜牢自动化要用的 360 张位图由你在自己的机器上提供，步骤见[本地游戏素材](docs/local-assets.md)。没有素材时可以安装、跑测试、构建源码包；镜牢任务会在发出任何输入之前停下并说明缺哪一组。

## 安装

需要 Windows 10/11 x64、Git 和 Python 3.11（CI 与锁文件使用的版本）。

```powershell
git clone https://github.com/sairaisaika/MaaLCB.git
```

```powershell
cd MaaLCB
```

```powershell
py -3.11 -m venv .venv
```

```powershell
.venv\Scripts\python -m pip install -c requirements-lock.txt -e ".[dev]"
```

## 验证安装

```powershell
.venv\Scripts\python tools/check_wiki.py
```

```powershell
.venv\Scripts\python tools/run_tests.py -q
```

```powershell
.venv\Scripts\python tools/check_local_assets.py
```

- 第一条应以 `ok — 0 problem(s)` 结束。
- 第二条的退出码应为 0。需要本机文件或真实游戏画面的测试会逐条跳过，并写出缺的是哪个文件；跳过不算通过，只表示这台机器没有条件验证。
- 第三条在新 checkout 上退出码是 2，并列出缺少的七组素材。这是预期结果，说明缺素材时会明确报告。

## 配置

桌面应用里的设置由 MXU 界面写入被 Git 忽略的 `config/` 目录。文件格式见[示例配置](docs/examples/config/README.md)，示例是合成数据。任务与队伍选项的含义见[任务设置](docs/task-settings.md)，连接与权限见[原生控制说明](docs/native-control.md)。

## 构建

Python 源码包和 wheel：

```powershell
.venv\Scripts\python -m build --outdir build/python-package
```

Windows 桌面应用由 `tools/build_windows_package.py` 用你自己下载的 MXU 与 MaaFramework 归档组装，工具按 [Windows 开发包](docs/windows-package.md)里登记的哈希核对输入，不联网下载。发行包只取已提交的文件，带着游戏素材就拒绝导出。这条路径在不含私有目录、不含游戏素材的全新克隆上构建通过过一次：包里没有游戏素材，清单校验一致，打包后的 Agent 自检按组写明缺哪些素材。构建目录要放在较短的路径下，否则打包后的 Agent 会因为套接字路径过长而停下。

预构建的桌面包有一个预发布版 [v0.1.3](https://github.com/sairaisaika/MaaLCB/releases/tag/v0.1.3)：里面没有任何游戏素材，MXU 与 MaaFramework 的对应源码在包内 `sources/`，用 `SHA256SUMS` 核对下载。它从未登录的下载复验过：校验和、清单、打包 Agent 自检、缺素材报告和编队回放都通过。整局通关、领奖和从 MXU 窗口启动没有在这个包上验证，程序也没有签名，Windows 可能弹出安全提示。

## 运行镜牢

需要先备齐[本地游戏素材](docs/local-assets.md)并构建桌面应用。

1. 打开 `dist/MaaLimbus/MaaLimbus.exe`。
2. 在 MuMu 里打开 Limbus Company，再在 MXU 的连接设置里选择对应设备与游戏语言。
3. 在 MXU 添加并启用「自动镜牢」，核对保存队伍、轮换和消费预算，然后点「开始任务」。续跑同一局前先检查日志和未决记录。

遇到停机时，先看 MXU 的运行日志和任务结果里的停止原因。反馈问题时提供应用版本、停止原因和已脱敏的相关截图；不要上传游戏素材或带账号信息的文件。

## 当前验收范围

- MuMu 的英语镜牢路径有独立的困难五层、领奖和轮换实机记录，是在维护者备齐素材的本机环境里做的。具体版本和范围见[验收文档](docs/acceptance.md)。
- 公开 checkout 上验证过的是安装、Wiki 守卫、公开测试和 Python 包构建。桌面发行包也从全新克隆构建并检查过一次。按[本地游戏素材](docs/local-assets.md)导入素材之后的整条实机流程，尚未由第三方在公开 checkout 上复验。
- 商店支持按保存体系购买藏品、有限刷新和对账。自动购买技能仍在开发。最新版本的整局连续运行、日语游戏画面和 Windows 游戏输入分别验收。
- 桌面任务列表包含镜牢之外的入口。各入口的完成范围见[设计与任务选项](docs/design.md)。

## 仓库结构

| 路径 | 内容 |
| --- | --- |
| `src/maalimbus/` | 画面识别、任务决策、交易和运行状态 |
| `agent/` | MaaFramework Agent 入口及原生观察 |
| `assets/` | ProjectInterface、Pipeline、语言资源、OCR 模型和本地素材清单 |
| `desktop/mxu/` | MXU 桌面端适配 |
| `tools/`、`tests/` | 构建、诊断工具和公开回归测试 |
| `docs/` | 设计、验收和中英文工程 Wiki |

新建文件或处理存储之前，先看 Wiki 的[文件落点表](docs/wiki/README.md#file-placement)：它写明设计、开发、本地和发布四类内容各放在哪里、谁负责、保留多久。

## 开发

```powershell
.venv\Scripts\python tools/wiki_route.py "商店购买 收据"
```

第一次参与开发请先读 [CONTRIBUTING.md](CONTRIBUTING.md)：怎么跑起来、东西在哪、哪些地方现在不好改。定位功能从[工程 Wiki](docs/wiki/README.md) 的短索引开始。跑测试一律用 `tools/run_tests.py`，它返回 pytest 自己的退出码。

## 许可

项目按 [AGPL-3.0-or-later](LICENSE) 发布。依赖与数据来源的许可见 [THIRD_PARTY_NOTICES](THIRD_PARTY_NOTICES/)。游戏素材归其权利方，不在本仓库内。
