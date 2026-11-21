# AGENTS.md

MaaLimbus — MaaFramework Win32 controller + ProjectInterface V2 + MXU + Python Agent 的工程约定。
This file is the entry point for agents working in this repo.

## 先读这些

定位功能或排查症状时，先用短索引 [`docs/wiki/agent-index.md`](docs/wiki/agent-index.md)，
或 `python tools/wiki_route.py "问题/错误文本"`。它返回当前代码符号、局部图、测试与验收边界，
通常比猜文件名快；只读相关章节，不要求全站通读。源码/实证与叙述冲突时核实并修正索引，
不让文档覆盖事实。实施计划在 wiki 第9章。这里不增加文件锁、审批或游戏运行门禁。

安装版实际通过卡点后，按 [Wiki 9：通过后复盘](docs/wiki/zh_cn/9-execution-plan.md#post-passage-review)
检视观察到的游戏机制、相邻页面与生产者/消费者接点、原方案遗漏的变体及替代方案。
健康脚本继续运行；期间只读原生证据并在内存分析，复盘在自然返回或正常串行维护时落盘。
不把局部用例通过当作整条管线完成，也不为写复盘暂停任务。

- 本机 `PROJECT.md`（如有）— 私有开发记录。公开 checkout 通过设计、验收与 Wiki 继续开发。
- `docs/design.md` — 设计约束。
- `docs/acceptance.md` — 验收口径。
- `docs/wiki/README.md` — 分层讲解 wiki（架构、运行时、业务流程、状态与数据、部署、质量、agent 规则层，中英双语）；叙述性文档层，不替代上面三个事实源。

规范术语以 [Wiki1.2](docs/wiki/zh_cn/1-overview.md#glossary) 为唯一词典；上下文入口见 [CONTEXT-MAP.md](CONTEXT-MAP.md)，正式架构迁移状态见 [9.4.6](docs/wiki/zh_cn/9-execution-plan.md#runtime-migration)。只读相关范围，不增加流程锁。

## 游戏时间与内容窗口

开始一次实机任务前，先读时钟，再读当前窗口实际有什么内容，然后决定跑什么；不要对已经重置或已经用掉的内容重试、等待或重放。

- 每周与每日内容按服务器时间滚动：镜牢周次与每周奖励按周重置，日常任务有每日上限，维护会中断会话。权威是游戏自己的通知页（`weekly_reset` / `weekly_moving`，`src/maalimbus/vision.py:392-396`）与账本，不是仓库里记的日期。
- 已经失效的内容不再当资源用：`WINDOW_RESET` 只点 Cancel（`src/maalimbus/window.py:438`），过期会话由 `run_wiring.expire()` 归档为 abandoned（`src/maalimbus/run_wiring.py:190`），轮换停在原队伍。
- 窗口里还有没花掉的周次或每日额度，就在本次启动里用掉，而不是留给下一次；花每周奖励只能由 `earned_its_payout()` 授权（`src/maalimbus/run_wiring.py:269`），「不知道」不算理由。
- 这条只要求读时钟与页面，不增加文件锁、审批或运行门禁，也不额外耗费 API 预算；定位仍走 `python tools/wiki_route.py`。

## Agent skills

### Project Wiki

维护索引、局部工程图、实施计划或跨 agent 交接时，从 [Wiki 维护与交接](docs/wiki/README.md#wiki-maintenance) 找到对应章节和规则，只读相关范围。
仓库卫生、存储盘点、收尾复盘和带日期的项目健康快照从 [项目健康与维护](docs/wiki/README.md#project-health) 进入。
新建文件或处理存储任务，直接看 [文件落点表](docs/wiki/README.md#file-placement)：设计、开发、本地、发布四个区各放什么、谁负责、留多久；普通改字不用读。

主机暴露了 **project-wiki** skill（上游 [projectWikiSkill](https://github.com/sairaisaika/projectWikiSkill)）时用它做这些维护；
项目入口和 hook 接法见 [Wiki 8.7](docs/wiki/zh_cn/8-agent-rules.md#project-wiki-hooks)。
`multi-agent-wiki` 已退役为兼容指针，不再并行加载两套通用规则。
中英镜像、schema-1 路由及测试退出码仍是 MaaLimbus 自己的规则。
已选任务可在 SessionStart 送达；读取上下文不等于重新核验源码，更不等于任务完成。

### Issue tracker

Issues and specs live as GitHub issues in `sairaisaika/MaaLCB`, read and written through the deck tools. See `docs/agents/issue-tracker.md`.

### Triage labels

The five canonical triage roles use their default label strings, plus the five `wayfinder:*` labels. See `docs/agents/triage-labels.md`.

### Domain docs

multi-context. See `docs/agents/domain.md`.

### Memory

Session conclusions are written back to agentmemory (project `MaaLimbus`) so the next session can retrieve them. See `docs/agents/memory.md`.

## 验证命令与退出码

跑测试一律用 `python tools/run_tests.py <参数>`，或者直接调用 pytest 并检查它自己的退出码。

不要写成 `pytest ... | tail && git commit`：管道的退出码来自 `tail`（或任何最后一段命令），于是红的套件会被提交。这个项目在 2026-10-22/23 各犯过一次，第二次是一个守卫测试红着进了仓库。

判定规则：退出码只有来自 pytest 进程本身才算数；要看裁剪后的输出就先用 `> build/x.log 2>&1` 落盘，再 `tail` 日志。
