<!-- markdownlint-disable MD033 MD041 -->
<p align="center">
  <img alt="LOGO" src="./assets/misc/Don-Quixote.png" width="256" height="256" />
</p>

<div align="center">

# MaaLimbus

<!-- markdownlint-disable-next-line MD036 -->
_✨ MAA assistant for Limbus Company ✨_

[![Pipeline](https://img.shields.io/badge/Pipeline-%23876f69?logo=paddypower&logoColor=%23FFFFFF)](https://github.com/MaaXYZ/MaaFramework)
[![Python](https://img.shields.io/badge/Python-3.11-3776AB?logo=python&logoColor=white)](https://github.com/sairaisaika/MaaLCB/tree/main/agent)
[![license](https://img.shields.io/github/license/sairaisaika/MaaLCB)](https://github.com/sairaisaika/MaaLCB/blob/main/LICENSE)
[![platform](https://img.shields.io/badge/platform-Windows-blueviolet)](https://github.com/sairaisaika/MaaLCB/releases)
[![tests](https://img.shields.io/github/actions/workflow/status/sairaisaika/MaaLCB/tests.yml?label=tests)](https://github.com/sairaisaika/MaaLCB/actions/workflows/tests.yml)
[![release](https://img.shields.io/github/v/release/sairaisaika/MaaLCB?include_prereleases&label=release)](https://github.com/sairaisaika/MaaLCB/releases)
[![stars](https://img.shields.io/github/stars/sairaisaika/MaaLCB?style=flat)](https://github.com/sairaisaika/MaaLCB/stargazers)
[![commit activity](https://img.shields.io/github/commit-activity/m/sairaisaika/MaaLCB)](https://github.com/sairaisaika/MaaLCB/commits/main)

Powered by [MaaFramework](https://github.com/MaaXYZ/MaaFramework) & [MXU](https://github.com/MistEO/MXU)

In development; pre-releases only.

[简体中文](README.md) | [English](README_en.md) | [Engineering wiki](docs/wiki/README.md) | [Live acceptance records](docs/acceptance.md)

</div>

## 📖 Before you use it

MaaLimbus automates Limbus Company by reading the screen. Today it targets the Mirror Dungeon on **Windows + the MuMu emulator + the English game client**.

- **It is in development, not a stable release.** A Mirror Dungeon run is not yet guaranteed to finish from one Start without stopping; when the program is unsure it stops and says why instead of clicking on. See "Current status" below.
- **Neither the repository nor the release package contains game assets.** Game art belongs to its rights holder. You supply the recognition images on your own machine, as described in [local game assets](docs/local-assets.md); without them a task stops before sending any input and names the missing group.
- Problems are welcome as [issues](https://github.com/sairaisaika/MaaLCB/issues). Include the app version, the stop reason from the log and redacted screenshots; do not upload game assets or files with account information.

## ✨ Features

- 🪞 **Mirror Dungeon**: enters from the lobby and handles starlight graces, starting gifts, theme packs, map nodes, battles, events, the shop and floor gifts until five floors are cleared.
- ⚔️ **Battles**: uses the game's own win-rate or damage auto-assignment, starts the turn and switches on the speed toggle.
- 🛒 **Shop**: buys gifts for the team's systems, with a bounded number of refreshes and a coin reserve; each purchase is recorded before the click and checked against coins and shelf afterwards.
- 🎁 **Claim rewards after a clear**: one switch, claim or not. A claim checks the offer on the reward page, never clicks "Give Up Rewards" and never changes the weekly-bonus switches.
- 🔁 **Several runs and team rotation**: one Start can play several runs, with one team or a rotation queue.
- 🗓️ **Mirror schedule** (not yet accepted on a live run): choose which days to play and how many runs a day; once the day's runs are done another Start ends at once. With MXU's own scheduled execution this hosts the app unattended.
- 👥 **Mirror team settings**: two per team. Gift systems are ticked freely, one, several or all, and none at all lets the program choose freely; the deployment order best follows the order set in the game (the program records the order it read together with its screenshot, so you can check it), or it can be written out in full.
- 🧾 **Resumes where it stopped**: shop, deployment and payout record their intent before they act, so after a stop or a closed game the next Start continues from the unfinished step.
- 📝 **A log you can read**: every step names the page it recognised and what it did; a stop states its reason.
- 📊 **Run data**: one row per finished task (time per floor, waits and re-reads, stop reason); `tools/run_report.py --history` turns the rows into a trend, with no account or local path in them.
- 🧹 **Tidies its own screenshots**: at the end of a task old diagnostic frames are moved to an archive folder, without manual cleanup and without deleting.
- 🚧 **In development**: the experience and thread dungeons only reach their entry page (labelled "in development" in the app); the Japanese client and Windows-client input are not accepted yet (labelled "experimental" and "not accepted yet"). Stamina exchange, skill replacement in the shop and in-app updates have no real function yet; their entries were taken out of the interface and return when there is something behind them.

## 🚦 Current status

Stated plainly, so you can decide whether to use it now:

- The whole chain "five floors cleared → rewards claimed → booked → next run started" has been completed on a live rig, but with several stops along the way that were fixed and resumed.
- It is slow: the latest unbroken floor 1 took about 24 minutes; the target is 10 minutes a floor.
- About 5,000 public tests pass in a clean environment without game assets; tests that need local assets or real game frames skip with a stated reason.
- Scope and versions of what was accepted are in the [acceptance records](docs/acceptance.md); goals and progress in [Wiki chapter 9](docs/wiki/en_us/9-execution-plan.md#public-goal).

## 🍽️ Getting started

1. Download the desktop package of a [pre-release](https://github.com/sairaisaika/MaaLCB/releases), or build it yourself as in the developer guide below. Pre-release packages are unsigned, so Windows may show a security prompt; check the download with the package's `SHA256SUMS`.
2. Prepare the recognition images on your machine as in [local game assets](docs/local-assets.md).
3. Open `MaaLimbus.exe`, open Limbus Company in MuMu, and choose the device and game language in the connection settings.
4. Add and tick the Mirror task, check the team, the rotation and "Claim rewards after a clear", and press Start.

What each setting means: [task settings](docs/task-settings.md). Connection and permissions: [native control](docs/native-control.md).

## 📦 What this repository has and does not have

| Has | Does not have |
| --- | --- |
| Source, Pipeline, language resources, design documents and a bilingual Wiki | Game assets: no icon, recognition template or game screenshot |
| OCR models (MaaCommonAssets, MIT; PaddleOCR, Apache-2.0) | A stable desktop release: pre-releases only |
| Public tests on synthetic material, an [example configuration](docs/examples/config/README.md), a dependency lock file | Anyone's account configuration, run screenshots or run records |

## 🛠️ Developer guide

New to the code? Read [CONTRIBUTING.md](CONTRIBUTING.md) first: how to get it running, where things live, and what is hard to change today. Find code by question with `tools/wiki_route.py`; details are in the [engineering wiki](docs/wiki/README.md).

You need Windows 10/11 x64, Git and Python 3.11 (the version CI and the lock file use).

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

Verify the installation:

```powershell
.venv\Scripts\python tools/check_wiki.py
```

```powershell
.venv\Scripts\python tools/run_tests.py -q
```

```powershell
.venv\Scripts\python tools/check_local_assets.py
```

- The first should end with `ok — 0 problem(s)`.
- The second should exit with 0; the whole suite takes about 10 minutes. Tests that need local files or real game frames skip one by one and name the missing file; a skip is not a pass, it only means this machine cannot verify it.
- The third exits with 2 on a new checkout and lists the missing asset groups. That is the expected result: missing assets are reported explicitly.

Find code by question:

```powershell
.venv\Scripts\python tools/wiki_route.py "shop purchase receipt"
```

Build the Python source package and wheel:

```powershell
.venv\Scripts\python -m build --outdir build/python-package
```

The Windows desktop application is assembled by `tools/build_windows_package.py` from MXU and MaaFramework archives you download yourself; the tool checks its inputs against the hashes recorded in [Windows package](docs/windows-package.md) and downloads nothing. A release package takes committed files only and refuses to export when game assets are present.

| Path | Contents |
| --- | --- |
| `src/maalimbus/` | Screen reading, task decisions, transactions and run state |
| `agent/` | The MaaFramework Agent entry and native observation |
| `assets/` | ProjectInterface, Pipeline, language resources, OCR models and the local asset manifest |
| `desktop/mxu/` | MXU desktop adaptation |
| `tools/`, `tests/` | Build and diagnostic tools, public regression tests |
| `docs/` | Design, acceptance and the bilingual engineering Wiki |

Before creating a file or handling storage, read the Wiki's [file placement table](docs/wiki/README.md#file-placement).

## 🙏 Acknowledgements

- [MaaFramework](https://github.com/MaaXYZ/MaaFramework): the recognition and control framework.
- [MXU](https://github.com/MistEO/MXU): the desktop GUI.
- [MaaCommonAssets](https://github.com/MaaXYZ/MaaCommonAssets) and [PaddleOCR](https://github.com/PaddlePaddle/PaddleOCR): the OCR models.
- [MaaEnd](https://github.com/MaaEnd/MaaEnd), [M9A](https://github.com/MAA1999/M9A) and other MAA ecosystem projects: references for hosting and for this page's structure.

## 📄 License

Released under [AGPL-3.0-or-later](LICENSE). Licences of dependencies and data sources are in [THIRD_PARTY_NOTICES](THIRD_PARTY_NOTICES/). Game assets belong to their rights holder and are not in this repository. This project is not affiliated with the game's developer or publisher.
