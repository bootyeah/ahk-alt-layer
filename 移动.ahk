#Requires AutoHotkey v2.0
; 提高脚本优先级和响应速度
ProcessSetPriority "High"
SetKeyDelay -1
; 保留键盘钩子，避免模拟按键时漏掉物理松开事件。
SendMode "Event"

; 全局防干扰掩码（针对 AHK 自身的组合键模拟）
A_MenuMaskKey := "vk07"

; ============================
; 1. 基础导航区 (WASD + Home/End)
; ============================
$!w::Send "{Up}"
$+!w::Send "+{Up}"

$!s::Send "{Down}"
$+!s::Send "+{Down}"

$!a::Send "{Left}"
$+!a::Send "+{Left}"

$!d::Send "{Right}"
$+!d::Send "+{Right}"

$>!,::Send "{Home}"
$+!,::Send "+{Home}"

$>!.::Send "{End}"
$+!.::Send "+{End}" 

; ============================
; 左 Alt 数字层（右 Alt + 逗号/句号用于 Home/End）
; ============================
#HotIf GetKeyState("LAlt", "P") && !GetKeyState("RAlt", "P")
    && !GetKeyState("Ctrl", "P") && !GetKeyState("Shift", "P")
    && !GetKeyState("LWin", "P") && !GetKeyState("RWin", "P")
*u::Send "1"
*i::Send "2"
*o::Send "3"

*j::Send "4"
*k::Send "5"
*l::Send "6"

*n::Send "0"
*m::Send "7"
*,::Send "8"
*.::Send "9"
*/::Send "."

*w::SendText "^"
*s::SendText "_"
*d::Send "="
*a::Send "("
*q::Send "-"
*e::Send "+"

#HotIf

; ============================
; 2. 功能键映射
; ============================
$!Space::Send "^{Space}"

; Alt + E = Enter (发送/确认)
$!e:: {
    Send "{Blind}{LAlt up}{RAlt up}"
    Send "{Blind}{vk07}"
    Send "{Enter}"
    if GetKeyState("LAlt", "P")
        Send "{Blind}{LAlt down}"
}

; 【新增】Shift + Alt + E = Shift + Enter (软回车/换行)
$+!e:: {
    ; 同样需要先松开物理 Alt，防止触发系统菜单
    Send "{Blind}{LAlt up}{RAlt up}"
    Send "{Blind}{vk07}"
    
    ; 发送带有 Shift 状态的回车键（+ 代表 Shift）
    Send "+{Enter}"
    
    ; 恢复物理 Alt 状态
    if GetKeyState("LAlt", "P")
        Send "{Blind}{LAlt down}"
}

; ============================
; 3. 关键修复区 (屏蔽 Alt+Backspace 撤销)
; ============================
*!Backspace::Send "{Backspace}"

; ============================
; 4. 右 Alt 组合删除（轻按一次，长按连发）
; ============================
>!LAlt::RepeatBackspace("LAlt", 60)
>!LWin::RepeatBackspace("LWin", 30)

RepeatBackspace(key, interval) {
    ; 即使两个键的松开事件都丢失，单次按住最多连发 3 秒。
    deadline := DllCall("GetTickCount64", "UInt64") + 3000
    Send "{Backspace}"
    if KeyWait(key, "T0.3")
        return

    while GetKeyState("RAlt", "P") && GetKeyState(key, "P")
        && DllCall("GetTickCount64", "UInt64") < deadline {
        Send "{Backspace}"
        Sleep interval
    }

    ; 等待触发键松开，避免硬件自动重按重新启动连发。
    KeyWait key
}

; ============================
; 5. Edge 屏蔽区（保留原有行为）
; ============================
#HotIf WinActive("ahk_exe msedge.exe")

    ; 屏蔽真实手滑按到的 Alt+F
    *!f::Return

    ; 【终极必杀技】：在按下 Alt 键的瞬间，偷偷发送一个废弃键 vk07
    ; 系统会以为你按了 "Alt + vk07"，所以当你松开 Alt 时，系统就不会认为你是“单按 Alt”了
    ; 这个动作是隐形的，完全不会影响你继续按 W A S D 进行组合！
    *LAlt::Send "{Blind}{vk07}"
    *LAlt Up::Return
    *RAlt::Send "{Blind}{vk07}"
    *RAlt Up::Return

#HotIf

; ============================
; 6. ChatGPT 屏蔽区（不把 Alt 事件交给应用）
; ============================
#HotIf WinActive("ahk_exe ChatGPT.exe")

    ; 不使用 ~ 前缀：AHK 仍能识别物理 Alt 并触发上面的组合键，
    ; 但 ChatGPT 不会收到 Alt 按下/松开，因此菜单不会进入访问键模式。
    *LAlt::Return
    *LAlt Up::Return
    ; 右 Alt/AltGr 直接按物理扫描码拦截，避免被识别为 Ctrl+Alt 后穿透。
    *SC138::Return
    *SC138 Up::Return

#HotIf
