import ctypes
from ctypes import wintypes
import keyboard
import time

WH_MOUSE_LL = 14

user32 = ctypes.WinDLL("user32", use_last_error=True)
kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)

# Callback prototype
LowLevelMouseProc = ctypes.WINFUNCTYPE(
    ctypes.c_int,
    ctypes.c_int,
    wintypes.WPARAM,
    wintypes.LPARAM
)

# SetWindowsHookExW
user32.SetWindowsHookExW.restype = wintypes.HHOOK
user32.SetWindowsHookExW.argtypes = [
    ctypes.c_int,
    LowLevelMouseProc,
    wintypes.HINSTANCE,
    wintypes.DWORD,
]

# UnhookWindowsHookEx
user32.UnhookWindowsHookEx.restype = wintypes.BOOL
user32.UnhookWindowsHookEx.argtypes = [wintypes.HHOOK]

# CallNextHookEx
user32.CallNextHookEx.restype = ctypes.c_int
user32.CallNextHookEx.argtypes = [
    wintypes.HHOOK,
    ctypes.c_int,
    wintypes.WPARAM,
    wintypes.LPARAM,
]

# GetMessageW
user32.GetMessageW.restype = wintypes.BOOL
user32.GetMessageW.argtypes = [
    ctypes.POINTER(wintypes.MSG),
    wintypes.HWND,
    wintypes.UINT,
    wintypes.UINT,
]

# GetModuleHandleW
kernel32.GetModuleHandleW.restype = wintypes.HMODULE
kernel32.GetModuleHandleW.argtypes = [wintypes.LPCWSTR]

mouse_brake_flag = False
loop_control = True


def block_mouse_callback(n_code, w_param, l_param):
    if n_code >= 0:
        return 1

    return user32.CallNextHookEx(
        None,
        n_code,
        w_param,
        l_param
    )

def change_flag(flag):
    global mouse_brake_flag
    mouse_brake_flag = flag

def block_mouse():
    global mouse_brake_flag
    pointer = LowLevelMouseProc(block_mouse_callback)

    h_instance = kernel32.GetModuleHandleW(None)

    hook_id = user32.SetWindowsHookExW(
        WH_MOUSE_LL,
        pointer,
        h_instance,
        0
    )

    if not hook_id:
        ctypes.get_last_error()
        return


    try:
        msg = wintypes.MSG()
        keyboard.on_press_key('win', lambda _: change_flag(True))
        while loop_control:
            if mouse_brake_flag:
                break

                # PM_REMOVE = 0x0001 (removes the message from queue after reading)
            if user32.PeekMessageW(ctypes.byref(msg), None, 0, 0, 0x0001):
                user32.TranslateMessage(ctypes.byref(msg))
                user32.DispatchMessageW(ctypes.byref(msg))
            time.sleep(0.1)

    except KeyboardInterrupt:
        pass

    finally:
        user32.UnhookWindowsHookEx(hook_id)
        keyboard.unhook_all()


if __name__ == "__main__":
    block_mouse()
