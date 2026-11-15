"""Windows 键盘鼠标。按住 CapsLock，用 J/I/K/L 移动，点按 Esc 退出。终端也可按 Ctrl+C。"""

import ctypes
from ctypes import wintypes as w
from contextlib import ExitStack
import math
from queue import Empty, SimpleQueue
import signal
import sys
import threading
from time import perf_counter, sleep
from typing import NamedTuple


# ── 可调参数 ──────────────────────────────────────────────────────────────
POINTER_TAP_PIXELS = 4.0       # 点按方向键的固定步长（像素）
POINTER_START_SPEED = 140.0    # 刚开始连续移动时的速度（像素/秒）
POINTER_MAX_SPEED = 2200.0     # 长按加速后接近的速度上限（像素/秒）
POINTER_ACCEL_TIME = 0.45      # 加速节奏（秒），值越大越晚进入高速
POINTER_ACCEL_EXPONENT = 2.4   # 加速曲线指数，兼顾初段精确定位与中后段高速巡航
HOLD_DELAY = 0.085             # 首次按下后开始连续移动的等待时间（秒）
TURN_GRACE_TIME = 0.065        # 换键转向时的动量衔接窗口（秒）
RESUME_WINDOW = 0.160          # 同向短暂停顿后续接巡航速度的时间窗口（秒）
FINE_MULTIPLIER = 0.25         # 按住左 Shift 时的步长和速度倍率
FINE_RAMP_ENTRY = 0.15         # 按下左 Shift 瞬间保留的最大加速进度（秒）
FINE_RAMP_CAP = 0.28           # 按住左 Shift 连续移动时的加速进度上限（秒）
EXIT_INPUT_ON_CAPS = True      # 按下 CapsLock 时若处于文本输入状态，自动取消输入框焦点
FRAME_HZ = 120.0               # 连续移动时的输出帧率
WHEEL_TAP_UNITS = 120.0        # 滚轮模式点按的步长，120 单位为一格
WHEEL_SPEED = 720.0            # 滚轮模式按住方向键时的速度（滚轮单位/秒）
WHEEL_QUANTUM = 1              # 最小滚轮增量，旧应用可设为 120（整格发送）

# 标准 QWERTY 的非扩展扫描码 -> (横向方向, 纵向方向)。
DIRECTION_KEYS = {
    0x24: (-1, 0),  # J 向左
    0x17: (0, -1),  # I 向上
    0x25: (0, 1),   # K 向下
    0x26: (1, 0),   # L 向右
}


# ── Win32 类型和绑定 ──────────────────────────────────────────────────────
if sys.platform != "win32":
    raise SystemExit("键盘鼠标需要 Windows。")

WH_KEYBOARD_LL = 13
HC_ACTION = 0
LLKHF_EXTENDED = 0x01
LLKHF_LOWER_IL_INJECTED = 0x02
LLKHF_INJECTED = 0x10
LLKHF_UP = 0x80

VK_TAB = 0x09
VK_SHIFT = 0x10
VK_CONTROL = 0x11
VK_MENU = 0x12
VK_CAPITAL = 0x14
VK_ESCAPE = 0x1B
VK_SPACE = 0x20
VK_LWIN = 0x5B
VK_LSHIFT = 0xA0
VK_RSHIFT = 0xA1
VK_LCONTROL = 0xA2
VK_RCONTROL = 0xA3
VK_LMENU = 0xA4
VK_RMENU = 0xA5
BYPASS_MODIFIERS = (VK_LCONTROL, VK_RCONTROL, VK_LWIN, VK_LMENU)

# 功能键使用字符串作为标识，与方向键的整数扫描码分开。
SPACE = "Space"
RIGHT_ALT = "Right Alt"
TAB = "Tab"
LEFT_SHIFT = "Left Shift"
EXIT_KEY = "Esc"
FUNCTION_KEYS = {
    VK_SPACE: SPACE, VK_RMENU: RIGHT_ALT, VK_TAB: TAB, VK_LSHIFT: LEFT_SHIFT, VK_ESCAPE: EXIT_KEY,
}

INPUT_MOUSE = 0
INPUT_KEYBOARD = 1
KEYEVENTF_KEYUP = 0x0002
MOUSEEVENTF_MOVE = 0x0001
MOUSEEVENTF_LEFTDOWN = 0x0002
MOUSEEVENTF_LEFTUP = 0x0004
MOUSEEVENTF_RIGHTDOWN = 0x0008
MOUSEEVENTF_RIGHTUP = 0x0010
MOUSEEVENTF_WHEEL = 0x0800
MOUSEEVENTF_HWHEEL = 0x1000
MOUSEEVENTF_VIRTUALDESK = 0x4000
MOUSEEVENTF_ABSOLUTE = 0x8000
BUTTON_FLAGS = {
    SPACE: (MOUSEEVENTF_LEFTDOWN, MOUSEEVENTF_LEFTUP),
    RIGHT_ALT: (MOUSEEVENTF_RIGHTDOWN, MOUSEEVENTF_RIGHTUP),
}

SM_XVIRTUALSCREEN = 76
SM_YVIRTUALSCREEN = 77
SM_CXVIRTUALSCREEN = 78
SM_CYVIRTUALSCREEN = 79
WM_QUIT = 0x0012
PM_REMOVE = 0x0001
QS_ALLINPUT = 0x04FF
MWMO_INPUTAVAILABLE = 0x0004
WAIT_OBJECT_0 = 0
WAIT_FAILED = 0xFFFFFFFF
INFINITE = 0xFFFFFFFF
CREATE_WAITABLE_TIMER_HIGH_RESOLUTION = 0x00000002
TIMER_ACCESS = 0x00100002  # SYNCHRONIZE | TIMER_MODIFY_STATE
GUI_CARETBLINKING = 0x00000001
COINIT_MULTITHREADED = 0x0
CLSCTX_INPROC_SERVER = 0x1
VT_BOOL = 11
VT_I4 = 3
VT_BSTR = 8

UIA_ControlTypePropertyId = 30003
UIA_ClassNamePropertyId = 30012
UIA_IsTextPatternAvailablePropertyId = 30040
UIA_IsValuePatternAvailablePropertyId = 30043
UIA_ValueIsReadOnlyPropertyId = 30046
UIA_IsTextEditPatternAvailablePropertyId = 30149

UIA_ComboBoxControlTypeId = 50003
UIA_EditControlTypeId = 50004
UIA_TextControlTypeId = 50020
UIA_CustomControlTypeId = 50025
UIA_GroupControlTypeId = 50026
UIA_DocumentControlTypeId = 50030
UIA_WindowControlTypeId = 50032
UIA_PaneControlTypeId = 50033
TEXT_CONTAINER_TYPES = (
    UIA_DocumentControlTypeId,
    UIA_GroupControlTypeId,
    UIA_CustomControlTypeId,
    UIA_TextControlTypeId,
    UIA_PaneControlTypeId,
)
NATIVE_EDIT_CLASSES = ("edit", "richedit", "scintilla")

ULONG_PTR = ctypes.c_size_t
LRESULT = ctypes.c_ssize_t
HOOKPROC = ctypes.WINFUNCTYPE(LRESULT, ctypes.c_int, w.WPARAM, w.LPARAM)


class GUID(ctypes.Structure):
    _fields_ = [
        ("Data1", w.DWORD), ("Data2", w.WORD), ("Data3", w.WORD),
        ("Data4", ctypes.c_ubyte * 8),
    ]

    def __init__(self, d1, d2, d3, *d4):
        super().__init__(d1, d2, d3, (ctypes.c_ubyte * 8)(*d4))


CLSID_CUIAutomation = GUID(0xFF48DBA4, 0x60EF, 0x4201, 0xAA, 0x87, 0x54, 0x10, 0x3E, 0xEF, 0x59, 0x4E)
IID_IUIAutomation = GUID(0x30CBE57D, 0xD9D0, 0x452A, 0xAB, 0x13, 0x7A, 0xC5, 0xAC, 0x48, 0x25, 0xEE)


class GUITHREADINFO(ctypes.Structure):
    _fields_ = [
        ("cbSize", w.DWORD), ("flags", w.DWORD),
        ("hwndActive", w.HWND), ("hwndFocus", w.HWND),
        ("hwndCapture", w.HWND), ("hwndMenuOwner", w.HWND),
        ("hwndMoveSize", w.HWND), ("hwndCaret", w.HWND),
        ("rcCaret", w.RECT),
    ]


class VARIANT_UNION(ctypes.Union):
    _fields_ = [
        ("lVal", w.LONG),
        ("boolVal", w.VARIANT_BOOL),
        ("bstrVal", w.LPWSTR),
        ("pad", ctypes.c_size_t * 2),
    ]


class VARIANT(ctypes.Structure):
    _anonymous_ = ("u",)
    _fields_ = [
        ("vt", w.USHORT),
        ("wReserved1", w.USHORT),
        ("wReserved2", w.USHORT),
        ("wReserved3", w.USHORT),
        ("u", VARIANT_UNION),
    ]


class KBDLLHOOKSTRUCT(ctypes.Structure):
    _fields_ = [
        ("vkCode", w.DWORD), ("scanCode", w.DWORD), ("flags", w.DWORD),
        ("time", w.DWORD), ("dwExtraInfo", ULONG_PTR),
    ]


class MOUSEINPUT(ctypes.Structure):
    _fields_ = [
        ("dx", w.LONG), ("dy", w.LONG), ("mouseData", w.DWORD),
        ("dwFlags", w.DWORD), ("time", w.DWORD), ("dwExtraInfo", ULONG_PTR),
    ]


class KEYBDINPUT(ctypes.Structure):
    _fields_ = [
        ("wVk", w.WORD), ("wScan", w.WORD), ("dwFlags", w.DWORD),
        ("time", w.DWORD), ("dwExtraInfo", ULONG_PTR),
    ]


class HARDWAREINPUT(ctypes.Structure):
    _fields_ = [("uMsg", w.DWORD), ("wParamL", w.WORD), ("wParamH", w.WORD)]


class INPUT_DATA(ctypes.Union):
    _fields_ = [("mi", MOUSEINPUT), ("ki", KEYBDINPUT), ("hi", HARDWAREINPUT)]


class INPUT(ctypes.Structure):
    _anonymous_ = ("data",)
    _fields_ = [("type", w.DWORD), ("data", INPUT_DATA)]


class MSG(ctypes.Structure):
    _fields_ = [
        ("hwnd", w.HWND), ("message", w.UINT), ("wParam", w.WPARAM),
        ("lParam", w.LPARAM), ("time", w.DWORD), ("pt", w.POINT), ("lPrivate", w.DWORD),
    ]


def bind(dll, name, result_type, *argument_types):
    function = getattr(dll, name)
    function.restype = result_type
    function.argtypes = argument_types
    return function


user32 = ctypes.WinDLL("user32", use_last_error=True)
kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
ole32 = ctypes.WinDLL("ole32", use_last_error=True)
oleaut32 = ctypes.WinDLL("oleaut32", use_last_error=True)
LPMSG = ctypes.POINTER(MSG)

SetWindowsHookExW = bind(user32, "SetWindowsHookExW", w.HHOOK, ctypes.c_int, HOOKPROC, w.HINSTANCE, w.DWORD)
CallNextHookEx = bind(user32, "CallNextHookEx", LRESULT, w.HHOOK, ctypes.c_int, w.WPARAM, w.LPARAM)
UnhookWindowsHookEx = bind(user32, "UnhookWindowsHookEx", w.BOOL, w.HHOOK)
GetAsyncKeyState = bind(user32, "GetAsyncKeyState", ctypes.c_short, ctypes.c_int)
SendInput = bind(user32, "SendInput", w.UINT, w.UINT, ctypes.POINTER(INPUT), ctypes.c_int)
SetProcessDPIAware = bind(user32, "SetProcessDPIAware", w.BOOL)
GetPhysicalCursorPos = bind(user32, "GetPhysicalCursorPos", w.BOOL, ctypes.POINTER(w.POINT))
GetSystemMetrics = bind(user32, "GetSystemMetrics", ctypes.c_int, ctypes.c_int)
GetForegroundWindow = bind(user32, "GetForegroundWindow", w.HWND)
GetWindowThreadProcessId = bind(user32, "GetWindowThreadProcessId", w.DWORD, w.HWND, ctypes.POINTER(w.DWORD))
GetGUIThreadInfo = bind(user32, "GetGUIThreadInfo", w.BOOL, w.DWORD, ctypes.POINTER(GUITHREADINFO))
GetClassNameW = bind(user32, "GetClassNameW", ctypes.c_int, w.HWND, w.LPWSTR, ctypes.c_int)
AttachThreadInput = bind(user32, "AttachThreadInput", w.BOOL, w.DWORD, w.DWORD, w.BOOL)
SetFocus = bind(user32, "SetFocus", w.HWND, w.HWND)
IsHungAppWindow = bind(user32, "IsHungAppWindow", w.BOOL, w.HWND)
MsgWaitForMultipleObjectsEx = bind(
    user32, "MsgWaitForMultipleObjectsEx", w.DWORD,
    w.DWORD, ctypes.POINTER(w.HANDLE), w.DWORD, w.DWORD, w.DWORD,
)
PeekMessageW = bind(user32, "PeekMessageW", w.BOOL, LPMSG, w.HWND, w.UINT, w.UINT, w.UINT)
TranslateMessage = bind(user32, "TranslateMessage", w.BOOL, LPMSG)
DispatchMessageW = bind(user32, "DispatchMessageW", LRESULT, LPMSG)
GetModuleHandleW = bind(kernel32, "GetModuleHandleW", w.HMODULE, w.LPCWSTR)
GetCurrentThreadId = bind(kernel32, "GetCurrentThreadId", w.DWORD)
CreateEventW = bind(kernel32, "CreateEventW", w.HANDLE, ctypes.c_void_p, w.BOOL, w.BOOL, w.LPCWSTR)
SetEvent = bind(kernel32, "SetEvent", w.BOOL, w.HANDLE)
CreateWaitableTimerExW = bind(
    kernel32, "CreateWaitableTimerExW", w.HANDLE, ctypes.c_void_p, w.LPCWSTR, w.DWORD, w.DWORD,
)
SetWaitableTimer = bind(
    kernel32, "SetWaitableTimer", w.BOOL, w.HANDLE, ctypes.POINTER(ctypes.c_longlong),
    w.LONG, ctypes.c_void_p, ctypes.c_void_p, w.BOOL,
)
WaitForMultipleObjects = bind(
    kernel32, "WaitForMultipleObjects", w.DWORD, w.DWORD, ctypes.POINTER(w.HANDLE), w.BOOL, w.DWORD,
)
CloseHandle = bind(kernel32, "CloseHandle", w.BOOL, w.HANDLE)
CoInitializeEx = bind(ole32, "CoInitializeEx", ctypes.c_long, ctypes.c_void_p, w.DWORD)
CoUninitialize = bind(ole32, "CoUninitialize", None)
CoCreateInstance = bind(
    ole32, "CoCreateInstance", ctypes.c_long,
    ctypes.POINTER(GUID), ctypes.c_void_p, w.DWORD, ctypes.POINTER(GUID), ctypes.POINTER(ctypes.c_void_p),
)
VariantClear = bind(oleaut32, "VariantClear", ctypes.c_long, ctypes.POINTER(VARIANT))


# ── 键盘钩子。只判定事件归属，再把必要的变化送入队列 ────────────────────
class ModeChange(NamedTuple):
    enabled: bool
    scroll: bool = False
    fine: bool = False


class KeyChange(NamedTuple):
    key: int | str
    down: bool
    at: float


def system_key_down(vk):
    return GetAsyncKeyState(vk) < 0


class KeyRouter:
    def __init__(self, enqueue, is_system_down=system_key_down):
        self.enqueue = enqueue
        self.is_system_down = is_system_down
        self.caps_route = None  # None 未按住，True 拦截，False 原生放行
        self.bypass_down = set()
        self.routes = {}  # 当前按键序列的 KeyDown 是否由本程序拦截
        self.exit_requested = False
        self.error = None

    def activate(self):
        scroll = TAB in self.routes or self.is_system_down(VK_TAB)
        fine = LEFT_SHIFT in self.routes or self.is_system_down(VK_LSHIFT)
        if scroll:
            self.routes.setdefault(TAB, False)
        if fine:
            self.routes.setdefault(LEFT_SHIFT, False)
        self.enqueue(ModeChange(True, scroll, fine))

    def caps(self, down):
        if down and self.caps_route is None:
            # 钩子先于当前事件更新异步键态。这里只读取先前已交给系统的键态。
            self.caps_route = not (self.is_system_down(VK_LSHIFT) or self.is_system_down(VK_CAPITAL))
            if self.caps_route:
                self.bypass_down = {vk for vk in BYPASS_MODIFIERS if self.is_system_down(vk)}
                if not self.bypass_down:
                    self.activate()
        swallow = self.caps_route is True
        if not down:
            self.caps_route = None
            if swallow:
                self.routes.clear()
                self.bypass_down.clear()
                self.enqueue(ModeChange(False))
        return swallow

    def route_active(self, vk, scan, flags, down):
        extended = flags & LLKHF_EXTENDED
        if vk == VK_CONTROL:
            vk = VK_RCONTROL if extended else VK_LCONTROL
        elif vk == VK_MENU:
            vk = VK_RMENU if extended else VK_LMENU
        elif vk == VK_SHIFT:
            vk = VK_LSHIFT if scan == 0x2A else VK_RSHIFT

        if vk in BYPASS_MODIFIERS:
            was_bypassed = bool(self.bypass_down)
            if down:
                self.bypass_down.add(vk)
            else:
                self.bypass_down.discard(vk)
            if not was_bypassed and self.bypass_down:
                self.enqueue(ModeChange(False))
            elif was_bypassed and not self.bypass_down:
                self.activate()
            return False

        key = FUNCTION_KEYS.get(vk)
        if key is None:
            if extended or scan not in DIRECTION_KEYS:
                return False
            key = scan

        if self.bypass_down:
            if down:
                self.routes[key] = False
            else:
                self.routes.pop(key, None)
            return False

        if down:
            previous = self.routes.get(key)
            if previous is not None:
                return previous  # 系统长按重复，保持首次按下的处理结果
            # 键可能在按 CapsLock 前就已经按下。把该次按键序列留给原应用。
            swallow = not self.is_system_down(vk)
            self.routes[key] = swallow
            if swallow and key != EXIT_KEY:
                self.enqueue(KeyChange(key, True, perf_counter()))
            return swallow

        swallow = self.routes.pop(key, None)
        if swallow and key == EXIT_KEY:
            self.exit_requested = True  # 吞掉完整的 Esc 按键序列后，由主循环退出
            return True
        if swallow or (swallow is False and key in (TAB, LEFT_SHIFT)):
            self.enqueue(KeyChange(key, False, perf_counter()))
        return swallow is True

    def hook(self, code, message, lparam):
        if code == HC_ACTION and self.error is None and not self.exit_requested:
            try:
                event = KBDLLHOOKSTRUCT.from_address(lparam)
                flags = event.flags
                if not flags & (LLKHF_INJECTED | LLKHF_LOWER_IL_INJECTED):
                    vk = event.vkCode
                    if vk == VK_CAPITAL:
                        if self.caps(not flags & LLKHF_UP):
                            return 1
                    elif self.caps_route is True:
                        if self.route_active(vk, event.scanCode, flags, not flags & LLKHF_UP):
                            return 1
            except Exception as error:
                # 由主循环退出并清理。异常发生后先恢复键盘直通。
                self.error = error
        return CallNextHookEx(None, code, message, lparam)


# ── 鼠标输出，只由工作线程调用 ────────────────────────────────────────────
def mouse_input(flags, dx=0, dy=0, wheel=0):
    event = INPUT(type=INPUT_MOUSE)
    event.mi = MOUSEINPUT(dx, dy, wheel & 0xFFFFFFFF, flags, 0, 0)
    return event


def send_mouse(*events):
    inputs = (INPUT * len(events))(*events)
    return SendInput(len(inputs), inputs, ctypes.sizeof(INPUT)) == len(inputs)


def move_pointer(dx, dy):
    cursor = w.POINT()
    if not GetPhysicalCursorPos(ctypes.byref(cursor)):
        return
    left = GetSystemMetrics(SM_XVIRTUALSCREEN)
    top = GetSystemMetrics(SM_YVIRTUALSCREEN)
    width = GetSystemMetrics(SM_CXVIRTUALSCREEN)
    height = GetSystemMetrics(SM_CYVIRTUALSCREEN)
    if width <= 0 or height <= 0:
        return

    x = min(width - 1, max(0, cursor.x + dx - left))
    y = min(height - 1, max(0, cursor.y + dy - top))
    # 取目标像素在 0～65535 坐标区间内的中心，避免相对移动被系统再次加速。
    absolute_x = ((2 * x + 1) * 32768) // width
    absolute_y = ((2 * y + 1) * 32768) // height
    flags = MOUSEEVENTF_MOVE | MOUSEEVENTF_ABSOLUTE | MOUSEEVENTF_VIRTUALDESK
    send_mouse(mouse_input(flags, absolute_x, absolute_y))


def scroll_pointer(dx, dy):
    events = []
    if dy:
        events.append(mouse_input(MOUSEEVENTF_WHEEL, wheel=-dy))  # 向下滚动对应负滚轮值
    if dx:
        events.append(mouse_input(MOUSEEVENTF_HWHEEL, wheel=dx))
    send_mouse(*events)


def key_input(vk, up=False):
    event = INPUT(type=INPUT_KEYBOARD)
    event.ki = KEYBDINPUT(vk, 0, KEYEVENTF_KEYUP if up else 0, 0, 0)
    return event


def send_escape():
    events = (INPUT * 2)(key_input(VK_ESCAPE, False), key_input(VK_ESCAPE, True))
    return SendInput(2, events, ctypes.sizeof(INPUT)) == 2


def vtable_call(obj, index, restype, *argtypes):
    vtbl = ctypes.cast(obj, ctypes.POINTER(ctypes.POINTER(ctypes.c_void_p))).contents
    fn = ctypes.WINFUNCTYPE(restype, ctypes.c_void_p, *argtypes)(vtbl[index])
    return lambda *args: fn(obj, *args)


class FocusWorker(threading.Thread):
    """独立线程检测并退出网页/应用的文本输入焦点，避免跨进程 COM 调用阻塞鼠标帧率。"""

    def __init__(self, stop_event, blur_event):
        super().__init__(name="KeyboardMouse-Focus", daemon=True)
        self.handles = (w.HANDLE * 2)(stop_event, blur_event)
        self.uia = ctypes.c_void_p()
        self.walker = ctypes.c_void_p()

    @staticmethod
    def release(obj):
        if obj and obj.value:
            vtable_call(obj, 2, w.ULONG)()
            obj.value = None

    def get_focused_element(self):
        if not self.uia.value:
            return None
        elem = ctypes.c_void_p()
        hr = vtable_call(self.uia, 8, ctypes.c_long, ctypes.POINTER(ctypes.c_void_p))(ctypes.byref(elem))
        return elem if hr == 0 and elem.value else None

    def get_parent_element(self, elem):
        if not (self.walker.value and elem and elem.value):
            return None
        parent = ctypes.c_void_p()
        hr = vtable_call(
            self.walker, 3, ctypes.c_long, ctypes.c_void_p, ctypes.POINTER(ctypes.c_void_p),
        )(elem, ctypes.byref(parent))
        return parent if hr == 0 and parent.value else None

    @staticmethod
    def set_element_focus(elem):
        if not (elem and elem.value):
            return False
        return vtable_call(elem, 3, ctypes.c_long)() == 0

    @staticmethod
    def get_property(elem, prop_id):
        var = VARIANT()
        hr = vtable_call(
            elem, 10, ctypes.c_long, ctypes.c_int, ctypes.POINTER(VARIANT),
        )(prop_id, ctypes.byref(var))
        if hr != 0:
            return None
        try:
            if var.vt == VT_I4:
                return int(var.lVal)
            if var.vt == VT_BOOL:
                return bool(var.boolVal)
            if var.vt == VT_BSTR:
                return var.bstrVal or ""
            return None
        finally:
            VariantClear(ctypes.byref(var))

    def elem_type(self, elem):
        return self.get_property(elem, UIA_ControlTypePropertyId)

    def elem_class(self, elem):
        return self.get_property(elem, UIA_ClassNamePropertyId) or ""

    def is_editable_element(self, elem):
        if not (elem and elem.value):
            return False
        ctrl_type = self.elem_type(elem)
        if ctrl_type is None:
            return False
        is_readonly = self.get_property(elem, UIA_ValueIsReadOnlyPropertyId)
        if ctrl_type == UIA_EditControlTypeId:
            return is_readonly is not True
        is_value = bool(self.get_property(elem, UIA_IsValuePatternAvailablePropertyId))
        is_text = bool(
            self.get_property(elem, UIA_IsTextPatternAvailablePropertyId)
            or self.get_property(elem, UIA_IsTextEditPatternAvailablePropertyId)
        )
        if ctrl_type == UIA_ComboBoxControlTypeId:
            return (is_value or is_text) and is_readonly is not True
        if ctrl_type in TEXT_CONTAINER_TYPES:
            return is_value and is_readonly is False
        return False

    def find_blur_targets(self, focused):
        doc = None
        top = None
        curr = self.get_parent_element(focused)
        depth = 0
        while curr and curr.value and depth < 24:
            depth += 1
            cls_name = self.elem_class(curr)
            if cls_name == "#32769":
                self.release(curr)
                break
            ctrl_type = self.elem_type(curr)
            if ctrl_type == UIA_DocumentControlTypeId and not self.is_editable_element(curr):
                self.release(doc)
                doc = curr
                curr = self.get_parent_element(doc)
                continue
            if ctrl_type in (UIA_PaneControlTypeId, UIA_WindowControlTypeId):
                self.release(top)
                top = curr
                curr = self.get_parent_element(top)
                continue
            nxt = self.get_parent_element(curr)
            self.release(curr)
            curr = nxt
        return doc, top

    @staticmethod
    def get_gui_info(tid=0):
        gti = GUITHREADINFO(cbSize=ctypes.sizeof(GUITHREADINFO))
        if GetGUIThreadInfo(tid, ctypes.byref(gti)) and (gti.hwndActive or gti.hwndFocus):
            return gti
        fg = GetForegroundWindow()
        if fg:
            fg_tid = GetWindowThreadProcessId(fg, None)
            if fg_tid and GetGUIThreadInfo(fg_tid, ctypes.byref(gti)):
                return gti
        return None

    @staticmethod
    def window_class(hwnd):
        if not hwnd:
            return ""
        buf = ctypes.create_unicode_buffer(64)
        length = GetClassNameW(hwnd, buf, len(buf))
        return buf.value[:length].lower() if length > 0 else ""

    def has_win32_text_focus(self, gti=None):
        gti = gti or self.get_gui_info()
        if not gti or not gti.hwndFocus:
            return False
        cls_name = self.window_class(gti.hwndFocus)
        if any(token in cls_name for token in NATIVE_EDIT_CLASSES):
            return True
        return bool((gti.flags & GUI_CARETBLINKING) or gti.hwndCaret)

    def blur_win32_focus(self, only_child=False, gti=None):
        gti = gti or self.get_gui_info()
        if not gti or not gti.hwndFocus or IsHungAppWindow(gti.hwndFocus):
            return False
        if only_child and gti.hwndFocus == gti.hwndActive:
            return False
        target_tid = GetWindowThreadProcessId(gti.hwndFocus, None)
        current_tid = GetCurrentThreadId()
        if not target_tid:
            return False
        target_hwnd = gti.hwndActive if gti.hwndFocus != gti.hwndActive else None
        attached = False
        if target_tid != current_tid:
            attached = bool(AttachThreadInput(current_tid, target_tid, True))
        try:
            SetFocus(target_hwnd)
            after = self.get_gui_info(target_tid)
            return bool(after and after.hwndFocus != gti.hwndFocus)
        finally:
            if attached:
                AttachThreadInput(current_tid, target_tid, False)

    def exit_text_input(self):
        focused = self.get_focused_element()
        if focused:
            try:
                if (
                    self.elem_class(focused) == "Chrome_RenderWidgetHostHWND"
                    and self.elem_type(focused) == UIA_PaneControlTypeId
                ):
                    # 浏览器标签页首次唤醒无障碍树时可能暂返容器节点，短暂等待渲染进程完成建树
                    self.release(focused)
                    sleep(0.025)
                    focused = self.get_focused_element()
                if focused and self.is_editable_element(focused):
                    doc, top = self.find_blur_targets(focused)
                    try:
                        if doc:
                            self.set_element_focus(doc)
                            sleep(0.020)
                            current = self.get_focused_element()
                            try:
                                if not (current and self.is_editable_element(current)):
                                    return
                            finally:
                                self.release(current)
                        elif top:
                            self.set_element_focus(top)
                    finally:
                        self.release(doc)
                        self.release(top)
                    if self.blur_win32_focus(only_child=True):
                        return
                    sleep(0.015)
                    current = self.get_focused_element()
                    try:
                        if current and self.is_editable_element(current):
                            send_escape()
                    finally:
                        self.release(current)
                    return
            finally:
                self.release(focused)

        gti = self.get_gui_info()
        if self.has_win32_text_focus(gti):
            if not self.blur_win32_focus(only_child=False, gti=gti):
                send_escape()

    def run(self):
        hr = CoInitializeEx(None, COINIT_MULTITHREADED)
        com_initialized = hr >= 0
        try:
            if com_initialized:
                if CoCreateInstance(
                    ctypes.byref(CLSID_CUIAutomation), None, CLSCTX_INPROC_SERVER,
                    ctypes.byref(IID_IUIAutomation), ctypes.byref(self.uia),
                ) == 0 and self.uia.value:
                    vtable_call(
                        self.uia, 14, ctypes.c_long, ctypes.POINTER(ctypes.c_void_p),
                    )(ctypes.byref(self.walker))
                    # 预热一次焦点查询，提前激活前台浏览器的无障碍树
                    self.release(self.get_focused_element())
            while True:
                wake = WaitForMultipleObjects(len(self.handles), self.handles, False, INFINITE)
                if wake == WAIT_OBJECT_0 or wake == WAIT_FAILED:
                    return
                if EXIT_INPUT_ON_CAPS:
                    try:
                        self.exit_text_input()
                    except Exception:
                        pass
        finally:
            self.release(self.walker)
            self.release(self.uia)
            if com_initialized:
                CoUninitialize()


class KeyboardMouse:
    def __init__(self, on_activate=None):
        self.on_activate = on_activate
        self.buttons_down = set()
        self.pending_ups = set()
        self.directions_down = set()
        self.enabled = False
        self.set_mode(ModeChange(False))

    def set_mode(self, change):
        was_enabled = self.enabled
        self.enabled, self.scroll, self.fine = change
        self.directions_down.clear()
        self.pending_tap_key = None
        self.hold_started_at = self.last_step_at = 0.0
        self.ramp_elapsed = 0.0
        self.last_dir = (0, 0)
        self.last_move_at = 0.0
        self.last_ramp_elapsed = 0.0
        self.sub_x = self.sub_y = 0.0
        if not self.enabled:
            self.release_buttons()
        elif not was_enabled and self.on_activate is not None:
            self.on_activate()

    def net_direction(self):
        dx = dy = 0
        for key in self.directions_down:
            x, y = DIRECTION_KEYS[key]
            dx += x
            dy += y
        return dx, dy

    def clear_axis_subpixel(self, dx):
        if not self.scroll:
            if dx:
                self.sub_x = 0.0
            else:
                self.sub_y = 0.0

    def release_buttons(self):
        self.pending_ups.update(self.buttons_down)
        self.retry_releases()

    def retry_releases(self):
        for key in tuple(self.pending_ups):
            if send_mouse(mouse_input(BUTTON_FLAGS[key][1])):
                self.pending_ups.remove(key)
                self.buttons_down.remove(key)

    def button(self, key, down):
        if down:
            if key in self.pending_ups:
                self.retry_releases()
            if key not in self.buttons_down and send_mouse(mouse_input(BUTTON_FLAGS[key][0])):
                self.buttons_down.add(key)
        elif key in self.buttons_down:
            self.pending_ups.add(key)
            self.retry_releases()

    def accept(self, change):
        if isinstance(change, ModeChange):
            self.set_mode(change)
            return
        if not self.enabled:
            return

        key, down, now = change
        self.advance(now)
        if key == TAB:
            if self.scroll != down:
                self.scroll = down
                self.sub_x = self.sub_y = 0.0  # 像素和滚轮单位分别累计
                self.ramp_elapsed = 0.0
        elif key == LEFT_SHIFT:
            if self.fine != down:
                self.fine = down
                if down:
                    self.ramp_elapsed = min(self.ramp_elapsed, FINE_RAMP_ENTRY)
        elif key in BUTTON_FLAGS:
            self.button(key, down)
        else:
            self.direction_key(key, down, now)

    def direction_key(self, key, down, now):
        if down == (key in self.directions_down):
            return
        prev_dx, prev_dy = self.net_direction()
        dx, dy = DIRECTION_KEYS[key]
        step = WHEEL_TAP_UNITS if self.scroll else POINTER_TAP_PIXELS

        if not down:
            self.directions_down.remove(key)
            if self.pending_tap_key == key:
                self.pending_tap_key = None
            new_dx, new_dy = self.net_direction()
            if not (new_dx or new_dy):
                if now <= self.hold_started_at + HOLD_DELAY:
                    self.last_ramp_elapsed = 0.0
                self.ramp_elapsed = 0.0
            elif not (prev_dx or prev_dy):
                # 原本两个反向键互相抵消，释放旧键后让新键立即起步并补发点按
                self.hold_started_at = now
                self.ramp_elapsed = 0.0
                if self.pending_tap_key in self.directions_down:
                    tap_dx, tap_dy = DIRECTION_KEYS[self.pending_tap_key]
                    self.pending_tap_key = None
                    self.clear_axis_subpixel(tap_dx)
                    self.output_motion(tap_dx * step, tap_dy * step)
            elif prev_dx * new_dx + prev_dy * new_dy < 0:
                self.hold_started_at = now
                self.ramp_elapsed = 0.0
            return

        was_empty = not self.directions_down
        self.directions_down.add(key)
        if any(DIRECTION_KEYS[held] == (-dx, -dy) for held in self.directions_down):
            self.pending_tap_key = key
            self.ramp_elapsed = 0.0
            self.last_ramp_elapsed = 0.0
            return
        self.pending_tap_key = None

        if was_empty or not (prev_dx or prev_dy):
            self.hold_started_at = now
            gap = now - self.last_move_at
            dot = dx * self.last_dir[0] + dy * self.last_dir[1]
            if not self.scroll and dot > 0 and gap <= RESUME_WINDOW and self.last_ramp_elapsed >= 0.15:
                # 同向巡航短暂停顿后续按：保留点按微调能力，长按后直接恢复巡航速度
                self.ramp_elapsed = self.last_ramp_elapsed * 0.65
            elif not self.scroll and dot == 0 and gap <= TURN_GRACE_TIME and self.last_ramp_elapsed >= 0.06:
                # 连续移动中快速换键直角转向：保留适度过弯动量
                self.ramp_elapsed = self.last_ramp_elapsed * 0.55
            else:
                self.ramp_elapsed = 0.0
            self.clear_axis_subpixel(dx)
            self.output_motion(dx * step, dy * step)
        elif self.scroll or now < self.hold_started_at + HOLD_DELAY:
            # 起步等待期内按下斜向键，补发该轴点按步长；已处于连续滑行时则直接平滑转向
            self.clear_axis_subpixel(dx)
            self.output_motion(dx * step, dy * step)

    def advance(self, now):
        if not self.directions_down:
            self.last_step_at = max(self.last_step_at, now)
            return
        hold_ready_at = self.hold_started_at + HOLD_DELAY
        start = max(self.last_step_at, hold_ready_at)
        self.last_step_at = max(self.last_step_at, now)
        dt = min(now - start, 2.0 / FRAME_HZ)
        if dt <= 0:
            return

        dx, dy = self.net_direction()
        if not (dx or dy):
            return
        if self.scroll:
            speed = WHEEL_SPEED
        else:
            # 取本帧中点的速度。初段保持平稳低速便于精确定位，随后快速拉升至巡航速度。
            mid_elapsed = self.ramp_elapsed + dt * 0.5
            progress = mid_elapsed / POINTER_ACCEL_TIME
            blend = 1.0 - math.exp(-(progress ** POINTER_ACCEL_EXPONENT))
            speed = POINTER_START_SPEED + (POINTER_MAX_SPEED - POINTER_START_SPEED) * blend
            self.ramp_elapsed += dt
            if self.fine:
                self.ramp_elapsed = min(self.ramp_elapsed, FINE_RAMP_CAP)
            self.last_dir = (dx, dy)
            self.last_move_at = now
            self.last_ramp_elapsed = self.ramp_elapsed
        distance = speed * dt / math.hypot(dx, dy)  # 斜向保持相同总速度
        self.output_motion(dx * distance, dy * distance)

    def frame(self, now, last_frame=None):
        self.retry_releases()
        if last_frame is not None and self.last_step_at < last_frame:
            self.last_step_at = last_frame
        self.advance(now)

    def output_motion(self, dx, dy):
        multiplier = FINE_MULTIPLIER if self.fine else 1.0
        total_x = self.sub_x + dx * multiplier
        total_y = self.sub_y + dy * multiplier
        quantum = WHEEL_QUANTUM if self.scroll else 1
        # 容忍浮点误差，避免刚好够一个单位的位移被舍掉。
        out_x = math.trunc(total_x / quantum + math.copysign(1e-9, total_x)) * quantum
        out_y = math.trunc(total_y / quantum + math.copysign(1e-9, total_y)) * quantum
        self.sub_x = total_x - out_x
        self.sub_y = total_y - out_y
        if out_x or out_y:
            if self.scroll:
                scroll_pointer(out_x, out_y)
            else:
                move_pointer(out_x, out_y)


class OutputWorker(threading.Thread):
    def __init__(self, stop_event, input_event, timer, blur_event=None):
        super().__init__(name="KeyboardMouse-Output")
        self.input_event = input_event
        self.timer = timer
        self.blur_event = blur_event
        self.handles = (w.HANDLE * 3)(stop_event, input_event, timer)
        self.commands = SimpleQueue()
        self.mouse = KeyboardMouse(
            on_activate=(lambda: SetEvent(self.blur_event)) if blur_event else None,
        )
        self.error = None

    def enqueue(self, change):
        self.commands.put(change)
        if not SetEvent(self.input_event):
            raise ctypes.WinError(ctypes.get_last_error())

    def arm_frame(self, deadline):
        delay = ctypes.c_longlong(-max(1, math.ceil((deadline - perf_counter()) * 10_000_000)))
        if not SetWaitableTimer(self.timer, ctypes.byref(delay), 0, None, None, False):
            raise ctypes.WinError(ctypes.get_last_error())

    def process(self):
        period = 1.0 / FRAME_HZ
        deadline = None
        last_frame = 0.0
        while True:
            wake = WaitForMultipleObjects(len(self.handles), self.handles, False, INFINITE)
            if wake == WAIT_OBJECT_0:
                return
            if wake == WAIT_FAILED:
                raise ctypes.WinError(ctypes.get_last_error())

            # 点按和鼠标按键立即处理，连续移动按帧输出。
            while True:
                try:
                    change = self.commands.get_nowait()
                except Empty:
                    break
                self.mouse.accept(change)

            if not (self.mouse.directions_down or self.mouse.pending_ups):
                deadline = None
                continue
            now = perf_counter()
            if deadline is None:
                last_frame = now
                deadline = now + period
                self.arm_frame(deadline)
            elif now >= deadline:
                self.mouse.frame(now, last_frame)
                last_frame = now
                deadline += (1 + int((now - deadline) / period)) * period
                self.arm_frame(deadline)
            elif wake == WAIT_OBJECT_0 + 2:
                self.arm_frame(deadline)

    def run(self):
        try:
            self.process()
        except Exception as error:
            self.error = error
        finally:
            # 安全桌面切换等情况可能暂时拒绝 SendInput，退出前短暂重试抬键。
            self.mouse.release_buttons()
            until = perf_counter() + 0.30
            while self.mouse.pending_ups and perf_counter() < until:
                sleep(0.01)
                self.mouse.retry_releases()
            if self.mouse.pending_ups and self.error is None:
                self.error = RuntimeError("Windows 拒绝了鼠标抬键事件，释放重试未成功。")


def message_loop(should_stop, router, worker):
    message = MSG()
    while not should_stop() and not router.exit_requested and router.error is None and worker.is_alive():
        result = MsgWaitForMultipleObjectsEx(0, None, 50, QS_ALLINPUT, MWMO_INPUTAVAILABLE)
        if result == WAIT_FAILED:
            raise ctypes.WinError(ctypes.get_last_error())
        while PeekMessageW(ctypes.byref(message), None, 0, 0, PM_REMOVE):
            if message.message == WM_QUIT:
                return
            TranslateMessage(ctypes.byref(message))
            DispatchMessageW(ctypes.byref(message))


def main():
    # 此进程只操作物理屏幕像素。该设置仅作用于本进程。
    SetProcessDPIAware()
    stop_requested = False

    def request_stop(_signum, _frame):
        nonlocal stop_requested
        stop_requested = True

    with ExitStack() as resources:
        previous_handler = signal.signal(signal.SIGINT, request_stop)
        resources.callback(signal.signal, signal.SIGINT, previous_handler)

        def own_handle(handle):
            if not handle:
                raise ctypes.WinError(ctypes.get_last_error())
            resources.callback(CloseHandle, handle)
            return handle

        stop_event = own_handle(CreateEventW(None, True, False, None))
        input_event = own_handle(CreateEventW(None, False, False, None))
        blur_event = own_handle(CreateEventW(None, False, False, None))
        timer = CreateWaitableTimerExW(None, None, CREATE_WAITABLE_TIMER_HIGH_RESOLUTION, TIMER_ACCESS)
        if not timer:
            timer = CreateWaitableTimerExW(None, None, 0, TIMER_ACCESS)
        own_handle(timer)

        focus_worker = FocusWorker(stop_event, blur_event)
        worker = OutputWorker(stop_event, input_event, timer, blur_event)
        router = KeyRouter(worker.enqueue)
        callback = HOOKPROC(router.hook)  # 持有引用，直到卸载钩子
        focus_worker.start()
        worker.start()
        try:
            print(
                "键盘鼠标启动中。按住 CapsLock，用 J/I/K/L 移动。"
                "退出请按住 CapsLock 点按 Esc，或在终端按 Ctrl+C。",
                flush=True,
            )
            module = GetModuleHandleW(None)
            if not module:
                raise ctypes.WinError(ctypes.get_last_error())
            hook = SetWindowsHookExW(WH_KEYBOARD_LL, callback, module, 0)
            if not hook:
                raise ctypes.WinError(ctypes.get_last_error())
            try:
                message_loop(lambda: stop_requested, router, worker)
            finally:
                if not UnhookWindowsHookEx(hook):
                    raise ctypes.WinError(ctypes.get_last_error())
        finally:
            SetEvent(stop_event)
            worker.join()
            focus_worker.join(timeout=0.3)

        if router.error is not None:
            raise router.error
        if worker.error is not None:
            raise worker.error
    print("键盘鼠标已退出。", flush=True)


if __name__ == "__main__":
    main()
