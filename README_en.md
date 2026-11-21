# MaaLimbus

[简体中文](README.md) · [Engineering wiki](docs/wiki/README.md) · [Live acceptance records](docs/acceptance.md)

MaaLimbus is a Windows automation project for Limbus Company. The desktop app uses MXU and ProjectInterface V2. A Python Agent identifies game screens and executes tasks through MaaFramework.

## What this repository has, and what it does not

| It has | It does not have |
| --- | --- |
| Source code, pipelines, language resources, design documents and a bilingual wiki | Game assets: not one icon, recognition template or game screenshot |
| OCR models (MaaCommonAssets, MIT; PaddleOCR, Apache-2.0) | A prebuilt Windows desktop package |
| Public tests that use synthetic material only, [example configuration](docs/examples/config/README.md) and a dependency lock file | Anyone's account configuration, captures or run records |

The game's artwork belongs to its rights holder and this project cannot establish that it may be redistributed. The 360 bitmaps Mirror Dungeon automation matches against are supplied by you on your own machine; see [local game assets](docs/local-assets.md). Without them you can install, run the tests and build the source package. A Mirror Dungeon task stops before it sends any input and names the missing group.

## Install

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

## Verify the installation

```powershell
.venv\Scripts\python tools/check_wiki.py
```

```powershell
.venv\Scripts\python tools/run_tests.py -q
```

```powershell
.venv\Scripts\python tools/check_local_assets.py
```

- The first ends with `ok — 0 problem(s)`.
- The second exits with status 0. Tests that need local files or real game imagery are skipped one by one, each naming the file it lacks. A skip is not a pass: it only says this machine cannot verify that case.
- The third exits with status 2 on a fresh checkout and lists the seven missing asset groups. That is the expected result: a missing asset is reported, not papered over.

## Configure

In the desktop app, MXU writes settings into the git-ignored `config/` directory. The [example configuration](docs/examples/config/README.md) shows the file format with synthetic data. See [task settings](docs/task-settings.md) for the task and team options and [native controller setup](docs/native-control.md) for connection and permissions.

## Build

Python source package and wheel:

```powershell
.venv\Scripts\python -m build --outdir build/python-package
```

The Windows desktop app is assembled by `tools/build_windows_package.py` from MXU and MaaFramework archives you download yourself; the tool checks its inputs against the hashes recorded in [Windows package](docs/windows-package.md) and downloads nothing. A release package takes committed files only and is refused when it carries game assets. This path has been built once from a fresh clone with no private directory and no game asset: the package carries no game asset, its manifest verifies, and the packaged Agent self-test names the missing asset groups. This repository publishes no prebuilt desktop package. Keep the build folder at a short path, or the packaged Agent stops because its socket path is too long.

## Run Mirror Dungeon

Supply the [local game assets](docs/local-assets.md) and build the desktop app first.

1. Open `dist/MaaLimbus/MaaLimbus.exe`.
2. Open Limbus Company in MuMu. In MXU connection settings, select the matching device and game language.
3. Enable the Mirror Dungeon task. Review its saved team, rotation and spending settings, then click **Start**. Check the last result and pending transactions before resuming an interrupted run.

If the task stops, check the MXU log and the stop reason in the result. A useful issue report includes the app version, the stop reason and relevant redacted screenshots; do not upload game assets or files that carry account data.

## Verified scope

- English Mirror Dungeon on MuMu has separate live records for Hard floor five, payout and team rotation, made on the maintainer's machine with the assets in place. See [acceptance records](docs/acceptance.md) for the versions and scope.
- What has been verified on a public checkout is installation, the wiki guard, the public tests and the Python package build. The desktop release package has also been built and inspected once from a fresh clone. The whole live flow after importing assets as [local game assets](docs/local-assets.md) describes has not been re-verified by a third party on a public checkout.
- The shop buys gifts using the saved team strategy and supports bounded refreshes and receipt reconciliation. Automated skill purchases are in development. A continuous full run on the latest build, Japanese gameplay and Windows game input have separate acceptance paths.
- MXU lists additional task entry points. See [design and task options](docs/design.md) for their implementation status.

## Repository layout

| Path | Contents |
| --- | --- |
| `src/maalimbus/` | Recognition, task decisions, transactions and run state |
| `agent/` | MaaFramework Agent entry and native observation |
| `assets/` | ProjectInterface, pipelines, language resources, OCR models and the local asset manifest |
| `desktop/mxu/` | MXU desktop integration |
| `tools/`, `tests/` | Builds, diagnostic tools and public regression tests |
| `docs/` | Design, acceptance records and the bilingual engineering wiki |

Before creating a file or handling storage, read the wiki's [file placement table](docs/wiki/README.md#file-placement): it says where design, development, local and release content goes, who owns it and how long it is kept.

## Development

```powershell
.venv\Scripts\python tools/wiki_route.py "shop purchase receipt"
```

Start feature lookup from the quick index of the [engineering wiki](docs/wiki/README.md). Always run tests through `tools/run_tests.py`, which returns pytest's own exit status.

## Licence

MaaLimbus is licensed under [AGPL-3.0-or-later](LICENSE). See [third-party notices](THIRD_PARTY_NOTICES/) for the licences of dependencies and data sources. Game artwork belongs to its rights holder and is not in this repository.
