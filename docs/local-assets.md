# 本地游戏素材 / Local game assets

[English below](#english)

这个仓库不带任何游戏画面：没有图标、识别模板，也没有游戏截图。游戏美术归其权利方所有，
本项目无法确认可以再分发，所以这些文件不进 Git、不进发行包，也不进 CI。镜牢自动化
需要的 360 张位图由你在自己的机器上提供。

没有素材时仍然可以安装、跑公开测试、构建源码包；镜牢任务会在发出任何输入之前停下，
并说明缺哪一组。工具只读本机文件，不下载、不上传，也不会用占位图冒充。

## 先看缺什么

```powershell
python tools/check_local_assets.py
```

退出码 0 表示七组都齐全，2 表示至少一组缺文件或内容不对。清单在
[`assets/resource/base/local-assets.json`](../assets/resource/base/local-assets.json)，
每一行记着用途、参考位图的 SHA-256 和像素尺寸。

| 组 | 数量 | 用在哪里 | 怎么提供 |
| --- | --- | --- | --- |
| `gifts` | 332 | 饰品选择、奖励与商店页的饰品图标识别 | 从你自己克隆的 Lix 参考仓复制 |
| `themes` | 5 | 主题包页的固定小图标 | 同上 |
| `battle` | 4 | 战斗界面的胜率与技能属性小图标 | 同上 |
| `navigation` | 10 | 队伍、人格详情、教程与星光页的返回箭头和勾选框 | 从你自己的截图裁切 |
| `reward` | 4 | 领奖页的付费 Claim 费用读取 | 同上 |
| `event` | 4 | 事件页判定概率字样 | 同上 |
| `map` | 1 | 楼层地图节点下方的徽记 | 同上 |

## 一、来自 Lix 参考仓的 341 张

这些是 [LixAssistantLimbusCompany](https://github.com/HSLix/LixAssistantLimbusCompany)
在提交 `431b432e22f0b0da08b95d7c478fa213be20b3e8` 上的原文件。由你自己克隆到被 Git 忽略的
`sources/upstream/`，本项目的工具不会替你克隆：

```powershell
git clone https://github.com/HSLix/LixAssistantLimbusCompany sources/upstream/LixAssistantLimbusCompany
```

```powershell
git -C sources/upstream/LixAssistantLimbusCompany checkout 431b432e22f0b0da08b95d7c478fa213be20b3e8
```

```powershell
python tools/import_lix_assets.py
```

每个文件先按清单里的 SHA-256 核对再写入；版本不对或文件被改过会被拒绝并点名。目录文件
（`gift-catalog.json` 等）不会被改写。这些图是否可以使用和保存，由你按该仓的许可和游戏
权利方的条款自行判断。

## 二、从你自己的截图裁切的 19 张

这些是游戏页面上的小块界面元素。清单里记了像素尺寸；其中 10 张还记了在 1920×1080 截图上
的裁切矩形，可以直接裁：

```powershell
python tools/import_local_templates.py --frame 你的截图.png --template image/navigation/tutorial-back.png
```

另外 9 张（`event` 的 4 张、`map` 的 1 张，以及 `navigation` 里的
`star-convert-unchecked-current`、`team-library-back`、`theme-card-clip`、`tutorial_next`）
当初没有留下裁切矩形。需要你按清单里的尺寸手工裁好，再交给工具做尺寸检查和重新编码：

```powershell
python tools/import_local_templates.py --bitmap 你裁好的图.png --template image/event/odds_high.png
```

工具写出的文件是重新编码的，不带原图的元数据。自己裁的图内容必然和参考位图不同，
`check_local_assets.py` 只核对尺寸，并把它们计为「own captures」。裁切位置是否正确，
只有实机运行才能证明。

## 三、桌面端队伍编辑器的 22 张头像

只在自己构建 MXU 桌面端时需要。队伍编辑器显示 12 张罪人头像和 10 张星光卡，它们同样来自
上面的 Lix 参考仓。备好参考仓之后运行：

```powershell
python tools/export_team_editor_artwork.py
```

它会在本机生成被 Git 忽略的 `desktop/mxu/teamArtwork.ts`。没有这个文件时，
`tools/patch_mxu_client.py` 会停下并说明原因，不会用空白图代替。

## 测试与发行包

- 公开测试不依赖这些素材。需要真实游戏画面的测试用 `needs_local` 标记声明所需文件，
  缺的时候逐条跳过并写出文件名，不算通过。
- 这些路径在 `.gitignore` 里逐条列出，但忽略规则不是隐私边界：不要把游戏素材、
  截图或带账号信息的文件放进提交、Issue、PR 或发行包。
- 发行包只从已提交的文件构建，导出前还会检查包目录，带着游戏素材就拒绝导出，
  见 [Windows 开发包](windows-package.md)。本机用 `tools/make_local_app.py` 组装的应用会带上
  你导入的素材，只供本机使用，不要分发。
- 打包后的应用用 `MaaLimbusAgent.exe --local-assets-check` 查看缺哪几组；素材放在应用目录的
  `assets/resource/base/image/` 下，可以在源码 checkout 里导入后整目录复制过去。

<a id="english"></a>

## English

This repository carries no game imagery: no icons, no recognition templates and no
screenshots. The game's artwork belongs to its rights holder and this project cannot
establish that it may be redistributed, so those files stay out of Git, out of release
packages and out of CI. The 360 bitmaps that Mirror Dungeon automation matches against
are supplied by you, on your own machine.

Without them you can still install the project, run the public tests and build the
source package. A Mirror Dungeon task stops before it sends any input and names the
missing group. The tools read local files only: they do not download, upload, or
substitute a placeholder for a missing bitmap.

### See what is missing

```powershell
python tools/check_local_assets.py
```

Exit status 0 means all seven groups are complete; 2 means at least one group has a
missing or invalid file. The manifest is
[`assets/resource/base/local-assets.json`](../assets/resource/base/local-assets.json):
each row records the purpose, the reference bitmap's SHA-256 and its pixel size.

| Group | Files | Used for | How to supply |
| --- | --- | --- | --- |
| `gifts` | 332 | gift icon identification on gift choice, reward and shop pages | copy from your own clone of the Lix reference project |
| `themes` | 5 | fixed glyphs of the theme pack page | same |
| `battle` | 4 | win-rate and skill-type glyphs of the battle HUD | same |
| `navigation` | 10 | back arrows and checkbox states on team, identity, tutorial and star pages | crop from your own screenshots |
| `reward` | 4 | reading the paid Claim cost on the run reward page | same |
| `event` | 4 | skill-check odds captions on event pages | same |
| `map` | 1 | the badge under each floor map node | same |

### 1. The 341 files from the Lix reference project

They are unmodified files of
[LixAssistantLimbusCompany](https://github.com/HSLix/LixAssistantLimbusCompany) at commit
`431b432e22f0b0da08b95d7c478fa213be20b3e8`. Clone it yourself into the git-ignored
`sources/upstream/` directory (the three commands above); this project's tools never
clone for you. `python tools/import_lix_assets.py` checks every file against the
recorded SHA-256 before writing it, refuses and names a file from another revision, and
does not rewrite the catalogs. Whether you may use and keep these images is yours to
judge under that project's licence and the game rights holder's terms.

### 2. The 19 crops from your own screenshots

They are small interface elements of game pages. The manifest records each pixel size;
for 10 of them it also records the rectangle on a 1920×1080 screenshot, so
`tools/import_local_templates.py --frame SHOT.png --template <manifest path>` cuts them
directly. The other 9 (the four `event` files, the `map` file, and
`star-convert-unchecked-current`, `team-library-back`, `theme-card-clip` and
`tutorial_next` under `navigation`) have no recorded rectangle: cut them by hand at the
listed size and pass `--bitmap CROP.png --template <manifest path>`.

The output is re-encoded and carries none of the source file's metadata. Your own crops
necessarily differ from the reference bitmaps, so `check_local_assets.py` checks only
their size and counts them as own captures. Only a live run proves a crop is right.

### 3. The 22 portraits of the desktop team editor

Needed only when you build the MXU desktop client yourself. The team editor shows 12
sinner portraits and 10 star cards, which also come from the Lix reference project. With
the reference checkout in place, `python tools/export_team_editor_artwork.py` generates
the git-ignored `desktop/mxu/teamArtwork.ts` on your machine. Without that file
`tools/patch_mxu_client.py` stops and says why; it does not substitute blank images.

### Tests and release packages

- The public tests do not need these files. A test that needs real game imagery
  declares the files with the `needs_local` marker and is skipped one by one, naming
  what is missing. A skip is not a pass.
- These paths are listed one by one in `.gitignore`, but an ignore rule is not a privacy
  boundary: keep game assets, screenshots and anything carrying account data out of
  commits, issues, pull requests and release packages.
- A release package is built from committed files only, and the export checks the
  package folder once more and refuses it when it carries game artwork; see
  [Windows package](windows-package.md). An app assembled locally with
  `tools/make_local_app.py` does carry the assets you imported: it is for this machine
  only and must not be redistributed.
- In a packaged app, `MaaLimbusAgent.exe --local-assets-check` reports the missing
  groups. The bitmaps live under `assets/resource/base/image/` of the app folder; import
  them in a source checkout and copy that directory over.
