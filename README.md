# ahk-alt-layer

我的 Windows 快捷键配置，使用 AutoHotkey v2。用 Alt + WASD 移动光标，用左 Alt 调出数字键，用右 Alt 组合键连续退格。脚本也处理了 Edge 和 ChatGPT 桌面端的 Alt 菜单误触。

## 运行

1. 在 Windows 上安装 [AutoHotkey v2](https://github.com/AutoHotkey/AutoHotkey/releases)。
2. 下载 [移动.ahk](./%E7%A7%BB%E5%8A%A8.ahk)，双击运行。
3. 要暂停快捷键或退出脚本，右键点击系统托盘里的 AutoHotkey 图标，选择 `Suspend Hotkeys` 或 `Exit`。

## 快捷键

表中的 `Alt` 表示左 Alt 或右 Alt。标明左右的组合使用对应一侧的键。

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

## 应用专属行为

- **Microsoft Edge**（`msedge.exe`）屏蔽 `Alt + F`，并抑制单按 Alt 时的菜单激活。
- **ChatGPT 桌面端**（`ChatGPT.exe`）拦截左、右 Alt 的按下和松开事件，避免进入菜单访问键模式。

## 自定义

在文本编辑器里打开 `移动.ahk` 即可修改映射。`!` 表示 Alt，`+` 表示 Shift，`>!` 表示右 Alt。应用专属规则写在各自的 `#HotIf WinActive(...)` 区块里。保存后，在系统托盘菜单选择 `Reload Script` 使改动生效。
