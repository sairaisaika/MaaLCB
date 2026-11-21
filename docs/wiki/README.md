# MaaLimbus Wiki

本仓库 wiki 的入口路由页。中文导航在前，English navigation 在后；两种语言的正文逐节镜像，文件名同名同结构。

This is the routing page for the repository wiki. Chinese navigation first, English navigation second; the two languages mirror section by section and share file names.

## Agent 快速入口 / Fast agent entry

### 定位功能与排查症状 / Feature lookup and troubleshooting

用[短索引](agent-index.md)或下面的路由命令。查实机状态看[当前实机检查点](zh_cn/9-execution-plan.md#current-checkpoint)，不要把历史记录当作当前实证。
Use [quick routes](agent-index.md) or the native router below. For live status, read the [current checkpoint](en_us/9-execution-plan.md#current-checkpoint) without treating historical results as current evidence.

```text
python tools/wiki_route.py "Grace purchase successor balance not proven"
python tools/wiki_route.py "GPU占用"
python tools/wiki_route.py "神经学习是否apply" --json
```

每次只返回相关功能的**当前代码符号 → 局部解释/图 → 窄范围验证 → 验收边界**。
函数行号随查询从源码重新定位，不依赖记忆猜路径；未实现功能明确指向设计。
没有匹配时再做一次有针对性的源码搜索并补路由，不让wiki挡住工作。

<a id="wiki-maintenance"></a>
### Wiki 维护与交接 / Wiki maintenance and handoff

短索引只负责导航。改路由时更新[路由声明](routes.json)；改 Wiki 正文或局部图时，从下方章节表找到负责该内容的小节，按源码和实证核对后就地更新，跨章节只链接，不复制正文。实施计划和未完成的验收项留在[第 9 章](zh_cn/9-execution-plan.md)；跨 agent 交接的可复用结论按[记忆规则](../agents/memory.md)处理。
只读任务所需范围，不增加文件锁、审批或固定流程。

The quick index is only for navigation. For route changes, update the [route declarations](routes.json). For Wiki text or diagrams, find the owning section in the chapter table below, verify it against source and evidence, and update it in place. Cross-link from other chapters rather than duplicating it. Keep implementation plans and open acceptance items in [chapter 9](en_us/9-execution-plan.md); follow the [memory guidance](../agents/memory.md) for reusable handoff conclusions.
Read only what the task needs. These routes add no locks, approvals, or fixed workflow.

## 中文导航

| 语言 | 索引入口 | 说明 |
| --- | --- | --- |
| 简体中文 | [`zh_cn/index.md`](zh_cn/index.md) | 中文为主文，术语保留英文原名并在首次出现时给中文 |
| English | [`en_us/index.md`](en_us/index.md) | 中文版的忠实镜像，逐节对应，不是摘要 |

章节一览（每页在两种语言下都存在，可直接点击）：

| 页码 | 中文标题 | English title |
| --- | --- | --- |
| 0 | [索引](zh_cn/index.md) | [Index](en_us/index.md) |
| 1 | [概览与术语](zh_cn/1-overview.md) | [Overview and Glossary](en_us/1-overview.md) |
| 2 | [架构](zh_cn/2-architecture.md) | [Architecture](en_us/2-architecture.md) |
| 3 | [运行时](zh_cn/3-runtime.md) | [Runtime](en_us/3-runtime.md) |
| 4 | [业务流程](zh_cn/4-business-flows.md) | [Business Flows](en_us/4-business-flows.md) |
| 5 | [状态与数据](zh_cn/5-state-and-data.md) | [State and Data](en_us/5-state-and-data.md) |
| 6 | [部署与运维](zh_cn/6-deployment.md) | [Deployment and Operations](en_us/6-deployment.md) |
| 7 | [质量与验收](zh_cn/7-quality.md) | [Quality and Acceptance](en_us/7-quality.md) |
| 8 | [Agent 规则层](zh_cn/8-agent-rules.md) | [Agent Rules Layer](en_us/8-agent-rules.md) |
| 9 | [实施计划与完成矩阵](zh_cn/9-execution-plan.md) | [Execution Plan and Acceptance Matrix](en_us/9-execution-plan.md) |

第 4 章已交付。第 8 章是元章节，讲怎么在这个仓库里干活，不讲产品行为。部分章节可能另有子页，子页只由该章自己的主页面链接。

本 Wiki 是叙述性文档层，不替代[设计约束](../design.md)和[验收口径](../acceptance.md)。公开 checkout 可查[最近记录的检查点](zh_cn/9-execution-plan.md#current-checkpoint)和[第 9 章](zh_cn/9-execution-plan.md)的计划与待验收项；有本机 `PROJECT.md` 时可参考其中的开发记录。记录不能证明当前实机状态。

## English navigation

| Language | Index entry | Notes |
| --- | --- | --- |
| 简体中文 | [`zh_cn/index.md`](zh_cn/index.md) | Chinese is the main text; terms keep their English names with a Chinese gloss at first use |
| English | [`en_us/index.md`](en_us/index.md) | A faithful mirror of the Chinese text, section by section — not a summary |

All pages, both languages:

| Page | English title | 中文标题 |
| --- | --- | --- |
| 0 | [Index](en_us/index.md) | [索引](zh_cn/index.md) |
| 1 | [Overview and Glossary](en_us/1-overview.md) | [概览与术语](zh_cn/1-overview.md) |
| 2 | [Architecture](en_us/2-architecture.md) | [架构](zh_cn/2-architecture.md) |
| 3 | [Runtime](en_us/3-runtime.md) | [运行时](zh_cn/3-runtime.md) |
| 4 | [Business Flows](en_us/4-business-flows.md) | [业务流程](zh_cn/4-business-flows.md) |
| 5 | [State and Data](en_us/5-state-and-data.md) | [状态与数据](zh_cn/5-state-and-data.md) |
| 6 | [Deployment and Operations](en_us/6-deployment.md) | [部署与运维](zh_cn/6-deployment.md) |
| 7 | [Quality and Acceptance](en_us/7-quality.md) | [质量与验收](zh_cn/7-quality.md) |
| 8 | [Agent Rules Layer](en_us/8-agent-rules.md) | [Agent 规则层](zh_cn/8-agent-rules.md) |

Page 4 is delivered. Chapter 8 is a meta chapter about working in this repository rather than product behaviour. Some chapters may add sub-pages; a sub-page is only reachable from its own chapter's main page.

This Wiki explains the project without replacing the [design constraints](../design.md) or [acceptance criteria](../acceptance.md). In a public checkout, use the [last recorded checkpoint](en_us/9-execution-plan.md#current-checkpoint) and [chapter 9](en_us/9-execution-plan.md) for plans and pending acceptance. A local `PROJECT.md`, when present, supplements these with development notes. Records alone do not establish current runtime state.

## docs/ 专题地图 / docs/ topic map

下表按主题链接延伸阅读，细节以原文为准。验收与进度记录、未落地的计划与实验、一次性交接记录、审计、许可正文和逐文件测试清单不在这份专题索引的范围内。未落地的计划不算已验收。

The table links to related topics by subject; consult each linked document for details. Acceptance and progress records, unimplemented plans and experiments, one-off handoffs, audits, license text, and per-file test inventories are outside this topic index. A plan is not acceptance evidence.

| 主题 / Theme | 文档 / Document |
| --- | --- |
| 运行时与两条运行路径 / Runtime and the two run paths | [`docs/runner.md`](../runner.md) — runner 作为库（去掉屏幕与输入之后的镜牢循环）；[`docs/agent-loop.md`](../agent-loop.md) — 打包应用驱动整轮运行的 pipeline 接缝。 |
| 架构契约与决策 / Architecture contract and decisions | [`docs/post-battle-ownership.md`](../post-battle-ownership.md) — 战后路径归 pipeline 还是归 driver；**给奖励卡、层礼、商店、下一层或入场返回加节点之前先读**。 |
| 原生控制与 MXU 配置 / Native control and MXU configuration | [`docs/native-control.md`](../native-control.md) — 原生客户端与窗口控制、四种控制方式；[`docs/task-settings.md`](../task-settings.md) — 任务与已保存队伍的设置项；[`docs/theme-packs.md`](../theme-packs.md) — 主题包选择任务（尚未接通地图与五层循环）。 |
| 商店设置 / Shop settings | [`docs/shop-settings.md`](../shop-settings.md) — 决定一次商店访问如何被限界、携带上限与解析器的三项镜牢设置。 |
| 商店的死位复活 / The shop's revive of a dead key slot | [`docs/shop-revive.md`](../shop-revive.md) — `Heal Sinner` 三步弹窗（三选项 → 选中罪人 → 复活通告）各自的文字证明、弹窗右下角那颗换词按钮、以及「按币值差记账」的收据契约。 |
| 打包与分发 / Packaging and distribution | [`docs/windows-package.md`](../windows-package.md) — Windows 开发包的实际构成与它的未验收边界。 |
| 更新链 / Update chain | [`docs/update-staging.md`](../update-staging.md) — `tools/check_update.py --stage` 的下载与暂存语义；[`docs/startup-updater.md`](../startup-updater.md) — 桌面快捷方式启动器的自更新流程。 |
| 框架一致性 / Framework conformance | [`docs/maaframework-conformance.md`](../maaframework-conformance.md) — 与 MaaFramework 上游协议的逐项对照**及其缺口段**，是「哪些协议特性本项目根本没断言」的集中来源。 |
| 黑盒学习 / Black-box learning | [`docs/learning.md`](../learning.md) — 图像哈希、按真实运行分组的训练数据准备与当前样本不足的诚实结论。 |
| 许可与上游对照 / License and upstream cross-check | [`docs/readme-license-reference.md`](../readme-license-reference.md) — 针对指定上游提交核对 README、LICENSE、构建指南与标准接口设计。 |
| 协作流程（agent 专用）/ Collaboration process (agent-facing) | [`docs/agents/domain.md`](../agents/domain.md)、[`docs/agents/issue-tracker.md`](../agents/issue-tracker.md)、[`docs/agents/memory.md`](../agents/memory.md)、[`docs/agents/triage-labels.md`](../agents/triage-labels.md) — 多上下文域文档、issue 追踪、记忆回写与 triage 标签约定（`AGENTS.md` 已在入口指向它们）。 |

<a id="project-health"></a>

## 项目健康与维护 / Project health and maintenance

这一节是仓库卫生、存储盘点和收尾复盘的入口，也是带日期的项目健康快照唯一的落点。快照是一次观测，过期就重测，不当作现状证书。这里不增加文件锁、审批或运行门禁。

This section is the entrance for repository hygiene, storage inventory and closeout review, and the one place the dated project-health snapshot lives. A snapshot is an observation: re-measure it instead of trusting it. Nothing here adds a file lock, an approval or a run gate.

**何时进来 / When to enter**

- 建文件前、生成产物后、暂存前、提交前：对照下面的[文件落点表](#file-placement)。目的地是公开仓库，所以 PR 文本、Release 资产和附件都按公开口径审。
- 项目目录接近 3 GB 提醒线，或交接、发版之前：先做只读盘点。大小、年代和 ignore 状态都不构成清理授权。
- 修复、事故、交接、暂停或恢复时：可复用的规则还给所属章节，运行证据留在 `docs/acceptance.md` 与[第 9 章](zh_cn/9-execution-plan.md)，未完成项留在第 9 章矩阵。安装版越过卡点后按[通过后复盘](zh_cn/9-execution-plan.md#post-passage-review)检视机制。
- Before creating a file, after generating output, before staging and before committing: check the [file placement table](#file-placement) below. The destination is a public repository, so PR text, release assets and attachments are reviewed as public too.
- When the project directory nears the 3 GB reminder, or before a handoff or a release: start with the read-only inventory. Size, age and ignore status grant no cleanup authority.
- At a fix, incident, handoff, pause or resume: return reusable rules to their owning chapter, keep run evidence in `docs/acceptance.md` and [chapter 9](en_us/9-execution-plan.md), keep open work in the chapter 9 matrix. After the installed build passes a blocker, review the mechanism as [post-passage review](en_us/9-execution-plan.md#post-passage-review) describes.

<a id="file-placement"></a>

**文件落点表 / File placement**

新建文件或处理存储之前先在这张表里找到它的区；普通改字不用读。四个区分别回答「放哪里、谁负责、从哪进、留多久」。表里写的是这个项目现有的目录，不要求新目录名，也不加 hook。

Find a new file's zone here before creating it or handling storage; an ordinary text edit needs none of this. The four zones answer where a file goes, who owns it, where to enter and how long it is kept. The table names the directories this project already has; it mandates no new directory name and adds no hook.

| 区 / Zone | 用途 / Purpose | 实际路径 / Paths | 负责者与入口 / Owner and entry | Git 规则来源 / Git rule source | 保留 / Retention |
| --- | --- | --- | --- | --- | --- |
| 设计区 / Design | 稳定的架构、契约、决定和正式图。 Stable architecture, contracts, decisions and canonical diagrams. | `docs/design.md`、`docs/acceptance.md`、`docs/wiki/`、`docs/adr/`、上面专题地图里的文档、`CONTEXT-MAP.md` 与各目录 `CONTEXT.md`、`docs/agents/`、`AGENTS.md`、`README.md`、`README_en.md` | 维护者；每处改动归所属章节，入口是上面的章节表。 The maintainer; each change belongs to its owning chapter, entered through the chapter table above. | 跟踪。`.gitignore` 里对 `AGENTS.md`、`CONTEXT.md`、`docs/agents/` 的否定行保证它们不被误忽略。 Tracked; the negation lines in `.gitignore` keep them from being ignored. | 长期保留，就地修改。任务收尾时只把验证过的结论写回这里，不复制草稿和日志。 Kept and edited in place. At closeout only verified conclusions are written back, never drafts or logs. |
| 设计区：源码与契约 / Design: source and contracts | 可公开的代码、接口契约、目录数据、许可与示例。 Public code, interface contracts, catalog data, licences and examples. | `src/`、`agent/`、`desktop/`、`tools/`、`tests/`、`assets/interface.json`、`assets/i18n/`、`assets/resource/`（位图除外 / bitmaps excepted）、`assets/misc/Don-Quixote.png`、`docs/examples/config/`、`pyproject.toml`、`requirements-lock.txt`、`LICENSE`、`THIRD_PARTY_NOTICES/`、`.github/workflows/` | 维护者；功能入口是[短索引](agent-index.md)。 The maintainer; features are entered through the quick index. | 跟踪。示例配置、锁文件和合成测试素材必须保持未被忽略：`docs/examples/config/` 下的 JSON 不受 `config/` 规则影响。 Tracked. Example configuration, the lock file and synthetic test material must stay un-ignored: the JSON under `docs/examples/config/` is outside the `config/` rules. | 长期保留。测试素材只收合成的；唯一随仓库的图片是应用图标，来源记在 `THIRD_PARTY_NOTICES/README.md`。 Kept. Test material is synthetic only; the one tracked image is the application icon, whose origin is recorded in `THIRD_PARTY_NOTICES/README.md`. |
| 开发区 / Development | 任务记录、草稿、实验和回执。 Task records, drafts, experiments and receipts. | `PROJECT.md`、`.codex/`、`.research/`、`.scratch/`、`tests/local/`、`tools/local/`，以及 issue 和 PR / plus issues and pull requests | 做这项任务的人或 agent；交接按[记忆规则](../agents/memory.md)。 Whoever does the task; handoffs follow the memory guidance. | 根 `.gitignore` 的 "Local development handoff" 与 "Workstation-only" 两段；`.gitattributes` 的 `export-ignore` 另外把它们挡在源码归档之外。 Two blocks of the root `.gitignore`; `export-ignore` in `.gitattributes` also keeps them out of source archives. | 留到结论提炼回设计区为止，不自动清理。只有审核过、可公开的证据才进仓库，落点是 `docs/acceptance.md` 和[第 9 章](zh_cn/9-execution-plan.md)。 Kept until the conclusion is distilled into the design zone; never cleaned automatically. Only reviewed, publishable evidence enters the repository, in `docs/acceptance.md` and [chapter 9](en_us/9-execution-plan.md). |
| 开发区：审计与回滚 / Development: audit and rollback | 账本引用的运行证据、冷归档、更新回滚点，以及更早的开发历史。 Run evidence that ledgers cite, the cold vault, update rollback points and earlier development history. | `evidence/`、`build/updates/`、仓库之外的冷归档（位置只记在本机）、维护者私下保留的原始开发仓 / the cold vault outside the repository (its location is recorded locally only) and the original development repository the maintainer keeps privately | 维护者；流程在[第 6 章](zh_cn/6-deployment.md#bounded-image-vault)，工具是 `tools/capture_retention.py` 和 `tools/prune_workspace.py`。 The maintainer; the procedure is in [chapter 6](en_us/6-deployment.md#bounded-image-vault). | `/evidence/`、`build/` 被忽略并 `export-ignore`。 Ignored and `export-ignore`. | **即使没有任何 Wiki 页面引用也保留。** 只按所有者流程退役；大小、年代和 ignore 状态都不是清理依据。 **Kept even when no wiki page cites it.** Retired only by the owner's procedure; size, age and ignore status are no grounds for cleanup. |
| 本地区：个人配置与状态 / Local: personal configuration and state | 账号相关的配置、账本、事务和凭据。 Account-related configuration, ledgers, transactions and credentials. | `config/`，或环境变量 `MAALIMBUS_DATA_PATH` 指向的目录；`.env`、`*.local.json`、密钥文件 / or the directory `MAALIMBUS_DATA_PATH` names; `.env`, `*.local.json`, key files | 每位用户自己；格式见[示例配置](../examples/config/README.md)。 Each user; the format is in the [example configuration](../examples/config/README.md). | `/config/`、`.env`、`*.local.json`、`*.pem` 等规则，加 `export-ignore`。**忽略规则不是隐私边界**：敏感内容只放在这个获批的位置，不放进仓库目录的别处。 Ignore rules plus `export-ignore`. **An ignore rule is not a privacy boundary**: sensitive content lives only in this approved location, nowhere else in the checkout. | 归用户所有，工具不替用户清理。不进提交、issue、PR、CI 或发行包。 The user's own; no tool cleans it. Never in a commit, issue, pull request, CI run or release package. |
| 本地区：游戏素材 / Local: game assets | 识别模板、图标、游戏截图、编辑器头像和参考仓副本。 Recognition templates, icons, game screenshots, editor portraits and the reference checkout. | `assets/resource/base/image/` 下的 PNG、`tests/fixtures/frames/` 与 `tests/fixtures/floor-gift-ocr-drift/` 下的 PNG、`desktop/mxu/teamArtwork.ts`、`sources/upstream/`、`yolo11n.pt` | 每位用户自己；入口是[本地游戏素材](../local-assets.md)，清单是 `assets/resource/base/local-assets.json`。 Each user; entered through [local game assets](../local-assets.md) and its manifest. | 根 `.gitignore` 末尾逐条列出的精确规则，只匹配这些文件；旁边的 JSON 仍然跟踪。 Exact rules at the end of the root `.gitignore`, matching these files only; the JSON beside them stays tracked. | 由用户本地导入，可以重新导入。无法确认可再分发，所以不进 Git、发行包和 CI。 Imported locally and re-importable. Redistribution is not established, so never in Git, a release package or CI. |
| 本地区：原始采样与诊断 / Local: raw samples and diagnostics | 原始截图、设备数据、运行日志和本机诊断。 Raw captures, device data, run logs and machine diagnostics. | `evidence/`、`logs/`、`runs/`、`*.log` | 产生它的那次运行；保留密度由 `tools/capture_retention.py` 决定。 The run that produced it; `tools/capture_retention.py` sets the retention density. | `/evidence/`、`/logs/`、`/runs/`、`*.log` | 按证据保留规则；被账本或验收记录引用的，归上面的审计与回滚。 By the evidence retention rule; anything a ledger or acceptance record cites belongs to audit and rollback above. |
| 本地区：可重建产物 / Local: rebuildable output | 构建输出、缓存和虚拟环境。 Build output, caches and virtual environments. | `build/`、`dist/`、`.venv/`、`__pycache__/`、`.pytest_cache/`、`.ruff_cache/`、`.cache/`、`*.egg-info/` | 产生它的命令。 The command that produced it. | 根 `.gitignore` 的共享规则，对所有人一致。纯个人、无敏感内容的临时文件用本机的 `.git/info/exclude`，不往共享规则里加。 Shared rules in the root `.gitignore`, the same for everyone. Purely personal, non-sensitive scratch files use the local `.git/info/exclude`, not the shared rules. | 可重建，所有者随时可以删除；`build/updates/`、正在使用的 `build/controller.lock` 和安装目录 `dist/MaaLimbus` 里的配置不属于这一行。 Rebuildable and deletable by its owner; `build/updates/`, a `build/controller.lock` in use and the configuration inside an installed `dist/MaaLimbus` do not belong to this row. |
| 发布区 / Release | 公开仓库的提交、源码归档、Python 包、Release 资产和 CI 产物。 Commits of the public repository, source archives, Python packages, release assets and CI artifacts. | 公开仓库的 Git 树；`build/python-package/`；Release 页面 / the public repository's Git tree, `build/python-package/` and the Releases page | 维护者逐项确认后发布；检查入口是 `tools/check_public_tree.py`。 Published by the maintainer, item by item; checked with `tools/check_public_tree.py`. | 只从审过的公开源码构建。CI 不上传任何产物。 Built only from reviewed public source. CI uploads nothing. | 已发布的内容不可变，有错就发新的；删除要逐项确认。 Published content is immutable: a wrong one is superseded, and deletion is confirmed item by item. |

**四件事分开核对 / Four separate checks**

一个文件是否被跟踪、是否被忽略、是否进了包、是否该保留，是四个互不推出的问题，各用各的只读办法回答：

Whether a file is tracked, ignored, packaged or to be kept are four questions that do not imply one another. Each has its own read-only answer:

| 问题 / Question | 怎么查 / How |
| --- | --- |
| 被跟踪吗 / Tracked? | `git ls-files --error-unmatch -- <path>` |
| 被哪条规则忽略 / Ignored by which rule? | `git check-ignore -v --no-index -- <path>` |
| 进了包吗 / Packaged? | `python tools/check_public_tree.py --archive <file>`，对源码归档、sdist 和 wheel 都适用。 Works on a source archive, an sdist and a wheel. |
| 该保留吗 / To be kept? | 看上表的保留列和所有者流程；Git 状态不回答这个问题。 The retention column above and the owner's procedure; Git state does not answer it. |

**仓库配置索引 / Repository configuration index**（2026-11-21 UTC 观测 / observed）

| 项 / Item | 现状 / State |
| --- | --- |
| 可见性与发布面 / Visibility and publication surfaces | 这个仓库是公开的；发布之前和每次改动发布面之后，用仓库元数据核对一次可见性，不从 URL 或本地目录名推断。提交、PR 文本、issue 附件、Release 资产和源码归档都属于公开面，按同一口径审。 This repository is public. Verify visibility from repository metadata before publishing and after any change of publication surface; never infer it from a URL or a local folder name. Commits, pull request text, issue attachments, release assets and source archives are all public surfaces and are reviewed alike. |
| 默认分支 / Default branch | `main` |
| Ignore 策略 / Ignore policy | 只有根目录 `.gitignore`，没有嵌套规则；`.gitattributes` 的 `export-ignore` 管源码归档。每条规则对应[文件落点表](#file-placement)里的一行。 Root `.gitignore` only, no nested rules; `export-ignore` in `.gitattributes` governs source archives. Each rule maps to a row of the [file placement table](#file-placement). |
| CI | `.github/workflows/tests.yml`：`windows-latest`、Python 3.11，在 PR 和 `main` 的 push 上按锁文件安装 `.[dev]`，然后依次跑 Wiki 守卫、公开树检查、缺素材报告（必须以退出码 2 报告缺失）、全量回归和 Python 包构建并检查包内容。只有 `contents: read`，不用 secrets，不上传任何产物，日志和截图不会变成可下载文件。 `.github/workflows/tests.yml`: `windows-latest`, Python 3.11, on pull requests and pushes to `main`; installs `.[dev]` from the lock file, then runs the wiki guard, the public-tree check, the missing-asset report (which must report the absence with exit status 2), the suite, and the Python package build with a check of what it packed. `contents: read` only, no secrets and no artifact upload, so no log or frame leaves the runner as a download. |
| PR 模板与 CODEOWNERS / PR template and CODEOWNERS | 缺失。 Missing. |
| 合并与发版门禁 / Merge and release gates | 未核实：分支保护和必需检查是仓库设置，不在仓库文件里。工作流存在或者跑绿，都不说明它是合并的必需检查。 Unverified: branch protection and required checks are repository settings, not repository files. A workflow that exists or is green does not show that it is required for merging. |

<a id="project-health-snapshot"></a>

**健康快照 / Health snapshot**（2026-11-21 UTC）

这份快照写在公开快照生成的时候。更早的开发记录（合并、发版、实机运行和本机存储的逐次观测）留在维护者的开发区，没有随公开仓库走。

This snapshot was written when the public snapshot was made. Earlier development records (merges, releases, live runs and local storage observations) stay in the maintainer's development zone and are not part of the public repository.

| 维度 / Dimension | 观测 / Observation | 判断与下一步 / Verdict and next step |
| --- | --- | --- |
| 公开历史 / Public history | 这个仓库的历史从公开快照的那一次提交开始。此前的开发历史由维护者私下保留，不在这里。 This repository's history starts at the commit of the public snapshot. Earlier development history is kept privately by the maintainer and is not here. | 有意为之。不要把旧历史推到这里。 Deliberate. Do not push the old history here. |
| 游戏素材 / Game assets | 仓库不带游戏位图：360 张识别模板和图标、6 张整屏截图夹具、22 张编码在源码里的编辑器头像都已移出，改由用户本地提供；清单只留路径、尺寸和 SHA-256。唯一随仓库的图片是应用图标。 No game bitmap is tracked: 360 recognition templates and icons, 6 full-frame screenshot fixtures and 22 editor portraits encoded into source were moved out and are supplied locally by each user; the manifest keeps paths, sizes and SHA-256 only. The one tracked image is the application icon. | 缺素材时镜牢任务在输入前停下并点名缺的组。19 张自行裁切的模板里有 9 张没有留下裁切矩形，只能手工裁，见[本地游戏素材](../local-assets.md)。 Without assets a Mirror Dungeon task stops before input and names the missing groups. Nine of the 19 self-cropped templates have no recorded rectangle and must be cut by hand; see [local game assets](../local-assets.md). |
| 公开 checkout 的可用性 / Usability of a public checkout | 在不含本机目录、不含游戏素材的 checkout 上，按 README 用锁文件装 Python 3.11 环境，Wiki 守卫和全量回归都以退出码 0 结束。需要本机文件或真实游戏画面的测试逐条跳过并写出缺的文件。 On a checkout with no local directory and no game asset, a Python 3.11 environment installed from the lock file as the README says ends the wiki guard and the full suite with exit status 0. Tests that need local files or real game imagery skip one by one, naming the file they lack. | 跳过不算通过。导入素材后的实机流程跑过一次：打包后的预任务拉起模拟器，「打开游戏」任务启动游戏，公开版从冷启动走到第 1 层并打赢四场战斗，之后在地图上一个下方没有徽记的商店类节点前安全停机，见 [验收记录](../acceptance.md) 最上面一节。整层通关、整局完成和领奖在公开版上还没有验证。桌面发行包已经从全新克隆完整构建过一次（见下面「桌面应用与发版」一行）。从网页下载的源码归档没有 `.git`，CI 不覆盖这种形态：发布后要另外从下载的归档装一遍、跑一遍，第一次这样做就查出一条假定有 git 的测试。 A skip is not a pass. The live flow after importing assets has run once: the packaged pretask started the emulator, the Open game task started the game, and the public build went from a cold start into floor 1 and won four battles, then stopped safely on the map before a shop-kind node drawn without a badge; see the first section of the [acceptance records](../acceptance.md). A floor clear, a completed run and a payout are unverified on the public build. The desktop release package has been built in full once from a fresh clone (see the desktop app row below). A source archive downloaded from the web page has no `.git`, a form CI does not cover: after publishing, install and run once from the downloaded archive as well. The first time that was done it found a test that assumed git. |
| 回归的实际覆盖 / What the regression really covers | 全量回归通过并不等于全部在跑。跳过分三类，各自写明原因：读本机 `evidence/`、`build/`、`dist/`、`config/` 的测试（`needs_local`）；所需运行已被存储预算退役的测试（退役证据守卫，按测试判定）；以及需要游戏位图的测试（由加载器抛出的 `MissingLocalAssets` 逐条转成点名的跳过）。 A green suite is not a suite that ran everything. Skips come in three kinds, each naming its reason: tests that read local `evidence/`, `build/`, `dist/` or `config/` (`needs_local`); tests whose run was retired by the storage budget (the retired-evidence guard, decided per test); and tests that need game bitmaps (the loaders' `MissingLocalAssets`, turned into a named skip one test at a time). | 守卫自己的测试在 `tests/test_local_prerequisites.py`、`tests/test_retired_evidence_guard.py` 和 `tests/test_local_assets.py`。缺的是已跟踪文件时仍然失败。待做：给仍然需要真实画面的识别测试补合成画面。 The guards' own tests are in those three files. A missing tracked file still fails. Open: synthetic frames for the recognition tests that still need real imagery. |
| 引用漂移 / Citation drift | 第 4、7 章共有 58 处按行号引用 `docs/acceptance.md`。那份文档总在顶部追加新小节，守卫只核对行号没有越界，看不到这种漂移。 Chapters 4 and 7 hold 58 line-number citations into `docs/acceptance.md`. That document is always prepended to, and the guard only checks that a line exists. | 待修：对顶部追加的文档改用小节锚点引用，再让守卫拒绝对它的行号引用。 Open: cite prepended documents by section anchor, then have the guard refuse line numbers into them. |
| 代码结构 / Code structure | `src/maalimbus/` 是平铺模块，其中 `runner.py` 约九千行；`tools/` 两百多个脚本里近一半是一次性的 `verify_*`。 `src/maalimbus/` is flat, with about nine thousand lines in `runner.py`; nearly half of the two-hundred-odd scripts in `tools/` are one-off `verify_*`. | 结构债集中在 `runner.py` 和一次性验证脚本。按[运行时迁移](zh_cn/9-execution-plan.md#runtime-migration)逐步拆，不做推倒重写。 Debt concentrates in `runner.py` and one-off verifiers; follow the [runtime migration](en_us/9-execution-plan.md#runtime-migration), not a rewrite. |
| `docs/` 布局 / `docs/` layout | Wiki 之外还有三十来份平铺文档，其中若干是没有落地的计划和审计；上面的专题地图刻意不列它们。一次性的交接和会话记录已经移出公开仓库。 Outside the wiki, thirty-odd flat documents include plans that never landed and audits; the topic map above omits them on purpose. One-off handoff and session records were moved out of the public repository. | 待整理：归入一个历史目录。Wiki 和验收文档里有指向它们的路径锚点，搬动要一起改。 Open: move them under one history directory together with the path anchors that cite them. |
| 桌面应用与发版 / Desktop app and releases | 第一个桌面包已作为预发布版 [v0.1.3](https://github.com/sairaisaika/MaaLCB/releases/tag/v0.1.3) 发布（提交 `68a77af`，232,341,637 字节），并从未登录的下载复验过：校验和、清单、打包 Agent 自检、缺素材报告、模拟器预任务的拒绝路径和编队回放都通过；应用内更新检查不把预发布当成更新。发布时查出构建器把 `SHA256SUMS` 写成了 CRLF，`sha256sum -c` 读不了；发布的那份是按原哈希重写的 LF 版本，构建器随后已改正。2026-11-21 第一次从全新克隆、按锁文件安装的环境完整跑通 `tools/build_windows_package.py`：538 个成员、约 232 MB，唯一的图片是应用图标，没有游戏位图、私有路径和隐私命中，清单校验一致，打包 Agent 自检写明七组素材缺失，编队回放通过。跑通之前连续查出五个只在干净环境出现的缺陷并修掉：许可文本被换行转换、MXU 许可没有保存上游原始字节、强制要求四个项目并未导入的包的许可文件、打包后的 Runner 找不到 MaaFramework、构建信息里写进本机绝对路径。源码声明的版本是 `pyproject.toml` 与 `assets/interface.json` 里的 0.1.3。应用内的更新检查指向 GitHub Releases。 The first desktop package is published as the pre-release [v0.1.3](https://github.com/sairaisaika/MaaLCB/releases/tag/v0.1.3) (commit `68a77af`, 232,341,637 bytes) and was re-verified from an anonymous download: the checksum, the manifest, the packaged Agent self-test, the missing-asset report, the refusal path of the emulator pretask and the deployment replay all pass; the in-app update check does not treat a pre-release as an update. Publishing found that the builder wrote `SHA256SUMS` with CRLF, which `sha256sum -c` cannot read; the published copy is an LF rewrite of the same hash, and the builder has since been fixed. On 2026-11-21 `tools/build_windows_package.py` ran in full for the first time from a fresh clone in an environment installed from the lock file: 538 members, about 232 MB, the application icon as its only image, no game bitmap, no private path and no privacy finding, a manifest that verifies, a packaged Agent self-test naming the seven missing asset groups, and a passing deployment replay. Five defects that only a clean environment shows were found and fixed on the way: line-ending conversion of the licence texts, the MXU licence not stored with its upstream bytes, mandatory notices for four packages the project never imports, a packaged Runner that could not find MaaFramework, and absolute build-machine paths in the build info. The source declares version 0.1.3 in `pyproject.toml` and `assets/interface.json`. The in-app update check points at GitHub Releases. | 发版是对外不可逆动作，逐项确认后再做；发布的包不带游戏素材，导出时由 `export_assets` 把关。战斗和主题两个打包回放要读游戏位图，在不带素材的发行包上会点名缺的位图后停下，它们只能在本机导入素材后的应用上跑。 Publishing is irreversible and confirmed item by item; a published package carries no game asset, which `export_assets` enforces at export. The packaged battle and theme replays read game bitmaps: on a release package without assets they stop and name the missing bitmap, so they can only run on an app with locally imported assets. |

**重测命令 / Re-measure**

```powershell
git status --short --ignored
python tools/check_wiki.py
python tools/check_public_tree.py
python tools/check_local_assets.py
python tools/run_tests.py -q -rs
```

存储盘点用 project-wiki skill 自带的只读脚本 `storage_inventory.py`，根目录限定为本仓库；它只读文件元数据，不清理。清理走各自的所有者流程：证据与冷归档见[第 6 章](zh_cn/6-deployment.md#bounded-image-vault)。

Storage inventory uses the read-only `storage_inventory.py` shipped with the project-wiki skill, scoped to this repository; it reads metadata and cleans nothing. Cleanup belongs to each owner's procedure: evidence and the cold vault are in [chapter 6](en_us/6-deployment.md#bounded-image-vault).

## 自检 / Self-check

wiki 有一道离线守卫。任何一页漂移——锚点指向不存在的文件、行号越界、导航行被改坏、只有一种语言加了小节、代码围栏没配对、图类型写错、双语篇幅失衡——它都会非零退出并列出问题：

```powershell
python tools/check_wiki.py
python -m pytest tests/test_wiki.py -q
```

离线守卫判断不了 Mermaid 正文能不能解析（它只认第一行的图类型关键字）。要验证渲染：

```powershell
python tools/make_wiki_mermaid_check.py
python -m http.server 8791 --bind 127.0.0.1
# 打开 http://127.0.0.1:8791/build/wiki-mermaid-check.html
```

必须走 HTTP：`file://` 页面不能 import mermaid 的 ES module，而且会**静默**失败——页面停在 "parsing" 不给结果。

The wiki has an offline guard. Any drift — a `path:line` anchor pointing at a file that does not exist, a line number past the end of the file, a broken navigation line, a section added to one language only, an unpaired code fence, a wrong diagram keyword, or a twin pair out of proportion — makes it exit non-zero and list what broke:

```powershell
python tools/check_wiki.py
python -m pytest tests/test_wiki.py -q
```

The offline guard cannot tell whether a mermaid body parses; it only reads the diagram keyword on the first line. To check rendering:

```powershell
python tools/make_wiki_mermaid_check.py
python -m http.server 8791 --bind 127.0.0.1
# open http://127.0.0.1:8791/build/wiki-mermaid-check.html
```

Serve over HTTP on purpose: a `file://` document cannot import the mermaid ES module, and it fails **silently** — the page sits on "parsing" with no result.


## 图的工程语义 / Engineering semantics of diagrams

| 图 / Diagram | 模型元素与连线语义 / Elements and relationships | wiki 落点 / Location |
| --- | --- | --- |
| 架构 / Architecture | 组件、责任边界、依赖和接口；不表达时间先后 / Components, responsibility boundaries, dependencies and interfaces; no timeline | 2-architecture.md |
| 流程 / Business process | 业务动作、判断、循环、完成与保留现场 / Activities, decisions, loops and outcomes | 4-business-flows.md |
| 时序 / Sequence | 参与者生命线、按时间的调用与响应；输入前记录意图、输入后核后继 / Lifelines, ordered calls and responses; intent before input, successor afterwards | 3-runtime.md |
| 数据模型 / Data model | 逻辑实体、属性、引用及基数；文件字段盘点另外标注，非数据库物理表 / Logical entities, attributes, references and cardinalities; JSON inventories are separate | 5-state-and-data.md |
| 部署 / Deployment | 主机、进程或运行环境、部署制品、通信协议；构建流程另图 / Hosts, processes/environments, artifacts and transport links; builds are separate | 6-deployment.md |
| 状态 / State machine | 状态、事件或守卫、迁移；pending 是状态，不是自动重试许可 / States, events/guards and transitions; pending is not retry permission | 5-state-and-data.md |

Mermaid 是绘图语法，不决定工程图类型。flowchart 语法可承载组件图或部署图，但必须按该图的模型元素与连线语义绘制。布局上下位置本身不表示设计层级或调用先后。

Mermaid is a drawing syntax, not the engineering model. A flowchart renderer can draw components or deployment nodes only when its elements and relationships follow that model. Vertical layout alone does not mean layering or temporal order.

## 分层图覆盖索引 / Feature diagram coverage

总架构与总流程用于导航，局部图用于解释具体守卫、交互、数据或失败恢复。以下链接不代表功能实机全验收；每段正文分别写明实现、保留帧验证与实机缺口。没有图的简单参数/纯函数按文字和源码索引解释，避免为画图而画图。

Overview diagrams are navigation; local diagrams explain specific guards, interactions, data and recovery. Links below do not claim complete live acceptance. Each section distinguishes implementation, retained evidence and live gaps. Simple parameters and pure functions need prose/source references rather than a diagram for every function.

| 功能 / Feature | 中文局部图 | English local view |
| --- | --- | --- |
| 连通节点实测步长 / Connected node geometry | [局部图](zh_cn/4-business-flows.md#feature-4-18) | [Local view](en_us/4-business-flows.md#feature-4-18) |
| 外部分类器适配 / Supplier classifier adapter | [局部图](zh_cn/9-execution-plan.md#feature-9-4-3) | [Local view](en_us/9-execution-plan.md#feature-9-4-3) |
| 地图测量改造计划 / Measured map geometry plan | [局部图](zh_cn/9-execution-plan.md#feature-9-4-4) | [Local view](en_us/9-execution-plan.md#feature-9-4-4) |
| 已结束战斗证据保留 / Completed battle retention | [局部图](zh_cn/9-execution-plan.md#feature-9-4-5) | [Local view](en_us/9-execution-plan.md#feature-9-4-5) |
| 运行时收敛迁移 / Runtime convergence migration | [局部图](zh_cn/9-execution-plan.md#feature-9-4-6) | [Local view](en_us/9-execution-plan.md#feature-9-4-6) |
| 识别、浮层与新观测 / Recognition, overlays and fresh observation | [3.1.5](zh_cn/3-runtime.md#feature-3-1-5) | [3.1.5](en_us/3-runtime.md#feature-3-1-5) |
| 未知页探索与待审标签 / Unknown-page exploration and proposed labels | [3.7](zh_cn/3-runtime.md#feature-3-7) | [3.7](en_us/3-runtime.md#feature-3-7) |
| 罪人模型、独立教师与上线边界 / Sinner model, independent teacher and promotion boundary | [3.8](zh_cn/3-runtime.md#feature-3-8) | [3.8](en_us/3-runtime.md#feature-3-8) |
| 购买价值学习与规则执行的分界 / Purchase-value learning versus rule execution | [3.9](zh_cn/3-runtime.md#feature-3-9) | [3.9](en_us/3-runtime.md#feature-3-9) |
| 启动意图与前台确认 / Launch intent and foreground confirmation | [4.2.1](zh_cn/4-business-flows.md#feature-4-2-1) | [4.2.1](en_us/4-business-flows.md#feature-4-2-1) |
| 入场与列表上下查找 / Entry and bidirectional team-list search | [4.3.2](zh_cn/4-business-flows.md#feature-4-3-2) | [4.3.2](en_us/4-business-flows.md#feature-4-3-2) |
| GUI Start原生适配链 / GUI Start native subtask adapter | [9.3.1](zh_cn/9-execution-plan.md#feature-9-3-1) | [9.3.1](en_us/9-execution-plan.md#feature-9-3-1) |
| 新版镜牢界面的适配计划 / Plan for adapting to the redesigned Mirror Dungeon | [9.3.2](zh_cn/9-execution-plan.md#feature-9-3-2) | [9.3.2](en_us/9-execution-plan.md#feature-9-3-2) |
| 旧局仍在跑时的 GUI Start 入口判定 / GUI Start entry decision while the old run is still playing | [9.3.3](zh_cn/9-execution-plan.md#feature-9-3-3) | [9.3.3](en_us/9-execution-plan.md#feature-9-3-3) |
| 参与者计数读不出时的入口与部署 / Entry and deployment when the participant counter cannot be read | [9.3.4](zh_cn/9-execution-plan.md#feature-9-3-4) | [9.3.4](en_us/9-execution-plan.md#feature-9-3-4) |
| 新版购买确认框的货币徽章 / The redesigned purchase dialog's currency badge | [9.3.5](zh_cn/9-execution-plan.md#feature-9-3-5) | [9.3.5](en_us/9-execution-plan.md#feature-9-3-5) |
| 按完成镜牢计数与藏品搜索开放 / Counting completed runs and opening the gift search | [9.3.6](zh_cn/9-execution-plan.md#feature-9-3-6) | [9.3.6](en_us/9-execution-plan.md#feature-9-3-6) |
| 奖励页两处误停：目录名错字与“价”的判据 / Two false stops on the reward page: a catalogue typo and what counts as a price | [9.3.7](zh_cn/9-execution-plan.md#feature-9-3-7) | [9.3.7](en_us/9-execution-plan.md#feature-9-3-7) |
| 视图读不动与识别卡死：视角恢复阶梯与停滞看门狗 / A page that cannot be read, and a recognition call that never returns: the viewport ladder and the stall watchdog | [9.3.8](zh_cn/9-execution-plan.md#feature-9-3-8) | [9.3.8](en_us/9-execution-plan.md#feature-9-3-8) |
| 读不出来的模态不结束整局：对话框自己的 Cancel 与目录外的藏品 / A modal that cannot be read does not end the run: the dialog's own Cancel, and gifts outside the catalogue | [9.3.9](zh_cn/9-execution-plan.md#feature-9-3-9) | [9.3.9](en_us/9-execution-plan.md#feature-9-3-9) |
| 场景读数不是授权：购买页上的按钮与退役的预留 / A scene read is not an authorization: the button on the purchase page, and the retired reservation | [9.3.10](zh_cn/9-execution-plan.md#feature-9-3-10) | [9.3.10](en_us/9-execution-plan.md#feature-9-3-10) |
| 购买标签来自这一局后来的观测：价值模型的门控式参与 / A purchase is labelled by what the same run later observed: gated participation of the value model | [9.3.11](zh_cn/9-execution-plan.md#feature-9-3-11) | [9.3.11](en_us/9-execution-plan.md#feature-9-3-11) |
| 神经购买排序的绑定凭据与重算留出 / Bound receipts and recomputed holdout for neural purchase ordering | [9.4.1](zh_cn/9-execution-plan.md#feature-9-4-1) | [9.4.1](en_us/9-execution-plan.md#feature-9-4-1) |
| 自动事实标签与人工复核优先关系 / Automatic factual labels and manual review precedence | [9.4.2](zh_cn/9-execution-plan.md#feature-9-4-2) | [9.4.2](en_us/9-execution-plan.md#feature-9-4-2) |
| 每场部署：复用、修正与提交 / Encounter deployment: reuse, correction and submission | [4.3.3](zh_cn/4-business-flows.md#feature-4-3-3) | [4.3.3](en_us/4-business-flows.md#feature-4-3-3) |
| 楼层礼物选择、到账与恢复 / Floor gifts: selection, receipts and recovery | [4.3.4](zh_cn/4-business-flows.md#feature-4-3-4) | [4.3.4](en_us/4-business-flows.md#feature-4-3-4) |
| 初始礼物、搜索与楼层主题 / Initial gifts, search and floor themes | [4.3.5](zh_cn/4-business-flows.md#feature-4-3-5) | [4.3.5](en_us/4-business-flows.md#feature-4-3-5) |
| 战斗配卡与真实进度 / Battle assignment and actual progress | [4.3.6](zh_cn/4-business-flows.md#feature-4-3-6) | [4.3.6](en_us/4-business-flows.md#feature-4-3-6) |
| 路线与事件是不同决策 / Routes and events are different decisions | [4.3.7](zh_cn/4-business-flows.md#feature-4-3-7) | [4.3.7](en_us/4-business-flows.md#feature-4-3-7) |
| 经验与纺锤共享的菜单链 / Shared Experience and Thread menu chain | [4.4.1](zh_cn/4-business-flows.md#feature-4-4-1) | [4.4.1](en_us/4-business-flows.md#feature-4-4-1) |
| 领奖与只记账恢复 / Payout and bookkeeping-only recovery | [4.6.1](zh_cn/4-business-flows.md#feature-4-6-1) | [4.6.1](en_us/4-business-flows.md#feature-4-6-1) |
| 未完成任务的真实边界 / Actual boundaries of unfinished tasks | [4.7.1](zh_cn/4-business-flows.md#feature-4-7-1) | [4.7.1](en_us/4-business-flows.md#feature-4-7-1) |
| 轮换政策与手动跳过 / Rotation policy and manual skip | [4.10](zh_cn/4-business-flows.md#feature-4-10) | [4.10](en_us/4-business-flows.md#feature-4-10) |
| 更新事务与失败回滚 / Update transaction and failure rollback | [6.4.5](zh_cn/6-deployment.md#feature-6-4-5) | [6.4.5](en_us/6-deployment.md#feature-6-4-5) |
| 发布包证据与私有数据隔离 / Package provenance and private-data exclusion | [6.7](zh_cn/6-deployment.md#feature-6-7) | [6.7](en_us/6-deployment.md#feature-6-7) |
| 学习数据的引用与复核关系 / Learning data references and review relationships | [5.5](zh_cn/5-state-and-data.md#feature-5-5) | [5.5](en_us/5-state-and-data.md#feature-5-5) |
| 购物与刷新分别结算 / Purchase and refresh settle separately | [4.3.8](zh_cn/4-business-flows.md#feature-4-3-8) | [4.3.8](en_us/4-business-flows.md#feature-4-3-8) |
| 冷启动、日志接口与授权恢复 / Cold launch, Journal and authorized recovery | [4.11](zh_cn/4-business-flows.md#feature-4-11) | [4.11](en_us/4-business-flows.md#feature-4-11) |
| 藏品目录滚动与地图手势归属 / Catalogue scroll and map gesture ownership | [4.12](zh_cn/4-business-flows.md#feature-4-12) | [4.12](en_us/4-business-flows.md#feature-4-12) |
| 战前预设、队伍绑定与顺序复用 / Presets, team binding and order reuse | [4.13](zh_cn/4-business-flows.md#feature-4-13) | [4.13](en_us/4-business-flows.md#feature-4-13) |
| 指定停页与零输入交还 / Requested page handoff before view inputs | [4.14](zh_cn/4-business-flows.md#feature-4-14) | [4.14](en_us/4-business-flows.md#feature-4-14) |
| 视口后继与坐标生命周期 / View successors and coordinate lifetime | [4.15](zh_cn/4-business-flows.md#feature-4-15) | [4.15](en_us/4-business-flows.md#feature-4-15) |
| 编队重置弹窗所有权与有界重开 / Deployment modal ownership and bounded reopening | [4.16](zh_cn/4-business-flows.md#feature-4-16) | [4.16](en_us/4-business-flows.md#feature-4-16) |
| 拦住的点击与相机返回 / Withheld map input and camera return | [4.17](zh_cn/4-business-flows.md#feature-4-17) | [4.17](en_us/4-business-flows.md#feature-4-17) |
| 有界公开参考源码缓存 / Bounded public source cache | [6.4.6](zh_cn/6-deployment.md#feature-6-4-6) | [6.4.6](en_us/6-deployment.md#feature-6-4-6) |
| 原生回调错误因果 / Native callback error cause | [9.3.13](zh_cn/9-execution-plan.md#feature-9-3-13) | [9.3.13](en_us/9-execution-plan.md#feature-9-3-13) |
| 图鉴、账户 box 与自动编队 / Catalogue, account box and automatic formation | [4.3.9](zh_cn/4-business-flows.md#feature-4-3-9) | [4.3.9](en_us/4-business-flows.md#feature-4-3-9) |
| 基线、分工与事实源 / Baseline, ownership and sources of truth | [9.1](zh_cn/9-execution-plan.md#feature-9-1) | [9.1](en_us/9-execution-plan.md#feature-9-1) |
| 看板卡、依赖与阶段出口 / Board cards, dependencies and phase exits | [9.2](zh_cn/9-execution-plan.md#feature-9-2) | [9.2](en_us/9-execution-plan.md#feature-9-2) |
| 失败自动恢复与显式运行次数 / Automatic recovery and the explicit run count | [9.3](zh_cn/9-execution-plan.md#feature-9-3) | [9.3](en_us/9-execution-plan.md#feature-9-3) |
| 学习与策略的架构边界 / Architecture boundary between learning and policy | [9.4](zh_cn/9-execution-plan.md#feature-9-4) | [9.4](en_us/9-execution-plan.md#feature-9-4) |
| 标签、评分与证据的数据模型 / Labels, scores and evidence data model | [9.5](zh_cn/9-execution-plan.md#feature-9-5) | [9.5](en_us/9-execution-plan.md#feature-9-5) |
| 资源监控的部署与接口 / Resource monitoring deployment and interface | [9.6](zh_cn/9-execution-plan.md#feature-9-6) | [9.6](en_us/9-execution-plan.md#feature-9-6) |
| 验收矩阵与回写纪律 / Acceptance matrix and write-back discipline | [9.7](zh_cn/9-execution-plan.md#feature-9-7) | [9.7](en_us/9-execution-plan.md#feature-9-7) |
| 正式运行时架构与唯一职责 / Normative runtime architecture and ownership | [2.6](zh_cn/2-architecture.md#feature-2-6) | [2.6](en_us/2-architecture.md#feature-2-6) |
| 统一动作协议与有界未知恢复 / Common action protocol and bounded unknown recovery | [3.10](zh_cn/3-runtime.md#feature-3-10) | [3.10](en_us/3-runtime.md#feature-3-10) |
| 页面身份预检与战斗读取 / Page-identity preflight and combat reads | [3.11](zh_cn/3-runtime.md#feature-3-11) | [3.11](en_us/3-runtime.md#feature-3-11) |
| 跨任务复用能力与领域约束 / Shared capabilities and domain constraints | [4.19](zh_cn/4-business-flows.md#feature-4-19) | [4.19](en_us/4-business-flows.md#feature-4-19) |
| 核心记录与语义适配 / Core records and semantic adapters | [5.6](zh_cn/5-state-and-data.md#feature-5-6) | [5.6](en_us/5-state-and-data.md#feature-5-6) |
| 证据容量、单份存储与安装边界 / Evidence capacity, single-copy storage and install boundary | [6.8](zh_cn/6-deployment.md#feature-6-8) | [6.8](en_us/6-deployment.md#feature-6-8) |
| 契约、整链与学习的独立验收 / Separate contract, whole-chain and learning acceptance | [7.4](zh_cn/7-quality.md#feature-7-4) | [7.4](en_us/7-quality.md#feature-7-4) |

| 输入前证据容量与崩溃恢复 / Pre-dispatch evidence capacity and crash recovery | [6.8.1](zh_cn/6-deployment.md#feature-6-8-1) | [6.8.1](en_us/6-deployment.md#feature-6-8-1) |
| 封存报告归档与引用不变性 / Closed-report archives and reference invariance | [6.8.2](zh_cn/6-deployment.md#feature-6-8-2) | [6.8.2](en_us/6-deployment.md#feature-6-8-2) |

| 精确字节与只读主页保留 / Exact bytes and input-free HOME retention | [6.8.3](zh_cn/6-deployment.md#feature-6-8-3) | [6.8.3](en_us/6-deployment.md#feature-6-8-3) |

| 导航学习的单份证据 / Single-copy navigation learning evidence | [6.8.4](zh_cn/6-deployment.md#feature-6-8-4) | [6.8.4](en_us/6-deployment.md#feature-6-8-4) |
| 诊断引用与已判断地图尝试 / Diagnostic roles and judged map attempts | [6.8.5](zh_cn/6-deployment.md#feature-6-8-5) | [6.8.5](en_us/6-deployment.md#feature-6-8-5) |

| 目标角色与地图恢复 / Target roles and map recovery | [4.20](zh_cn/4-business-flows.md#feature-4-20) | [4.20](en_us/4-business-flows.md#feature-4-20) |

新增功能或修复改变状态/交互时，审查对应局部图及双语段落；不能只改总览。Mermaid 解析通过只证明语法，覆盖索引只证明可找到说明，二者都不等于游戏 pipeline 通关。

When a feature or fix changes interactions/states, review its local diagram and paired prose, not only the overview. Mermaid parsing verifies syntax and this map verifies discoverability; neither proves a complete gameplay pipeline.


规范词典 / Canonical dictionary: [中文](zh_cn/1-overview.md#glossary) · [English](en_us/1-overview.md#glossary)。正式架构已接受，实施状态独立记录；原入口只作导航。

| 原生观察同帧绑定 / Native same-frame observation | [3.12](zh_cn/3-runtime.md#feature-3-12) | [3.12](en_us/3-runtime.md#feature-3-12) |
