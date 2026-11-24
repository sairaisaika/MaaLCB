<!-- markdownlint-disable MD033 MD041 -->
<p align="center">
  <img alt="LOGO" src="./assets/misc/Don-Quixote.png" width="256" height="256" />
</p>

<div align="center">

# MaaLimbus

<!-- markdownlint-disable-next-line MD036 -->
_✨ MAA 边狱公司小助手 ✨_

[![Pipeline](https://img.shields.io/badge/Pipeline-%23876f69?logo=paddypower&logoColor=%23FFFFFF)](https://github.com/MaaXYZ/MaaFramework)
[![Python](https://img.shields.io/badge/Python-3.11-3776AB?logo=python&logoColor=white)](https://github.com/sairaisaika/MaaLCB/tree/main/agent)
[![license](https://img.shields.io/github/license/sairaisaika/MaaLCB)](https://github.com/sairaisaika/MaaLCB/blob/main/LICENSE)
[![platform](https://img.shields.io/badge/platform-Windows-blueviolet)](https://github.com/sairaisaika/MaaLCB/releases)
[![tests](https://img.shields.io/github/actions/workflow/status/sairaisaika/MaaLCB/tests.yml?label=tests)](https://github.com/sairaisaika/MaaLCB/actions/workflows/tests.yml)
[![release](https://img.shields.io/github/v/release/sairaisaika/MaaLCB?include_prereleases&label=release)](https://github.com/sairaisaika/MaaLCB/releases)
[![stars](https://img.shields.io/github/stars/sairaisaika/MaaLCB?style=flat)](https://github.com/sairaisaika/MaaLCB/stargazers)
[![commit activity](https://img.shields.io/github/commit-activity/m/sairaisaika/MaaLCB)](https://github.com/sairaisaika/MaaLCB/commits/main)

Powered by [MaaFramework](https://github.com/MaaXYZ/MaaFramework) & [MXU](https://github.com/MistEO/MXU)

开发中，目前只有预发布版。

[简体中文](README.md) | [English](README_en.md) | [工程 Wiki](docs/wiki/README.md) | [实机验收记录](docs/acceptance.md)

</div>

## 📖 使用须知

MaaLimbus 是基于图像识别的 Limbus Company（边狱公司）自动化工具，目前只面向 **Windows + MuMu 模拟器 + 英文游戏界面**的镜像迷宫（镜牢）。

- **还在开发，不是稳定版。** 一局镜牢目前还不能保证一次开始、不停机打完；程序在拿不准时会停下并说明原因，而不是继续乱点。当前进度见下面的「当前状态」。
- **仓库和发行包里不带任何游戏素材。** 游戏美术归其权利方所有。镜牢要用的识别图由你在自己的机器上提供，步骤见[本地游戏素材](docs/local-assets.md)；没有素材时任务会在发出任何输入之前停下，并说明缺哪一组。
- 遇到问题欢迎提 [Issue](https://github.com/sairaisaika/MaaLCB/issues)。反馈时附上应用版本、日志里的停止原因和已脱敏的截图；不要上传游戏素材或带账号信息的文件。

## ✨ 功能一览

- 🪞 **自动镜牢**：从大厅进本，依次处理星光增益、初始藏品、主题包、地图走点、战斗、事件、商店、楼层藏品，直到五层通关。
- ⚔️ **战斗**：使用游戏自带的胜率／伤害自动配卡并开战，自动开启倍速。
- 🛒 **商店**：按队伍体系购买藏品，支持有限次数刷新和金币保留；每笔购买先记意图再点击，买完核对金币和货架。
- 🎁 **通关后领取奖励**：一个开关，领或不领。领取会核对奖励页的报价，绝不点「放弃奖励」，也不改每周加成的开关。
- 🔁 **连续多局与队伍轮换**：一次开始可以打多局；可单队，也可按队列轮换。
- 🗓️ **镜牢日程**（实机待验收）：选「哪几天打、每天几局」，当天打够后再点开始会直接结束。配合 MXU 自带的定时执行即可挂机托管。
- 👥 **镜牢队伍设置**：每支队伍两项。藏品体系直接勾选，可以勾一个、几个或全部，一个都不勾就让程序自由选；出战顺序推荐跟随游戏里排好的（程序把读到的顺序连同截图记下来，方便核对），也可以写出完整顺序。
- 🧾 **停了能接着跑**：商店、出战、领奖都是「先记账再操作」，中途停机或关掉游戏后，下次开始会从未完成的那一步接上。
- 📝 **看得懂的日志**：每一步写出认出了什么画面、做了什么；停机时写明原因。
- 📊 **运行数据**：每个任务结束记一行（各层用时、等待与重读次数、停机原因），`tools/run_report.py --history` 汇总趋势，不含账号和本机路径。
- 🧹 **自己整理截图**：任务结束时把旧的诊断截图移到归档目录，不靠人工清理，也不删除。
- 🚧 **开发中**：经验本、纺锤本目前只能走到入口页面（界面上标着「开发中」）；日语界面和 Windows 客户端输入尚未验收（界面上标着「实验性」「未验收」）。体力兑换、商店技能替换、应用内自动更新还没有真实功能，它们的入口已从界面拿掉，做好再放回来。

## 🚦 当前状态

如实说明，方便你判断要不要现在就用：

- 实机上已经走通过「五层通关 → 领奖 → 记账 → 自动开下一局」的完整链路，但中途停过多次，是修完再续跑打通的。
- 速度还不理想：最近一次不停机的第 1 层用了约 24 分钟，目标是每层 10 分钟以内。
- 公开测试约 5,000 条，在不带游戏素材的干净环境里通过；需要本机素材或真实游戏画面的测试会带着原因跳过。
- 详细的验收范围和版本见[验收文档](docs/acceptance.md)，目标与进度见 [Wiki 第 9 章](docs/wiki/zh_cn/9-execution-plan.md#public-goal)。

## 🍽️ 食用指南

1. 下载[预发布版](https://github.com/sairaisaika/MaaLCB/releases)的桌面包，或按下面「开发者指南」自己构建。预发布包没有签名，Windows 可能弹出安全提示；用包里的 `SHA256SUMS` 核对下载。
2. 按[本地游戏素材](docs/local-assets.md)在自己的机器上准备识别图。
3. 打开 `MaaLimbus.exe`，在 MuMu 里打开 Limbus Company，在连接设置里选择对应设备和游戏语言。
4. 添加并勾选「自动镜牢」，核对队伍、轮换和「通关后领取奖励」，点「开始任务」。

设置项的含义见[任务设置](docs/task-settings.md)，连接与权限见[原生控制说明](docs/native-control.md)。

## 📦 这个仓库有什么、没有什么

| 有 | 没有 |
| --- | --- |
| 源码、Pipeline、语言资源、设计文档与中英文 Wiki | 游戏素材：图标、识别模板和游戏截图一张都不带 |
| OCR 模型（MaaCommonAssets，MIT；PaddleOCR，Apache-2.0） | 正式版桌面包：目前只有预发布版 |
| 只用合成素材的公开测试、[示例配置](docs/examples/config/README.md)、依赖锁文件 | 任何人的账号配置、运行截图和运行记录 |

## 🛠️ 开发者指南

第一次参与请先读 [CONTRIBUTING.md](CONTRIBUTING.md)：怎么跑起来、东西在哪、哪些地方现在不好改。按问题找代码用 `tools/wiki_route.py`，更细的内容在[工程 Wiki](docs/wiki/README.md)。

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

验证安装：

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
- 第二条的退出码应为 0，全量约 10 分钟。需要本机文件或真实游戏画面的测试会逐条跳过，并写出缺的是哪个文件；跳过不算通过，只表示这台机器没有条件验证。
- 第三条在新 checkout 上退出码是 2，并列出缺少的素材组。这是预期结果，说明缺素材时会明确报告。

按问题找代码：

```powershell
.venv\Scripts\python tools/wiki_route.py "商店购买 收据"
```

构建 Python 源码包和 wheel：

```powershell
.venv\Scripts\python -m build --outdir build/python-package
```

Windows 桌面应用由 `tools/build_windows_package.py` 用你自己下载的 MXU 与 MaaFramework 归档组装，工具按 [Windows 开发包](docs/windows-package.md)里登记的哈希核对输入，不联网下载；发行包只取已提交的文件，带着游戏素材就拒绝导出。

| 路径 | 内容 |
| --- | --- |
| `src/maalimbus/` | 画面识别、任务决策、交易和运行状态 |
| `agent/` | MaaFramework Agent 入口及原生观察 |
| `assets/` | ProjectInterface、Pipeline、语言资源、OCR 模型和本地素材清单 |
| `desktop/mxu/` | MXU 桌面端适配 |
| `tools/`、`tests/` | 构建、诊断工具和公开回归测试 |
| `docs/` | 设计、验收和中英文工程 Wiki |

新建文件或处理存储之前，先看 Wiki 的[文件落点表](docs/wiki/README.md#file-placement)。

## 🙏 致谢

- [MaaFramework](https://github.com/MaaXYZ/MaaFramework)：识别与控制的核心框架。
- [MXU](https://github.com/MistEO/MXU)：桌面界面。
- [MaaCommonAssets](https://github.com/MaaXYZ/MaaCommonAssets) 与 [PaddleOCR](https://github.com/PaddlePaddle/PaddleOCR)：OCR 模型。
- [MaaEnd](https://github.com/MaaEnd/MaaEnd)、[M9A](https://github.com/MAA1999/M9A) 等 MAA 生态项目：托管方式与文档结构的参考。

## 📄 许可

项目按 [AGPL-3.0-or-later](LICENSE) 发布。依赖与数据来源的许可见 [THIRD_PARTY_NOTICES](THIRD_PARTY_NOTICES/)。游戏素材归其权利方，不在本仓库内。本项目与游戏的开发商、发行商没有关联。
