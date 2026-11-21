# Home Row Pilot｜手留在主键区

一套为盲打设计的 Windows 键盘工具。按住 `Alt`，用 `WASD` 移动文本光标，也能选字、输入数字和退格。按住 `CapsLock`，用 `IJKL` 移动鼠标指针，还能点击、拖拽和滚动。编辑文字和操作界面时，手都可以留在主键区附近。

## 快速开始

两个脚本各自独立运行。

- **文本导航与编辑** · 安装 [AutoHotkey v2](https://github.com/AutoHotkey/AutoHotkey/releases)，下载并双击 [my-hotkey.ahk](./my-hotkey.ahk)。从系统托盘的 AutoHotkey 菜单可以暂停（`Suspend Hotkeys`）或退出（`Exit`）。
- **键盘鼠标** · 安装 Python（可用 3.13），下载 [keyboard_trackpad.py](./keyboard_trackpad.py)，在文件所在目录运行下方命令。脚本只用 Python 标准库和 Windows 自带的 API，无需安装第三方包。

```powershell
py keyboard_trackpad.py
```

## Alt 层 · 文本导航与编辑

未标明左右的 `Alt` 组合可以用任一侧的 Alt 键。

### 导航与选区

| 按键 | 动作 |
| --- | --- |
| `Alt + W / A / S / D` | 上 / 左 / 下 / 右 |
| `Shift + Alt + W / A / S / D` | 向对应方向扩展选区 |
| `右 Alt + ,` / `右 Alt + .` | `Home` / `End` |
| `Shift + Alt + ,` / `Shift + Alt + .` | `Shift + Home` / `Shift + End` |

### 左 Alt 数字层

按住左 Alt，再按下表中的键。数字层要求右 Alt、Ctrl、Shift 和 Win 都处于松开状态。

| 按键 | 输出 |
| --- | --- |
| `U` / `I` / `O` | `1` / `2` / `3` |
| `J` / `K` / `L` | `4` / `5` / `6` |
| `M` / `,` / `.` | `7` / `8` / `9` |
| `N` / `/` | `0` / `.` |

数字层还给 `W` 和 `S` 定义了 `^` 和 `_`，这两组按键与导航绑定重叠。按常规 Alt 组合识别时，`Alt + W` 和 `Alt + S` 的方向键绑定优先。

### 编辑与输入

| 按键 | 动作 |
| --- | --- |
| `Alt + Space` | 发送 `Ctrl + Space` |
| `Alt + E` | 发送 `Enter`，用于确认或发送 |
| `Shift + Alt + E` | 发送 `Shift + Enter`，用于支持该组合的应用内换行 |
| `Alt + Backspace` | 发送普通 `Backspace`，避免触发撤销 |
| 按住右 Alt，再按左 Alt | 按下时退格一次，长按约 0.3 秒后每 60 毫秒连发 |
| 按住右 Alt，再按左 Win | 按下时退格一次，长按约 0.3 秒后每 30 毫秒连发 |

连发会在松开任一组合键后停止，每次按住最多连发到触发后的约 3 秒。

### 应用专属行为

- **Microsoft Edge**（`msedge.exe`）屏蔽 `Alt + F`，并抑制单按 Alt 时的菜单激活。
- **ChatGPT 桌面端**（`ChatGPT.exe`）拦截左、右 Alt 的按下和松开事件，避免进入菜单访问键模式。

## CapsLock 层 · 键盘鼠标

先按住 `CapsLock`，再按下表中的键。松开 `CapsLock` 即退出鼠标模式，回到正常输入。方向键按标准 QWERTY 的物理键位识别。

| 按键 | 动作 |
| --- | --- |
| `I` / `J` / `K` / `L` | 向上 / 左 / 下 / 右移动鼠标指针。点按小幅移动，长按持续加速 |
| `Space` | 鼠标左键。按住并移动指针可拖拽 |
| `右 Alt` | 鼠标右键 |
| `Tab` + `I/J/K/L` | 按住 `Tab`，将方向键切换为相应方向的纵向或横向滚动 |
| `左 Shift` + `I/J/K/L` | 按住左 Shift，以更小步长和更低速度移动指针 |
| `Esc` | 退出脚本，也可以在终端按 `Ctrl + C` |

需要切换大小写锁定时，先按住左 `Shift`，再点按 `CapsLock`。

## 自定义

- **文本导航** · 在 `my-hotkey.ahk` 中修改按键映射。`!` 表示 Alt，`+` 表示 Shift，`>!` 表示右 Alt。应用专属规则写在各自的 `#HotIf WinActive(...)` 区块里。保存后，在系统托盘菜单选择 `Reload Script`。
- **键盘鼠标** · 在 `keyboard_trackpad.py` 顶部调整点按步长、长按速度、加速和滚轮灵敏度。脚本默认会在进入鼠标模式时尝试退出当前文本输入状态。将 `EXIT_INPUT_ON_CAPS` 改为 `False` 可关闭这个行为。保存后重启脚本。
