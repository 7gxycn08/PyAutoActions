import ctypes
import os
from ctypes import wintypes
import keyboard
import time

WH_MOUSE_LL = 14
OCR_NORMAL = 32512

user32 = ctypes.WinDLL("user32", use_last_error=True)
kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
cursor_path = fr"{os.getcwd()}\Dependency\Cursor\invisible.cur"

# --- PROTOTYPES ---
LowLevelMouseProc = ctypes.WINFUNCTYPE(ctypes.c_int, ctypes.c_int, wintypes.WPARAM, wintypes.LPARAM)
user32.SetWindowsHookExW.restype = wintypes.HHOOK
# noinspection SpellCheckingInspection
user32.SetWindowsHookExW.argtypes = [ctypes.c_int, LowLevelMouseProc, wintypes.HINSTANCE, wintypes.DWORD]
user32.UnhookWindowsHookEx.restype = wintypes.BOOL
# noinspection SpellCheckingInspection
user32.UnhookWindowsHookEx.argtypes = [wintypes.HHOOK]
user32.CallNextHookEx.restype = ctypes.c_int
# noinspection SpellCheckingInspection
user32.CallNextHookEx.argtypes = [wintypes.HHOOK, ctypes.c_int, wintypes.WPARAM, wintypes.LPARAM]
kernel32.GetModuleHandleW.restype = wintypes.HMODULE
# noinspection SpellCheckingInspection
kernel32.GetModuleHandleW.argtypes = [wintypes.LPCWSTR]

# --- GLOBAL STATE ---
mouse_brake_flag = False
# Keep the pointer global so Python doesn't garbage collect it!
mouse_pointer = LowLevelMouseProc(lambda n, w, l: 1 if n >= 0 else user32.CallNextHookEx(None, n, w, l))


def set_custom_cursor(path):
    handle = user32.LoadCursorFromFileW(path)
    user32.SetSystemCursor(handle, OCR_NORMAL)

def restore_system_cursors():
    # SPI_SET_CURSORS = 0x0057
    # This tells Windows to reload all cursors from the registry/settings
    user32.SystemParametersInfoW(0x0057, 0, None, 0)

def change_flag(flag):
    global mouse_brake_flag
    mouse_brake_flag = flag

# Register the Win key ONCE when the script starts
keyboard.on_press_key('win', lambda _: change_flag(True))

def move_mouse():
    try:
        user32.SetProcessDPIAware()
    except AttributeError:
        pass
    width = user32.GetSystemMetrics(0)
    height = user32.GetSystemMetrics(1)
    off_x = width + 1
    off_y = height - height
    user32.SetCursorPos(off_x, off_y)

def block_mouse():
    global mouse_brake_flag

    # Reset the flag at the very start of every run
    mouse_brake_flag = False

    h_instance = kernel32.GetModuleHandleW(None)
    hook_id = user32.SetWindowsHookExW(WH_MOUSE_LL, mouse_pointer, h_instance, 0)

    if not hook_id:
        return

    move_mouse()
    set_custom_cursor(cursor_path)
    try:
        msg = wintypes.MSG()
        while True:  # loop_control is redundant if we use mouse_brake_flag
            if mouse_brake_flag:
                break

            # Pump the message queue (Required for Low Level Hooks to work)
            if user32.PeekMessageW(ctypes.byref(msg), None, 0, 0, 0x0001):
                user32.TranslateMessage(ctypes.byref(msg))
                user32.DispatchMessageW(ctypes.byref(msg))

            time.sleep(0.01)  # Reduced sleep for better responsiveness

    except KeyboardInterrupt:
        pass
    finally:
        user32.UnhookWindowsHookEx(hook_id)
        restore_system_cursors()
        # DO NOT call keyboard.unhook_all() here,
        # otherwise the 'win' key stops working for the next time you call block_mouse()