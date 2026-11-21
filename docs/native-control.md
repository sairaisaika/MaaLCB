# 原生客户端与窗口控制

客户端使用 MaaEnd 同款 MXU 桌面界面，以 ProjectInterface 配置任务、队伍选项、
游戏语言和控制器。新增中文界面词条；游戏识别资源仍为英语和日语。
`assets/misc/Don-Quixote.png` 是本项目生成的小唐图标，通过 PI 的 `icon`
加载到窗口、标题栏、关于页和托盘，不修改 MXU 可执行文件。

## 参考实际实现

本次核对 MaaEnd 提交 `850e5fa026cd5daebe74ef73ddb265cdc7b55d21` 的
[PI 控制配置](https://github.com/MaaEnd/MaaEnd/blob/850e5fa026cd5daebe74ef73ddb265cdc7b55d21/assets/interface.json)：

| 本项目控制器 | Maa 截图 | Maa 鼠标 | Maa 键盘 |
| --- | --- | --- | --- |
| windows-window（默认） | Background | SendMessageWithCursorPos | PostMessage |
| windows-background | Background | SendMessageWithWindowPos | PostMessage |
| windows（保留旧名称） | ScreenDC | Seize | Seize |

三种组合与 MaaEnd 相同，保留已有 `windows` 配置名称；CLI 从同一 PI 文件
读取控制参数，不再硬编码前台方式。GUI 已由 MXU 读取这些设置。
Lix `431b432e22f0b0da08b95d7c478fa213be20b3e8` 的
`lalc_backend/input/input_handler.py` 默认后台状态，鼠标/键盘使用窗口消息；
`update_to.bat` 也包含标准 RunAs 启动。没有引入它的控制器或 BlockInput。

MaaEnd 三种 Win32 控制器均设置 `permission_required: true`。
MXU 在任务启动时处理正常的 Windows 管理员启动，不需要另外通过聊天选择题批准。
项目不会自动重试先前已取消的 UAC，也不绕过 Windows 的输入隔离。

<a id="unattended-start"></a>

## 无人值守启动：模拟器、游戏、任务

从开机到进游戏分三段，每段各管一件事，做法对照 MaaEnd：

| 段 | 谁来做 | 说明 |
| --- | --- | --- |
| 启动 MaaLimbus 并自动开始 | MXU 自带设置 | 「开机自启动」会建一个登录时运行的计划任务；「启动后自动执行」指定要跑的配置。这两项是 MXU 的设置，不在本项目的任务里。 |
| 启动模拟器 | 预任务 `launch_emulator` | MXU 在连接 ADB 设备**之前**运行它。它启动你填的模拟器程序，然后等模拟器的 ADB 地址能连上；模拟器已经在运行就什么都不做。 |
| 启动游戏 | 任务「打开游戏」 | 连接之后由 MaaFramework 启动游戏并独立确认前台。游戏已经在前台时不重复启动；启动后一直没到前台，就关闭游戏再启动一次，只修一次。 |

预任务的四个设置：模拟器程序的完整路径、启动参数（用来选实例）、ADB 地址（要和 MXU 连接的地址一致，只接受本机地址）、最长等待秒数（10–600，默认 180）。程序路径留空表示模拟器由你自己打开，这时地址连不上会直接说明原因，不会去猜模拟器装在哪里。

MXU 在预任务之后不会再等设备出现，所以等待是预任务自己做的：每秒试一次连接，连上后再等 5 秒。它判断的是 ADB 端口能连上，不是安卓已经开机完成；之后的「打开游戏」任务会等到游戏真正在前台。预任务的结论用退出码表示（0 通过，1 未通过），并打印原因，例如 `emulator_program_not_configured`、`emulator_not_reachable`。MXU v2.7.1 对预任务失败只记一条警告并继续，接下来连接设备会失败并停下。

可以不经过 MXU 单独试预任务：

```powershell
python agent/main.py --pretask launch_emulator '{"launch_emulator": {"program": "", "arguments": "", "address": "127.0.0.1:16384", "wait_seconds": "60"}}'
```

打包后的应用里，同一个预任务由 `agent/MaaLimbusAgent.exe --pretask launch_emulator` 执行。

## 实机证据边界

窗口消息是否被 Limbus 接受，必须以操作后的实际页面变化证明；不能由枚举解析
或后台方式的名称推断。最新只读检查记录在 `build/control-reference-preflight.json`：
游戏 PID 40196 / HIGH 12288，检查进程 MEDIUM 8192；游戏最小化且客户区 0×0。
FramePool/Background 原生截图失败，日志同时保留访问拒绝与零尺寸错误；
不单独把截图失败全部归因于权限。未发送游戏输入，未验证实机导航/战斗。

只读检查使用 Null 鼠标与键盘、单控制器锁和有限等待：

```powershell
python tools/probe_win32.py --binary <Maa目录> --capture Background
```

完整困难镜牢五层、领奖和换队循环尚未接通，不将本次界面配置或回放写作通关。
