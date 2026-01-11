from PySide6.QtWidgets import (QMenu, QSystemTrayIcon, QApplication, QVBoxLayout, QListWidget,
                               QPushButton, QFileDialog, QMainWindow, QWidget, QMessageBox, QHBoxLayout,
                               QListWidgetItem, QSizePolicy, QInputDialog)
from PySide6.QtGui import QIcon, QAction, QPixmap, QImage, QActionGroup
from PySide6.QtCore import QCoreApplication, QSettings, Qt, QSize, Signal, QThread
from pathlib import Path
from PIL import Image
from RefreshRateSwitch import DevMode
import json
import sys
import os
import configparser
import ctypes
import ctypes.wintypes as wintypes
import win32com.client
import io
import urllib.request
import time
import subprocess
import winsound

KERNEL_32 = ctypes.WinDLL("kernel32")
USER_32 = ctypes.WinDLL("user32")


class ProcessCheckEntry32(ctypes.Structure):
    _fields_ = [
        ('dwSize', wintypes.DWORD),
        ('cntUsage', wintypes.DWORD),
        ('th32ProcessID', wintypes.DWORD),
        ('th32DefaultHeapID', ctypes.POINTER(ctypes.c_ulong)),
        ('th32ModuleID', wintypes.DWORD),
        ('cntThreads', wintypes.DWORD),
        ('th32ParentProcessID', wintypes.DWORD),
        ('pcPriClassBase', ctypes.c_long),
        ('dwFlags', wintypes.DWORD),
        ('szExeFile', wintypes.CHAR * 260),
    ]


class ProcessMonitor(QWidget):
    finished = Signal()
    notification = Signal(bool)

    def __init__(self, process_list, is_refresh):
        super().__init__()
        self.delay = None
        self.reverse_toggle = None
        self.shutting_down = False
        self.manual_hdr = None
        self.exception_msg = None
        self.primary_monitor = None
        self.found_process = False
        self.main_process = None
        # noinspection SpellCheckingInspection
        self.noti_state = None
        self.is_refresh = is_refresh
        self.current_refresh_rate = None
        self.ENUM_CURRENT_SETTINGS = -1
        self.CDS_UPDATE_REGISTRY = 0x01
        self.DISPLAY_CHANGE_SUCCESSFUL = 0

        self.finished.connect(self.on_finished_show_msg, Qt.ConnectionType.QueuedConnection)
        self.process_thread = QThread()
        self.process_list = process_list

        self.hdr_switch = ctypes.CDLL(r"Dependency\HDRSwitch.dll")
        self.SetGlobalHDRState = self.hdr_switch.SetGlobalHDRState
        self.SetGlobalHDRState.arg_types = [ctypes.c_bool]
        self.SetGlobalHDRState.restype = None

        self.SetPrimaryHDRState = self.hdr_switch.SetHDRonPrimary
        self.SetPrimaryHDRState.arg_types = [ctypes.c_bool]
        self.SetPrimaryHDRState.restype = None

        self.is_hdr_running = self.hdr_switch.GetGlobalHDRState
        self.is_hdr_running.restype = ctypes.c_bool

    @staticmethod
    def get_appdata_path(filename):
        appdata_dir = os.environ['APPDATA']
        app_dir = 'PyAutoActions'
        full_path = os.path.join(appdata_dir, app_dir)

        if not os.path.exists(full_path):
            os.makedirs(full_path)

        return os.path.join(full_path, filename)

    def process_monitor(self):
        while not self.shutting_down:
            try:
                if self.manual_hdr:
                    time.sleep(20)
                    self.manual_hdr = False

                if not self.found_process:
                    self.process_thread.run = self.process_check
                    self.process_thread.start()
                else:
                    if not self.is_process_running(self.main_process):
                        self.found_process = False
                        self.manual_hdr = False
                        if self.reverse_toggle == "HDR To SDR":
                            self.toggle_hdr(True)  # Enable HDR when process exits
                            if self.noti_state:
                                self.notification.emit(True)
                        else:
                            self.toggle_hdr(False)  # Disable HDR when process exits if "SDR To HDR"
                            if self.noti_state:
                                self.notification.emit(False)

                # Add delay based on self.delay value
                if self.delay == "High":
                    time.sleep(5)
                elif self.delay == "Medium":
                    time.sleep(3)
                elif self.delay == "Low":
                    time.sleep(1)

            except RuntimeError:
                break
            except Exception as e:
                self.exception_msg = f"process_monitor: {e}"
                self.finished.emit()
                break

    def process_check(self):
        try:
            for process in self.process_list:
                base_process = os.path.basename(process)
                i = self.is_process_running(base_process)
                if i:
                    if self.reverse_toggle == "SDR To HDR":
                        self.found_process = True
                        self.main_process = base_process
                        self.toggle_hdr(True)  # Enable HDR at process launch

                        if self.noti_state:
                            self.notification.emit(True)
                        break

                    elif self.reverse_toggle == "HDR To SDR":
                        self.found_process = True
                        self.main_process = base_process
                        self.toggle_hdr(False)  # Disable HDR at process launch

                        if self.noti_state:
                            self.notification.emit(False)
                        break

        except Exception as e:
            self.shutting_down = True
            self.exception_msg = f"process_check: {e}"
            self.finished.emit()
            return

    def toggle_hdr(self, enable):
        try:
            if self.is_refresh:
                if self.reverse_toggle == "SDR To HDR":
                    if enable:
                        self.switch_refresh_rate()
                    else:
                        self.switch_back_refresh_rate()
                elif self.reverse_toggle == "HDR To SDR":
                    if not enable:
                        self.switch_refresh_rate()
                    else:
                        self.switch_back_refresh_rate()

            if self.primary_monitor:
                self.SetPrimaryHDRState(enable)
            else:
                self.SetGlobalHDRState(enable)

        except Exception as e:
            self.exception_msg = f"toggle_hdr: {e}"
            self.finished.emit()

    def check_json_data(self):
        json_path = self.get_appdata_path("refresh_rate_data.json")
        with open(json_path) as f:
            data = json.load(f)
        json_text = json.dumps(data)
        if self.main_process in json_text:
            return True
        else:
            return False

    def get_refresh_from_json(self):
        json_path = self.get_appdata_path("refresh_rate_data.json")
        with open(json_path) as f:
            data = json.load(f)

        refresh_rate = data[self.main_process]
        return refresh_rate

    def switch_refresh_rate(self):
        if self.is_refresh:
            proceed = self.check_json_data()
            if proceed:
                target_refresh_rate = self.get_refresh_from_json()
                dev_mode = DevMode()
                dev_mode.dmSize = ctypes.sizeof(DevMode)
                USER_32.EnumDisplaySettingsW(None, self.ENUM_CURRENT_SETTINGS, ctypes.byref(dev_mode))
                self.current_refresh_rate = dev_mode.dmDisplayFrequency
                dev_mode.dmDisplayFrequency = int(target_refresh_rate)
                dev_mode.dmFields = 0x400000
                result = USER_32.ChangeDisplaySettingsExW(None, ctypes.byref(dev_mode), None,
                                                          self.CDS_UPDATE_REGISTRY, None)
                if result == self.DISPLAY_CHANGE_SUCCESSFUL:
                    pass
                else:
                    self.exception_msg = f"switch_refresh_rate: Failed to change refresh_rate"
                    self.finished.emit()

    def switch_back_refresh_rate(self):
        if self.is_refresh:
            proceed = self.check_json_data()
            if proceed:
                dev_mode = DevMode()
                dev_mode.dmSize = ctypes.sizeof(DevMode)
                dev_mode.dmDisplayFrequency = int(self.current_refresh_rate)
                dev_mode.dmFields = 0x400000
                result = USER_32.ChangeDisplaySettingsExW(None, ctypes.byref(dev_mode), None,
                                                          self.CDS_UPDATE_REGISTRY, None)
                if result == self.DISPLAY_CHANGE_SUCCESSFUL:
                    pass
                else:
                    self.exception_msg = f"switch_back_refresh_rate: Failed to change refresh_rate"
                    self.finished.emit()

    # noinspection PyTypeChecker
    def is_process_running(self, process_name: str) -> bool:
        try:
            # Take a snapshot of all processes
            h_snapshot = KERNEL_32.CreateToolhelp32Snapshot(0x00000002, 0)
            if h_snapshot == wintypes.HANDLE(-1).value:
                raise ctypes.WinError(ctypes.get_last_error())

            entry = ProcessCheckEntry32()
            entry.dwSize = ctypes.sizeof(ProcessCheckEntry32)

            found = False
            if KERNEL_32.Process32First(h_snapshot, ctypes.byref(entry)):
                while True:
                    exe_name = entry.szExeFile.decode(errors='ignore')
                    if exe_name.lower() == process_name.lower():
                        found = True
                        break
                    if not KERNEL_32.Process32Next(h_snapshot, ctypes.byref(entry)):
                        break

            KERNEL_32.CloseHandle(h_snapshot)
            return found
        except Exception as e:
            self.exception_msg = f"is_process_running {e}"
            self.finished.emit()
            return False

    def on_finished_show_msg(self):
        warning_message_box = QMessageBox()
        warning_message_box.setWindowTitle("PyAutoActions Error")
        warning_message_box.setWindowIcon(QIcon(r"Resources\main.ico"))
        warning_message_box.setFixedSize(400, 200)
        warning_message_box.setIcon(QMessageBox.Icon.Critical)
        warning_message_box.setText(f"{self.exception_msg}")
        winsound.MessageBeep()
        warning_message_box.exec()


class BitMapInfoHeaders(ctypes.Structure):
    _fields_ = [("biSize", ctypes.c_uint),
                ("biWidth", ctypes.c_int),
                ("biHeight", ctypes.c_int),
                ("biPlanes", ctypes.c_ushort),
                ("biBitCount", ctypes.c_ushort),
                ("biCompression", ctypes.c_uint),
                ("biSizeImage", ctypes.c_uint),
                ("biXPixelsPerMeter", ctypes.c_int),
                ("biYPixelsPerMeter", ctypes.c_int),
                ("biClrUsed", ctypes.c_uint),
                ("biClrImportant", ctypes.c_uint)]


# noinspection SpellCheckingInspection
class WNDCLASS(ctypes.Structure):
    _fields_ = [
        ("style", wintypes.UINT),
        ("lpfnWndProc", ctypes.WINFUNCTYPE(ctypes.c_long,
                                           wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM)),
        ("cbClsExtra", ctypes.c_int),
        ("cbWndExtra", ctypes.c_int),
        ("hInstance", wintypes.HINSTANCE),
        ("hIcon", wintypes.HANDLE),
        ("hCursor", wintypes.HANDLE),
        ("hbrBackground", wintypes.HANDLE),
        ("lpszMenuName", wintypes.LPCWSTR),
        ("lpszClassName", wintypes.LPCWSTR),
    ]


class MainWindow(QMainWindow):
    warning_signal = Signal()
    update_signal = Signal()
    refresh_signal = Signal()
    display_change_signal = Signal()

    def __init__(self):
        super().__init__()
        self.settings = QSettings("7gxycn08@Github", "PyAutoActions")
        self.warning_signal.connect(self.warning_box, Qt.ConnectionType.QueuedConnection)
        self.update_signal.connect(self.update_box, Qt.ConnectionType.QueuedConnection)
        self.refresh_signal.connect(self.refresh_box, Qt.ConnectionType.QueuedConnection)
        self.display_change_signal.connect(self.prewarm_window, Qt.ConnectionType.QueuedConnection)
        self.setAcceptDrops(True)
        self.dropped_file_path = None
        self.current_file_path = None
        self.refresh = None
        self.reverse_status = None
        self.exception_msg = None
        self.update_msg = None
        self.ICON_SIZE = 64
        self.action_names = []
        self.monitor_thread = None
        self.boot_status = None
        self.display_change_flag = True

        self.display_change_thread = QThread()
        self.monitor_thread = QThread()
        self.update_thread = QThread()
        self.process_launch_thread = QThread()
        self.run_as_admin_thread = QThread()
        self.save_config_thread = QThread()

        self.script_path = f"{os.path.abspath(sys.argv[0])}"
        self.config = configparser.ConfigParser()
        self.load_or_create_config()
        self.config.read(self.get_appdata_path("processlist.ini"))
        self.list_str = self.config['HDR_APPS']['processes']
        self.process_list = self.list_str.split(', ') if self.list_str else []

        self.current_version = 139  # Version Checking Number.
        self.setWindowTitle("PyAutoActions v1.3.9")
        self.setWindowIcon(QIcon(os.path.abspath(r"Resources\main.ico")))
        self.setGeometry(100, 100, 600, 400)

        self.menu_bar = self.menuBar()
        self.file_menu = self.menu_bar.addMenu('File')
        self.check_for_update_action = QAction('Check for Update on Startup', self.file_menu)
        self.check_for_update_action.setCheckable(True)
        self.check_for_update_action.triggered.connect(self.save_update_settings)

        self.notifications_action = QAction('Enable Notifications', self.file_menu)
        self.notifications_action.setCheckable(True)
        self.notifications_action.triggered.connect(self.save_update_settings)

        self.refresh_rate_switching_action = QAction("Enable Refresh Rate Switching", self.file_menu)
        self.refresh_rate_switching_action.setCheckable(True)
        self.refresh_rate_switching_action.triggered.connect(self.save_update_settings)

        self.file_menu.addSeparator()

        self.about_in_menu_bar = QAction(QIcon(r"Resources\about.ico"), 'About', self)
        self.about_in_menu_bar.triggered.connect(self.about_page)
        self.exit_from_menu_bar = QAction(QIcon(r"Resources\exit.ico"), 'Exit Application', self)
        self.exit_from_menu_bar.triggered.connect(self.close_tray_icon)
        self.file_menu.addActions([self.check_for_update_action, self.notifications_action,
                                   self.refresh_rate_switching_action,
                                   self.about_in_menu_bar, self.exit_from_menu_bar])

        self.monitor_menu = self.menu_bar.addMenu('Monitor Selection')
        self.all_action = QAction('All Monitors', self.monitor_menu)
        self.all_action.setCheckable(True)
        self.all_action.triggered.connect(self.all_monitors)
        self.primary_action = QAction('Primary Monitor', self.monitor_menu)
        self.primary_action.setCheckable(True)
        self.primary_action.triggered.connect(self.primary_monitor)
        self.monitor_menu.addActions([self.all_action, self.primary_action])

        self.delay_menu = self.menu_bar.addMenu('Detection')
        self.low_delay = QAction('Low', self.delay_menu)
        self.low_delay.setCheckable(True)
        self.low_delay.triggered.connect(lambda: self.update_delay("Low"))

        self.medium_delay = QAction('Medium', self.delay_menu)
        self.medium_delay.setCheckable(True)
        self.medium_delay.triggered.connect(lambda: self.update_delay("Medium"))

        self.high_delay = QAction('High', self.delay_menu)
        self.high_delay.setCheckable(True)
        self.high_delay.triggered.connect(lambda: self.update_delay("High"))

        self.delay_menu.addActions([self.low_delay, self.medium_delay, self.high_delay])

        self.reverse_toggle_menu = self.menu_bar.addMenu('Toggle Mode')

        self.sdr2hdr = QAction('SDR To HDR', self.reverse_toggle_menu)
        self.sdr2hdr.setCheckable(True)
        self.sdr2hdr.triggered.connect(lambda: self.update_reverse("SDR To HDR"))

        self.hdr2sdr = QAction('HDR To SDR', self.reverse_toggle_menu)
        self.hdr2sdr.setCheckable(True)
        self.hdr2sdr.triggered.connect(lambda: self.update_reverse("HDR To SDR"))

        self.reverse_toggle_menu.addActions([self.sdr2hdr, self.hdr2sdr])

        self.action_group = QActionGroup(self)
        self.action_group.addAction(self.low_delay)
        self.action_group.addAction(self.medium_delay)
        self.action_group.addAction(self.high_delay)
        self.action_group.setExclusive(True)
        self.action_group.triggered.connect(self.save_group_settings)

        self.action_group_2 = QActionGroup(self)
        self.action_group_2.addAction(self.sdr2hdr)
        self.action_group_2.addAction(self.hdr2sdr)
        self.action_group_2.setExclusive(True)
        self.action_group_2.triggered.connect(self.save_group_settings_2)

        self.action_group_3 = QActionGroup(self)
        self.action_group_3.addAction(self.all_action)
        self.action_group_3.addAction(self.primary_action)
        self.action_group_3.setExclusive(True)
        self.action_group_3.triggered.connect(self.save_group_settings_3)

        self.central_widget = QWidget(self)
        self.setCentralWidget(self.central_widget)
        self.list_widget = QListWidget()
        size_policy = QSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.list_widget.setSizePolicy(size_policy)
        self.list_widget.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.list_widget.customContextMenuRequested.connect(self.show_qlw_context_menu)
        self.list_widget.itemDoubleClicked.connect(self.double_click_run)

        self.add_button = QPushButton('Add Application')
        self.remove_button = QPushButton('Remove Application')

        self.add_button.setFixedSize(150, 25)
        self.remove_button.setFixedSize(150, 25)

        layout = QVBoxLayout(self.central_widget)
        layout.setContentsMargins(5, 0, 5, 10)
        layout.setSpacing(5)
        button_layout = QHBoxLayout()

        layout.addWidget(self.list_widget)
        layout.addLayout(button_layout)

        button_layout.addStretch()
        button_layout.addWidget(self.add_button)
        button_layout.addWidget(self.remove_button)
        button_layout.addStretch()

        self.add_button.clicked.connect(self.add_exe)
        self.remove_button.clicked.connect(self.remove_selected_entry)
        self.menu = QMenu()
        self.menu.setWindowFlag(Qt.WindowType.WindowStaysOnTopHint, True)
        self.menu.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.menu.setWindowFlags(self.menu.windowFlags() | Qt.WindowType.FramelessWindowHint)

        self.tray_icon = QSystemTrayIcon(self)
        self.tray_icon.setToolTip("PyAutoActions")
        self.tray_icon.setIcon(QIcon(os.path.abspath(r"Resources\main.ico")))
        self.tray_icon.activated.connect(self.tray_icon_activated)
        self.tray_icon.setContextMenu(self.menu)

        self.submenu = QMenu('Game Launcher', self.menu)
        self.submenu.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.submenu.setWindowFlags(self.menu.windowFlags() | Qt.WindowType.FramelessWindowHint)
        self.submenu.setIcon(QIcon(r"Resources\main.ico"))
        self.menu.addMenu(self.submenu)
        self.menu.addSeparator()

        self.start_hidden_action = QAction('Start In Tray', self.menu)
        self.start_hidden_action.setCheckable(True)
        self.start_hidden_action.setChecked(bool(self.settings.value("start_hidden", defaultValue=False, type=bool)))
        self.start_hidden_action.triggered.connect(self.toggle_start_hidden)

        self.run_on_boot_action = QAction('Run on System Boot', self.menu)
        self.run_on_boot_action.setCheckable(True)
        if self.already_added_shortcut():
            self.run_on_boot_action.setChecked(True)
        else:
            self.run_on_boot_action.setChecked(False)
        self.run_on_boot_action.triggered.connect(self.run_on_boot)

        self.about_button = QAction(QIcon(r"Resources\about.ico"), 'About')
        self.about_button.triggered.connect(self.about_page)

        self.action_exit = QAction(QIcon(r"Resources\exit.ico"), 'Exit')
        self.action_exit.triggered.connect(self.close_tray_icon)

        self.menu.addActions([self.start_hidden_action, self.run_on_boot_action, self.about_button, self.action_exit])
        self.start_hidden_checked = self.settings.value("start_hidden", defaultValue=False, type=bool)
        self.start_hidden_action.setChecked(bool(self.start_hidden_checked))
        self.tray_icon.setContextMenu(self.menu)
        self.start_hidden_check()
        self.tray_icon.show()

        delay = self.settings.value("GroupSettings", defaultValue="High")
        mode = self.settings.value("GroupSettings2", defaultValue="SDR To HDR")
        monitors = self.settings.value("GroupSettings3", defaultValue="All Monitors")
        update = self.settings.value("check_for_updates", defaultValue=True, type=bool)
        notify = self.settings.value("notifications", defaultValue=True, type=bool)
        refresh = self.settings.value("refresh_rate_switching", defaultValue=True, type=bool)

        self.check_for_update_action.setChecked(bool(update))
        self.notifications_action.setChecked(bool(notify))
        self.refresh_rate_switching_action.setChecked(bool(refresh))

        self.monitor = ProcessMonitor(self.process_list, refresh)

        self.monitor_thread.run = self.monitor.process_monitor
        self.monitor_thread.start()
        self.monitor.delay = delay  # Update process monitor so it stays in sync upon restarts.
        self.display_change_thread.run = self.display_change_monitor
        self.display_change_thread.start()
        # noinspection SpellCheckingInspection
        self.monitor.noti_state = notify
        self.load_processes_from_config()
        self.create_actions()
        self.monitor.notification.connect(self.show_notification)

        if monitors == "All Monitors":
            self.all_monitors()
        else:
            self.primary_monitor()

        if self.check_for_update_action.isChecked():
            self.update_thread.run = self.check_for_update
            self.update_thread.start()

        self.restore_group_settings()
        self.restore_group_settings_2()
        self.restore_group_settings_3()
        self.update_delay(delay)
        self.update_reverse(mode)

    # --- window procedure ---
    def wnd_proc(self, hwnd: int, msg: int, wparam: int, lparam: int) -> int:
        user32 = ctypes.WinDLL("user32")
        if msg == 0x007E:
            self.display_change_signal.emit()
        elif msg == 0x0002:
            user32.PostQuitMessage(0)
        return user32.DefWindowProcW(hwnd, msg, wparam, lparam)

    # noinspection SpellCheckingInspection
    def display_change_monitor(self):
        h_instance = KERNEL_32.GetModuleHandleW(None)
        class_name = "DisplayWatch"

        wndclass = WNDCLASS()
        wndclass.style = 0x0002 | 0x0001
        wnd_proc_type = ctypes.WINFUNCTYPE(ctypes.c_long,
                                           wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM)
        wnd_proc_c = wnd_proc_type(self.wnd_proc)
        wndclass.lpfnWndProc = wnd_proc_c
        wndclass.hInstance = h_instance
        wndclass.lpszClassName = class_name
        wndclass.hIcon = None
        wndclass.hCursor = None
        wndclass.hbrBackground = None
        wndclass.lpszMenuName = None
        wndclass.cbClsExtra = wndclass.cbWndExtra = 0

        if not USER_32.RegisterClassW(ctypes.byref(wndclass)):
            raise ctypes.WinError()

        hwnd = USER_32.CreateWindowExW(
            0, class_name, "hidden", 0,
            0, 0, 0, 0,
            0, 0, h_instance, None
        )
        if not hwnd:
            raise ctypes.WinError()

        msg = wintypes.MSG()
        while self.display_change_flag:  # check flag each iteration
            while USER_32.PeekMessageW(ctypes.byref(msg), 0, 0, 0, 1):
                USER_32.TranslateMessage(ctypes.byref(msg))
                USER_32.DispatchMessageW(ctypes.byref(msg))
            time.sleep(0.01)  # small sleep to avoid 100% CPU

    def prewarm_window(self):
        self.move(-10000, -10000)  # off-screen
        self.show()
        self.hide()
        self.center_window()

    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls():  # Files are sent as URLs
            event.acceptProposedAction()
        else:
            event.ignore()

    def dropEvent(self, event):
        urls = event.mimeData().urls()
        if urls:
            # Get the first file path
            self.dropped_file_path = urls[0].toLocalFile()

            # Confirm action
            event.acceptProposedAction()
            self.add_exe()

    def show_notification(self, status):
        if status:
            self.tray_icon.showMessage(
                "",
                "HDR Turned On.",
                QSystemTrayIcon.MessageIcon.Information,
                5000  # duration in ms
            )
        if not status:
            self.tray_icon.showMessage(
                "",
                "HDR Turned OFF.",
                QSystemTrayIcon.MessageIcon.Information,
                5000  # duration in ms
            )

    def all_monitors(self):
        self.monitor.global_monitors = True
        self.monitor.primary_monitor = False

    def primary_monitor(self):
        self.monitor.primary_monitor = True
        self.monitor.global_monitors = False

    def center_window(self):
        screen = app.primaryScreen()
        screen_geometry = screen.availableGeometry()
        frame_geom = self.frameGeometry()
        center_point = screen_geometry.center()  # Center of the screen
        frame_geom.moveCenter(center_point)  # Move the window's frame to screen center
        self.move(frame_geom.topLeft())  # Position the window

    def check_for_update(self):
        update_url = "https://raw.githubusercontent.com/7gxycn08/PyAutoActions/main/current_version.txt"
        try:
            with urllib.request.urlopen(update_url) as response:
                content = response.read().decode().strip()

            number = int(content)
            if self.current_version < number:
                self.update_msg = f"PyAutoActions v{'.'.join(str(number))} Update Available.\n\n Open releases page?"
                self.update_signal.emit()

        except Exception as e:
            self.exception_msg = f"Check_For_Update Error: {e}"
            self.warning_signal.emit()

    def save_update_settings(self):
        if self.check_for_update_action.isChecked():
            self.settings.setValue("check_for_updates", True)
            self.check_for_update()
        else:
            self.settings.setValue("check_for_updates", False)

        if self.notifications_action.isChecked():
            self.settings.setValue("notifications", True)
            # noinspection SpellCheckingInspection
            self.monitor.noti_state = True
        else:
            self.settings.setValue("notifications", False)
            # noinspection SpellCheckingInspection
            self.monitor.noti_state = False

        if self.refresh_rate_switching_action.isChecked():
            self.settings.setValue("refresh_rate_switching", True)
            self.monitor.is_refresh = True
        else:
            self.settings.setValue("refresh_rate_switching", False)
            self.monitor.is_refresh = False

    def save_group_settings(self):
        for action in self.action_group.actions():
            if action.isChecked():
                self.settings.setValue("GroupSettings", action.text())
                break

    def save_group_settings_2(self):
        for action in self.action_group_2.actions():
            if action.isChecked():
                self.settings.setValue("GroupSettings2", action.text())
                break

    def save_group_settings_3(self):
        for action in self.action_group_3.actions():
            if action.isChecked():
                self.settings.setValue("GroupSettings3", action.text())
                break

    def restore_group_settings(self):
        checked_action = self.settings.value("GroupSettings", "High")
        for action in self.action_group.actions():
            if action.text() == checked_action:
                action.setChecked(True)
                break

    def restore_group_settings_2(self):
        checked_action = self.settings.value("GroupSettings2", "SDR To HDR")
        for action in self.action_group_2.actions():
            if action.text() == checked_action:
                action.setChecked(True)
                break

    def restore_group_settings_3(self):
        checked_action = self.settings.value("GroupSettings3", "All Monitors")
        if checked_action == "All Monitors":
            self.monitor.global_monitors = True
            self.monitor.primary_monitor = False
        else:
            self.monitor.global_monitors = False
            self.monitor.primary_monitor = True

        for action in self.action_group_3.actions():
            if action.text() == checked_action:
                action.setChecked(True)
                break

    def start_hidden_check(self):
        if self.start_hidden_checked:
            self.prewarm_window()
            self.hide()
        else:
            self.center_window()
            self.show()

    def update_delay(self, delay):
        self.monitor.delay = delay

    def update_reverse(self, status):
        if status == "SDR To HDR":
            self.monitor.SetGlobalHDRState(False)
        elif status == "HDR To SDR":
            self.monitor.SetGlobalHDRState(True)
        else:
            pass
        self.monitor.reverse_toggle = status
        self.reverse_status = status

    def warning_box(self):
        warning_message_box = QMessageBox(self)
        warning_message_box.setIcon(QMessageBox.Icon.Warning)
        warning_message_box.setWindowTitle("PyAutoActions Error")
        warning_message_box.setWindowIcon(QIcon(r"Resources\main.ico"))
        warning_message_box.setFixedSize(400, 200)
        warning_message_box.setText(f"{self.exception_msg}")
        winsound.MessageBeep()
        screen = app.primaryScreen()
        screen_geometry = screen.availableGeometry()
        x = (screen_geometry.width() - warning_message_box.width()) // 2
        y = (screen_geometry.height() - warning_message_box.height()) // 2
        warning_message_box.move(x, y)
        warning_message_box.exec()

    def update_box(self):
        update_message_box = QMessageBox(self)
        update_message_box.setIcon(QMessageBox.Icon.Information)
        update_message_box.setWindowTitle("PyAutoActions")
        update_message_box.setWindowIcon(QIcon(r"Resources\main.ico"))
        update_message_box.setStandardButtons(QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        update_message_box.setFixedSize(400, 200)
        update_message_box.setText(f"{self.update_msg}")
        winsound.MessageBeep()
        screen = app.primaryScreen()
        screen_geometry = screen.availableGeometry()
        x = (screen_geometry.width() - update_message_box.width()) // 2
        y = (screen_geometry.height() - update_message_box.height()) // 2
        update_message_box.move(x, y)
        update_message_box.finished.connect(self.on_update_box_finished)
        update_message_box.exec()

    def on_update_box_finished(self, result):  # noqa
        if result == QMessageBox.StandardButton.Yes:
            subprocess.Popen("start https://github.com/7gxycn08/PyAutoActions/releases",
                             shell=True, creationflags=subprocess.CREATE_NEW_CONSOLE)

    def refresh_box(self):
        refresh_message_box = QMessageBox(self)
        refresh_message_box.setIcon(QMessageBox.Icon.Question)
        refresh_message_box.setWindowTitle("PyAutoActions")
        refresh_message_box.setWindowIcon(QIcon(r"Resources\main.ico"))
        refresh_message_box.setStandardButtons(QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        refresh_message_box.setFixedSize(400, 200)
        refresh_message_box.setText(f"Do you want to enable refresh rate switching for this exe?")
        winsound.MessageBeep()
        screen = app.primaryScreen()
        screen_geometry = screen.availableGeometry()
        x = (screen_geometry.width() - refresh_message_box.width()) // 2
        y = (screen_geometry.height() - refresh_message_box.height()) // 2
        refresh_message_box.move(x, y)
        refresh_message_box.finished.connect(self.on_refresh_box_finished)
        refresh_message_box.exec()

    def on_refresh_box_finished(self, result):
        if result == QMessageBox.StandardButton.Yes:
            self.refresh_rate_entry()

    def show_qlw_context_menu(self, pos):
        item = self.list_widget.itemAt(pos)
        if item is None:
            return  # Only show menu if an item is clicked

        menu = QMenu()
        set_refresh_action = menu.addAction("Set Refresh Rate")
        set_command_action = menu.addAction("Set Command Args")
        action = menu.exec(self.list_widget.mapToGlobal(pos))

        if action == set_refresh_action:
            self.current_file_path = item.text()
            self.refresh_rate_entry()
        elif action == set_command_action:
            self.current_file_path = item.text()
            self.command_args_entry()

    def command_args_entry(self):
        command_args = QInputDialog(self)
        command_args.setWindowTitle("PyAutoActions")
        command_args.setLabelText("Enter Command Args:")
        command_args.setWindowIcon(QIcon(r"Resources\main.ico"))
        command_args.setFixedSize(400, 200)
        command_args.textValueSelected.connect(self.save_command_args_info)
        winsound.MessageBeep()
        screen = app.primaryScreen()
        screen_geometry = screen.availableGeometry()
        x = (screen_geometry.width() - command_args.width()) // 2
        y = (screen_geometry.height() - command_args.height()) // 2
        command_args.move(x, y)
        command_args.show()  # Non-blocking

    def refresh_rate_entry(self):
        refresh_dialog = QInputDialog(self)
        refresh_dialog.setWindowTitle("PyAutoActions")
        refresh_dialog.setLabelText("Enter Target Refresh Rate Value:")
        refresh_dialog.setWindowIcon(QIcon(r"Resources\main.ico"))
        refresh_dialog.setFixedSize(400, 200)
        refresh_dialog.textValueSelected.connect(self.save_refresh_info)
        winsound.MessageBeep()
        screen = app.primaryScreen()
        screen_geometry = screen.availableGeometry()
        x = (screen_geometry.width() - refresh_dialog.width()) // 2
        y = (screen_geometry.height() - refresh_dialog.height()) // 2
        refresh_dialog.move(x, y)
        refresh_dialog.show()  # Non-blocking

    def exit_confirm_box(self):
        exit_message_box = QMessageBox(self)
        exit_message_box.setIcon(QMessageBox.Icon.Question)
        exit_message_box.setStandardButtons(QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        exit_message_box.setWindowTitle("PyAutoActions")
        exit_message_box.setWindowIcon(QIcon(r"Resources\main.ico"))
        exit_message_box.setFixedSize(400, 200)
        exit_message_box.setText(f"Do you want to exit PyAutoActions?")
        winsound.MessageBeep()
        screen = app.primaryScreen()
        screen_geometry = screen.availableGeometry()
        x = (screen_geometry.width() - exit_message_box.width()) // 2
        y = (screen_geometry.height() - exit_message_box.height()) // 2
        exit_message_box.move(x, y)
        result = exit_message_box.exec()
        return result

    def save_command_args_info(self, command_args):
        if command_args:
            json_path = self.get_appdata_path("command_args_data.json")
            file_path = Path(json_path)
            base_exe = os.path.basename(self.current_file_path)
            data = {f"{base_exe}": f"{command_args}"}  # new or updated values

            # Step 1: Load existing data if file exists
            if file_path.exists():
                with open(file_path, "r") as f:
                    existing_data = json.load(f)
            else:
                existing_data = {}

            # Step 2: Update existing data
            existing_data.update(data)

            # Step 3: Save back to file
            with open(file_path, "w") as f:
                json.dump(existing_data, f, indent=4)
        else:
            self.exception_msg = "save_command_args_info: Unexpected Error Occurred."
            self.warning_signal.emit()
            count = self.list_widget.count()
            if count > 0:
                last_item = self.list_widget.takeItem(count - 1)
                selected_text = last_item.text()
                exe_index_to_remove = self.process_list.index(selected_text)
                self.delete_submenu_action(exe_index_to_remove)
                self.process_list.pop(exe_index_to_remove)
                self.save_config()
                self.list_widget.takeItem(self.list_widget.row(last_item))
                self.create_actions()
                self.update_classes_variables()
                del last_item

    def save_refresh_info(self, refresh_rate):
        if refresh_rate.isdigit():
            json_path = self.get_appdata_path("refresh_rate_data.json")
            file_path = Path(json_path)
            base_exe = os.path.basename(self.current_file_path)
            data = {f"{base_exe}": f"{refresh_rate}"}  # new or updated values

            # Step 1: Load existing data if file exists
            if file_path.exists():
                with open(file_path, "r") as f:
                    existing_data = json.load(f)
            else:
                existing_data = {}

            # Step 2: Update existing data
            existing_data.update(data)

            # Step 3: Save back to file
            with open(file_path, "w") as f:
                json.dump(existing_data, f, indent=4)
        else:
            self.exception_msg = "save_refresh_info: Refresh Value Not a Valid Number."
            self.warning_signal.emit()
            count = self.list_widget.count()
            if count > 0:
                last_item = self.list_widget.takeItem(count - 1)
                selected_text = last_item.text()
                exe_index_to_remove = self.process_list.index(selected_text)
                self.delete_submenu_action(exe_index_to_remove)
                self.process_list.pop(exe_index_to_remove)
                self.save_config()
                self.list_widget.takeItem(self.list_widget.row(last_item))
                self.create_actions()
                self.update_classes_variables()
                del last_item

    def extract_icon(self, file_path, icon_index=0):
        try:
            shell32_dll = ctypes.WinDLL("shell32.dll")
            extract_icon_w = shell32_dll.ExtractIconW
            icon_handle = extract_icon_w(0, file_path, icon_index)
            if icon_handle <= 1:
                return None
        except Exception as e:
            self.exception_msg = f"extract_icon: {e}"
            self.warning_signal.emit()
            return None

        return icon_handle

    def get_icon_as_image_object(self, file_path, icon_index=0):
        try:
            icon_handle = self.extract_icon(file_path, icon_index)
            user32_dll = ctypes.WinDLL("user32.dll")
            get_dc = user32_dll.GetDC
            destroy_icon = user32_dll.DestroyIcon
            release_dc = user32_dll.ReleaseDC
            draw_icon_ex = user32_dll.DrawIconEx

            gdi32_dll = ctypes.WinDLL("gdi32")
            create_compatible_dc = gdi32_dll.CreateCompatibleDC
            create_compatible_bitmap = gdi32_dll.CreateCompatibleBitmap
            select_object = gdi32_dll.SelectObject
            get_di_bits = gdi32_dll.GetDIBits
            delete_object = gdi32_dll.DeleteObject
            delete_dc = gdi32_dll.DeleteDC

            if icon_handle is None:
                return None

            elif icon_handle:
                hdc = get_dc(0)
                mem_dc = create_compatible_dc(hdc)
                bitmap = create_compatible_bitmap(hdc, self.ICON_SIZE, self.ICON_SIZE)
                select_object(mem_dc, bitmap)

                draw_icon_ex(
                    mem_dc, 0, 0, icon_handle, self.ICON_SIZE, self.ICON_SIZE, 0, None, 0x0003 | 0x0008
                )

                bmp_header = BitMapInfoHeaders()
                bmp_header.biSize = ctypes.sizeof(BitMapInfoHeaders)
                bmp_header.biWidth = self.ICON_SIZE
                bmp_header.biHeight = -self.ICON_SIZE
                bmp_header.biPlanes = 1
                bmp_header.biBitCount = 32
                bmp_header.biCompression = 0

                bmp_str = ctypes.create_string_buffer(self.ICON_SIZE * self.ICON_SIZE * 4)
                get_di_bits(mem_dc, bitmap, 0, self.ICON_SIZE, bmp_str, ctypes.byref(bmp_header),
                            0)

                im = Image.frombuffer(
                    'RGBA',
                    (self.ICON_SIZE, self.ICON_SIZE),
                    bmp_str, 'raw', 'BGRA', 0, 1)  # noqa

                destroy_icon(icon_handle)
                delete_object(bitmap)
                delete_dc(mem_dc)
                release_dc(0, hdc)

                return im
        except AttributeError:
            self.exception_msg = "get_icon_as_image_object: Failed to get image object"
            self.warning_signal.emit()
            return None

    @staticmethod
    def resize_pixmap(pixmap, width, height):
        new_size = QSize(width, height)
        return pixmap.scaled(new_size, Qt.AspectRatioMode.KeepAspectRatio,
                             Qt.TransformationMode.SmoothTransformation)

    def pil_image_to_q_icon(self, image_object):
        if image_object is None:
            return QIcon(r"Resources\game.png")
        else:
            byte_array = io.BytesIO()
            image_object.save(byte_array, format='PNG')
            q_image = QImage()
            q_image.loadFromData(byte_array.getvalue())

            q_pixmap = QPixmap.fromImage(q_image)
            resized_pixmap = self.resize_pixmap(q_pixmap, 32, 32)
            return QIcon(resized_pixmap)

    def delete_submenu_action(self, index):
        if self.submenu.actions():
            item_to_delete = self.submenu.actions()[index]
            self.submenu.removeAction(item_to_delete)

    def create_actions(self):
        try:
            list_widget_items = [self.list_widget.item(i).text() for i in range(self.list_widget.count()) if
                                 self.list_widget.item(i).text()]
            unique_items_set = set()
            self.submenu.clear()

            if not list_widget_items:
                empty_action = QAction("Empty", self.menu)
                empty_action.setEnabled(False)
                self.submenu.addAction(empty_action)
                return
            else:
                for item_text in list_widget_items:
                    if item_text not in unique_items_set:
                        base_name = os.path.basename(item_text)
                        if base_name.endswith(".exe"):
                            base_name = base_name[:-4]
                        image_object = self.get_icon_as_image_object(item_text)
                        icon = self.pil_image_to_q_icon(image_object)
                        pixmap_icon = QIcon(icon)
                        new_action = QAction(pixmap_icon, base_name, self.menu)

                        def create_action_closure(item):
                            return lambda: self.on_action_triggered(item)

                        new_action.triggered.connect(create_action_closure(item_text))
                        self.submenu.addAction(new_action)
                        unique_items_set.add(item_text)

        except Exception as e:
            self.exception_msg = f"create_actions: {e}"
            self.warning_signal.emit()

    def run_as_admin(self, executable_path, command_exists):
        shell32_dll = ctypes.WinDLL("shell32.dll")
        shell_execute_w = shell32_dll.ShellExecuteW
        try:
            folder_path = os.path.dirname(executable_path)
            if not command_exists:
                shell_execute_w(None, "runas", executable_path, None, folder_path, 1)
            else:
                shell_execute_w(None, "runas", executable_path, command_exists, folder_path, 1)
        except Exception as e:
            self.exception_msg = f"run_as_admin: {e}"
            self.warning_signal.emit()

    def double_click_run(self):
        self.on_action_triggered(self.list_widget.currentItem().text())

    def on_action_triggered(self, path):
        try:
            self.monitor.main_process = os.path.basename(path)
            self.monitor.found_process = True
            self.monitor.manual_hdr = True
            self.monitor.reverse_toggle = self.reverse_status

            if self.monitor.noti_state:
                if self.reverse_status == "HDR To SDR":
                    self.show_notification(False)
                    self.monitor.toggle_hdr(False)
                else:
                    self.show_notification(True)
                    self.monitor.toggle_hdr(True)

            command_exists = self.get_command_arg(os.path.basename(path))
            if not command_exists:
                self.process_launch_thread.run = lambda: subprocess.run(path, cwd=os.path.dirname(path),
                                                                        shell=True, check=True)
                self.process_launch_thread.start()
            else:
                self.process_launch_thread.run = lambda: subprocess.run(path, command_exists, cwd=os.path.dirname(path),
                                                                        shell=True, check=True)
                self.process_launch_thread.start()

        except subprocess.CalledProcessError:
            self.run_as_admin_thread.run = lambda: self.run_as_admin(path, command_exists)
            self.run_as_admin_thread.start()
        except Exception as e:
            self.exception_msg = f"on_action_triggered: {e}"
            self.warning_signal.emit()

    def get_command_arg(self, exe_name):
        json_path = Path(self.get_appdata_path("command_args_data.json"))
        if not json_path.exists():
            return None
        try:
            with json_path.open("r", encoding="utf-8") as f:
                data = json.load(f)
            return data.get(exe_name)

        except Exception as e:
            self.exception_msg = f"get_command_arg: {e}"
            self.warning_signal.emit()
            return None

    def update_classes_variables(self):
        self.monitor.process_list = self.process_list

    def run_on_boot(self):
        checked = self.run_on_boot_action.isChecked()
        self.settings.setValue("run_on_boot", checked)
        state = self.already_added_shortcut()
        if not state:
            self.add_to_startup()
        else:
            self.remove_start_shortcut()

    def remove_start_shortcut(self):
        if self.already_added_shortcut():
            try:
                exe_name = "PyAutoActions"
                shortcut_name = exe_name + '.lnk'

                shell = win32com.client.Dispatch("WScript.Shell")
                startup_folder = shell.SpecialFolders("Startup")
                shortcut_path = os.path.join(startup_folder, shortcut_name)

                if os.path.exists(shortcut_path):
                    os.remove(shortcut_path)

            except Exception as e:
                self.exception_msg = f"remove_start_shortcut: {e}"
                self.warning_signal.emit()

    def toggle_start_hidden(self):
        checked = self.start_hidden_action.isChecked()
        self.settings.setValue("start_hidden", checked)

    def already_added_shortcut(self):
        try:
            exe_name = "PyAutoActions"
            shortcut_name = exe_name + '.lnk'

            shell = win32com.client.Dispatch("WScript.Shell")
            startup_folder = shell.SpecialFolders("Startup")
            shortcut_path = os.path.join(startup_folder, shortcut_name)

            if os.path.exists(shortcut_path):
                return True
            else:
                return False
        except Exception as e:
            self.exception_msg = f"already_added_shortcut: {e}"
            self.warning_signal.emit()

    def add_to_startup(self):
        if not self.already_added_shortcut():
            try:
                executable_name = "PyAutoActions.exe"
                icon_path = fr"{os.getcwd()}\Resources\main.ico"

                current_path = os.path.join(os.getcwd(), executable_name)

                shell = win32com.client.Dispatch("WScript.Shell")
                startup_folder = shell.SpecialFolders("Startup")
                shortcut_path = os.path.join(startup_folder, executable_name.replace('.exe', '.lnk'))

                shortcut = shell.CreateShortcut(shortcut_path)
                shortcut.TargetPath = current_path
                shortcut.WorkingDirectory = os.getcwd()
                shortcut.IconLocation = icon_path
                shortcut.save()

            except Exception as e:
                self.exception_msg = f"add_to_startup: {e}"
                self.warning_signal.emit()

    @staticmethod
    def about_page():
        subprocess.Popen("start https://github.com/7gxycn08/PyAutoActions",
                         shell=True, creationflags=subprocess.CREATE_NEW_CONSOLE)

    def tray_icon_activated(self, reason):
        if reason == QSystemTrayIcon.ActivationReason.Trigger:
            self.show_window()
        elif reason == QSystemTrayIcon.ActivationReason.Context:
            self.menu.show()

    def close_tray_icon(self):
        if self.exit_confirm_box() == QMessageBox.StandardButton.Yes:
            self.display_change_flag = False
            self.display_change_thread.wait()
            self.monitor.shutting_down = True
            self.tray_icon.setToolTip("Shutting Down")
            self.window().hide()
            self.monitor_thread.wait()
            QCoreApplication.quit()

    def show_window(self):
        self.center_window()
        self.show()
        self.activateWindow()

    # noinspection PyMethodMayBeStatic
    def remove_data_entry(self, process_key):
        json_path = self.get_appdata_path("refresh_rate_data.json")
        self.remove_data(json_path, process_key)
        json_path = self.get_appdata_path("command_args_data.json")
        self.remove_data(json_path, process_key)

    # noinspection PyMethodMayBeStatic
    def remove_data(self, json_path, process_key):
        with open(json_path, "r") as f:
            data = json.load(f)
        key = os.path.basename(process_key)
        if key in data:
            del data[key]
        with open(json_path, "w") as f:
            json.dump(data, f, indent=4)

    def remove_selected_entry(self):
        try:
            selected_item = self.list_widget.currentItem()

            if selected_item is not None and selected_item.text().strip():
                selected_text = selected_item.text()
                exe_index_to_remove = self.process_list.index(selected_text)
                self.delete_submenu_action(exe_index_to_remove)
                self.process_list.pop(exe_index_to_remove)
                self.save_config()
                self.list_widget.takeItem(self.list_widget.row(selected_item))
                self.create_actions()
                self.update_classes_variables()
                self.remove_data_entry(selected_text)

            else:
                self.exception_msg = "Nothing to remove."
                self.warning_signal.emit()

        except ValueError as ve:
            self.exception_msg = ve
            self.warning_signal.emit()
        except Exception as e:
            self.exception_msg = f"Nothing to remove. {e}"
            self.warning_signal.emit()

    def add_exe(self):
        try:
            if self.dropped_file_path:
                file_path = self.dropped_file_path
                self.current_file_path = file_path
                if self.refresh_rate_switching_action.isChecked() and file_path:
                    self.refresh_signal.emit()
            else:
                file_dialog = QFileDialog()
                file_path, _ = file_dialog.getOpenFileName(self, "Select Executable", "",
                                                           "Executable Files (*.exe)")
                self.current_file_path = file_path
                if self.refresh_rate_switching_action.isChecked() and file_path:
                    self.refresh_signal.emit()
            if file_path:
                exe_path = os.path.abspath(file_path)
                if exe_path in self.process_list:
                    self.exception_msg = f"Process {exe_path} already exists in the list."
                    self.warning_signal.emit()
                    self.dropped_file_path = None

                elif file_path[-4:].lower() != ".exe":
                    self.exception_msg = f"File {exe_path} is not a valid exe."
                    self.warning_signal.emit()
                    self.dropped_file_path = None

                else:
                    icon = self.get_icon_as_image_object(exe_path)
                    q_icon = self.pil_image_to_q_icon(icon)
                    list_item = QListWidgetItem()
                    list_item.setIcon(q_icon)
                    list_item.setText(exe_path)
                    self.list_widget.addItem(list_item)
                    self.create_actions()
                    self.process_list.append(exe_path)
                    self.save_config_thread.run = self.save_config
                    self.save_config_thread.start()
                    self.update_classes_variables()
                    self.dropped_file_path = None

        except Exception as e:
            self.exception_msg = f"add_exe: {e}"
            self.warning_signal.emit()
            self.dropped_file_path = None

    def load_or_create_config(self):
        config = self.config
        config_path = self.get_appdata_path("processlist.ini")
        try:
            if not os.path.isfile(config_path):
                with open(config_path, 'w', encoding="utf-8") as configfile:
                    config.add_section('HDR_APPS')
                    config.set('HDR_APPS', 'processes', '')
                    config.write(configfile)  # type: ignore
            else:
                config.read(config_path)
        except Exception as e:
            self.exception_msg = f"load_or_create_config: {e}"
            self.warning_signal.emit()

    @staticmethod
    def get_appdata_path(filename):
        appdata_dir = os.environ['APPDATA']
        app_dir = 'PyAutoActions'
        full_path = os.path.join(appdata_dir, app_dir)

        if not os.path.exists(full_path):
            os.makedirs(full_path)

        return os.path.join(full_path, filename)

    def save_config(self):
        try:
            self.list_str = ', '.join(self.process_list)
            self.config['HDR_APPS']['processes'] = self.list_str
            config_path = self.get_appdata_path('processlist.ini')
            with open(config_path, 'w') as configfile:
                self.config.write(configfile)  # type: ignore
                self.update_classes_variables()
        except Exception as e:
            self.exception_msg = f"save_config: {e}"
            self.warning_signal.emit()

    def load_processes_from_config(self):
        try:
            self.list_widget.clear()
            self.config.read(self.get_appdata_path("processlist.ini"))
            if 'HDR_APPS' in self.config and 'processes' in self.config['HDR_APPS']:
                process_list_str = self.config['HDR_APPS']['processes']
                processes = process_list_str.split(', ')
                for process in processes:
                    if process:
                        icon = self.get_icon_as_image_object(process)
                        q_icon = self.pil_image_to_q_icon(icon)
                        list_item = QListWidgetItem()
                        list_item.setIcon(q_icon)
                        list_item.setText(process)
                        self.list_widget.addItem(list_item)
                self.update_classes_variables()
        except Exception as e:
            self.exception_msg = f"load_processes_from_config: {e}"
            self.warning_signal.emit()


if __name__ == "__main__":
    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)
    app.setStyle("Fusion")
    window = MainWindow()
    sys.exit(app.exec())
