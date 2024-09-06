from PySide6.QtWidgets import (QMenu, QSystemTrayIcon, QApplication, QVBoxLayout, QListWidget,
                               QPushButton, QFileDialog, QMainWindow, QWidget, QMessageBox, QHBoxLayout,
                               QListWidgetItem, QSizePolicy)
from PySide6.QtGui import QIcon, QAction, QPixmap, QImage, QActionGroup, QCursor, QMouseEvent
from PySide6.QtCore import QCoreApplication, QSettings, Qt, QSize, Signal, QObject, QEvent
import sys
import os
import configparser
import ctypes
import win32com.client
from PIL import Image
import io
import uuid
import urllib.request
import time
import threading
import subprocess
import winsound


class ProcessMonitor(QWidget):
    finished = Signal()

    def __init__(self, process_list):
        super().__init__()
        self.delay = None
        self.reverse_toggle = None
        self.shutting_down = False
        self.manual_hdr = None
        self.exception_msg = None
        self.finished.connect(self.on_finished_show_msg, Qt.ConnectionType.QueuedConnection)

        self.process_thread = None

        self.process_list = process_list

        self.found_process = False
        self.main_process = None

        self.hdr_switch = ctypes.CDLL(r"Dependency\HDRSwitch.dll")
        self.SetGlobalHDRState = self.hdr_switch.SetGlobalHDRState
        self.SetGlobalHDRState.arg_types = [ctypes.c_bool]
        self.SetGlobalHDRState.restype = None

        self.is_hdr_running = self.hdr_switch.GetGlobalHDRState
        self.is_hdr_running.arg_types = [ctypes.c_uint32]
        self.is_hdr_running.restype = ctypes.c_bool
        self.uid = int(uuid.uuid4())
        self.toggle_state = self.is_hdr_running(ctypes.c_uint32(self.uid))

    def check_hdr_state(self):
        self.toggle_state = self.is_hdr_running(ctypes.c_uint32(self.uid))

    def process_monitor(self):
        while not self.shutting_down:
            try:
                if self.manual_hdr:
                    time.sleep(20)
                    self.manual_hdr = False

                if not self.found_process:
                    self.process_thread = threading.Thread(target=self.process_check, daemon=True)
                    self.process_thread.start()
                else:
                    self.check_hdr_state()
                    if not self.is_process_running(self.main_process):
                        self.found_process = False
                        self.manual_hdr = False
                        if self.reverse_toggle == "HDR To SDR":
                            self.toggle_hdr(True)  # Enable HDR when process exits
                        else:
                            self.toggle_hdr(False)  # Disable HDR when process exits if "SDR To HDR"

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
                if self.is_process_running(os.path.basename(process)):
                    self.check_hdr_state()
                    if self.reverse_toggle == "SDR To HDR" and not self.toggle_state:
                        self.found_process = True
                        self.main_process = os.path.basename(process)
                        self.toggle_hdr(True)  # Enable HDR at process launch
                        break
                    elif self.reverse_toggle == "HDR To SDR" and self.toggle_state:
                        self.found_process = True
                        self.main_process = os.path.basename(process)
                        self.toggle_hdr(False)  # Disable HDR at process launch
                        break

        except Exception as e:
            self.shutting_down = True
            self.exception_msg = f"process_check: {e}"
            self.finished.emit()
            return

    def toggle_hdr(self, enable):
        try:
            self.SetGlobalHDRState(enable)
        except Exception as e:
            self.exception_msg = f"toggle_hdr: {e}"
            self.finished.emit()

    # noinspection PyTypeChecker
    def is_process_running(self, process_name):
        process_query_limited_information = 0x1000

        try:
            processes = (ctypes.c_ulong * 2048)()
            cb = ctypes.c_ulong(ctypes.sizeof(processes))
            ctypes.windll.psapi.EnumProcesses(ctypes.byref(processes), cb, ctypes.byref(cb))

            process_count = cb.value // ctypes.sizeof(ctypes.c_ulong)
            for i in range(process_count):
                process_id = processes[i]
                process_handle = ctypes.windll.kernel32.OpenProcess(process_query_limited_information, False,
                                                                    process_id)

                if process_handle:
                    buffer_size = 260
                    buffer = ctypes.create_unicode_buffer(buffer_size)
                    success = ctypes.windll.kernel32.QueryFullProcessImageNameW(process_handle, 0, buffer,
                                                                                ctypes.byref(
                                                                                    ctypes.c_ulong(buffer_size)))
                    ctypes.windll.kernel32.CloseHandle(process_handle)

                    if success:
                        process_name_actual = os.path.basename(buffer.value)
                        if process_name_actual == process_name:
                            return True
            return False

        except Exception as e:
            self.exception_msg = f"is_process_running {e}"
            self.finished.emit()
            return False

    def call_set_global_hdr_state(self):
        self.check_hdr_state()

        if self.reverse_toggle == "SDR To HDR":
            if self.toggle_state:  # HDR is currently enabled
                self.toggle_hdr(False)  # Disable HDR when process exits
            else:
                self.toggle_hdr(True)  # Enable HDR at process launch
        elif self.reverse_toggle == "HDR To SDR":
            if self.toggle_state:  # HDR is currently enabled
                self.toggle_hdr(False)  # Disable HDR at process launch
            else:
                self.toggle_hdr(True)  # Enable HDR when process exits

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


class RightClickFilter(QObject):
    def eventFilter(self, source, event):
        if isinstance(event, QMouseEvent):
            if event.type() == QEvent.Type.MouseButtonPress:
                if event.button() == Qt.MouseButton.RightButton:
                    return True  # Ignore single right-click event
            elif event.type() == QEvent.Type.MouseButtonDblClick:
                if event.button() == Qt.MouseButton.RightButton:
                    return True  # Ignore double right-click event

        return super().eventFilter(source, event)


class MainWindow(QMainWindow):
    warning_signal = Signal()
    update_signal = Signal()

    def __init__(self):
        super().__init__()
        self.settings = QSettings("7gxycn08@Github", "PyAutoActions")
        self.warning_signal.connect(self.warning_box, Qt.ConnectionType.QueuedConnection)
        self.update_signal.connect(self.update_box, Qt.ConnectionType.QueuedConnection)
        self.exception_msg = None
        self.update_msg = None
        self.ICON_SIZE = 64
        self.action_names = []
        self.monitor_thread = None
        self.boot_status = None
        self.script_path = f"{os.path.abspath(sys.argv[0])}"
        self.config = configparser.ConfigParser()
        self.load_or_create_config()
        self.config.read(self.get_appdata_path("processlist.ini"))
        self.list_str = self.config['HDR_APPS']['processes']
        self.process_list = self.list_str.split(', ') if self.list_str else []

        self.current_version = 121 # Version Checking Number.
        self.setWindowTitle("PyAutoActions v1.2.1")
        self.setWindowIcon(QIcon(os.path.abspath(r"Resources\main.ico")))
        self.setGeometry(100, 100, 600, 400)

        self.menu_bar = self.menuBar()
        self.file_menu = self.menu_bar.addMenu('File')
        self.check_for_update_action = QAction('Check for Update on Startup', self.file_menu)
        self.check_for_update_action.setCheckable(True)
        self.check_for_update_action.triggered.connect(self.save_update_settings)
        self.file_menu.addSeparator()
        self.about_in_menu_bar = QAction(QIcon(r"Resources\about.ico"), 'About', self)
        self.about_in_menu_bar.triggered.connect(self.about_page)
        self.exit_from_menu_bar = QAction(QIcon(r"Resources\exit.ico"), 'Exit Application', self)
        self.exit_from_menu_bar.triggered.connect(self.close_tray_icon)
        self.file_menu.addActions([self.check_for_update_action, self.about_in_menu_bar, self.exit_from_menu_bar])
        update = self.settings.value("check_for_updates", defaultValue=True, type=bool)
        self.check_for_update_action.setChecked(bool(update))

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
        self.restore_group_settings()
        self.action_group.triggered.connect(self.save_group_settings)

        self.action_group_2 = QActionGroup(self)
        self.action_group_2.addAction(self.sdr2hdr)
        self.action_group_2.addAction(self.hdr2sdr)
        self.action_group_2.setExclusive(True)
        self.restore_group_settings_2()
        self.action_group_2.triggered.connect(self.save_group_settings_2)

        self.central_widget = QWidget(self)
        self.setCentralWidget(self.central_widget)

        self.list_widget = QListWidget()
        size_policy = QSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.list_widget.setSizePolicy(size_policy)

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
        self.menu.installEventFilter(RightClickFilter(self.menu))
        self.menu.setWindowFlag(Qt.WindowType.WindowStaysOnTopHint, True)
        self.menu.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.menu.setWindowFlags(self.menu.windowFlags() | Qt.WindowType.FramelessWindowHint)

        self.tray_icon = QSystemTrayIcon(self)
        self.tray_icon.setToolTip("PyAutoActions")
        self.tray_icon.setIcon(QIcon(os.path.abspath(r"Resources\main.ico")))
        self.tray_icon.activated.connect(self.tray_icon_activated)

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
        self.monitor = ProcessMonitor(self.process_list)
        self.monitor_thread = threading.Thread(target=self.monitor.process_monitor)
        self.monitor_thread.start()
        delay = self.settings.value("GroupSettings", defaultValue="High")
        mode = self.settings.value("GroupSettings2", defaultValue="SDR To HDR")
        self.update_delay(delay)
        self.update_reverse(mode)
        self.monitor.delay = delay  # Update process monitor so it stays in sync upon restarts.
        self.load_processes_from_config()
        self.create_actions()
        if self.check_for_update_action.isChecked():
            self.update_thread = threading.Thread(target=self.check_for_update)
            self.update_thread.start()

    def center_window(self):
        screen = app.primaryScreen()
        screen_geometry = screen.availableGeometry()
        window_geometry = self.frameGeometry()
        x = (screen_geometry.width() - window_geometry.width()) // 2
        y = (screen_geometry.height() - window_geometry.height()) // 2
        self.move(x, y)

    def check_for_update(self):
        update_url = "https://raw.githubusercontent.com/7gxycn08/PyAutoActions/main/current_version.txt"
        try:
            with urllib.request.urlopen(update_url) as response:
                content = response.read().decode().strip()

            number = int(content)
            if self.current_version < number:
                self.update_msg = f"PyAutoActions v{'.'.join(str(number))} Update Available."
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

    def start_hidden_check(self):
        if self.start_hidden_checked:
            self.hide()
        else:
            self.center_window()
            self.show()

    def update_delay(self, delay):
        self.monitor.delay = delay

    def update_reverse(self, status):
        if status == "SDR To HDR":
            self.monitor.SetGlobalHDRState(False)
        else:
            self.monitor.SetGlobalHDRState(True)
        self.monitor.reverse_toggle = status

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
        update_message_box.setFixedSize(400, 200)
        update_message_box.setText(f"{self.update_msg}")
        winsound.MessageBeep()
        screen = app.primaryScreen()
        screen_geometry = screen.availableGeometry()
        x = (screen_geometry.width() - update_message_box.width()) // 2
        y = (screen_geometry.height() - update_message_box.height()) // 2
        update_message_box.move(x, y)
        update_message_box.exec()

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

    def extract_icon(self, file_path, icon_index=0):
        try:
            icon_handle = ctypes.windll.shell32.ExtractIconW(0, file_path, icon_index)
            if icon_handle <= 1:
                return None
        except Exception as e:
            self.exception_msg = f"extract_icon: {e}"
            self.warning_signal.emit()
            return None

        return icon_handle

    def get_icon_as_image_object(self, file_path, icon_index=0):
        icon_handle = self.extract_icon(file_path, icon_index)

        if icon_handle is None:
            return
        elif icon_handle:
            hdc = ctypes.windll.user32.GetDC(0)
            mem_dc = ctypes.windll.gdi32.CreateCompatibleDC(hdc)
            bitmap = ctypes.windll.gdi32.CreateCompatibleBitmap(hdc, self.ICON_SIZE, self.ICON_SIZE)
            ctypes.windll.gdi32.SelectObject(mem_dc, bitmap)

            ctypes.windll.user32.DrawIconEx(
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
            ctypes.windll.gdi32.GetDIBits(mem_dc, bitmap, 0, self.ICON_SIZE, bmp_str, ctypes.byref(bmp_header),
                                          0)

            im = Image.frombuffer(
                'RGBA',
                (self.ICON_SIZE, self.ICON_SIZE),
                bmp_str, 'raw', 'BGRA', 0, 1)

            ctypes.windll.user32.DestroyIcon(icon_handle)
            ctypes.windll.gdi32.DeleteObject(bitmap)
            ctypes.windll.gdi32.DeleteDC(mem_dc)
            ctypes.windll.user32.ReleaseDC(0, hdc)

            return im
        else:
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
                        base_name = os.path.basename(item_text).rstrip(".exe")
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

    def run_as_admin(self, executable_path):
        try:
            folder_path = os.path.dirname(executable_path)

            ctypes.windll.shell32.ShellExecuteW(None, "runas", executable_path, None, folder_path, 1)
        except Exception as e:
            self.exception_msg = f"run_as_admin: {e}"
            self.warning_signal.emit()

    def on_action_triggered(self, path):
        try:
            self.monitor.main_process = os.path.basename(path)
            self.monitor.found_process = True
            self.monitor.manual_hdr = True
            self.monitor.count = True
            self.monitor.call_set_global_hdr_state()
            (threading.Thread(target=lambda: subprocess.run(path, cwd=os.path.dirname(path), shell=True, check=True))
             .start())
        except subprocess.CalledProcessError:
            threading.Thread(target=lambda: self.run_as_admin(path), daemon=True).start()
        except Exception as e:
            self.exception_msg = f"on_action_triggered: {e}"
            self.warning_signal.emit()

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
        if reason == QSystemTrayIcon.ActivationReason.DoubleClick:
            self.show_window()
        elif reason == QSystemTrayIcon.ActivationReason.Context:
            self.menu.exec(QCursor.pos())

    def close_tray_icon(self):
        if self.exit_confirm_box() == QMessageBox.StandardButton.Yes:
            self.monitor.shutting_down = True
            QCoreApplication.quit()
        else:
            pass

    def show_window(self):
        self.center_window()
        self.show()
        self.activateWindow()

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

                if self.monitor.toggle_state and self.monitor.found_process:
                    self.monitor.found_process = False
                    self.monitor.call_set_global_hdr_state()

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
            file_dialog = QFileDialog()
            file_path, _ = file_dialog.getOpenFileName(self, "Select Executable", "", "Executable Files (*.exe)")
            if file_path:
                exe_path = os.path.abspath(file_path)
                if exe_path in self.process_list:
                    self.exception_msg = f"Process {exe_path} already exists in the list."
                    self.warning_signal.emit()

                else:
                    icon = self.get_icon_as_image_object(exe_path)
                    q_icon = self.pil_image_to_q_icon(icon)
                    list_item = QListWidgetItem()
                    list_item.setIcon(q_icon)
                    list_item.setText(exe_path)
                    self.list_widget.addItem(list_item)
                    self.create_actions()
                    self.process_list.append(exe_path)
                    threading.Thread(target=self.save_config, daemon=True).start()
                    self.update_classes_variables()
        except Exception as e:
            self.exception_msg = f"add_exe: {e}"
            self.warning_signal.emit()

    def load_or_create_config(self):
        config = self.config
        config_path = self.get_appdata_path("processlist.ini")
        try:
            if not os.path.isfile(config_path):
                with open(config_path, 'w') as configfile:
                    config.add_section('HDR_APPS')
                    config.set('HDR_APPS', 'processes', '')
                    config.write(configfile)
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
                self.config.write(configfile)
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
    with open(r'Resources\custom.css', 'r') as file:
        stylesheet = file.read()
    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)
    app.setStyleSheet(stylesheet)
    window = MainWindow()
    sys.exit(app.exec())
