# 参与开发 / Contributing

中文在前，English below.

这份文档写给第一次打开仓库的人。它只讲三件事：怎么跑起来、东西在哪、哪些地方现在不好改。
更细的内容在[工程 Wiki](docs/wiki/README.md)，按问题查位置用 `python tools/wiki_route.py "你的问题"`。

## 一、十分钟跑起来

环境与安装命令以 [README](README.md) 为准（Windows 10/11 x64、Python 3.11、虚拟环境、`pip install -c requirements-lock.txt -e ".[dev]"`）。装好之后：

```powershell
.venv\Scripts\python tools/run_tests.py -q tests/test_global_settings.py
```

```powershell
.venv\Scripts\python tools/run_tests.py -q
```

第一条几秒钟跑完，用来确认环境没问题。第二条是全量，约 9 分钟。没有本机游戏素材和运行证据时，会有七百多个测试带着原因跳过，这是预期的：仓库不带任何游戏素材（见 [本地素材](docs/local-assets.md)）。
跑测试一律用 `tools/run_tests.py`，它返回 pytest 自己的退出码；不要把 pytest 接到管道后面再判断成败。

两点容易踩的坑：

- 本机正在用安装版跑任务时，一批测试会以 `another_controller_owns_game` 失败（它们和真实任务抢同一把控制器锁）。等任务停了再跑全量。
- 提交前跑 `python tools/check_public_tree.py`。它拒绝本机路径、账号与设备标识、游戏素材和二进制。测试里需要「一个本机路径」当样例时写成 `Z:/someone/...`，不要写成真实用户目录的形状。

## 二、东西在哪

程序分两个进程：界面是未修改的 MXU（读 `assets/interface.json`），它启动 Python 写的 Agent（`agent/`），Agent 通过 MaaFramework 截图和点击。一次任务是一个「看 → 想 → 做」的循环：

| 环节 | 位置 | 说明 |
| --- | --- | --- |
| 看：截图与文字识别 | `agent/recognition.py`（`observe`、`analyze`） | 把一帧变成一条记录：文字、框、页面 |
| 看：这是哪个页面 | `src/maalimbus/vision.py`（`classify`）、`src/maalimbus/pages.py` | `pages.py` 是页面登记表：每个页面归谁、能做什么、允许的后继 |
| 想：这一步该点什么 | `src/maalimbus/window.py`（`plan_step`、`STEP_ROWS`） | 纯函数，不碰设备；简单页面只是 `STEP_ROWS` 里的一行 |
| 做：循环与事务 | `src/maalimbus/runner.py`（`MirrorRunner.step`） | 发出点击、核对后继、记账；商店、出战、领奖各有一个「先记意图再点」的事务模块 |
| 设置怎么到程序里 | `assets/interface.json` 的选项 → `assets/resource/base/pipeline/mirror.json` 里同名节点的 `attach` → Agent 用 `context.get_node_data` 读 | 新增一个设置要同时改这两个文件和三种语言的 `assets/i18n/*.json` |

常见问题的入口：

| 想改什么 | 从哪里看起 |
| --- | --- |
| 商店买什么 | `runner.py` 里 `step` 的商店段 → `gift_plan.shop_wanted`、`shop_priority.load`、`runner.shop_state`、`shop_learning.rank_offers` |
| 出战顺序 | `deployment_transaction.prepare`、`team_vision`、`global_settings.parse_order` |
| 通关领奖 | `reward_task.execute`、`paid_reward_action.prepare`、`reward_receipt_audit.verify` |
| 队伍设置、镜牢日程、自动领奖 | `global_settings.py`、`mirror_schedule.py`、`reward_task_budget.py` |
| 运行数据与界面日志 | `run_history.py`、`run_report.py`、`page_names.py` |
| 截图占用与回收 | `capture_retention.py`（`settle`） |

**游戏新增一个页面时要改的地方：** `vision.py`（`classify` 认出它）、`pages.py`（登记）、`page_names.py`（给它一个玩家看得懂的名字）、`window.py`（`STEP_ROWS` 加一行，或在 `_plan_step` 里写规则）、`assets/resource/<语言>/locale.json`（它的文字）、以及对应测试。`tests/test_pages.py` 会指出漏登记的表。

## 三、现在不好改的地方（如实说明）

2026-11-23 请独立评审从「没见过这个仓库的工程师」角度看过一遍，结论是：外围模块可以由人放心修改，核心循环目前实际上只有带着完整上下文的 AI 改得动。具体是：

- `MirrorRunner.step` 一个函数 3,339 行；`window._plan_step` 812 行，`vision.classify` 469 行，`recognition.analyze` 433 行。
- 1,694 个函数里只有 46 个带类型标注；循环的状态是一个没有类型的字典。
- 没有配置 linter、formatter 和类型检查；约三分之一的模块是紧凑的一行多语句写法。
- 有几十个测试直接断言源码文本，所以现在整体跑格式化会打断它们。
- 很多注释在讲某次运行的经过（带运行编号），而不是讲不变式；Wiki 很大，按行号的引用会悄悄过期。

改进顺序和进度记在 [Wiki 第 9 章「公开版目标」](docs/wiki/zh_cn/9-execution-plan.md#public-goal)。在那之前，**新代码请按近期的小模块来写**：`mirror_schedule.py`、`run_history.py`、`global_settings.py` ——开头的说明写清这个模块保证什么，PEP 8，报错时指出错的是哪个输入，测试测行为而不是源码文本。

## 四、提交

- 一个提交做一件事；说明里写清楚改了什么、为什么，以及**哪些没有验证**。
- 测试通过后才提交。改了行为就改 Wiki 对应的章节（中英两份）和 `docs/wiki/routes.json`；新模块必须有路由（`tests/test_wiki_route_coverage.py` 会检查）。
- 不要提交游戏素材、截图、账号或设备信息。

---

# Contributing (English)

This page is for someone opening the repository for the first time. It covers how to get it running, where things live, and what is hard to change today. Details are in the [engineering Wiki](docs/wiki/README.md); find code by question with `python tools/wiki_route.py "your question"`.

## 1. Running in ten minutes

Follow the [README](README_en.md) for the environment (Windows 10/11 x64, Python 3.11, a virtual environment, `pip install -c requirements-lock.txt -e ".[dev]"`). Then:

```powershell
.venv\Scripts\python tools/run_tests.py -q tests/test_global_settings.py
```

```powershell
.venv\Scripts\python tools/run_tests.py -q
```

The first takes seconds and tells you the environment works. The second is the whole suite, about 9 minutes. Without local game assets and run evidence, more than seven hundred tests skip with a stated reason; that is expected, because the repository ships no game assets (see [local assets](docs/local-assets.md)). Always run tests through `tools/run_tests.py`, which returns pytest's own exit code.

Two things to know:

- While the installed app is running a task on the same machine, a group of tests fails with `another_controller_owns_game`: they compete with the real task for one controller lock. Run the full suite when no task is running.
- Run `python tools/check_public_tree.py` before committing. It rejects local paths, account and device identifiers, game assets and binaries. When a test needs "some local path" as sample data, write `Z:/someone/...`, not the shape of a real user folder.

## 2. Where things live

There are two processes: the GUI is an unmodified MXU reading `assets/interface.json`; it starts the Python Agent (`agent/`), which captures and clicks through MaaFramework. A task is an observe, plan, act loop:

| Stage | Where | Notes |
| --- | --- | --- |
| Observe: capture and OCR | `agent/recognition.py` (`observe`, `analyze`) | Turns a frame into a record: texts, boxes, page |
| Observe: which page is this | `src/maalimbus/vision.py` (`classify`), `src/maalimbus/pages.py` | `pages.py` is the page registry: owner, allowed actions, expected successors |
| Plan: what to click | `src/maalimbus/window.py` (`plan_step`, `STEP_ROWS`) | Pure functions, no device; a simple page is one row of `STEP_ROWS` |
| Act: the loop and its transactions | `src/maalimbus/runner.py` (`MirrorRunner.step`) | Sends input, checks the successor, books results; shop, deployment and payout each have a "record the intent, then click" transaction module |
| How a setting reaches the program | an option in `assets/interface.json` → the `attach` of the node of the same name in `assets/resource/base/pipeline/mirror.json` → read by the Agent with `context.get_node_data` | A new setting changes both files and the three `assets/i18n/*.json` |

Entry points for common questions:

| To change | Start reading at |
| --- | --- |
| What the shop buys | the shop section of `step` in `runner.py` → `gift_plan.shop_wanted`, `shop_priority.load`, `runner.shop_state`, `shop_learning.rank_offers` |
| Deployment order | `deployment_transaction.prepare`, `team_vision`, `global_settings.parse_order` |
| Claiming rewards | `reward_task.execute`, `paid_reward_action.prepare`, `reward_receipt_audit.verify` |
| Team settings, Mirror schedule, automatic claim | `global_settings.py`, `mirror_schedule.py`, `reward_task_budget.py` |
| Run data and the task log | `run_history.py`, `run_report.py`, `page_names.py` |
| Screenshot storage | `capture_retention.py` (`settle`) |

**When the game adds a page, change:** `vision.py` (`classify` recognises it), `pages.py` (register it), `page_names.py` (a player-facing name), `window.py` (a row in `STEP_ROWS` or a rule in `_plan_step`), `assets/resource/<language>/locale.json` (its texts) and the tests. `tests/test_pages.py` names a registry table you forgot.

## 3. What is hard to change today

On 2026-11-23 an independent review looked at the repository as an engineer who had never seen it. Its conclusion: the periphery can be changed by a person with confidence; the core loop is, in practice, changeable only by an AI agent holding the whole context. Specifically:

- `MirrorRunner.step` is one function of 3,339 lines; `window._plan_step` has 812, `vision.classify` 469, `recognition.analyze` 433.
- 46 of 1,694 functions carry a type annotation; the loop's state is an untyped dictionary.
- No linter, formatter or type checker is configured; about a third of the modules use a dense several-statements-per-line style.
- Some dozens of tests assert on source text, so a blanket reformat would break them today.
- Many comments narrate a past run (with its run id) instead of stating an invariant; the Wiki is large, and its line-number citations go stale silently.

The order of improvements and their progress are recorded in [Wiki chapter 9, "public-version goal"](docs/wiki/en_us/9-execution-plan.md#public-goal). Until then, **write new code like the recent small modules**: `mirror_schedule.py`, `run_history.py`, `global_settings.py`. A docstring that states what the module guarantees, PEP 8, errors that name the bad input, and tests of behaviour rather than of source text.

## 4. Commits

- One change per commit; say what changed, why, and **what was not verified**.
- Commit only when tests pass. A behaviour change updates the matching Wiki section (both languages) and `docs/wiki/routes.json`; a new module must have a route (`tests/test_wiki_route_coverage.py` checks).
- Never commit game assets, screenshots, or account or device information.
