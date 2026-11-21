# 示例配置 / Example configuration

这两份文件是合成的示例，不是任何人的账号数据。它们展示私有配置目录 `config/` 里两份
文件的格式；`config/` 整个被 Git 忽略，真实配置只留在你的机器上。

These two files are synthetic examples, not anyone's account data. They show the format
of two files in the private `config/` directory, which Git ignores entirely; your real
configuration stays on your machine.

| 文件 / File | 内容 / Contents | 读取它的代码 / Loaded by |
| --- | --- | --- |
| `user-team-profiles.json` | 保存队伍：游戏内队伍槽位、出战顺序、流派关键词 / saved teams: in-game team slot, deployment order, keyword systems | `ProfileStore` in `src/maalimbus/storage.py` |
| `user-task-settings.json` | 镜牢难度、单队或轮换，以及经验本、纺锤本默认队伍 / Mirror difficulty, single team or rotation, luxcavation default teams | `TaskPreferences` in `src/maalimbus/task_preferences.py` |

桌面应用里这些设置由 MXU 的界面写入，一般不需要手改。要从示例起步，把两份文件复制到
`config/` 再按自己的队伍修改；`slot` 必须是你游戏里真实存在的保存队伍槽位（1–40）。

In the desktop app MXU writes these settings from its own UI, so hand editing is rarely
needed. To start from the examples, copy both files into `config/` and edit them for
your teams; `slot` must be a saved team slot that really exists in your game (1–40).

`tests/test_example_config.py` 用上面两个加载器读取这两份示例，格式变了测试会失败。

`tests/test_example_config.py` reads both examples through the two loaders above, so the
test fails when the format changes.
